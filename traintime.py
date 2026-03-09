"""
traintime.py — MTA Train Schedule Display for Union St. (R32)
Designed for Raspberry Pi. Fullscreen tkinter UI with live GTFS-RT data.
"""

import tkinter as tk
from tkinter import font as tkfont
import threading
import time
import traceback
import os
from datetime import datetime

try:
    from nyct_gtfs import NYCTFeed
except ImportError:
    print("ERROR: nyct-gtfs not installed. Run: pip3 install nyct-gtfs --break-system-packages")
    raise

# ── Configuration ──────────────────────────────────────────────────────────────
STATIONS        = {"R32": "Union St", "F23": "4 Av - 9 St"}
BOROUGH         = "Brooklyn"
FEED_IDS        = ["R", "F", "G"] # MTA feed routes (nyct-gtfs v2.1.0+)
TRAINS_PER_STATION = 3           # rows to display per station
MAX_TRAINS      = len(STATIONS) * TRAINS_PER_STATION
REFRESH_SECS    = 30             # how often to poll the API
FULLSCREEN      = os.environ.get("FULLSCREEN", "1") != "0" # Set to 0 to run in a window
RETRY_BASE_SECS = 5              # base delay for retry on error
RETRY_MAX_SECS  = 120            # max delay cap for retry backoff

