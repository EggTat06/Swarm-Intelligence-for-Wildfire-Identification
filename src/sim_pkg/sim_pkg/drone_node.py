import rclpy
from rclpy.node import Node
from std_msgs.msg import String
import json
import random
import math
import uuid


class SwarmManagerNode(Node):
    def __init__(self):
        super().__init__("swarm_manager_node")

        self.telemetry_pub = self.create_publisher(String, "drone_telemetry", 10)
        self.env_sub = self.create_subscription(
            String, "environment_state", self.env_callback, 10
        )
        self.cmd_sub = self.create_subscription(
            String, "swarm_control", self.cmd_callback, 10
        )

        self.env_data = {}
        self.discovered_fires = set()

        # Time step of simulation
        self.dt = 0.5

        # Swarm config
        self.home_x = 325575.0
        self.home_y = 325575.0
        self.altitude_levels = [88.0, 91.0, 100.0]

        # Sensory properties
        self.fire_sensor_range = 6000.0  # 6km
        self.obstacle_range = 1500.0  # 1.5km minimum threshold

        self.drones = {}

        # Initialize default 10 drones
        for _ in range(10):
            self.add_drone()

        self.timer = self.create_timer(self.dt, self.control_loop)
        self.get_logger().info("Swarm Manager Initialized with 10 drones.")

    def add_drone(self):
        drone_id = "drone_" + str(uuid.uuid4())[:6]

        # Kinematics parameters
        v = random.uniform(15.0, 25.0)  # Cruise speed 15-25 m/s
        rmin = random.uniform(50.0, 100.0)  # Minimum turning radius 50-100m
        wmax = v / rmin  # Max angular velocity (rad/s)

        self.drones[drone_id] = {
            "id": drone_id,
            "x": self.home_x,
            "y": self.home_y,
            "alt": random.choice(self.altitude_levels),
            "heading": random.uniform(0, 2 * math.pi),  # radians
            "target_heading": random.uniform(0, 2 * math.pi),
            "v": v,
            "rmin": rmin,
            "wmax": wmax,
            "battery": 100.0,
        }
        self.get_logger().info(f"Added {drone_id} to swarm. Total: {len(self.drones)}")

    def remove_drone(self):
        if len(self.drones) > 0:
            removed_id = list(self.drones.keys())[0]
            del self.drones[removed_id]
            self.get_logger().info(
                f"Removed {removed_id} from swarm. Total: {len(self.drones)}"
            )

    def cmd_callback(self, msg):
        try:
            cmd = json.loads(msg.data)
            if cmd.get("action") == "add":
                self.add_drone()
            elif cmd.get("action") == "remove":
                self.remove_drone()
        except Exception as e:
            self.get_logger().error(f"Error parsing swarm control command: {e}")

    def env_callback(self, msg):
        try:
            self.env_data = json.loads(msg.data)
        except Exception as e:
            self.get_logger().error(f"Error parsing environment data: {e}")

    def apply_kinematics(self, drone):
        # 1. Sense Environment Layer
        self.sense_fires(drone)
        self.obstacle_avoidance(drone)
        self.boundary_adherence(drone)

        # 2. PID Control for Heading (omega)
        angle_diff = drone["target_heading"] - drone["heading"]

        # Normalize angle diff between -pi and pi
        angle_diff = (angle_diff + math.pi) % (2 * math.pi) - math.pi

        # Simple Proportional controller: P * angle_diff
        P = 0.5
        omega = P * angle_diff

        # Cap angular velocity
        if omega > drone["wmax"]:
            omega = drone["wmax"]
        if omega < -drone["wmax"]:
            omega = -drone["wmax"]

        # 3. Kinematic Equations
        drone["heading"] += omega * self.dt
        drone["heading"] = drone["heading"] % (2 * math.pi)

        drone["x"] += drone["v"] * math.cos(drone["heading"]) * self.dt
        drone["y"] += drone["v"] * math.sin(drone["heading"]) * self.dt

        drone["battery"] -= 0.01

    def sense_fires(self, drone):
        # Sensory range of 6km as assumed in requirements
        fires = self.env_data.get("fires", [])
        for f in fires:
            if f["id"] not in self.discovered_fires:
                dist = math.hypot(drone["x"] - f["x"], drone["y"] - f["y"])
                if dist <= self.fire_sensor_range:
                    self.discovered_fires.add(f["id"])
                    self.get_logger().info(
                        f"{drone['id']} identified {f['id']}! Shared to Swarm via 4G."
                    )

    def obstacle_avoidance(self, drone):
        # Simulate obstacle sensors tracking other drones (range 1-5km)
        for other_id, other in self.drones.items():
            if other_id == drone["id"]:
                continue
            if other["alt"] != drone["alt"]:
                continue  # Different altitude layer

            dist = math.hypot(drone["x"] - other["x"], drone["y"] - other["y"])
            if dist < self.obstacle_range:
                # Steer away from closest neighbor
                drone["target_heading"] += math.pi / 4

        # Drift noise (exploration)
        if random.random() < 0.05:
            drone["target_heading"] += random.uniform(-0.5, 0.5)

    def boundary_adherence(self, drone):
        grid_w = self.env_data.get("grid", {}).get("width", 651150.0)
        grid_h = self.env_data.get("grid", {}).get("height", 651150.0)
        padding = 10000.0  # 10km boundary turn around

        if (
            drone["x"] < padding
            or drone["x"] > grid_w - padding
            or drone["y"] < padding
            or drone["y"] > grid_h - padding
        ):
            # Turn softly towards center
            dx = (grid_w / 2) - drone["x"]
            dy = (grid_h / 2) - drone["y"]
            drone["target_heading"] = math.atan2(dy, dx)

    def control_loop(self):
        payloads = []
        for d_id in list(self.drones.keys()):
            drone = self.drones[d_id]
            if drone["battery"] <= 0:
                self.get_logger().info(f"{d_id} battery depleted. Returning/Removed.")
                del self.drones[d_id]
                continue

            self.apply_kinematics(drone)

            payloads.append(
                {
                    "drone_id": d_id,
                    "x": drone["x"],
                    "y": drone["y"],
                    "alt": drone["alt"],
                    "battery": round(drone["battery"], 2),
                    "heading": round(drone["heading"], 2),
                }
            )

        # Pack into a single batch telemetry message to avoid span flooding the bridge
        msg = String()
        msg.data = json.dumps(
            {
                "type": "swarm_telemetry",
                "drones": payloads,
                "discovered_fires": list(self.discovered_fires),
            }
        )
        self.telemetry_pub.publish(msg)


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
