CREATE EXTENSION IF NOT EXISTS timescaledb;

-- Table to log overall missions and their final success metrics
CREATE TABLE IF NOT EXISTS missions (
    mission_id UUID PRIMARY KEY,
    start_time TIMESTAMPTZ NOT NULL,
    end_time TIMESTAMPTZ,
    swarm_parameters JSONB NOT NULL,
    time_to_first_detection FLOAT, -- in seconds
    success BOOLEAN DEFAULT FALSE
);

-- Table for high-frequency telemetry data from all drones
CREATE TABLE IF NOT EXISTS telemetry (
    time TIMESTAMPTZ NOT NULL,
    drone_id VARCHAR(50) NOT NULL,
    mission_id UUID REFERENCES missions(mission_id),
    latitude FLOAT NOT NULL,
    longitude FLOAT NOT NULL,
    altitude FLOAT NOT NULL,
    battery_level FLOAT,
    pheromone_level FLOAT -- How much pheromone it corresponds to structurally
);

-- Convert telemetry to a hypertable for performance
SELECT create_hypertable('telemetry', 'time');

-- Table for YOLO bounding box verification events
CREATE TABLE IF NOT EXISTS yolo_detections (
    time TIMESTAMPTZ NOT NULL,
    drone_id VARCHAR(50) NOT NULL,
    mission_id UUID REFERENCES missions(mission_id),
    confidence_score FLOAT NOT NULL,
    bounding_box JSONB, -- Coordinates of the bounding box
    image_reference VARCHAR(255), -- Link/ID to image if saved in object storage
    is_true_positive BOOLEAN -- Can be updated later for reinforcement learning feedback
);

-- Convert detections to hypertable
SELECT create_hypertable('yolo_detections', 'time');
