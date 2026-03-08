# 🚇 TrainTime

A real-time MTA train schedule display for the **Union St. (R)** station in Brooklyn, built in Python and designed to run on a **Raspberry Pi**.

![Python](https://img.shields.io/badge/python-3.7+-blue) ![MTA GTFS-RT](https://img.shields.io/badge/data-MTA%20GTFS--RT-yellow)

## Features

- 🟡 Live R train arrival times for Union St. (Brooklyn)
- 🔄 Auto-refreshes every 30 seconds from the MTA GTFS-Realtime feed
- 🖥️ Fullscreen `tkinter` UI — great for a dedicated display
- ⏱️ Color-coded countdowns (green → amber → red as train approaches)
- 📡 No API key required

## Requirements

- Python 3.7+
- `nyct-gtfs` library

## Install

```bash
pip3 install nyct-gtfs --break-system-packages
```

## Run

```bash
python3 traintime.py
```

Press **Escape** to quit the fullscreen app.

## Running on Raspberry Pi

Make sure a display is connected. To run over SSH with a display:

```bash
export DISPLAY=:0 && python3 traintime.py
```