# Direction labels and colors
DIRECTION_LABELS = {
    "N": "↑ Manh/Queens",
    "S": "↓ Brooklyn/CI"
}
DIR_COLORS = {
    "N": "#34D399",  # Greenish for North (Manhattan direction)
    "S": "#FBBF24"   # Yellowish for South (Brooklyn direction)
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
BG_COLOR        = "#0A0E1A"
PANEL_BG        = "#111827"
HEADER_COLOR    = "#1E2A40"
TEXT_PRIMARY    = "#F0F4FF"
TEXT_SECONDARY  = "#8896B0"
ACCENT_COLOR    = "#3B82F6"
BORDER_COLOR    = "#1E2A3D"
GREEN_COLOR     = "#22C55E"
AMBER_COLOR     = "#F59E0B"
RED_COLOR       = "#EF4444"

# ── App ─────────────────────────────────────────────────────────────────────────
class TraintimeApp:
    def __init__(self, root):
        self.root = root
        self.root.title("TrainTime — Union St.")
        self.root.configure(bg=BG_COLOR)
        if FULLSCREEN:
            self.root.attributes("-fullscreen", True)
        else:
            self.root.geometry("800x480") # Default window size
        self.root.bind("<Escape>", lambda e: self.root.destroy())
        self.root.bind("<F11>",    lambda e: self.root.attributes("-fullscreen",
                                         not self.root.attributes("-fullscreen")))

        self.trains = []
        self.last_updated = None
        self.status_msg = "Connecting…"
        self.is_error = False
        self.consecutive_errors = 0
        self.lock = threading.Lock()

        self._build_ui()
        self._start_refresh_thread()

    # ── UI Build ────────────────────────────────────────────────────────────────
    def _build_ui(self):
        if FULLSCREEN:
            sw = self.root.winfo_screenwidth()
            sh = self.root.winfo_screenheight()
        else:
            sw = 800
            sh = 480

        # Fonts — pick sizes based on screen width
        # Increased scaling factor by 1.8x to make fonts and UI elements much bigger
        scale = max(0.5, sw / 1280) * 1.8
        self.scale = scale
        self.fnt_title   = tkfont.Font(family="DejaVu Sans", size=int(24*scale), weight="bold")
        self.fnt_sub     = tkfont.Font(family="DejaVu Sans", size=int(12*scale))
        self.fnt_header  = tkfont.Font(family="DejaVu Sans", size=int(11*scale), weight="bold")
        self.fnt_route   = tkfont.Font(family="DejaVu Sans", size=int(14*scale), weight="bold")
        self.fnt_time    = tkfont.Font(family="DejaVu Sans", size=int(16*scale), weight="bold")
        self.fnt_min     = tkfont.Font(family="DejaVu Sans", size=int(11*scale))
        self.fnt_dest    = tkfont.Font(family="DejaVu Sans", size=int(13*scale))
        self.fnt_status  = tkfont.Font(family="DejaVu Sans", size=int(10*scale))
        self.fnt_message = tkfont.Font(family="DejaVu Sans", size=int(18*scale))

        # ── Header bar ──────────────────────────────────────────────────────────
        header = tk.Frame(self.root, bg=HEADER_COLOR, pady=int(4*scale))
        header.pack(fill="x")

        left = tk.Frame(header, bg=HEADER_COLOR)
        left.pack(side="left", padx=int(16*scale))

        tk.Label(left, text="MTA TrainTime", font=self.fnt_title,
                 bg=HEADER_COLOR, fg=TEXT_PRIMARY).pack(anchor="w")
        tk.Label(left, text=f"{BOROUGH} · R train", font=self.fnt_sub,
                 bg=HEADER_COLOR, fg=TEXT_SECONDARY).pack(anchor="w")

        right = tk.Frame(header, bg=HEADER_COLOR)
        right.pack(side="right", padx=int(16*scale))

        self.clock_label = tk.Label(right, text="", font=self.fnt_time,
                                    bg=HEADER_COLOR, fg=TEXT_PRIMARY)
        self.clock_label.pack(anchor="e")
        self.status_label = tk.Label(right, text="", font=self.fnt_status,
                                     bg=HEADER_COLOR, fg=TEXT_SECONDARY)
        self.status_label.pack(anchor="e")

        # ── Column headers ───────────────────────────────────────────────────────
        col_frame = tk.Frame(self.root, bg=PANEL_BG, pady=int(2*scale))
        col_frame.pack(fill="x", padx=int(16*scale), pady=(int(4*scale), 0))

        col_frame.columnconfigure(0, minsize=int(40*scale))   # route badge
        col_frame.columnconfigure(1, weight=1)                # station AND destination
        col_frame.columnconfigure(2, minsize=int(130*scale))  # direction (wider)
        col_frame.columnconfigure(3, minsize=int(120*scale))  # time

        headers = [("", 0), ("Station / Destination", 1), ("Dir.", 2), ("", 3)]
        anchors = ["center",  "w",  "center", "e"]
        for text, col in headers:
            tk.Label(col_frame, text=text, font=self.fnt_header,
                     bg=PANEL_BG, fg=TEXT_SECONDARY, padx=int(8*scale),
                     anchor=anchors[col]).grid(row=0, column=col, sticky="ew")

        # Separator
        sep = tk.Frame(self.root, bg=BORDER_COLOR, height=1)
        sep.pack(fill="x", padx=int(16*scale))

        # ── Train rows container ─────────────────────────────────────────────────
        self.rows_frame = tk.Frame(self.root, bg=BG_COLOR)
        self.rows_frame.pack(fill="both", expand=True, padx=int(16*scale),
                             pady=(int(2*scale), int(4*scale)))
        for c in [0, 1, 2, 3]:
            self.rows_frame.columnconfigure(c, weight=(0 if c in [0,2,3] else 1))
        self.rows_frame.columnconfigure(0, minsize=int(60*scale))
        self.rows_frame.columnconfigure(2, minsize=int(80*scale))
        self.rows_frame.columnconfigure(3, minsize=int(120*scale))

        # Center message label (for loading / error / no trains)
        self.center_message = tk.Label(self.rows_frame, text="", font=self.fnt_message,
                                       bg=BG_COLOR, fg=TEXT_SECONDARY, anchor="center")

        # Pre-create row label sets (reuse, don't destroy/recreate every tick)
        self._row_widgets = []
        for i in range(MAX_TRAINS):
            bg = BG_COLOR if i % 2 == 0 else PANEL_BG
            row = {}

            # Route badge (Canvas circle)
            badge_canvas = tk.Canvas(self.rows_frame, width=int(28*scale),
                                     height=int(28*scale), bg=bg,
                                     highlightthickness=0, bd=0)
            badge_canvas.grid(row=i, column=0, sticky="nsew",
                              pady=int(4*scale), padx=int(8*scale))
            row["badge_canvas"] = badge_canvas
            row["badge_bg"]     = bg

            # Station / Dest block
            dest_frame = tk.Frame(self.rows_frame, bg=bg)
            dest_frame.grid(row=i, column=1, sticky="w", padx=int(8*scale))
            sta_lbl = tk.Label(dest_frame, text="", font=self.fnt_dest, bg=bg, fg="#93C5FD")
            sta_lbl.pack(side="top", anchor="w")
            dest_lbl = tk.Label(dest_frame, text="", font=self.fnt_min, bg=bg, fg=TEXT_PRIMARY)
            dest_lbl.pack(side="top", anchor="w")
            row["sta"]  = sta_lbl
            row["dest"] = dest_lbl

            # Direction
            dir_lbl = tk.Label(self.rows_frame, text="", font=self.fnt_status,
                               bg=bg, fg=TEXT_SECONDARY, anchor="center")
            dir_lbl.grid(row=i, column=2, sticky="ew")
            row["dir"] = dir_lbl

            # Arrival time
            time_frame = tk.Frame(self.rows_frame, bg=bg)
            time_frame.grid(row=i, column=3, sticky="ew", padx=int(8*scale))
            mins_lbl = tk.Label(time_frame, text="", font=self.fnt_time,
                                bg=bg, anchor="e")
            mins_lbl.pack(side="right")
            mins_unit = tk.Label(time_frame, text="", font=self.fnt_status,
                                 bg=bg, fg=TEXT_SECONDARY, anchor="e")
            mins_unit.pack(side="right", padx=(0, int(3*scale)))
            row["mins"]      = mins_lbl
            row["mins_unit"] = mins_unit

            self._row_widgets.append(row)
        # No footer for RPi display to save space
        
        # Show loading state on startup
        self._show_center_message("🔄  Connecting to MTA…")

        self._tick_clock()

    # ── Center Message ───────────────────────────────────────────────────────────
    def _show_center_message(self, text, color=None):
        """Show a centered message and hide all train rows."""
        for row in self._row_widgets:
            row["badge_canvas"].grid_remove()
            row["sta"].master.grid_remove()
            row["dir"].grid_remove()
            row["mins"].pack_forget()
            row["mins_unit"].pack_forget()
            row["mins"].master.grid_remove()
        self.center_message.config(text=text, fg=color or TEXT_SECONDARY)
        self.center_message.place(relx=0.5, rely=0.4, anchor="center")

    def _hide_center_message(self):
        """Hide the center message and restore train row grid structure."""
        self.center_message.place_forget()
        sc = self.scale
        for i, row in enumerate(self._row_widgets):
            row["badge_canvas"].grid(row=i, column=0, sticky="nsew",
                                     pady=int(4*sc), padx=int(8*sc))
            row["sta"].master.grid(row=i, column=1, sticky="w", padx=int(8*sc))
            row["dir"].grid(row=i, column=2, sticky="ew")
            row["mins"].master.grid(row=i, column=3, sticky="ew", padx=int(8*sc))
            row["mins"].pack(side="right")
            row["mins_unit"].pack(side="right", padx=(0, int(3*sc)))

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
            self.status_label.config(text=f"Updated {age}s ago", fg=TEXT_SECONDARY)
        elif is_err:
            self.status_label.config(text=f"⚠ {msg}", fg=AMBER_COLOR)
        else:
            self.status_label.config(text=msg, fg=TEXT_SECONDARY)

        self.root.after(1000, self._tick_clock)

    # ── Data Fetching (background thread) ────────────────────────────────────────
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
                    self.status_msg = f"Retrying… ({self.consecutive_errors})"

                # Show error in UI but keep any stale data visible
                self.root.after(0, self._update_ui)

                # Exponential backoff: 5, 10, 20, 40, 80, 120, 120, ...
                delay = min(RETRY_BASE_SECS * (2 ** (self.consecutive_errors - 1)),
                            RETRY_MAX_SECS)
                print(f"[TrainTime] Error fetching data (attempt {self.consecutive_errors}): {e}")
                traceback.print_exc()
                time.sleep(delay)

    def _fetch_trains(self):
        now_ts = datetime.now().timestamp()
        arrivals_by_station = {s: [] for s in STATIONS.keys()}
        
        for feed_id in FEED_IDS:
            try:
                feed = NYCTFeed(feed_id)
            except Exception as e:
                print(f"[TrainTime] Error fetching feed {feed_id}: {e}")
                continue
                
            for trip in feed.trips:
                for stop_time in trip.stop_time_updates:
                    stop_base = stop_time.stop_id[:-1] if stop_time.stop_id and len(stop_time.stop_id) > 1 else ""
                    if stop_base in STATIONS:
                        direction = stop_time.stop_id[-1] if stop_time.stop_id[-1] in ("N", "S") else "?"
                        arrival_ts = stop_time.arrival or stop_time.departure
                        if arrival_ts is None:
                            continue
                        if hasattr(arrival_ts, "timestamp"):
                            arr_epoch = arrival_ts.timestamp()
                        else:
                            arr_epoch = float(arrival_ts)
                        mins_away = (arr_epoch - now_ts) / 60
                        if mins_away < -0.5:  # already departed
                            continue
                        route = trip.route_id
                        dest = getattr(trip, 'headsign_text', None) \
                            or getattr(trip, 'nyc_train_id', None) \
                            or "Unknown"
                        arrivals_by_station[stop_base].append({
                            "station":   STATIONS[stop_base],
                            "route":     route,
                            "dest":      dest,
                            "direction": direction,
                            "mins":      mins_away,
                            "epoch":     arr_epoch,
                        })

        # Combine
        combined_arrivals = []
        for s in STATIONS.keys():
            st_arr = arrivals_by_station[s]
            st_arr.sort(key=lambda x: x["mins"])
            combined_arrivals.extend(st_arr[:TRAINS_PER_STATION])
            
        # Optional: master sort by time, or leave grouped by station. We will leave grouped by station!
        # combined_arrivals.sort(key=lambda x: x["mins"])

        with self.lock:
            self.trains = combined_arrivals
            self.last_updated = datetime.now()
            self.status_msg = "Live"

    # ── UI Update (main thread) ───────────────────────────────────────────────────
    def _update_ui(self):
        with self.lock:
            trains = list(self.trains)
            last   = self.last_updated
            is_err = self.is_error
            err_count = self.consecutive_errors

        count = len(trains)

        if count == 0 and last is None and not is_err:
            # Still loading for the first time
            self._show_center_message("🔄  Connecting to MTA…")
            return
        elif count == 0 and is_err and last is None:
            # Never successfully loaded — show error
            self._show_center_message("⚠  Can't reach MTA feed\nRetrying…", RED_COLOR)
            return
        elif count == 0 and not is_err:
            # Successfully fetched but no trains
            self._show_center_message("No trains scheduled")
            return

        # We have data to show — hide center message
        self._hide_center_message()

        sc = self.scale
        for i, row in enumerate(self._row_widgets):
            if i < count:
                t = trains[i]
                mins  = t["mins"]
                route = t["route"]

                # Badge (smaller)
                c = row["badge_canvas"]
                c.delete("all")
                color      = ROUTE_COLORS.get(route, "#666")
                text_color = ROUTE_TEXT_COLORS.get(route, "#000")
                c.create_oval(0, 0, int(28*sc), int(28*sc), fill=color, outline="")
                c.create_text(int(14*sc), int(14*sc), text=route,
                              font=self.fnt_route, fill=text_color)

                # Station and Destination
                row["sta"].config(text=t["station"])
                
                dest = t["dest"]
                if len(dest) > 24:
                    dest = dest[:22] + "…"
                row["dest"].config(text="to " + dest)

                # Direction (colored)
                dir_text = DIRECTION_LABELS.get(t["direction"], t["direction"])
                dir_color = DIR_COLORS.get(t["direction"], TEXT_SECONDARY)
                row["dir"].config(text=dir_text, fg=dir_color)

                # Minutes
                if mins < 1:
                    row["mins"].config(text="Now", fg=GREEN_COLOR)
                    row["mins_unit"].config(text="")
                elif mins < 2:
                    row["mins"].config(text="1", fg=AMBER_COLOR)
                    row["mins_unit"].config(text="min")
                elif mins > 60:
                    t_obj = datetime.fromtimestamp(t["epoch"])
                    row["mins"].config(text=t_obj.strftime("%I:%M").lstrip("0"), fg=TEXT_PRIMARY)
                    row["mins_unit"].config(text="")
                else:
                    c = GREEN_COLOR if mins > 5 else (AMBER_COLOR if mins > 2 else RED_COLOR)
                    row["mins"].config(text=str(int(mins)), fg=c)
                    row["mins_unit"].config(text="min")
            else:
                # Hide unused rows
                c = row["badge_canvas"]
                c.delete("all")
                row["sta"].config(text="")
                row["dest"].config(text="")
                row["dir"].config(text="")
                row["mins"].config(text="")
                row["mins_unit"].config(text="")
        # Update status in header instead of deleted footer
        if last and is_err:
            with self.lock:
                self.status_msg = f"⚠ Connection lost (retrying…) · Showing data from {last.strftime('%I:%M %p').lstrip('0')}"


# ── Entry Point ──────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    root = tk.Tk()
    app  = TraintimeApp(root)
    root.mainloop()
