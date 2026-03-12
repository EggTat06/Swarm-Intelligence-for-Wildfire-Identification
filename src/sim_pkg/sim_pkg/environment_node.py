import rclpy
from rclpy.node import Node
from std_msgs.msg import String
import json
import random


class EnvironmentNode(Node):
    def __init__(self):
        super().__init__("environment_node")
        # Publisher for environment state updates
        self.env_pub = self.create_publisher(String, "environment_state", 10)

        # Timer to update environment variables periodically (e.g., every 5 seconds)
        self.timer = self.create_timer(5.0, self.publish_environment)

        # Initial Environment States
        # 2D Grid size
        self.grid_width = 1000
        self.grid_height = 1000

        self.season = "Summer"
        self.canopy_density = 0.8  # 0.0 to 1.0 (Dense summer pine)

        self.wind_speed = 5.0  # m/s
        self.wind_direction = 45.0  # degrees

        # Simplified topography map (e.g., average elevation, or a function)
        self.base_elevation = 500.0  # meters

        self.get_logger().info("Environment Node Initialized.")

    def update_environment(self):
        # Introduce slight variations to simulate real-time dynamics
        self.wind_speed += random.uniform(-0.5, 0.5)
        self.wind_speed = max(0.0, self.wind_speed)

        self.wind_direction = (self.wind_direction + random.uniform(-5.0, 5.0)) % 360

        # Fire ignition scenario
        # Simulating a fire event randomly or controlled via another service/topic.
        # Keeping it simple for the initial node.

    def publish_environment(self):
        self.update_environment()

        env_state = {
            "grid": {"width": self.grid_width, "height": self.grid_height},
            "season": self.season,
            "canopy_density": self.canopy_density,
            "wind": {
                "speed": round(self.wind_speed, 2),
                "direction": round(self.wind_direction, 2),
            },
            "topography": {"base_elevation": self.base_elevation},
        }

        msg = String()
        msg.data = json.dumps(env_state)
        self.env_pub.publish(msg)
        self.get_logger().info(f"Published Environment State: {msg.data}")


def main(args=None):
    rclpy.init(args=args)
    node = EnvironmentNode()

    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        node.get_logger().info("Environment Node stopped cleanly.")
    except Exception as e:
        node.get_logger().error(f"Error in Environment Node: {e}")
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == "__main__":
    main()
