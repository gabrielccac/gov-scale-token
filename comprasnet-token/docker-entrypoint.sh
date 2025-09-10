#!/bin/bash
# docker-entrypoint.sh

# Start Xvfb in the background on display :99
Xvfb :99 -screen 0 1280x720x16 &
XVFB_PID=$!

# Function to cleanup Xvfb
cleanup() {
    echo "Cleaning up Xvfb process..."
    kill $XVFB_PID 2>/dev/null
    wait $XVFB_PID 2>/dev/null
}

# Set trap to cleanup on script exit
trap cleanup EXIT

# Execute the main command passed to the script (our python app)
exec "$@"
