import rclpy
from rclpy.node import Node
from std_msgs.msg import String
import json
import random
import math
import uuid
import sys

REAL_DT = 0.5  # ROS timer tick – real seconds
SIM_DT = 10.0  # Simulation seconds per tick  (1 real-min = 20 sim-min)

V_MAX = 45.0  # m/s  (user specified)
MASS = 1.0  # virtual DSP particle mass
P_EXP = 2  # Physicomimetics exponent p=2  →  G*R²*(9/16)


class DroneNode(Node):
    def __init__(self, drone_id=None):
        if drone_id is None:
            drone_id = "drone_" + str(uuid.uuid4())[:6]

        super().__init__(drone_id)
        self.drone_id = drone_id

        # Publishers & Subscribers
        self.telemetry_pub = self.create_publisher(String, "swarm_telemetry", 10)
        self.notif_pub = self.create_publisher(String, "drone_notifications", 10)

        self.env_sub = self.create_subscription(
            String, "environment_state", self.env_callback, 10
        )
        self.cmd_sub = self.create_subscription(
            String, "swarm_control", self.cmd_callback, 10
        )
        self.telem_sub = self.create_subscription(
            String, "swarm_telemetry", self.telem_callback, 10
        )
        self.peer_states = {}

        # Environment & Map
        self.env_data = {}
        self.world_w = 300_000.0
        self.world_h = 300_000.0
        self.home_x = 150_000.0
        self.home_y = 150_000.0

        self.altitude_levels = [88.0, 91.0, 100.0]
        self.fire_sensor_range = 1_000.0  # 1 km
        self.dsp_reached_threshold = 4_000.0  # 4 km
        self.discovered_fires = set()
        self.is_deployed = False
        self.is_returning_home = False
        self.uptime_ticks = 0
        self.init_drone()
        self.timer = self.create_timer(REAL_DT, self.control_loop)
        self.get_logger().info(
            f"Drone {self.drone_id} initialized | v={self.v:.1f}m/s | dsp=({self.dsp_x:.0f},{self.dsp_y:.0f})"
        )

    def init_drone(self):
        self.v = random.uniform(15.0, 25.0)
        self.rmin = random.uniform(200.0, 500.0)
        self.wmax = self.v / self.rmin

        self.x = self.home_x
        self.y = self.home_y
        self.alt = random.choice(self.altitude_levels)
        self.heading = random.uniform(0, 2 * math.pi)
        self.target_heading = random.uniform(0, 2 * math.pi)

        self.battery = 100.0

        border = 5_000.0
        self.dsp_x = random.uniform(border, self.world_w - border)
        self.dsp_y = random.uniform(border, self.world_h - border)
        self.dsp_vx = 0.0
        self.dsp_vy = 0.0

        self.state = "TRACKING_DSP"
        self.random_walk_timer = 0.0
        self.commanded_target_x = None
        self.commanded_target_y = None

    # ------------------------------------------------------------------ #
    # ROS Callbacks
    # ------------------------------------------------------------------ #
    def env_callback(self, msg):
        try:
            d = json.loads(msg.data)
            if "grid" in d:
                self.world_w = d["grid"].get("width", self.world_w)
                self.world_h = d["grid"].get("height", self.world_h)
            self.env_data = d
        except Exception as e:
            self.get_logger().error(f"env_callback: {e}")

    def cmd_callback(self, msg):
        try:
            cmd = json.loads(msg.data)
            action = cmd.get("action") or cmd.get("command") or ""
            target_id = cmd.get("drone_id")

            if action == "command" and target_id == self.drone_id:
                self.state = "COMMANDED"
                self.commanded_target_x = float(cmd["target_x"])
                self.commanded_target_y = float(cmd["target_y"])
                self.get_logger().info(
                    f"→ COMMANDED ({self.commanded_target_x:.0f},{self.commanded_target_y:.0f})"
                )

            elif action == "release" and target_id == self.drone_id:
                if self.state in ("COMMANDED", "COMMANDED_WALK"):
                    self.state = "TRACKING_DSP"
                    self.get_logger().info("Released → TRACKING_DSP")

            elif action == "remove" and target_id == self.drone_id:
                self.get_logger().info("Termination command received. Exiting.")
                sys.exit(0)

            elif action == "DEPLOY":
                self.is_deployed = True
                self.is_returning_home = False
                self.discovered_fires.clear()

            elif action == "ABORT":
                self.is_deployed = False
                self.is_returning_home = True
                self.state = "RETURNING_HOME"

            elif action == "RESET":
                self.is_deployed = False
                self.is_returning_home = False
                self.init_drone()
                self.peer_states.clear()

        except Exception as e:
            self.get_logger().error(f"cmd_callback: {e}")

    def telem_callback(self, msg):
        try:
            d = json.loads(msg.data)

            if (
                d.get("type") == "drone_heartbeat"
                and d.get("drone_id") != self.drone_id
            ):
                d_id = d["drone_id"]
                self.peer_states[d_id] = {
                    "x": d["x"],
                    "y": d["y"],
                    "dsp_x": d["dsp_x"],
                    "dsp_y": d["dsp_y"],
                }

                remote_fires = d.get("discovered_fires", [])
                for fx, fy in remote_fires:
                    self.discovered_fires.add((fx, fy))

        except Exception as e:
            self.get_logger().error(f"telem_callback error: {e}")

    def _publish_notification(self, message):
        msg = String()
        msg.data = json.dumps(
            {
                "type": "drone_notification",
                "drone_id": self.drone_id,
                "message": message,
            }
        )
        self.notif_pub.publish(msg)
        self.get_logger().info(f"NOTIFY: {message}")

    # ------------------------------------------------------------------ #
    # DSP Physicomimetics (Decentralized)
    # ------------------------------------------------------------------ #
    def _update_dsp(self):
        self.uptime_ticks += 1
        if self.uptime_ticks < 3:
            return

        N = len(self.peer_states) + 1

        gw = self.world_w
        gh = self.world_h

        # ── Compute partition distance R ──────────────────────────────────
        world_area = gw * gh
        search_area = (world_area * math.pi * math.sqrt(3) / 6.0) / N
        R = 2.0 * math.sqrt(search_area / math.pi)

        # ── Fmax = Vmax × mass / dt ────────────────────────────────────────
        Fmax = V_MAX * MASS / SIM_DT
        G_const = Fmax * (R**2) * (9.0 / 16.0)

        fx, fy = 0.0, 0.0

        # ── Border repulsion ──────────────────────────────────────────
        border = 5_000.0
        border_f = Fmax * 0.5
        if self.dsp_x < border:
            fx += border_f
        if self.dsp_x > gw - border:
            fx -= border_f
        if self.dsp_y < border:
            fy += border_f
        if self.dsp_y > gh - border:
            fy -= border_f

        # ── Pairwise gravitational forces (Only if N > 1) ─────────────
        if N > 1:
            for peer_id, peer in self.peer_states.items():
                dx = peer["dsp_x"] - self.dsp_x
                dy = peer["dsp_y"] - self.dsp_y
                dist = math.hypot(dx, dy)

                if dist < 1.0:
                    dx = random.uniform(-1.0, 1.0)
                    dy = random.uniform(-1.0, 1.0)
                    dist = math.hypot(dx, dy)
                    if dist < 1e-9:
                        dx, dy, dist = 1.0, 0.0, 1.0

                f_mag = min(G_const / (dist**2), Fmax)
                direction = math.atan2(dy, dx)
                sign = -1.0 if dist < R else 1.0

                fx += sign * f_mag * math.cos(direction)
                fy += sign * f_mag * math.sin(direction)

        # ── Second-order integration: v̇ = F, ẋ = v ───────────────────
        self.dsp_vx += fx * SIM_DT
        self.dsp_vy += fy * SIM_DT

        v_mag = math.hypot(self.dsp_vx, self.dsp_vy)
        if v_mag > Fmax:
            self.dsp_vx = self.dsp_vx / v_mag * Fmax
            self.dsp_vy = self.dsp_vy / v_mag * Fmax

        self.dsp_x = max(0.0, min(gw, self.dsp_x + self.dsp_vx * SIM_DT))
        self.dsp_y = max(0.0, min(gh, self.dsp_y + self.dsp_vy * SIM_DT))

    # ------------------------------------------------------------------ #
    # Kinematics & States
    # ------------------------------------------------------------------ #
    def _update_kinematics(self):
        gw = self.world_w
        gh = self.world_h

        if self.state == "TRACKING_DSP":
            d_dsp = math.hypot(self.dsp_x - self.x, self.dsp_y - self.y)
            if d_dsp <= self.dsp_reached_threshold:
                self.state = "RANDOM_WALK"
                self.random_walk_timer = math.sqrt(gw**2 + gh**2) / (2.0 * self.v)
            else:
                self.target_heading = math.atan2(
                    self.dsp_y - self.y, self.dsp_x - self.x
                )

        elif self.state == "RANDOM_WALK":
            self.random_walk_timer -= SIM_DT
            if self.random_walk_timer <= 0:
                self.state = "TRACKING_DSP"
            elif random.random() < 0.05:
                self.target_heading += random.uniform(-math.pi / 4, math.pi / 4)

        elif self.state == "COMMANDED":
            tx, ty = self.commanded_target_x, self.commanded_target_y
            dist_to_target = math.hypot(tx - self.x, ty - self.y)
            if dist_to_target <= self.dsp_reached_threshold:
                self.state = "COMMANDED_WALK"
                self._publish_notification(
                    f"Reached commanded location ({tx/1000:.1f}km, {ty/1000:.1f}km). Patrolling area."
                )
            else:
                self.target_heading = math.atan2(ty - self.y, tx - self.x)

        elif self.state == "COMMANDED_WALK":
            if random.random() < 0.06:
                self.target_heading += random.uniform(-math.pi / 3, math.pi / 3)

        elif self.state == "RETURNING_HOME":
            self.target_heading = math.atan2(self.home_y - self.y, self.home_x - self.x)
            dist_to_home = math.hypot(self.home_x - self.x, self.home_y - self.y)
            if dist_to_home <= 1000.0:
                self.state = "LANDED"
                self.x = self.home_x
                self.y = self.home_y
                self.get_logger().info("LANDED at base.")

        elif self.state == "LANDED":
            pass

        # ── Heading PID ────────────────────────
        angle_diff = (self.target_heading - self.heading + math.pi) % (
            2 * math.pi
        ) - math.pi
        omega = max(-self.wmax, min(self.wmax, 2.0 * angle_diff))
        self.heading = (self.heading + omega * REAL_DT) % (2 * math.pi)

        # ── Position update ────────────────────────────
        if self.state != "LANDED" and (self.is_deployed or self.is_returning_home):
            self.x = max(
                0.0, min(gw, self.x + self.v * math.cos(self.heading) * SIM_DT)
            )
            self.y = max(
                0.0, min(gh, self.y + self.v * math.sin(self.heading) * SIM_DT)
            )

        # Battery drain
        self.battery -= 0.001 * SIM_DT

    def _sense_fires(self):
        fires = self.env_data.get("ca_cells", self.env_data.get("fires", []))
        for f in fires:
            if f.get("state", 0) not in (1, 2):
                continue

            if math.hypot(self.x - f["x"], self.y - f["y"]) <= self.fire_sensor_range:
                is_known = False
                for cx, cy in self.discovered_fires:
                    if math.hypot(f["x"] - cx, f["y"] - cy) <= 10000.0:
                        is_known = True
                        break

                if not is_known:
                    self.discovered_fires.add((f["x"], f["y"]))
                    self._publish_notification(
                        f"Fire detected at ({f['x']/1000:.1f}km, {f['y']/1000:.1f}km)!"
                    )

    # ------------------------------------------------------------------ #
    # Main loop
    # ------------------------------------------------------------------ #
    def control_loop(self):
        if self.battery <= 0:
            self.get_logger().info("Battery depleted. Drone shutting down.")
            sys.exit(0)

        self._update_dsp()
        self._update_kinematics()

        if self.is_deployed:
            self._sense_fires()
        msg = String()
        msg.data = json.dumps(
            {
                "type": "drone_heartbeat",
                "drone_id": self.drone_id,
                "x": round(self.x, 2),
                "y": round(self.y, 2),
                "alt": self.alt,
                "v": self.v,
                "heading": round(self.heading, 3),
                "battery": round(self.battery, 2),
                "state": self.state,
                "commanded_target_x": round(self.commanded_target_x, 2)
                if self.commanded_target_x is not None
                else None,
                "commanded_target_y": round(self.commanded_target_y, 2)
                if self.commanded_target_y is not None
                else None,
                "dsp_x": round(self.dsp_x, 2),
                "dsp_y": round(self.dsp_y, 2),
                "discovered_fires": list(self.discovered_fires),
            }
        )
        self.telemetry_pub.publish(msg)


def main(args=None):
    rclpy.init(args=args)
    drone_id = None
    is_deployed = False
    for arg in sys.argv[1:]:
        if arg == "--deployed":
            is_deployed = True
        elif not arg.startswith("--"):
            drone_id = arg

    node = DroneNode(drone_id=drone_id)
    if is_deployed:
        node.is_deployed = True

    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == "__main__":
    main()
