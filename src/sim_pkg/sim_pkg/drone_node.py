import rclpy
from rclpy.node import Node
from std_msgs.msg import String
import json
import random
import math
import uuid

# ─── Simulation time scaling ────────────────────────────────────────────────
REAL_DT = 0.5  # ROS timer tick – real seconds
SIM_DT = 10.0  # Simulation seconds per tick  (1 real-min = 20 sim-min)

# ─── DSP Physicomimetics parameters ─────────────────────────────────────────
# Vmax = maximum drone cruise speed (m/s), used as the DSP virtual particle Vmax
V_MAX = 45.0  # m/s  (user specified)
MASS = 1.0  # virtual DSP particle mass
P_EXP = 2  # Physicomimetics exponent p=2  →  G*R²*(9/16)


class SwarmManagerNode(Node):
    def __init__(self):
        super().__init__("swarm_manager_node")

        self.telemetry_pub = self.create_publisher(String, "drone_telemetry", 10)
        self.notif_pub = self.create_publisher(String, "drone_notifications", 10)
        self.env_sub = self.create_subscription(
            String, "environment_state", self.env_callback, 10
        )
        self.cmd_sub = self.create_subscription(
            String, "swarm_control", self.cmd_callback, 10
        )

        self.env_data = {}
        self.env_data = {}
        self.discovered_fires = set()
        self.mission_start_time = None
        self.first_detection_time = None
        self.visited_cells = set()  # Unique cells visited by any drone
        self.is_returning_home = False

        # World constants
        self.home_x = 150_000.0
        self.home_y = 150_000.0
        self.world_w = 300_000.0
        self.world_h = 300_000.0

        self.altitude_levels = [88.0, 91.0, 100.0]
        self.fire_sensor_range = 5_000.0  # 5 km
        self.dsp_reached_threshold = 4_000.0  # 4 km

        self.drones = {}
        for _ in range(10):
            self.add_drone()

        self.timer = self.create_timer(REAL_DT, self.control_loop)
        self.get_logger().info(
            f"SwarmManager ready | real_dt={REAL_DT}s  sim_dt={SIM_DT}s  Vmax={V_MAX}m/s"
        )

    # ------------------------------------------------------------------ #
    # Drone lifecycle                                                      #
    # ------------------------------------------------------------------ #
    def add_drone(self, drone_id=None):
        drone_id = drone_id or ("drone_" + str(uuid.uuid4())[:6])

        # Realistic UAV cruise speed range (m/s)
        v = random.uniform(15.0, 25.0)
        rmin = random.uniform(200.0, 500.0)  # realistic min turn radius (m)
        wmax = v / rmin

        # Scatter the initial DSP point randomly across the world so the
        # repulsion system starts from a non-degenerate configuration.
        border = 5_000.0
        init_dsp_x = random.uniform(border, self.world_w - border)
        init_dsp_y = random.uniform(border, self.world_h - border)

        self.drones[drone_id] = {
            "id": drone_id,
            # Position: start at home base
            "x": self.home_x,
            "y": self.home_y,
            "alt": random.choice(self.altitude_levels),
            "heading": random.uniform(0, 2 * math.pi),
            "target_heading": random.uniform(0, 2 * math.pi),
            "v": v,
            "rmin": rmin,
            "wmax": wmax,
            "battery": 100.0,
            # DSP virtual particle starts at random scatter position
            "dsp_x": init_dsp_x,
            "dsp_y": init_dsp_y,
            # DSP 2nd-order velocity (v̇ = F, ẋ = v)
            "dsp_vx": 0.0,
            "dsp_vy": 0.0,
            # Agent state
            "state": "TRACKING_DSP",
            "random_walk_timer": 0.0,
            # Commanded state
            "commanded_target_x": None,
            "commanded_target_y": None,
            # Breadcrumb path tracking
            "path": [[self.home_x, self.home_y]],
        }
        self.get_logger().info(
            f"+ {drone_id} (v={v:.1f}m/s) dsp=({init_dsp_x:.0f},{init_dsp_y:.0f})"
        )

    def remove_drone(self, drone_id=None):
        if not self.drones:
            return
        target = drone_id if drone_id in self.drones else next(iter(self.drones))
        del self.drones[target]
        self.get_logger().info(f"- {target} | remaining {len(self.drones)}")

    # ------------------------------------------------------------------ #
    # ROS callbacks                                                        #
    # ------------------------------------------------------------------ #
    def env_callback(self, msg):
        try:
            d = json.loads(msg.data)
            # Update world size if provided
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

            if action == "add":
                self.add_drone()

            elif action == "remove":
                self.remove_drone(cmd.get("drone_id"))

            elif action == "command":
                d = self.drones.get(cmd.get("drone_id"))
                if d:
                    d["state"] = "COMMANDED"
                    d["commanded_target_x"] = float(cmd["target_x"])
                    d["commanded_target_y"] = float(cmd["target_y"])
                    self.get_logger().info(
                        f"{d['id']} → COMMANDED ({d['commanded_target_x']:.0f},{d['commanded_target_y']:.0f})"
                    )

            elif action == "release":
                d = self.drones.get(cmd.get("drone_id"))
                if d and d["state"] in ("COMMANDED", "COMMANDED_WALK"):
                    d["state"] = "TRACKING_DSP"
                    self.get_logger().info(f"{d['id']} released → TRACKING_DSP")

            elif action == "DEPLOY":
                if self.mission_start_time is None:
                    self.mission_start_time = self.get_clock().now()
                    self.is_returning_home = False
                    for d in self.drones.values():
                        d["path"] = [[d["x"], d["y"]]]
                    self.visited_cells = set()
                    self.discovered_fires = set()
                    self.first_detection_time = None
                    self.get_logger().info("Mission Start. Paths and metrics cleared.")

            elif action == "ABORT":
                if self.mission_start_time is not None:
                    self.get_logger().info(
                        "Abort requested. Reporting immediately and returning to base."
                    )
                    self._generate_mission_report()
                    self.is_returning_home = True
                    for d in self.drones.values():
                        d["state"] = "RETURNING_HOME"

            elif action == "RESET":
                self.get_logger().info(
                    "Resetting swarm to home and clearing metrics..."
                )
                self.mission_start_time = None
                self.first_detection_time = None
                self.is_returning_home = False
                for d in self.drones.values():
                    d["x"] = self.home_x
                    d["y"] = self.home_y
                    d["path"] = [[self.home_x, self.home_y]]
                    d["battery"] = 100.0
                    d["state"] = "TRACKING_DSP"
                    # Reset DSP points too
                    d["dsp_x"] = random.uniform(5_000, self.world_w - 5_000)
                    d["dsp_y"] = random.uniform(5_000, self.world_h - 5_000)
                    d["dsp_vx"] = 0.0
                    d["dsp_vy"] = 0.0

        except Exception as e:
            self.get_logger().error(f"cmd_callback: {e}")

    def _generate_mission_report(self):
        if self.mission_start_time is None:
            return

        end_time = self.get_clock().now()
        duration = (end_time - self.mission_start_time).nanoseconds / 1e9

        # Calculate area coverage
        # Assuming each cell is 500x500 as per environment_node.py
        total_cells = (self.world_w / 500) * (self.world_h / 500)
        coverage_pct = (
            (len(self.visited_cells) / total_cells) * 100 if total_cells > 0 else 0
        )

        report = {
            "type": "mission_report",
            "start_time": self.mission_start_time.to_msg().sec,
            "duration": duration,
            "first_detection_seconds": self.first_detection_time,
            "drones_deployed": len(self.drones),
            "fires_identified": len(self.discovered_fires),
            "area_coverage_pct": round(coverage_pct, 2),
            "drone_paths": {d_id: d["path"] for d_id, d in self.drones.items()},
        }

        msg = String()
        msg.data = json.dumps(report)
        self.telemetry_pub.publish(
            msg
        )  # Using telemetry_pub for simplicity, bridge will catch it
        self.get_logger().info(
            f"MISSION REPORT: {len(self.discovered_fires)} fires, {duration:.1f}s duration"
        )

    # ------------------------------------------------------------------ #
    # DSP Physicomimetics (second-order: v̇ = F,  ẋ = v)                  #
    # ------------------------------------------------------------------ #
    def _update_dsps(self):
        N = len(self.drones)
        if N == 0:
            return

        gw = self.world_w
        gh = self.world_h

        # ── Compute partition distance R ──────────────────────────────────
        # search_area = (WorldArea × π × √3 / 6) / N
        world_area = gw * gh
        search_area = (world_area * math.pi * math.sqrt(3) / 6.0) / N
        R = 2.0 * math.sqrt(search_area / math.pi)

        # ── Fmax = Vmax × mass / dt ────────────────────────────────────────
        Fmax = V_MAX * MASS / SIM_DT
        # G constant for p=2: Gconstant = Fmax × R² × (9/16)
        G_const = Fmax * (R**2) * (9.0 / 16.0)

        drone_list = list(self.drones.values())

        for drone in drone_list:
            # Net force on this DSP point
            fx, fy = 0.0, 0.0

            # ── Border repulsion ──────────────────────────────────────────
            border = 5_000.0
            border_f = Fmax * 0.5
            if drone["dsp_x"] < border:
                fx += border_f
            if drone["dsp_x"] > gw - border:
                fx -= border_f
            if drone["dsp_y"] < border:
                fy += border_f
            if drone["dsp_y"] > gh - border:
                fy -= border_f

            # ── Pairwise gravitational forces ─────────────────────────────
            for other in drone_list:
                if other["id"] == drone["id"]:
                    continue

                dx = other["dsp_x"] - drone["dsp_x"]
                dy = other["dsp_y"] - drone["dsp_y"]
                dist = math.hypot(dx, dy)

                # If DSP points overlap, jitter to give a nonzero direction
                if dist < 1.0:
                    dx = random.uniform(-1.0, 1.0)
                    dy = random.uniform(-1.0, 1.0)
                    dist = math.hypot(dx, dy)
                    if dist < 1e-9:
                        dx, dy, dist = 1.0, 0.0, 1.0

                # F_mag = Gconstant / dist²  (capped at Fmax)
                f_mag = min(G_const / (dist**2), Fmax)

                # direction = atan2(Δy, Δx)  — angle from own DSP to other DSP
                direction = math.atan2(dy, dx)

                # Sign: repulsive (away) when dist < R, attractive (toward) when dist > R
                sign = -1.0 if dist < R else 1.0

                fx += sign * f_mag * math.cos(direction)
                fy += sign * f_mag * math.sin(direction)

            # ── Second-order integration: v̇ = F, ẋ = v ───────────────────
            # Update DSP velocity
            drone["dsp_vx"] += fx * SIM_DT
            drone["dsp_vy"] += fy * SIM_DT

            # Clamp DSP velocity to Fmax magnitude (prevents runaway)
            v_mag = math.hypot(drone["dsp_vx"], drone["dsp_vy"])
            if v_mag > Fmax:
                drone["dsp_vx"] = drone["dsp_vx"] / v_mag * Fmax
                drone["dsp_vy"] = drone["dsp_vy"] / v_mag * Fmax

            # Update DSP position
            drone["dsp_x"] = max(
                0.0, min(gw, drone["dsp_x"] + drone["dsp_vx"] * SIM_DT)
            )
            drone["dsp_y"] = max(
                0.0, min(gh, drone["dsp_y"] + drone["dsp_vy"] * SIM_DT)
            )

    # ------------------------------------------------------------------ #
    # Per-drone state machine — position uses SIM_DT                      #
    # ------------------------------------------------------------------ #
    def _update_drone(self, drone):
        gw = self.world_w
        gh = self.world_h
        state = drone["state"]

        if state == "TRACKING_DSP":
            d_dsp = math.hypot(drone["dsp_x"] - drone["x"], drone["dsp_y"] - drone["y"])
            if d_dsp <= self.dsp_reached_threshold:
                # DSP reached → random walk
                drone["state"] = "RANDOM_WALK"
                # time = sqrt(W² + H²) / (2 × cruise_speed)
                drone["random_walk_timer"] = math.sqrt(gw**2 + gh**2) / (
                    2.0 * drone["v"]
                )
            else:
                # Steer toward own DSP point
                drone["target_heading"] = math.atan2(
                    drone["dsp_y"] - drone["y"], drone["dsp_x"] - drone["x"]
                )

        elif state == "RANDOM_WALK":
            drone["random_walk_timer"] -= SIM_DT
            if drone["random_walk_timer"] <= 0:
                drone["state"] = "TRACKING_DSP"
            elif random.random() < 0.05:
                drone["target_heading"] += random.uniform(-math.pi / 4, math.pi / 4)

        elif state == "COMMANDED":
            tx, ty = drone["commanded_target_x"], drone["commanded_target_y"]
            dist_to_target = math.hypot(tx - drone["x"], ty - drone["y"])
            if dist_to_target <= self.dsp_reached_threshold:
                drone["state"] = "COMMANDED_WALK"
                self._publish_notification(
                    drone["id"],
                    f"Reached commanded location ({tx/1000:.1f}km, {ty/1000:.1f}km). Patrolling area.",
                )
            else:
                drone["target_heading"] = math.atan2(ty - drone["y"], tx - drone["x"])

        elif state == "COMMANDED_WALK":
            # Random patrol until user releases
            if random.random() < 0.06:
                drone["target_heading"] += random.uniform(-math.pi / 3, math.pi / 3)

        elif state == "RETURNING_HOME":
            drone["target_heading"] = math.atan2(
                self.home_y - drone["y"], self.home_x - drone["x"]
            )
            dist_to_home = math.hypot(
                self.home_x - drone["x"], self.home_y - drone["y"]
            )
            if dist_to_home <= 500.0:
                drone["state"] = "LANDED"
                drone["x"] = self.home_x
                drone["y"] = self.home_y
                self.get_logger().info(f"{drone['id']} has LANDED at base.")

        elif state == "LANDED":
            pass

        # ── Heading PID (real dt for angular rate) ────────────────────────
        angle_diff = (drone["target_heading"] - drone["heading"] + math.pi) % (
            2 * math.pi
        ) - math.pi
        omega = max(-drone["wmax"], min(drone["wmax"], 2.0 * angle_diff))
        drone["heading"] = (drone["heading"] + omega * REAL_DT) % (2 * math.pi)

        # ── Position update (scaled by SIM_DT) ────────────────────────────
        if state != "LANDED" and (
            self.mission_start_time is not None or self.is_returning_home
        ):
            drone["x"] = max(
                0.0,
                min(gw, drone["x"] + drone["v"] * math.cos(drone["heading"]) * SIM_DT),
            )
            drone["y"] = max(
                0.0,
                min(gh, drone["y"] + drone["v"] * math.sin(drone["heading"]) * SIM_DT),
            )

        # Append to path if moved > 50m
        last_p = drone["path"][-1]
        if math.hypot(drone["x"] - last_p[0], drone["y"] - last_p[1]) > 50.0:
            drone["path"].append([round(drone["x"], 1), round(drone["y"], 1)])
            # Keep path length reasonable if needed, but for now we follow user instructions

        # Battery drain ∝ sim time
        drone["battery"] -= 0.001 * SIM_DT

        # Track path and visited cells
        if self.mission_start_time:
            # Track unique 500m cells
            cell_i = int(drone["x"] / 500)
            cell_j = int(drone["y"] / 500)
            self.visited_cells.add((cell_i, cell_j))

        self._sense_fires(drone)

    def _sense_fires(self, drone):
        fires = self.env_data.get("ca_cells", self.env_data.get("fires", []))
        for f in fires:
            if f.get("state", 0) not in (1, 2):
                continue
            fid = f.get("id", f"cell_{f.get('i',0)}_{f.get('j',0)}")
            if fid not in self.discovered_fires:
                if (
                    math.hypot(drone["x"] - f["x"], drone["y"] - f["y"])
                    <= self.fire_sensor_range
                ):
                    self.discovered_fires.add(fid)

                    if self.first_detection_time is None and self.mission_start_time:
                        dt = (
                            self.get_clock().now() - self.mission_start_time
                        ).nanoseconds / 1e9
                        self.first_detection_time = round(dt, 2)

                    self._publish_notification(
                        drone["id"],
                        f"Fire detected at ({f['x']/1000:.1f}km, {f['y']/1000:.1f}km)!",
                    )

    def _publish_notification(self, drone_id, message):
        msg = String()
        msg.data = json.dumps(
            {
                "type": "drone_notification",
                "drone_id": drone_id,
                "message": message,
            }
        )
        self.notif_pub.publish(msg)
        self.get_logger().info(f"NOTIFY [{drone_id}]: {message}")

    # ------------------------------------------------------------------ #
    # Main control loop                                                    #
    # ------------------------------------------------------------------ #
    def control_loop(self):
        self._update_dsps()

        payloads = []
        for d_id in list(self.drones):
            d = self.drones[d_id]
            if d["battery"] <= 0:
                del self.drones[d_id]
                continue
            self._update_drone(d)
            payloads.append(
                {
                    "drone_id": d_id,
                    "x": d["x"],
                    "y": d["y"],
                    "alt": d["alt"],
                    "v": d["v"],
                    "heading": round(d["heading"], 3),
                    "battery": round(d["battery"], 2),
                    "state": d["state"],
                    "dsp_x": d["dsp_x"],
                    "dsp_y": d["dsp_y"],
                    "path": d["path"],
                }
            )

        msg = String()
        msg.data = json.dumps(
            {
                "type": "swarm_telemetry",
                "drones": payloads,
                "discovered_fires": list(self.discovered_fires),
            }
        )
        self.telemetry_pub.publish(msg)

        # Check if all drones are home after abort
        if self.is_returning_home:
            all_home = True
            for d in self.drones.values():
                if d["state"] != "LANDED":
                    all_home = False
                    break

            if all_home and len(self.drones) > 0:
                self.get_logger().info("All drones returned to base. Clearing mission.")
                self.is_returning_home = False
                self.mission_start_time = None
                self.first_detection_time = None

                fin_msg = String()
                fin_msg.data = json.dumps({"type": "MISSION_CLEARED"})
                self.telemetry_pub.publish(fin_msg)


def main(args=None):
    rclpy.init(args=args)
    node = SwarmManagerNode()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == "__main__":
    main()
