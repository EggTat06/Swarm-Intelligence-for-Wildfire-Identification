import rclpy
from rclpy.node import Node
from std_msgs.msg import String
import json
import random
import time

try:
    from ultralytics import YOLO

    HAS_YOLO = True
except ImportError:
    HAS_YOLO = False


class VisionProcessingNode(Node):
    def __init__(self):
        super().__init__("vision_processing")

        # In a real environment, this subscribes to a sensor_msgs/Image topic.
        # For the simulation, we subscribe to drone_telemetry to "see" if a drone is near a mocked fire.
        self.telemetry_sub = self.create_subscription(
            String, "drone_telemetry", self.telemetry_callback, 10
        )

        self.yolo_pub = self.create_publisher(String, "yolo_detections", 10)

        # Mock fire location for simulation
        self.mock_fire_x = 500.0
        self.mock_fire_y = 500.0
        self.detection_radius = (
            100.0  # Drone must be within 100m to catch fire in camera FOV
        )

        if HAS_YOLO:
            self.get_logger().info("YOLOv8 library found. Initializing model...")
            # self.model = YOLO('yolov8n-fire.pt') # Placeholder for real weights
        else:
            self.get_logger().info(
                "YOLOv8 not installed. Falling back to mocked inference."
            )

    def telemetry_callback(self, msg):
        try:
            data = json.loads(msg.data)
            dx = data["lon"] - self.mock_fire_x
            dy = data["lat"] - self.mock_fire_y
            distance = (dx**2 + dy**2) ** 0.5

            # If drone is close enough to the coordinates, simulate visual detection
            if distance < self.detection_radius:
                # Simulate "true positive" probability
                is_true_positive = (
                    random.random() > 0.1
                )  # 90% confidence of true positive
                confidence = random.uniform(0.75, 0.99)

                # Mock bounding box coords
                bbox = {
                    "x": random.uniform(100, 400),
                    "y": random.uniform(100, 400),
                    "w": 50,
                    "h": 50,
                }

                payload = {
                    "drone_id": data["drone_id"],
                    "timestamp": time.time(),
                    "confidence": confidence,
                    "bbox": bbox,
                    "is_true_positive": is_true_positive,
                    "model_used": "yolov8n-fire" if HAS_YOLO else "mocked-yolo",
                }

                out_msg = String()
                out_msg.data = json.dumps(payload)
                self.yolo_pub.publish(out_msg)

                self.get_logger().info(
                    f"Fire Detected by {data['drone_id']} with confidence {confidence:.2f}"
                )

        except Exception as e:
            self.get_logger().error(f"Error in vision processing: {e}")


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
