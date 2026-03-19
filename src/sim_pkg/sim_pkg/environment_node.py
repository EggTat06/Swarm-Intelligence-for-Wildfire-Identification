import rclpy
from rclpy.node import Node
from std_msgs.msg import String
import json
import random
import math

# ─── World & CA configuration ────────────────────────────────────────────────
GRID_W_M = 300_000.0
GRID_H_M = 300_000.0
CELL_L = 500.0
GRID_NX = int(GRID_W_M / CELL_L)  # 200
GRID_NY = int(GRID_H_M / CELL_L)  # 200

UNBURNT = 0
EARLY_BURN = 1
FULL_BURN = 2
EXTINGUISH = 3
ASH = 4

EARLY_TO_FULL_TIME = 10.0
EXT_TO_ASH_TIME = 20.0
SPREAD_BASE_RATE = 0.8
DT_BASE = 10.0
REAL_DT = 0.5
SIM_DT = 10.0  # Must match drone_node.py

BIOME_ANCHORS = [
    # (center_x, center_y, sigma_m, label, entity_mix)
    (
        150_000 - 30_000,
        150_000 - 30_000,
        12_000,
        "north_city",
        {"building": 15, "factory": 3},
    ),
    (
        150_000 + 25_000,
        150_000 - 35_000,
        10_000,
        "east_town",
        {"building": 10, "factory": 2},
    ),
    (150_000, 150_000 + 30_000, 14_000, "south_suburb", {"building": 9}),
    (150_000 - 35_000, 150_000 + 15_000, 11_000, "west_village", {"building": 10}),
    (150_000 + 5_000, 150_000, 8_000, "central_park", {"lake": 2}),
    (150_000 - 20_000, 150_000 - 15_000, 9_000, "river_delta", {"lake": 3}),
    (150_000 + 30_000, 150_000 + 20_000, 7_000, "mountain_lake", {"lake": 2}),
]

N_FOREST_BLOBS = 30  # number of Gaussian forest cluster centres
FOREST_COVERAGE = 0.7  # target forest fraction of map


