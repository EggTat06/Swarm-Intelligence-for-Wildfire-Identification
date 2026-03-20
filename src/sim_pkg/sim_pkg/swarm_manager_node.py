import rclpy
from rclpy.node import Node
from std_msgs.msg import String
import json
import uuid
import subprocess
import os
import signal
import math

# ─── Simulation time scaling ────────────────────────────────────────────────
REAL_DT = 0.5  # ROS timer tick – real seconds
SIM_DT = 10.0  # Simulation seconds per tick  (1 real-min = 20 sim-min)
import numpy as np


class SwarmManagerNode(Node):
    def __init__(self):
        super().__init__("swarm_manager_node")

        # UI Bridge Publisher
        self.drone_telemetry_pub = self.create_publisher(String, "drone_telemetry", 10)

        # UI Bridge Subscribers
        self.cmd_sub = self.create_subscription(
            String, "swarm_control", self.cmd_callback, 10
        )
        self.env_sub = self.create_subscription(
            String, "environment_state", self.env_callback, 10
        )

        # Inter-Drone Swarm telemetry (Pub/Sub)
        self.swarm_telemetry_pub = self.create_publisher(String, "swarm_telemetry", 10)
        self.swarm_telemetry_sub = self.create_subscription(
            String, "swarm_telemetry", self.swarm_telem_callback, 10
        )

        self.env_data = {}
        self.world_w = 300_000.0
        self.world_h = 300_000.0
        self.home_x = 150_000.0
        self.home_y = 150_000.0

        # Process & State tracking
        self.active_drones = {}  # {drone_id: subprocess.Popen}
        self.latest_drone_states = {}  # {drone_id: state_dict}
        self.drone_paths = {}  # {drone_id: [[x, y], ...]}

        self.discovered_fires = set()
        self.mission_start_time = None
        self.first_detection_time = None
        self.visited_cells = set()
        self.is_returning_home = False

        # Area coverage via boolean occupancy grid (200m resolution)
        self.resolution = 200.0
        self.grid_w = int(self.world_w / self.resolution)
        self.grid_h = int(self.world_h / self.resolution)
        self.occupancy_grid = np.zeros((self.grid_w, self.grid_h), dtype=bool)

        # Precompute boolean mask for a drone's vision radius (5000m)
        self.vision_r_cells = int(5000.0 / self.resolution)
        y, x = np.ogrid[
            -self.vision_r_cells : self.vision_r_cells + 1,
            -self.vision_r_cells : self.vision_r_cells + 1,
        ]
        self.vision_mask = x**2 + y**2 <= self.vision_r_cells**2

        # Add initial drones
        for _ in range(10):
            self.add_drone()

        self.timer = self.create_timer(REAL_DT, self.aggregation_loop)
        self.get_logger().info(f"SwarmManager C&C ready | real_dt={REAL_DT}s")

    # ------------------------------------------------------------------ #
    # Drone Process Spawner
    # ------------------------------------------------------------------ #
    def add_drone(self, drone_id=None):
        drone_id = drone_id or ("drone_" + str(uuid.uuid4())[:6])

        # Use direct python execution to bypass 'ros2 run' overhead (slow search/source)
        # We assume drone_node.py is in the same directory as this script.
        import sys

        script_path = os.path.join(os.path.dirname(__file__), "drone_node.py")
        cmd = [sys.executable, script_path, drone_id]

        if self.mission_start_time is not None:
            cmd.append("--deployed")

        proc = subprocess.Popen(
            cmd,
            stdout=subprocess.DEVNULL,
            preexec_fn=os.setsid,
            stderr=subprocess.STDOUT,
            env=os.environ.copy(),  # Ensure ROS 2 env is inherited
        )
        self.active_drones[drone_id] = proc
        self.drone_paths[drone_id] = [[self.home_x, self.home_y]]

        self.get_logger().info(f"Spawned drone process: {drone_id}")

    def remove_drone(self, drone_id=None):
        if not self.active_drones:
            return

        if drone_id and drone_id in self.active_drones:
            target_id = drone_id
            proc = self.active_drones.pop(target_id)
        else:
            target_id, proc = self.active_drones.popitem()

        # Directly kill the process to prevent any zombies
        try:
            os.killpg(os.getpgid(proc.pid), signal.SIGTERM)
        except ProcessLookupError:
            self.get_logger().warn(f"Process for {target_id} was already dead.")

        # Clean up local references
        if target_id in self.latest_drone_states:
            self.latest_drone_states.pop(target_id, None)
        if target_id in self.drone_paths:
            self.drone_paths.pop(target_id, None)

        self.get_logger().info(
            f"Terminated {target_id} | remaining {len(self.active_drones)}"
        )

    def cleanup_dead_processes(self):
        # Prevent zombie processes
        dead_ids = []
        for d_id, proc in self.active_drones.items():
            if proc.poll() is not None:
                dead_ids.append(d_id)

        if dead_ids:
            for d_id in dead_ids:
                if d_id in self.active_drones:
                    self.active_drones.pop(d_id, None)
                if d_id in self.latest_drone_states:
                    self.latest_drone_states.pop(d_id, None)
                self.get_logger().info(f"Cleaned up dead process: {d_id}")

    # ------------------------------------------------------------------ #
    # ROS callbacks
    # ------------------------------------------------------------------ #
    def env_callback(self, msg):
        try:
            d = json.loads(msg.data)
            if "grid" in d:
                new_w = d["grid"].get("width", self.world_w)
                new_h = d["grid"].get("height", self.world_h)
                if new_w != self.world_w or new_h != self.world_h:
                    self.world_w = new_w
                    self.world_h = new_h
                    self.grid_w = int(self.world_w / self.resolution)
                    self.grid_h = int(self.world_h / self.resolution)
                    self.occupancy_grid = np.zeros(
                        (self.grid_w, self.grid_h), dtype=bool
                    )
            self.env_data = d
        except Exception as e:
            self.get_logger().error(f"env_callback: {e}")

    def cmd_callback(self, msg):
        try:
            cmd = json.loads(msg.data)
            action = cmd.get("action") or cmd.get("command") or ""

            if action == "add":
                self.add_drone()

            elif action == "remove":
                self.remove_drone(cmd.get("drone_id"))

            elif action == "DEPLOY":
                if self.mission_start_time is None:
                    self.mission_start_time = self.get_clock().now()
                    self.is_returning_home = False
                    self.visited_cells.clear()
                    self.discovered_fires.clear()
                    self.first_detection_time = None
                    self.occupancy_grid.fill(False)

                    # Clear paths, reset to current positions
                    for d_id, state in self.latest_drone_states.items():
                        self.drone_paths[d_id] = [[state["x"], state["y"]]]

                    self.get_logger().info(
                        "Mission Start. Paths and metrics cleared. Broadcasting DEPLOY to swarm."
                    )
                    self.swarm_telemetry_pub.publish(msg)

            elif action == "ABORT":
                if self.mission_start_time is not None:
                    self.get_logger().info(
                        "Abort requested. Reporting immediately and returning to base."
                    )
                    self._generate_mission_report()
                    self.is_returning_home = True
                    self.swarm_telemetry_pub.publish(msg)

            elif action == "RESET":
                self.get_logger().info("Resetting swarm. Broadcasting RESET.")
                self.mission_start_time = None
                self.first_detection_time = None
                self.is_returning_home = False
                self.visited_cells.clear()
                self.occupancy_grid.fill(False)
                for d_id in self.drone_paths:
                    self.drone_paths[d_id] = [[self.home_x, self.home_y]]

                self.swarm_telemetry_pub.publish(msg)

            elif action in ("command", "release"):
                # Pass-through targeted commands directly to the swarm topic
                self.swarm_telemetry_pub.publish(msg)

        except Exception as e:
            self.get_logger().error(f"cmd_callback: {e}")

    def swarm_telem_callback(self, msg):
        try:
            d = json.loads(msg.data)
            if d.get("type") == "drone_heartbeat":
                d_id = d["drone_id"]
                x = d["x"]
                y = d["y"]

                # Append to path if moved > 50m
                if d_id not in self.drone_paths:
                    self.drone_paths[d_id] = [[x, y]]
                else:
                    last_p = self.drone_paths[d_id][-1]
                    if math.hypot(x - last_p[0], y - last_p[1]) > 50.0:
                        self.drone_paths[d_id].append([round(x, 1), round(y, 1)])

                # Attach the path back onto the dictionary for aggregation
                d["path"] = self.drone_paths[d_id]

                self.latest_drone_states[d_id] = d

                # Update global discovered fires
                for f in d.get("discovered_fires", []):
                    self.discovered_fires.add(tuple(f))

                # Track exact area using boolean grid
                if self.mission_start_time:
                    cx = int(x / self.resolution)
                    cy = int(y / self.resolution)

                    r = self.vision_r_cells
                    x_min = max(0, cx - r)
                    x_max = min(self.grid_w, cx + r + 1)
                    y_min = max(0, cy - r)
                    y_max = min(self.grid_h, cy + r + 1)

                    # Compute offsets in the mask array
                    mx_min = r - (cx - x_min)
                    mx_max = r + (x_max - cx)
                    my_min = r - (cy - y_min)
                    my_max = r + (y_max - cy)

                    if x_max > x_min and y_max > y_min:
                        self.occupancy_grid[
                            x_min:x_max, y_min:y_max
                        ] |= self.vision_mask[mx_min:mx_max, my_min:my_max]

                    if (
                        self.first_detection_time is None
                        and len(self.discovered_fires) > 0
                    ):
                        dt = (
                            self.get_clock().now() - self.mission_start_time
                        ).nanoseconds / 1e9
                        self.first_detection_time = round(dt, 2)

        except Exception as e:
            self.get_logger().error(f"telem_agg_callback error: {e}")

    # ------------------------------------------------------------------ #
    # Mission Reports & Aggregation
    # ------------------------------------------------------------------ #
    def _generate_mission_report(self):
        if self.mission_start_time is None:
            return

        end_time = self.get_clock().now()
        duration = (end_time - self.mission_start_time).nanoseconds / 1e9

        total_cells = self.grid_w * self.grid_h
        covered_cells = np.count_nonzero(self.occupancy_grid)
        coverage_pct = (covered_cells / total_cells) * 100 if total_cells > 0 else 0

        report = {
            "type": "mission_report",
            "start_time": self.mission_start_time.to_msg().sec,
            "duration": duration,
            "first_detection_seconds": self.first_detection_time,
            "drones_deployed": len(self.active_drones),
            "fires_identified": len(self.discovered_fires),
            "area_coverage_pct": round(coverage_pct, 2),
            "drone_paths": self.drone_paths,
        }

        msg = String()
        msg.data = json.dumps(report)
        self.drone_telemetry_pub.publish(msg)
        self.get_logger().info(
            f"MISSION REPORT: {len(self.discovered_fires)} fires, {duration:.1f}s duration"
        )

    def aggregation_loop(self):
        self.cleanup_dead_processes()

        payloads = list(self.latest_drone_states.values())

        msg = String()
        msg.data = json.dumps(
            {
                "type": "swarm_telemetry",  # This matches the frontend expectations of a single message
                "drones": payloads,
                "discovered_fires": list(self.discovered_fires),
            }
        )
        self.drone_telemetry_pub.publish(msg)

        # Check if all drones are home after abort
        if self.is_returning_home:
            all_home = True
            for d in payloads:
                if d["state"] != "LANDED":
                    all_home = False
                    break

            if all_home and len(payloads) > 0:
                self.get_logger().info("All drones returned to base. Clearing mission.")
                self.is_returning_home = False
                self.mission_start_time = None
                self.first_detection_time = None

                fin_msg = String()
                fin_msg.data = json.dumps({"type": "MISSION_CLEARED"})
                self.drone_telemetry_pub.publish(fin_msg)


def main(args=None):
    rclpy.init(args=args)
    node = SwarmManagerNode()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        for d_id, proc in list(node.active_drones.items()):
            try:
                proc.terminate()
            except Exception:
                pass
        node.destroy_node()
        rclpy.shutdown()


if __name__ == "__main__":
    main()
