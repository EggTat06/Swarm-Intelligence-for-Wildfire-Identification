from fastapi import FastAPI, WebSocket, WebSocketDisconnect
import json
import asyncio
import uuid
import datetime
import threading

import rclpy
from rclpy.node import Node
from std_msgs.msg import String

from fastapi.middleware.cors import CORSMiddleware
import psycopg2
from psycopg2.extras import RealDictCursor

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # In production, restrict this to the dashboard URL
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Database config
DB_CONFIG = {
    "host": "localhost",
    "database": "swarm_wildfire_db",
    "user": "swarm_user",
    "password": "swarm_password",
    "port": 5432,
}


def get_db_connection():
    return psycopg2.connect(**DB_CONFIG)


def init_db():
    # Ensure connection works
    try:
        conn = get_db_connection()
        conn.close()
        print("Connected to TimescaleDB")
    except Exception as e:
        print(f"Database connection failed: {e}")


class ConnectionManager:
    def __init__(self):
        self.active_connections: list[WebSocket] = []

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)

    def disconnect(self, websocket: WebSocket):
        self.active_connections.remove(websocket)

    async def broadcast(self, message: str):
        for connection in self.active_connections:
            try:
                await connection.send_text(message)
            except Exception:
                pass


manager = ConnectionManager()
loop = None

# Global reference to Node to allow FastAPI to publish
ros_node = None


class FastAPIBridgeNode(Node):
    def __init__(self):
        super().__init__("fastapi_bridge_node")
        self.env_sub = self.create_subscription(
            String, "environment_state", self.env_callback, 10
        )
        self.telemetry_sub = self.create_subscription(
            String, "drone_telemetry", self.telemetry_callback, 10
        )
        self.notif_sub = self.create_subscription(
            String, "drone_notifications", self.notif_callback, 10
        )
        self.cmd_pub = self.create_publisher(String, "swarm_control", 10)

    def env_callback(self, msg):
        try:
            payload = json.loads(msg.data)
            payload["type"] = "environment_state"
            if loop is not None:
                asyncio.run_coroutine_threadsafe(
                    manager.broadcast(json.dumps(payload)), loop
                )
        except Exception as e:
            self.get_logger().error(f"Error parsing environment state: {e}")

    def telemetry_callback(self, msg):
        try:
            payload = json.loads(msg.data)

            # If it's a mission report, save to DB
            if payload.get("type") == "mission_report":
                self.save_mission_to_db(payload)

            if loop is not None:
                asyncio.run_coroutine_threadsafe(
                    manager.broadcast(json.dumps(payload)), loop
                )
        except Exception as e:
            self.get_logger().error(f"Error parsing telemetry: {e}")

    def save_mission_to_db(self, report):
        try:
            conn = get_db_connection()
            cur = conn.cursor()

            mission_id = str(uuid.uuid4())
            start_time = datetime.datetime.fromtimestamp(report["start_time"])

            cur.execute(
                """
                INSERT INTO missions (mission_id, start_time, end_time, swarm_parameters, time_to_first_detection, success, drone_paths)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
                """,
                (
                    mission_id,
                    start_time,
                    start_time + datetime.timedelta(seconds=report["duration"]),
                    json.dumps(
                        {
                            "drones": report["drones_deployed"],
                            "coverage": report["area_coverage_pct"],
                        }
                    ),
                    report["first_detection_seconds"],
                    report["fires_identified"] > 0,
                    json.dumps(report.get("drone_paths", {})),
                ),
            )

            # The schema has a 'telemetry' table. Let's use it for a few sample points or just store the whole path blob somewhere.
            # For now, let's keep it simple and just save the mission.
            # If we want to show paths later, we might need a another table or JSONB in missions.

            conn.commit()
            cur.close()
            conn.close()
            self.get_logger().info(f"Saved mission {mission_id} to database.")
        except Exception as e:
            self.get_logger().error(f"Failed to save mission to DB: {e}")

    def notif_callback(self, msg):
        try:
            payload = json.loads(msg.data)
            if loop is not None:
                asyncio.run_coroutine_threadsafe(
                    manager.broadcast(json.dumps(payload)), loop
                )
        except Exception as e:
            self.get_logger().error(f"Error parsing notification: {e}")

    def publish_command(self, action_str):
        msg = String()
        msg.data = action_str
        self.cmd_pub.publish(msg)


def run_ros2_node():
    global ros_node
    rclpy.init()
    ros_node = FastAPIBridgeNode()
    try:
        rclpy.spin(ros_node)
    except KeyboardInterrupt:
        pass
    finally:
        ros_node.destroy_node()
        rclpy.shutdown()


@app.on_event("startup")
async def startup_event():
    global loop
    loop = asyncio.get_running_loop()
    init_db()
    ros2_thread = threading.Thread(target=run_ros2_node, daemon=True)
    ros2_thread.start()


@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await manager.connect(websocket)
    try:
        while True:
            data = await websocket.receive_text()
            print(f"Received UI Command: {data}")

            try:
                cmd = json.loads(data)
                # Forward any command-like message to ROS
                is_command = cmd.get("type") in ["swarm_control", "command"] or cmd.get(
                    "action"
                ) in ["RESET", "DEPLOY", "ABORT"]
                if is_command and ros_node:
                    ros_node.publish_command(json.dumps(cmd))
            except Exception as e:
                print(f"Error parsing command from UI: {e}")

    except WebSocketDisconnect:
        manager.disconnect(websocket)


@app.get("/history/missions")
async def get_missions():
    try:
        conn = get_db_connection()
        cur = conn.cursor(cursor_factory=RealDictCursor)
        cur.execute("SELECT * FROM missions ORDER BY start_time DESC LIMIT 20")
        rows = cur.fetchall()
        cur.close()
        conn.close()
        return rows
    except Exception as e:
        print(f"Error fetching missions: {e}")
        return []


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)