class EnvironmentNode(Node):
    def __init__(self):
        super().__init__("environment_node")
        self.env_pub = self.create_publisher(String, "environment_state", 10)
        self.notif_pub = self.create_publisher(String, "drone_notifications", 10)
        self.timer = self.create_timer(REAL_DT, self.publish_environment)

        self.grid_width = GRID_W_M
        self.grid_height = GRID_H_M
        self.season = "Summer"
        self.wind_speed = 8.0
        self.wind_dir = 45.0
        self.base_elev = 500.0

        random.seed(42)  # deterministic world layout per run
        self.static_entities = self._gen_biome_entities()

        self.get_logger().info(
            f"Generated {len(self.static_entities)} biome entities "
            f"({sum(1 for e in self.static_entities if e['type']=='forest')} forests)."
        )

        # Precompute per-cell forest density (done once)
        self._density_map = self._precompute_density()

        self.cmd_sub = self.create_subscription(
            String, "swarm_control", self.cmd_callback, 10
        )

        # CA grid
        self._reset_ca()

    def _reset_ca(self):
        self._accum = [[0.0] * GRID_NY for _ in range(GRID_NX)]
        self._state = [[UNBURNT] * GRID_NY for _ in range(GRID_NX)]
        self._time_in_st = [[0.0] * GRID_NY for _ in range(GRID_NX)]
        self._active = set()

        random.seed()  # release fixed seed for stochastic simulation
        self._seed_fires(count=15)

    def cmd_callback(self, msg):
        try:
            cmd = json.loads(msg.data)
            if cmd.get("action") == "RESET":
                self.get_logger().info("Resetting environment layout and fires...")
                # Regenerate entities for a "different map" feel
                # Note: We use a random seed for layout if we want it to vary,
                # or keep it fixed if we want same entities but different fires.
                # User said "generate different maps", so let's vary the seed or just call gen again.
                # Since random.seed(42) was used in __init__, let's NOT call seed(42) here to get variety.
                self.static_entities = self._gen_biome_entities()
                self._density_map = self._precompute_density()
                self._reset_ca()
                self.publish_environment()
                self.get_logger().info(
                    f"Environment reset. New entity count: {len(self.static_entities)}"
                )
        except Exception as e:
            self.get_logger().error(f"Error in cmd_callback: {e}")

        self.get_logger().info(
            f"CA grid {GRID_NX}x{GRID_NY}, "
            f"{len(self._active)} cells in initial active set."
        )

    # ------------------------------------------------------------------ #
    # Gaussian biome entity generation                                     #
    # ------------------------------------------------------------------ #
    def _gaussian_point(self, cx, cy, sigma, margin=3_000.0):
        """Sample a point from a 2-D Gaussian, clamped to world bounds."""
        x = random.gauss(cx, sigma)
        y = random.gauss(cy, sigma)
        x = max(margin, min(GRID_W_M - margin, x))
        y = max(margin, min(GRID_H_M - margin, y))
        return x, y

    def _gen_biome_entities(self):
        entities = []

        # ── 1. City / town entities (Gaussian around anchor centres) ─────
        for cx, cy, sigma, label, mix in BIOME_ANCHORS:
            for etype, count in mix.items():
                for _ in range(count):
                    x, y = self._gaussian_point(cx, cy, sigma)
                    eid = f"{etype}_{random.randint(1000,9999)}"
                    ent = {"id": eid, "type": etype, "x": x, "y": y}
                    if etype == "building":
                        ent["size"] = random.uniform(350, 600)
                        ent["height"] = random.uniform(20, 120)
                    elif etype == "factory":
                        ent["size"] = random.uniform(300, 1000)
                    elif etype == "lake":
                        ent["size"] = random.uniform(1_500, 6_000)
                    entities.append(ent)

        # ── 2. Forest blobs — Gaussian clusters filling 70%+ of the map ─
        #   Place cluster centres by avoiding city anchors (repulsion heuristic)
        city_centres = [(cx, cy) for cx, cy, *_ in BIOME_ANCHORS]

        forest_centres = []
        attempts = 0
        while len(forest_centres) < N_FOREST_BLOBS and attempts < 2000:
            attempts += 1
            # Random candidate inside map
            fx = random.uniform(5_000, GRID_W_M - 5_000)
            fy = random.uniform(5_000, GRID_H_M - 5_000)
            # Reject if too close to any city anchor
            too_close = any(
                math.hypot(fx - cx, fy - cy) < 12_000 for cx, cy in city_centres
            )
            if not too_close:
                forest_centres.append((fx, fy))

        # For 70% coverage: each forest entity covers a roughly circular region.
        # Tune entity count and size so area sum ≈ 0.70 * world_area.
        # We use 30 blobs × ~20 entities each, each with radius 2–5 km.
        for fcx, fcy in forest_centres:
            blob_sigma = random.uniform(4_000, 10_000)
            n_trees = random.randint(12, 20)
            for _ in range(n_trees):
                x, y = self._gaussian_point(fcx, fcy, blob_sigma)
                size = random.uniform(4_000, 7_000)
                entities.append(
                    {
                        "id": f"forest_{random.randint(1000,9999)}",
                        "type": "forest",
                        "x": x,
                        "y": y,
                        "size": size,
                    }
                )

        return entities

    # ------------------------------------------------------------------ #
    # Forest density lookup (precomputed)                                  #
    # ------------------------------------------------------------------ #
    def _precompute_density(self):
        forests = [e for e in self.static_entities if e["type"] == "forest"]
        dm = [[0.0] * GRID_NY for _ in range(GRID_NX)]
        for i in range(GRID_NX):
            cx = (i + 0.5) * CELL_L
            for j in range(GRID_NY):
                cy = (j + 0.5) * CELL_L
                d = 0.05
                for f in forests:
                    dist = math.hypot(cx - f["x"], cy - f["y"])
                    if dist < f["size"]:
                        d += 0.9 * (1.0 - dist / f["size"])
                dm[i][j] = min(1.0, d)
        return dm

    # ------------------------------------------------------------------ #
    # Fire seeding (forest cells only)                                     #
    # ------------------------------------------------------------------ #
    def _seed_fires(self, count=3):
        forests = [e for e in self.static_entities if e["type"] == "forest"]
        seeded = 0
        for attempt in range(200):
            if seeded >= count:
                break
            f = random.choice(forests)
            angle = random.uniform(0, 2 * math.pi)
            radius = random.uniform(0, f["size"] * 0.6)
            fx = f["x"] + radius * math.cos(angle)
            fy = f["y"] + radius * math.sin(angle)
            i = max(0, min(GRID_NX - 1, int(fx / CELL_L)))
            j = max(0, min(GRID_NY - 1, int(fy / CELL_L)))
            # Only seed if cell has decent forest density
            if self._density_map[i][j] > 0.2:
                self._state[i][j] = FULL_BURN
                self._active.add((i, j))
                self._expand_neighbours(i, j)
                self._publish_fire_notification(f["x"], f["y"])
                seeded += 1

    def _expand_neighbours(self, i, j):
        for di in (-1, 0, 1):
            for dj in (-1, 0, 1):
                ni, nj = i + di, j + dj
                if 0 <= ni < GRID_NX and 0 <= nj < GRID_NY:
                    self._active.add((ni, nj))

    def _publish_fire_notification(self, x, y):
        msg = String()
        msg.data = json.dumps(
            {
                "type": "drone_notification",
                "drone_id": "ENVIRONMENT",
                "message": f"Wildfire ignited at ({x:.0f},{y:.0f})!",
            }
        )
        self.notif_pub.publish(msg)

    # ------------------------------------------------------------------ #
    # Adaptive dt per cell                                                 #
    # ------------------------------------------------------------------ #
    # Adaptive dt per cell (simulation seconds per tick)
    def _cell_dt(self, i, j):
        density = self._density_map[i][j]
        wind_fac = self.wind_speed / 20.0
        a = wind_fac + density - 0.5
        # Base progression is SIM_DT (10s per tick).
        # We scale it slightly by weather/density.
        return SIM_DT * math.exp(a * 0.5)

    def _spread_speed(self, fi, fj, ti, tj):
        dx = (ti - fi) * CELL_L
        dy = (tj - fj) * CELL_L
        dist = math.hypot(dx, dy)
        if dist == 0:
            return 0.0
        wd_rad = math.radians(self.wind_dir)
        dot = (dx / dist) * math.cos(wd_rad) + (dy / dist) * math.sin(wd_rad)
        density = self._density_map[fi][fj]
        R = SPREAD_BASE_RATE * (1.0 + 0.5 * dot) * (0.5 + density)
        # Higher density = faster spread
        return max(0.0, R)

    # ------------------------------------------------------------------ #
    # CA step                                                              #
    # ------------------------------------------------------------------ #
    def _step_ca(self):
        # Wildfire spreading and transitions have been disabled.
        # Fires remain permanently at their static initialized size.
        pass

    # ------------------------------------------------------------------ #
    # Payload                                                              #
    # ------------------------------------------------------------------ #
    def _ca_payload(self):
        cells = []
        for i, j in list(self._active):
            st = self._state[i][j]
            if st == UNBURNT:
                continue
            cells.append(
                {
                    "i": i,
                    "j": j,
                    "x": (i + 0.5) * CELL_L,
                    "y": (j + 0.5) * CELL_L,
                    "state": st,
                }
            )
        return cells

    # ------------------------------------------------------------------ #
    # Publish                                                              #
    # ------------------------------------------------------------------ #
    def _update_env(self):
        self.wind_speed += random.uniform(-0.3, 0.3)
        self.wind_speed = max(0.5, min(20.0, self.wind_speed))
        self.wind_dir = (self.wind_dir + random.uniform(-5.0, 5.0)) % 360
        self._step_ca()

    def publish_environment(self):
        self._update_env()
        env_state = {
            "grid": {
                "width": self.grid_width,
                "height": self.grid_height,
                "cell_size": CELL_L,
                "nx": GRID_NX,
                "ny": GRID_NY,
            },
            "season": self.season,
            "wind": {
                "speed": round(self.wind_speed, 2),
                "direction": round(self.wind_dir, 2),
            },
            "topography": {"base_elevation": self.base_elev},
            "entities": self.static_entities,
            "ca_cells": self._ca_payload(),
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
        node.get_logger().info("EnvironmentNode stopped.")
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == "__main__":
    main()
