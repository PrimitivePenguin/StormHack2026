#!/bin/bash

# Function to kill all background processes started by this script on exit
cleanup() {
    echo "Stopping Pygame and Flask..."
    kill $(jobs -p) 2>/dev/null
}

# Run the cleanup function if the user presses Ctrl+C or exits
trap cleanup EXIT

echo "Starting Flask server and Pygame application..."

# 1. Start Flask in the background
# Replace 'server.py' with your actual Flask file name
python3 ./malfoy_GUI/server.py & 

# Give Flask 2 seconds to boot up before launching Pygame
sleep 2

# 2. Start Pygame in the foreground
# Replace 'game.py' with your actual Pygame file name
python3 ./malfoy_GUI/gui.py

# Keep the script alive as long as Pygame is running
wait
