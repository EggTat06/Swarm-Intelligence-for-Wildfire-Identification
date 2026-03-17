import rclpy
from rclpy.node import Node
from std_msgs.msg import String
import json
import random
import math


class VisionProcessingNode(Node):
    """
    Simulated vision processing node.
    Subscribes to the new batch swarm_telemetry format and checks each drone's
    position against known CA fire cells.  Publishes yolo_detections for any
    drone whose position falls within detection_radius of an active fire cell.
    """

    def __init__(self):
        super().__init__("vision_processing")

        self.telemetry_sub = self.create_subscription(
            String, "drone_telemetry", self.telemetry_callback, 10
        )
        self.env_sub = self.create_subscription(
            String, "environment_state", self.env_callback, 10
        )
        self.yolo_pub = self.create_publisher(String, "yolo_detections", 10)

        self.env_data = {}
        # How close a drone must be to a fire cell to trigger visual detection
        self.detection_radius = 2_000.0  # 2 km

        self.get_logger().info("VisionProcessingNode ready (batch telemetry format).")

    def env_callback(self, msg):
        try:
            self.env_data = json.loads(msg.data)
        except Exception as e:
            self.get_logger().error(f"env_callback: {e}")

    def telemetry_callback(self, msg):
        try:
            data = json.loads(msg.data)

            # New batch format: {"type": "swarm_telemetry", "drones": [...]}
            drones = data.get("drones", [])
            if not drones:
                return

            ca_cells = self.env_data.get("ca_cells", [])
            burning_cells = [c for c in ca_cells if c.get("state", 0) in (1, 2)]

            for drone in drones:
                drone_x = drone.get("x", 0.0)
                drone_y = drone.get("y", 0.0)
                drone_id = drone.get("drone_id", "unknown")

                for cell in burning_cells:
                    dist = math.hypot(drone_x - cell["x"], drone_y - cell["y"])
                    if dist < self.detection_radius:
                        confidence = random.uniform(0.75, 0.99)
                        payload = {
                            "drone_id": drone_id,
                            "cell_i": cell["i"],
                            "cell_j": cell["j"],
                            "fire_x": cell["x"],
                            "fire_y": cell["y"],
                            "fire_state": cell["state"],
                            "confidence": round(confidence, 3),
                            "is_true_positive": random.random() > 0.1,
                            "model_used": "mocked-yolo",
                            "bbox": {
                                "x": random.uniform(100, 400),
                                "y": random.uniform(100, 400),
                                "w": 50,
                                "h": 50,
                            },
                        }
                        out_msg = String()
                        out_msg.data = json.dumps(payload)
                        self.yolo_pub.publish(out_msg)
                        self.get_logger().info(
                            f"Visual fire detection: {drone_id} near cell "
                            f"({cell['i']},{cell['j']}) conf={confidence:.2f}"
                        )
                        break  # one detection per drone per tick is enough

        except Exception as e:
            self.get_logger().error(f"vision_processing error: {e}")


def main(args=None):
    rclpy.init(args=args)
    node = VisionProcessingNode()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == "__main__":
    main()
