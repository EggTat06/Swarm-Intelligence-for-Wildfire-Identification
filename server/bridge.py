from fastapi import FastAPI, WebSocket, WebSocketDisconnect
import json
import asyncio
import random
import uuid
import datetime

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
            await connection.send_text(message)


manager = ConnectionManager()


# Mock ROS2 background thread emitting events
async def mock_ros_bridge():
    while True:
        await asyncio.sleep(2)

        # Telemetry
        if random.random() > 0.5:
            telemetry = {
                "type": "telemetry",
                "drone_id": f"Drone-{random.randint(1,24)}",
                "lat": random.uniform(45.0, 45.3),
                "lon": random.uniform(-112.5, -112.0),
                "alt": random.uniform(80, 150),
                "battery": random.uniform(20, 100),
            }
            await manager.broadcast(json.dumps(telemetry))

        # YOLO Detection Event
        if random.random() > 0.9:
            detected = {
                "type": "yolo_detection",
                "drone_id": f"Drone-{random.randint(1,24)}",
                "confidence": random.uniform(0.7, 0.99),
                "bbox": {"x": 200, "y": 200, "w": 50, "h": 50},
                "is_true_positive": True,
            }
            await manager.broadcast(json.dumps(detected))


@app.on_event("startup")
async def startup_event():
    asyncio.create_task(mock_ros_bridge())


@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await manager.connect(websocket)
    try:
        while True:
            data = await websocket.receive_text()
            # Handle UI commands (e.g., Deploy Swarm)
            print(f"Received UI Command: {data}")
    except WebSocketDisconnect:
        manager.disconnect(websocket)


@app.get("/history/missions")
async def get_missions():
    # Mock TimescaleDB history pull
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
