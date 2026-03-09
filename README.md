# 🚇 TrainTime

A real-time MTA train schedule display for Brooklyn stations, designed for a **Raspberry Pi** with a touchscreen.

![Python](https://img.shields.io/badge/python-3.7+-blue) ![MTA GTFS-RT](https://img.shields.io/badge/data-MTA%20GTFS--RT-yellow)

## 🌟 Features

- 🚉 **Multi-Station Support**: Cycles between **Union St. (R)** and **4 Av - 9 St (F, G, R)**.
- 🔢 **5-Train View**: Displays the next 5 upcoming trains per station.
- 👆 **Interactive Touch**: Tap the screen at any time to skip to the next station and reset the 10s auto-rotate timer.
- ⏱️ **Live Countdown**: Minutes away now update in real-time between data fetches for smooth "approaching" visuals.
- ⏳ **Custom Thresholds**: Filter out trains arriving too soon to catch (configurable).
- 🔄 **High Frequency**: Polls the MTA API every **10 seconds** to stay perfectly in sync.
- 🖥️ **Tailored UI**: Bolder route badges and larger fonts optimized for small-form-factor displays (480p).
- 🔁 **Resilient**: Automatic retry with exponential backoff on connection errors.

## 🚀 Quick Start

### 1. Clone the repo

```bash
git clone https://github.com/stanchanpsu/traintime.git
cd traintime
```

### 2. Install dependencies

```bash
# Recommended to use a virtual environment
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

### 3. Run

```bash
python traintime.py
```

Press **Escape** to quit, or **F11** to toggle fullscreen.

## ⚙️ Configuration

You can customize behavior using environment variables:

| Variable | Description | Default |
| :--- | :--- | :--- |
| `FULLSCREEN` | Set to `0` to run in a window for local testing. | `1` |
| `MIN_THRESHOLD_MINS` | Only show trains that are at least X minutes away. | `5` |

Example:
```bash
FULLSCREEN=0 MIN_THRESHOLD_MINS=3 python traintime.py
```

## 🛠️ Raspberry Pi Setup

### Prerequisites

- Raspberry Pi (3 or newer) with a touchscreen (e.g., the official 7" 800x480 or similar).
- Internet connection.
- Raspberry Pi OS with desktop.

### Automatic Auto-start

Run the included setup script to configure the app to start automatically on boot:

```bash
chmod +x setup.sh
./setup.sh
```

This sets up a `traintime.service` unit. You can view logs with:
```bash
journalctl -u traintime -f
```

## 🔍 Debugging

If you suspect train data is missing, we've included a standalone debug tool to check raw MTA feeds:
```bash
./venv/bin/python debug_mta.py
```

## 📜 Commands

```bash
sudo systemctl start traintime    # Start the app
sudo systemctl stop traintime     # Stop the app (Graceful shutdown)
sudo systemctl restart traintime  # Restart after updates
sudo systemctl status traintime   # Check if it's running
```
