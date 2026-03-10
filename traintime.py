"""
traintime.py — MTA Train Schedule Display
Designed for Raspberry Pi. Fullscreen tkinter UI with live GTFS-RT data.
Cycles between stations every 10 seconds.
"""

from datetime import datetime
import os
import traceback
import time
import threading
from tkinter import font as tkfont
import tkinter as tk
print("Script starting...")


try:
    from nyct_gtfs import NYCTFeed
except ImportError:
    print("ERROR: nyct-gtfs not installed. Run: pip3 install nyct-gtfs --break-system-packages")
    raise

# ── Configuration ──────────────────────────────────────────────────────────────
STATIONS = {"R32": "Union St", "F23": "4 Av - 9 St"}
BOROUGH = "Brooklyn"
FEED_IDS = ["R", "F", "G"]  # MTA feed routes (nyct-gtfs v2.1.0+)
TRAINS_PER_STATION = 5           # rows to display per station
MAX_TRAINS = TRAINS_PER_STATION
REFRESH_SECS = 10             # Fetch from MTA every 10s
CYCLE_SECS = 10             # seconds to show each station
# skip trains arriving in < threshold mins
MIN_MINS_AWAY = float(os.environ.get("MIN_THRESHOLD_MINS", "5"))
print(
    f"[DEBUG] MIN_THRESHOLD_MINS env var: {os.environ.get('MIN_THRESHOLD_MINS', 'NOT SET')}")
print(f"[DEBUG] MIN_MINS_AWAY: {MIN_MINS_AWAY}")
# Set to 0 to run in a window
FULLSCREEN = os.environ.get("FULLSCREEN", "1") != "0"
RETRY_BASE_SECS = 5              # base delay for retry on error
RETRY_MAX_SECS = 120            # max delay cap for retry backoff

# Direction labels and colors
DIRECTION_LABELS = {
    "N": "↑ Manh/Queens",
    "S": "↓ Brooklyn"
}
DIR_COLORS = {
    "N": "#34D399",  # Greenish for North (Manhattan direction)
    "S": "#FBBF24"   # Yellowish for South (Brooklyn direction)
}

# Route-specific direction overrides
ROUTE_DIRECTION_LABELS = {
    "G": {
        "N": "↑ Queens"
    }
}

# Route colors (MTA official)
ROUTE_COLORS = {
    "R": "#FCCC0A",  # Yellow (BMT Broadway)
    "N": "#FCCC0A",
    "Q": "#FCCC0A",
    "W": "#FCCC0A",
    "D": "#FF6319",  # Orange (IND Sixth Avenue)
    "F": "#FF6319",  # Orange (IND Sixth Avenue)
    "G": "#6CBE45",  # Light Green (IND Crosstown)
}
ROUTE_TEXT_COLORS = {
    "R": "#000000",
    "N": "#000000",
    "Q": "#000000",
    "W": "#000000",
    "D": "#FFFFFF",
    "F": "#FFFFFF",
    "G": "#FFFFFF",
}

# ── Color Palette ───────────────────────────────────────────────────────────────
BG_COLOR = "#0A0E1A"
PANEL_BG = "#111827"
HEADER_COLOR = "#1E2A40"
TEXT_PRIMARY = "#F0F4FF"
TEXT_SECONDARY = "#8896B0"
ACCENT_COLOR = "#3B82F6"
BORDER_COLOR = "#1E2A3D"
GREEN_COLOR = "#22C55E"
AMBER_COLOR = "#F59E0B"
RED_COLOR = "#EF4444"

# ── App ─────────────────────────────────────────────────────────────────────────


