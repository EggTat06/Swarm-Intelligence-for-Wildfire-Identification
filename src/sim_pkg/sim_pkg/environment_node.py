import rclpy
from rclpy.node import Node
from std_msgs.msg import String
import json
import random
import math


class EnvironmentNode(Node):
    def __init__(self):
        super().__init__("environment_node")
        self.env_pub = self.create_publisher(String, "environment_state", 10)
        # 0.5s timestep as requested
        self.timer = self.create_timer(0.5, self.publish_environment)

        # 651.15km x 651.15km grid in meters
        self.grid_width = 651150.0
        self.grid_height = 651150.0

        self.season = "Summer"
        self.wind_speed = 5.0
        self.wind_direction = 45.0
        self.base_elevation = 500.0

        self.static_entities = self.generate_static_entities()
        self.fires = []
        self.max_fires = 20

        self.get_logger().info("Expanded 651km x 651km Environment Node Initialized.")

    def generate_static_entities(self):
        entities = []
        # Scaled up quantities for the larger map
        for _ in range(20):
            entities.append(
                {
                    "id": f"factory_{random.randint(1000, 9999)}",
                    "type": "factory",
                    "x": random.uniform(20000, 630000),
                    "y": random.uniform(20000, 630000),
                    "size": random.uniform(1000, 3000),
                }
            )

        for _ in range(50):
            entities.append(
                {
                    "id": f"building_{random.randint(1000, 9999)}",
                    "type": "building",
                    "x": random.uniform(20000, 630000),
                    "y": random.uniform(20000, 630000),
                    "size": random.uniform(500, 2000),
                    "height": random.uniform(50, 300),
                }
            )

        for _ in range(10):
            entities.append(
                {
                    "id": f"lake_{random.randint(1000, 9999)}",
                    "type": "lake",
                    "x": random.uniform(50000, 600000),
                    "y": random.uniform(50000, 600000),
                    "size": random.uniform(5000, 20000),
                }
            )

        for _ in range(40):
            entities.append(
                {
                    "id": f"forest_{random.randint(1000, 9999)}",
                    "type": "forest",
                    "x": random.uniform(20000, 630000),
                    "y": random.uniform(20000, 630000),
                    "size": random.uniform(4000, 15000),
                }
            )

        return entities

    def get_temperature(self, x, y):
        base_temp = 25.0
        for ent in self.static_entities:
            dist = math.hypot(x - ent["x"], y - ent["y"])
            if ent["type"] == "lake" and dist < ent["size"] * 2:
                base_temp -= 5.0 * (1 - dist / (ent["size"] * 2))
            elif ent["type"] == "factory" and dist < 5000:
                base_temp += 10.0 * (1 - dist / 5000)
        return round(base_temp, 2)

    def get_forest_density(self, x, y):
        density = 0.1
        for ent in self.static_entities:
            if ent["type"] == "forest":
                dist = math.hypot(x - ent["x"], y - ent["y"])
                if dist < ent["size"]:
                    density += 0.8 * (1 - dist / ent["size"])
        return round(min(1.0, density), 2)

    def spawn_fire_logic(self):
        # 1% chance per half-second to spawn a fire, until max_fires is reached
        if len(self.fires) < self.max_fires and random.random() < 0.01:
            forests = [e for e in self.static_entities if e["type"] == "forest"]
            if not forests:
                return

            target_forest = random.choice(forests)

            # Spawn fire randomly within the radius of the chosen forest
            angle = random.uniform(0, 2 * math.pi)
            radius = random.uniform(0, target_forest["size"])
            fire_x = target_forest["x"] + radius * math.cos(angle)
            fire_y = target_forest["y"] + radius * math.sin(angle)

            self.fires.append(
                {
                    "id": f"fire_{str(random.randint(1000,9999))}",
                    "x": fire_x,
                    "y": fire_y,
                    "size": random.uniform(500, 2000),
                    "identified": False,  # Tracked by drones later
                }
            )
            self.get_logger().info(
                f"New wildfire spawned at ({fire_x:.0f}, {fire_y:.0f}) inside {target_forest['id']}"
            )

    def update_environment(self):
        self.wind_speed += random.uniform(-0.5, 0.5)
        self.wind_speed = max(0.0, self.wind_speed)
        self.wind_direction = (self.wind_direction + random.uniform(-5.0, 5.0)) % 360

        self.spawn_fire_logic()

    def publish_environment(self):
        self.update_environment()

        center_temp = self.get_temperature(self.grid_width / 2, self.grid_height / 2)
        center_density = self.get_forest_density(
            self.grid_width / 2, self.grid_height / 2
        )

        env_state = {
            "grid": {"width": self.grid_width, "height": self.grid_height},
            "season": self.season,
            "global_temperature": center_temp,
            "global_canopy_density": center_density,
            "wind": {
                "speed": round(self.wind_speed, 2),
                "direction": round(self.wind_direction, 2),
            },
            "topography": {"base_elevation": self.base_elevation},
            "entities": self.static_entities,
            "fires": self.fires,
        }

        msg = String()
        msg.data = json.dumps(env_state)
        self.env_pub.publish(msg)


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
