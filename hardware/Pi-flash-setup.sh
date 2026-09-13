#!/bin/bash

# Raspberry Pi Camera Recorder Setup Script
# Prepares laptop environment and creates files needed to flash Pi for traffic capture
# Part of truck-safety-vision-system project - collects training data for CMV detection

set -e  # Exit immediately if any command fails

echo "=== Raspberry Pi Camera Recorder Setup ==="
echo ""

# Safety check - prevent running this script on the Pi itself
if grep -q "Raspberry Pi" /proc/cpuinfo 2>/dev/null; then
    echo "ERROR: This script should run on your laptop, not the Pi!"
    exit 1
fi

# Step 1: Ensure wget is available for downloading packages
echo "[1/5] Checking prerequisites..."
command -v wget >/dev/null 2>&1 || { 
    echo "Installing wget..."; 
    sudo apt-get update && sudo apt-get install -y wget; 
}

# Step 2: Install Raspberry Pi Imager (official tool for flashing SD cards)
echo "[2/5] Checking for Raspberry Pi Imager..."
if ! command -v rpi-imager >/dev/null 2>&1; then
    echo "Installing Raspberry Pi Imager..."
    wget -q https://downloads.raspberrypi.org/imager/imager_latest_amd64.deb -O /tmp/rpi-imager.deb
    sudo dpkg -i /tmp/rpi-imager.deb
    sudo apt-get install -f -y  # Fix any dependency issues
fi

# Step 3: Create the camera recording script that will run on the Pi
# This script captures images every 2 seconds for Edge Impulse training data
echo "[3/5] Creating camera recording script..."
cat > /tmp/camera-recorder.sh << 'PIEOF'
#!/bin/bash

# Configuration - where to store captured images
MOUNT_POINT="/mnt/external-ssd"
IMAGE_DIR="${MOUNT_POINT}/training-captures"
DATE=$(date +%Y%m%d-%H%M%S)
SESSION_DIR="${IMAGE_DIR}/session-${DATE}"

# Mount external SSD if not already mounted
# Adjust /dev/sda1 if your SSD is on a different device
if ! mountpoint -q ${MOUNT_POINT}; then
    sudo mkdir -p ${MOUNT_POINT}
    sudo mount /dev/sda1 ${MOUNT_POINT}
fi

# Create directory for this capture session
mkdir -p ${SESSION_DIR}

echo "Starting camera capture at $(date)"
echo "Saving to: ${SESSION_DIR}"

# Main capture loop - takes 1920x1080 images every 2 seconds
# Images saved as JPEG for Edge Impulse compatibility
while true; do
    TIMESTAMP=$(date +%Y%m%d-%H%M%S)
    libcamera-still -o "${SESSION_DIR}/frame-${TIMESTAMP}.jpg" \
        --width 1920 --height 1080 \
        --nopreview --timeout 1
    sleep 2  # Wait 2 seconds between captures
done
PIEOF

chmod +x /tmp/camera-recorder.sh

# Step 4: Create systemd service for auto-start on boot
# This ensures camera recording begins automatically when Pi powers on
echo "[4/5] Creating systemd service file..."
cat > /tmp/camera-recorder.service << 'SVCEOF'
[Unit]
Description=Camera Recording Service
After=network.target  # Start after network is available

[Service]
Type=simple
User=pi
ExecStart=/home/pi/camera-recorder.sh
Restart=always  # Restart if it crashes
RestartSec=10   # Wait 10 seconds before restarting

[Install]
WantedBy=multi-user.target  # Enable for normal boot
SVCEOF

# Step 5: Summary
echo ""
echo "[5/5] Setup complete!"
echo ""
echo "Files created in /tmp/:"
echo "  - camera-recorder.sh (captures images on Pi)"
echo "  - camera-recorder.service (auto-start configuration)"
echo ""
echo "Next steps:"
echo "1. Insert SD card into your laptop"
echo "2. Run: rpi-imager"
echo "3. Choose Raspberry Pi OS (64-bit)"
echo "4. Configure WiFi and SSH in advanced options"
echo "5. Flash the SD card"
echo "6. See vision-system-setup.md for post-flash configuration"