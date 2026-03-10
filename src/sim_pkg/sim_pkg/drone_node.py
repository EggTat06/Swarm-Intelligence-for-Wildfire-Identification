import rclpy
from rclpy.node import Node
from std_msgs.msg import String
import json
import random
import math
import uuid


class DroneNode(Node):
    def __init__(self):
        super().__init__("drone_node_" + str(uuid.uuid4().hex[:6]))
        self.drone_id = self.get_name()

        # Publishers and Subscribers
        self.telemetry_pub = self.create_publisher(String, "drone_telemetry", 10)
        self.env_sub = self.create_subscription(
            String, "environment_state", self.env_callback, 10
        )

        # State
        self.x = random.uniform(0, 1000)
        self.y = random.uniform(0, 1000)
        self.altitude = 100.0
        self.battery = 100.0
        self.heading = random.uniform(0, 360)  # degrees
        self.speed = 10.0  # m/s

        self.env_data = None

        # Control Loop
        self.timer = self.create_timer(1.0, self.control_loop)
        self.get_logger().info(
            f"Drone {self.drone_id} Initialized at ({self.x:.2f}, {self.y:.2f})"
        )

    def env_callback(self, msg):
        try:
            self.env_data = json.loads(msg.data)
        except Exception as e:
            self.get_logger().error(f"Error parsing environment data: {e}")

    def control_loop(self):
        # Consume battery
        self.battery -= 0.1
        if self.battery <= 0:
            self.get_logger().info(f"Drone {self.drone_id} battery depleted.")
            return

        # Subsumption Architecture:
        # 1. Obstacle Avoidance (Mocked as random turn if near other drones/terrain)
        # 2. Boundary Adherence
        # 3. Dynamic Space Partition (Exploration / Pheromone tracking)

        self.apply_subsumption_logic()

        # Update Position
        rad = math.radians(self.heading)
        self.x += self.speed * math.cos(rad)
        self.y += self.speed * math.sin(rad)

        self.publish_telemetry()

    def apply_subsumption_logic(self):
        # Level 1: Avoidance (Simulated with a small random jitter to avoid getting stuck)
        if random.random() < 0.05:
            self.heading += random.uniform(-20, 20)

        # Level 2: Boundary Adherence
        grid_w = self.env_data["grid"]["width"] if self.env_data else 1000
        grid_h = self.env_data["grid"]["height"] if self.env_data else 1000

        padding = 50
        if (
            self.x < padding
            or self.x > grid_w - padding
            or self.y < padding
            or self.y > grid_h - padding
        ):
            # Turn towards center
            dx = (grid_w / 2) - self.x
            dy = (grid_h / 2) - self.y
            self.heading = math.degrees(math.atan2(dy, dx))

        # Level 3: Dynamic Space Partition (DSP) Pheromones
        # If there is wind, shift search pattern against the wind or along it based on strategy
        if self.env_data and "wind" in self.env_data:
            wind_dir = self.env_data["wind"]["direction"]
            # Influence heading slightly based on wind to simulate drift or search strategy
            # For exploration, cross-wind search is usually efficient.
            if random.random() < 0.1:
                self.heading = (wind_dir + 90) % 360

    def publish_telemetry(self):
        msg = String()
        # pheromone level dropped is correlated to canopy density (denser canopy requires stronger pheromones or slower decay mapping)
        phero = 1.0
        if self.env_data and "canopy_density" in self.env_data:
            phero = 1.0 * self.env_data["canopy_density"]

        payload = {
            "drone_id": self.drone_id,
            "lat": self.y,  # mapped lazily to y
            "lon": self.x,  # mapped lazily to x
            "alt": self.altitude,
            "battery": round(self.battery, 2),
            "pheromone": round(phero, 2),
        }
        msg.data = json.dumps(payload)
        self.telemetry_pub.publish(msg)


def main(args=None):
    rclpy.init(args=args)
    node = DroneNode()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == "__main__":
    main()
