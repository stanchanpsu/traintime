# 🚇 TrainTime

A real-time MTA train schedule display for the **Union St. (R)** station in Brooklyn, built in Python and designed to run on a **Raspberry Pi**.

![Python](https://img.shields.io/badge/python-3.7+-blue) ![MTA GTFS-RT](https://img.shields.io/badge/data-MTA%20GTFS--RT-yellow)

## Features

- 🟡 Live R train arrival times for Union St. (Brooklyn)
- 🔄 Auto-refreshes every 30 seconds from the MTA GTFS-Realtime feed
- 🖥️ Fullscreen `tkinter` UI — great for a dedicated display
- ⏱️ Color-coded countdowns (green → amber → red as train approaches)
- 🔁 Automatic retry with exponential backoff on connection errors
- 📡 No API key required

## Quick Start

### 1. Clone the repo

```bash
git clone https://github.com/stanchanpsu/traintime.git
cd traintime
```

### 2. Install dependencies

```bash
pip3 install -r requirements.txt --break-system-packages
```

### 3. Run

```bash
python3 traintime.py
```

Press **Escape** to quit the fullscreen app, or **F11** to toggle fullscreen.

## Raspberry Pi Setup

### Prerequisites

- Raspberry Pi 3 or newer
- Display connected via HDMI
- Internet connection
- Raspberry Pi OS with desktop (for tkinter/X11)

### One-Command Setup

After cloning, run the setup script to install dependencies and configure auto-start on boot:

```bash
chmod +x setup.sh
./setup.sh
```

This will:
1. Install Python dependencies
2. Set up a systemd service for auto-start on boot
3. Optionally start the app immediately

### Running over SSH

If you want to run manually over SSH (with a display connected to the Pi):

```bash
export DISPLAY=:0 && python3 traintime.py
```

### Useful Commands

```bash
sudo systemctl start traintime    # Start the app
sudo systemctl stop traintime     # Stop the app
sudo systemctl restart traintime  # Restart
sudo systemctl status traintime   # Check status
journalctl -u traintime -f        # View live logs
```
