#!/bin/bash
set -e

# Update system
apt-get update && apt-get upgrade -y

# Install Docker
apt-get install -y docker.io
systemctl start docker
systemctl enable docker

# Add ubuntu user to docker group
usermod -aG docker ubuntu

# Create app directory
mkdir -p /opt/ascii-player
chown -R ubuntu:ubuntu /opt/ascii-player

echo "Setup complete. SSH in and run:"
echo "  docker pull ascii-player:latest"
echo "  docker run -it --rm --device=/dev/snd --device=/dev/dri ascii-player:latest --webcam --width=80"
