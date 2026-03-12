import rclpy
from rclpy.node import Node
from std_msgs.msg import String
import json
import psycopg2
from psycopg2.extras import Json
import uuid
import datetime
from typing import Any


class MetricsNode(Node):
    def __init__(self):
        super().__init__("metrics_node")

        self.db_conn: Any = None
        self.connect_to_db()

        # Subscribers
        self.telemetry_sub = self.create_subscription(
            String, "drone_telemetry", self.telemetry_callback, 10
        )
        self.yolo_sub = self.create_subscription(
            String, "yolo_detections", self.yolo_callback, 10
        )
        self.mission_sub = self.create_subscription(
            String, "mission_control", self.mission_callback, 10
        )

        self.current_mission_id: Any = None
        self.mission_start_time: Any = None

        self.get_logger().info("Metrics Node Initialized.")

    def connect_to_db(self):
        try:
            self.db_conn = psycopg2.connect(
                dbname="swarm_wildfire_db",
                user="swarm_user",
                password="swarm_password",
                host="localhost",
                port="5432",
            )
            self.db_conn.autocommit = True
            self.get_logger().info("Connected to TimescaleDB.")
        except Exception as e:
            self.get_logger().error(f"Failed to connect to TimescaleDB: {e}")

    def mission_callback(self, msg):
        try:
            data = json.loads(msg.data)
            action = data.get("action")

            if action == "start":
                self.current_mission_id = str(uuid.uuid4())
                self.mission_start_time = datetime.datetime.now()
                params = data.get("parameters", {})

                if self.db_conn:
                    with self.db_conn.cursor() as cur:
                        cur.execute(
                            "INSERT INTO missions (mission_id, start_time, swarm_parameters) VALUES (%s, %s, %s)",
                            (
                                self.current_mission_id,
                                self.mission_start_time,
                                Json(params),
                            ),
                        )
                self.get_logger().info(f"Started Mission {self.current_mission_id}")

            elif action == "end":
                success = data.get("success", False)
                if self.current_mission_id and self.mission_start_time:
                    end_time = datetime.datetime.now()
                    time_to_detect = (
                        (end_time - self.mission_start_time).total_seconds()
                        if success
                        else None
                    )

                    if self.db_conn:
                        with self.db_conn.cursor() as cur:
                            cur.execute(
                                """UPDATE missions
                                   SET end_time = %s, time_to_first_detection = %s, success = %s
                                   WHERE mission_id = %s""",
                                (
                                    end_time,
                                    time_to_detect,
                                    success,
                                    self.current_mission_id,
                                ),
                            )
                    self.get_logger().info(
                        f"Ended Mission {self.current_mission_id}. Success: {success}"
                    )
                    self.current_mission_id = None
        except Exception as e:
            self.get_logger().error(f"Mission processing error: {e}")

    def telemetry_callback(self, msg):
        if not self.current_mission_id or not self.db_conn:
            return

        try:
            data = json.loads(msg.data)
            with self.db_conn.cursor() as cur:
                cur.execute(
                    """INSERT INTO telemetry (time, drone_id, mission_id, latitude, longitude, altitude, battery_level, pheromone_level)
                       VALUES (NOW(), %s, %s, %s, %s, %s, %s, %s)""",
                    (
                        data["drone_id"],
                        self.current_mission_id,
                        data["lat"],
                        data["lon"],
                        data["alt"],
                        data.get("battery", 100),
                        data.get("pheromone", 0.0),
                    ),
                )
        except Exception as e:
            self.get_logger().debug(f"Telemetry error: {e}")

    def yolo_callback(self, msg):
        if not self.current_mission_id or not self.db_conn:
            return

        try:
            data = json.loads(msg.data)
            with self.db_conn.cursor() as cur:
                cur.execute(
                    """INSERT INTO yolo_detections (time, drone_id, mission_id, confidence_score, bounding_box, is_true_positive)
                       VALUES (NOW(), %s, %s, %s, %s, %s)""",
                    (
                        data["drone_id"],
                        self.current_mission_id,
                        data["confidence"],
                        Json(data["bbox"]),
                        data.get("is_true_positive"),
                    ),
                )
            self.get_logger().info(
                f"YOLO Detection logged for drone {data['drone_id']}"
            )
        except Exception as e:
            self.get_logger().error(f"YOLO processing error: {e}")


def main(args=None):
    rclpy.init(args=args)
    node = MetricsNode()

    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        node.get_logger().info("Metrics Node stopped cleanly.")
    except Exception as e:
        node.get_logger().error(f"Error in Metrics Node: {e}")
    finally:
        if node.db_conn:
            node.db_conn.close()
        node.destroy_node()
        rclpy.shutdown()


if __name__ == "__main__":
    main()
