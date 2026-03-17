#!/bin/bash
# setup.sh — Install and configure TrainTime on a Raspberry Pi
# Run this after cloning the repo: ./setup.sh

set -e

echo "🚇 TrainTime — Raspberry Pi Setup"
echo "──────────────────────────────────"

# 1. Install Python dependencies
echo ""
echo "📦 Creating virtual environment and installing dependencies…"
python3 -m venv venv
source venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt

# 2. Install the systemd service for auto-start on boot
echo ""
echo "⚙️  Setting up auto-start service…"
sudo cp traintime.service /etc/systemd/system/traintime.service
sudo systemctl daemon-reload
sudo systemctl enable traintime.service
echo "   ✅ Service enabled — TrainTime will start on boot"

# 3. Optionally start it now
echo ""
read -p "🚀 Start TrainTime now? [y/N] " -n 1 -r
echo
if [[ $REPLY =~ ^[Yy]$ ]]; then
    sudo systemctl start traintime.service
    echo "   ✅ TrainTime is running!"
    echo "   View logs: journalctl -u traintime -f"
else
    echo "   To start manually: sudo systemctl start traintime"
    echo "   Or reboot and it will start automatically."
fi

echo ""
echo "──────────────────────────────────"
echo "✅ Setup complete!"
echo ""
echo "Useful commands:"
echo "  sudo systemctl start traintime    # Start"
echo "  sudo systemctl stop traintime     # Stop"
echo "  sudo systemctl restart traintime  # Restart"
echo "  sudo systemctl status traintime   # Status"
echo "  journalctl -u traintime -f        # Live logs"
