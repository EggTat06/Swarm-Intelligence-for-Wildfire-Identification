#!/bin/bash
# Swarm Wildfire Project - Full System Launcher for WSL

echo "🔥 Starting Swarm Wildfire System..."

#=======================================================
# 1. Start the Database (Docker)
#=======================================================
echo "📦 1/4 Starting TimescaleDB via Docker Compose..."
# Check if docker-compose is installed
if command -v docker-compose &> /dev/null; then
    docker-compose up -d
elif command -v docker &> /dev/null && docker compose version &> /dev/null; then
    docker compose up -d
else
    echo "⚠️ Docker or Docker Compose not found. Please ensure the database is running manually."
fi


#=======================================================
# 2. Setup ROS 2 Environment & Build Workspace
#=======================================================
echo "🛠️ 2/4 Building and sourcing ROS 2 Workspace..."
source /opt/ros/jazzy/setup.bash || { echo "❌ Failed to source ROS 2 Jazzy"; exit 1; }

# Create python venv if it doesn't exist
if [ ! -d "venv" ]; then
    echo "Creating Python virtual environment..."
    python3 -m venv venv --system-site-packages
    source venv/bin/activate
    pip install fastapi uvicorn setuptools psycopg2-binary ultralytics

    touch venv/COLCON_IGNORE
else
    source venv/bin/activate
fi

# Build ROS 2 packages
colcon build --symlink-install || { echo "❌ Failed to build ROS 2 workspace"; exit 1; }
source install/setup.bash || { echo "❌ Failed to source local workspace"; exit 1; }


#=======================================================
# 3. Start ROS 2 Nodes (in background)
#=======================================================
echo "🚁 3/4 Launching ROS 2 Nodes..."
ros2 run sim_pkg environment_node &
ENV_PID=$!
sleep 1 # Give environment a moment to start

ros2 run sim_pkg drone_node &
DRONE_PID=$!

ros2 run sim_pkg vision_processing &
VISION_PID=$!

ros2 run sim_pkg metrics_node &
METRICS_PID=$!


#=======================================================
# 4. Start Backend Server & Frontend (in background)
#=======================================================
echo "🌐 4/4 Starting Web Services..."

# Start FastAPI Backend
cd server
../venv/bin/python bridge.py &
BACKEND_PID=$!
cd ..

# Start Vite Frontend
cd frontend
# Install node modules if missing
if [ ! -d "node_modules" ]; then
    echo "Installing frontend dependencies..."
    npm install
fi
npm run dev &
FRONTEND_PID=$!
cd ..


#=======================================================
# Wait and Cleanup
#=======================================================
echo ""
echo "✅ All systems are running!"
echo "   - Frontend: http://localhost:5173"
echo "   - Backend:  http://localhost:8000"
echo "   - Database: localhost:5432"
echo ""
echo "Press Ctrl+C to stop all services."

# Trap Ctrl+C to kill all background processes
trap "echo '🛑 Stopping system...'; kill $ENV_PID $DRONE_PID $VISION_PID $METRICS_PID $BACKEND_PID $FRONTEND_PID; exit 0" SIGINT SIGTERM

# Wait indefinitely until interrupted
wait