class TraintimeApp:
    def __init__(self, root):
        self.root = root
        self.root.title("TrainTime")
        self.root.configure(bg=BG_COLOR)
        if FULLSCREEN:
            self.root.attributes("-fullscreen", True)
            self.root.config(cursor="none")
        else:
            # Default window size for local testing
            self.root.geometry("720x480")
        self.root.bind("<Escape>", lambda e: self.root.destroy())
        self.root.bind("<F11>", lambda e: self.root.attributes("-fullscreen",
                                                               not self.root.attributes("-fullscreen")))
        # Manual cycle on click/touch
        self.root.bind("<Button-1>", self._manual_cycle)

        self.trains = []
        self.last_updated = None
        self.status_msg = "Connecting…"
        self.is_error = False
        self.consecutive_errors = 0
        self.lock = threading.Lock()

        self.station_ids = list(STATIONS.keys())
        self.station_index = 0
        self.cycle_after_id = None

        self._build_ui()
        self._start_refresh_thread()
        self._cycle_loop()

    # ── UI Build ────────────────────────────────────────────────────────────────
    def _build_ui(self):
        if FULLSCREEN:
            sw = self.root.winfo_screenwidth()
            sh = self.root.winfo_screenheight()
        else:
            sw = 720
            sh = 480

        # Proportional scaling for single-view (No destination, 5 rows)
        scale = max(0.5, sw / 1280) * 2.3
        self.scale = scale
        self.fnt_title = tkfont.Font(
            family="DejaVu Sans", size=int(26*scale), weight="bold")
        self.fnt_sub = tkfont.Font(family="DejaVu Sans", size=int(11*scale))
        self.fnt_header = tkfont.Font(
            family="DejaVu Sans", size=int(10*scale), weight="bold")
        self.fnt_route = tkfont.Font(
            family="DejaVu Sans", size=int(28*scale), weight="bold")
        self.fnt_time = tkfont.Font(
            family="DejaVu Sans", size=int(26*scale), weight="bold")
        self.fnt_min = tkfont.Font(family="DejaVu Sans", size=int(14*scale))
        self.fnt_dest = tkfont.Font(family="DejaVu Sans", size=int(16*scale))
        self.fnt_status = tkfont.Font(family="DejaVu Sans", size=int(20*scale))
        self.fnt_message = tkfont.Font(
            family="DejaVu Sans", size=int(22*scale))

        # ── Slim Header (Clock & Status on one line) ───────────────────────────
        header = tk.Frame(self.root, bg=BG_COLOR, pady=int(2*scale))
        header.pack(side="top", fill="x", padx=int(12*scale))

        # Station Name (Left)
        self.station_label = tk.Label(header, text="", font=self.fnt_title,
                                      bg=BG_COLOR, fg=ACCENT_COLOR)
        self.station_label.pack(side="left")

        # Status & Clock Frame (Right)
        right = tk.Frame(header, bg=BG_COLOR)
        right.pack(side="right")

        self.clock_label = tk.Label(right, text="", font=self.fnt_time,
                                    bg=BG_COLOR, fg=TEXT_PRIMARY)
        self.clock_label.pack(side="right", padx=(int(8*scale), 0))

        self.status_label = tk.Label(right, text="", font=self.fnt_status,
                                     bg=BG_COLOR, fg=TEXT_SECONDARY)
        self.status_label.pack(side="right")

        # ── Train rows container ─────────────────────────────────────────────────
        self.rows_frame = tk.Frame(self.root, bg=BG_COLOR)
        self.rows_frame.pack(fill="both", expand=True, padx=int(16*scale),
                             pady=(int(2*scale), int(4*scale)))
        for c in [0, 1, 2]:
            self.rows_frame.columnconfigure(
                c, weight=(0 if c in [0, 2] else 1))
        self.rows_frame.columnconfigure(0, minsize=int(80*scale))
        self.rows_frame.columnconfigure(2, minsize=int(160*scale))

        # Center message label (for loading / error / no trains)
        self.center_message = tk.Label(self.rows_frame, text="", font=self.fnt_message,
                                       bg=BG_COLOR, fg=TEXT_SECONDARY, anchor="center")

        # Pre-create row label sets (reuse, don't destroy/recreate every tick)
        self._row_widgets = []
        for i in range(MAX_TRAINS):
            bg = BG_COLOR if i % 2 == 0 else PANEL_BG
            row = {}

            # Route badge (Canvas circle)
            badge_canvas = tk.Canvas(self.rows_frame, width=int(60*scale),
                                     height=int(60*scale), bg=bg,
                                     highlightthickness=0, bd=0)
            badge_canvas.grid(row=i, column=0, sticky="nsew",
                              pady=int(2*scale), padx=int(8*scale))
            row["badge_canvas"] = badge_canvas
            row["badge_bg"] = bg

            # Direction
            dir_lbl = tk.Label(self.rows_frame, text="", font=self.fnt_status,
                               bg=bg, fg=TEXT_SECONDARY, anchor="w")
            dir_lbl.grid(row=i, column=1, sticky="ew",
                         padx=int(16*scale), pady=int(2*scale))
            row["dir"] = dir_lbl

            # Arrival time
            time_frame = tk.Frame(self.rows_frame, bg=bg)
            time_frame.grid(row=i, column=2, sticky="ew", padx=int(8*scale))
            mins_lbl = tk.Label(time_frame, text="", font=self.fnt_time,
                                bg=bg, anchor="e")
            mins_lbl.pack(side="right")
            mins_unit = tk.Label(time_frame, text="", font=self.fnt_status,
                                 bg=bg, fg=TEXT_SECONDARY, anchor="e")
            mins_unit.pack(side="right", padx=(0, int(4*scale)))
            row["mins"] = mins_lbl
            row["mins_unit"] = mins_unit

            self._row_widgets.append(row)

        # Show loading state on startup
        self._show_center_message("🔄  Connecting to MTA…")
        self._tick_clock()

    # ── Center Message ───────────────────────────────────────────────────────────
    def _show_center_message(self, text, color=None):
        """Show a centered message and hide all train rows."""
        for row in self._row_widgets:
            row["badge_canvas"].grid_remove()
            row["dir"].grid_remove()
            row["mins"].master.grid_remove()
        self.center_message.config(text=text, fg=color or TEXT_SECONDARY)
        self.center_message.place(relx=0.5, rely=0.4, anchor="center")

    def _hide_center_message(self):
        """Hide the center message and restore train row grid structure."""
        self.center_message.place_forget()
        sc = self.scale
        for i, row in enumerate(self._row_widgets):
            row["badge_canvas"].grid(row=i, column=0, sticky="nsew",
                                     pady=int(2*sc), padx=int(8*sc))
            row["dir"].grid(row=i, column=1, sticky="ew",
                            padx=int(16*sc), pady=int(2*sc))
            row["mins"].master.grid(
                row=i, column=2, sticky="ew", padx=int(8*sc))
            row["mins"].pack(side="right")
            row["mins_unit"].pack(side="right", padx=(0, int(4*sc)))

    # ── Clock ────────────────────────────────────────────────────────────────────
    def _tick_clock(self):
        now = datetime.now()
        self.clock_label.config(text=now.strftime("%I:%M:%S %p").lstrip("0"))

        with self.lock:
            is_err = self.is_error
            last = self.last_updated
            msg = self.status_msg

        if last and not is_err:
            age = int((now - last).total_seconds())
            if age > REFRESH_SECS * 2:
                self.status_label.config(
                    text=f"Stale ({age}s)", fg=AMBER_COLOR)
            else:
                self.status_label.config(text=f"Live", fg=TEXT_SECONDARY)
        elif is_err:
            self.status_label.config(text=f"⚠ Error", fg=AMBER_COLOR)
        else:
            self.status_label.config(text=msg, fg=TEXT_SECONDARY)

        self.root.after(1000, self._tick_clock)

    # ── Cycling ──────────────────────────────────────────────────────────────────
    def _manual_cycle(self, event=None):
        """Force a cycle and reset timer on touch/click."""
        if self.cycle_after_id:
            self.root.after_cancel(self.cycle_after_id)
        self._cycle_loop()

    def _cycle_loop(self):
        """Rotate through the stations."""
        with self.lock:
            if self.station_ids:
                self.station_index = (
                    self.station_index + 1) % len(self.station_ids)
        self._update_ui()
        self.cycle_after_id = self.root.after(
            CYCLE_SECS * 1000, self._cycle_loop)

    # ── Data Fetching ────────────────────────────────────────────────────────────
    def _start_refresh_thread(self):
        t = threading.Thread(target=self._refresh_loop, daemon=True)
        t.start()

    def _refresh_loop(self):
        while True:
            try:
                self._fetch_trains()
                with self.lock:
                    self.is_error = False
                    self.consecutive_errors = 0
                self.root.after(0, self._update_ui)
                time.sleep(REFRESH_SECS)
            except Exception as e:
                with self.lock:
                    self.consecutive_errors += 1
                    self.is_error = True
                    self.status_msg = f"Error ({self.consecutive_errors})"
                print(f"[TrainTime] Error: {e}")
                traceback.print_exc()
                delay = min(
                    RETRY_BASE_SECS * (2 ** (self.consecutive_errors - 1)), RETRY_MAX_SECS)
                time.sleep(delay)

    def _fetch_trains(self):
        now_ts = datetime.now().timestamp()
        arrivals_by_station = {s: [] for s in STATIONS.keys()}

        for feed_id in FEED_IDS:
            try:
                feed = NYCTFeed(feed_id)
                for trip in feed.trips:
                    for stop_time in trip.stop_time_updates:
                        stop_id = getattr(stop_time, 'stop_id', None)
                        if not stop_id:
                            continue

                        stop_base = stop_id[:-1] if len(stop_id) > 1 else ""
                        if stop_base in STATIONS:
                            direction = stop_id[-1]
                            arrival_ts = stop_time.arrival or stop_time.departure
                            if not arrival_ts:
                                continue

                            arr_epoch = arrival_ts.timestamp() if hasattr(
                                arrival_ts, "timestamp") else float(arrival_ts)
                            mins_away = (arr_epoch - now_ts) / 60

                            if mins_away < MIN_MINS_AWAY:
                                continue

                            route = trip.route_id
                            dest = getattr(trip, 'headsign_text',
                                           None) or "Unknown"

                            arrivals_by_station[stop_base].append({
                                "station_id": stop_base,
                                "route": route,
                                "dest": dest,
                                "direction": direction,
                                "epoch": arr_epoch
                            })
            except Exception as e:
                print(f"[TrainTime] Error fetching feed {feed_id}: {e}")

        total_found = 0
        combined = []
        for s in STATIONS.keys():
            st_arr = arrivals_by_station[s]
            st_arr.sort(key=lambda x: x["epoch"])
            combined.extend(st_arr[:10])  # Buffers for rotation
            total_found += len(st_arr)

        print(
            f"[TrainTime] Fetch cycle complete. Found {total_found} total trains at {datetime.now().strftime('%H:%M:%S')}")

        with self.lock:
            self.trains = combined
            self.last_updated = datetime.now()
            self.status_msg = "Live"

    # ── UI Update ─────────────────────────────────────────────────────────────────
    def _update_ui(self):
        with self.lock:
            if not self.station_ids:
                return
            current_id = self.station_ids[self.station_index]
            now_ts = datetime.now().timestamp()

            # Filter live for trains >= MIN_MINS_AWAY
            trains = [t for t in self.trains if t.get(
                "station_id") == current_id]
            trains = [t for t in trains if (
                t["epoch"] - now_ts)/60 >= MIN_MINS_AWAY][:MAX_TRAINS]

            self.station_label.config(text=STATIONS.get(current_id, ""))
            last = self.last_updated
            is_err = self.is_error

        count = len(trains)
        if count == 0:
            if last is None and not is_err:
                self._show_center_message("🔄  Connecting…")
            elif not is_err:
                self._show_center_message(f"Next train in >{MIN_MINS_AWAY}m")
            return

        self._hide_center_message()
        sc = self.scale
        # note: now_ts already captured above

        for i, row in enumerate(self._row_widgets):
            if i < count:
                t = trains[i]
                arr_epoch = t["epoch"]
                mins = (arr_epoch - now_ts) / 60
                route = t["route"]

                c = row["badge_canvas"]
                c.delete("all")
                color = ROUTE_COLORS.get(route, "#666")
                text_color = ROUTE_TEXT_COLORS.get(route, "#000")
                c.create_oval(0, 0, int(60*sc), int(60*sc),
                              fill=color, outline="")
                c.create_text(int(30*sc), int(30*sc), text=route,
                              font=self.fnt_route, fill=text_color)

                direction = t["direction"]

                # Direction text with route-specific override
                dir_text = ROUTE_DIRECTION_LABELS.get(route, {}).get(direction)
                if not dir_text:
                    dir_text = DIRECTION_LABELS.get(direction, direction)

                row["dir"].config(text=dir_text,
                                  fg=DIR_COLORS.get(direction, TEXT_SECONDARY))

                if mins < 1:
                    row["mins"].config(text="Now", fg=GREEN_COLOR)
                    row["mins_unit"].config(text="")
                elif mins < 2:
                    row["mins"].config(text="1", fg=AMBER_COLOR)
                    row["mins_unit"].config(text="min")
                else:
                    clr = GREEN_COLOR if mins > 5 else (
                        AMBER_COLOR if mins > 2 else RED_COLOR)
                    row["mins"].config(text=str(int(mins)), fg=clr)
                    row["mins_unit"].config(text="min")
            else:
                row["badge_canvas"].delete("all")
                row["dir"].config(text="")
                row["mins"].config(text="")
                row["mins_unit"].config(text="")


# ── Entry Point ──────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    root = tk.Tk()
    app = TraintimeApp(root)
    root.mainloop()
