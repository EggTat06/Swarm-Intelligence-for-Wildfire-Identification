from fastapi import FastAPI, WebSocket, WebSocketDisconnect
import json
import asyncio
import uuid
import datetime
import threading

import rclpy
from rclpy.node import Node
from std_msgs.msg import String

app = FastAPI()


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
loop = asyncio.get_event_loop()

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
        self.cmd_pub = self.create_publisher(String, "swarm_control", 10)

    def env_callback(self, msg):
        try:
            payload = json.loads(msg.data)
            payload["type"] = "environment_state"
            asyncio.run_coroutine_threadsafe(
                manager.broadcast(json.dumps(payload)), loop
            )
        except Exception as e:
            self.get_logger().error(f"Error parsing environment state: {e}")

    def telemetry_callback(self, msg):
        try:
            # Passes the swarm batch telemetry through
            payload = json.loads(msg.data)
            asyncio.run_coroutine_threadsafe(
                manager.broadcast(json.dumps(payload)), loop
            )
        except Exception as e:
            self.get_logger().error(f"Error parsing telemetry: {e}")

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
                if cmd.get("type") == "swarm_control" and ros_node:
                    ros_node.publish_command(json.dumps(cmd))
            except Exception as e:
                print(f"Error parsing command from UI: {e}")

    except WebSocketDisconnect:
        manager.disconnect(websocket)


@app.get("/history/missions")
async def get_missions():
    return [
        {
            "mission_id": str(uuid.uuid4()),
            "start_time": datetime.datetime.now().isoformat(),
            "time_to_first_detection": 142.5,
            "success": True,
            "swarm_parameters": {"decay": 0.05, "radius": 50},
        }
    ]


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)
