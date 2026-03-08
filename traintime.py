"""
traintime.py — MTA Train Schedule Display for Union St. (R32)
Designed for Raspberry Pi. Fullscreen tkinter UI with live GTFS-RT data.
"""

import tkinter as tk
from tkinter import font as tkfont
import threading
import time
from datetime import datetime

try:
    from nyct_gtfs import NYCTFeed
except ImportError:
    print("ERROR: nyct-gtfs not installed. Run: pip3 install nyct-gtfs --break-system-packages")
    raise

# ── Configuration ──────────────────────────────────────────────────────────────
STATION_STOP_ID = "R32"          # Union St, Brooklyn (R train)
STATION_NAME    = "Union St"
BOROUGH         = "Brooklyn"
FEED_ID         = "nqrw"         # MTA feed for N/Q/R/W trains
MAX_TRAINS      = 8              # rows to display
REFRESH_SECS    = 30             # how often to poll the API

# Direction labels
DIRECTION_LABELS = {
    "N": "↑ Manhattan / Queens",
    "S": "↓ Bay Ridge"
}

# Route colors (MTA official)
ROUTE_COLORS = {
    "R": "#FCCC0A",  # Yellow (BMT Broadway)
    "N": "#FCCC0A",
    "Q": "#FCCC0A",
    "W": "#FCCC0A",
    "D": "#FF6319",
}
ROUTE_TEXT_COLORS = {
    "R": "#000000",
    "N": "#000000",
    "Q": "#000000",
    "W": "#000000",
    "D": "#FFFFFF",
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
        self.root.attributes("-fullscreen", True)
        self.root.bind("<Escape>", lambda e: self.root.destroy())
        self.root.bind("<F11>",    lambda e: self.root.attributes("-fullscreen",
                                         not self.root.attributes("-fullscreen")))

        self.trains = []
        self.last_updated = None
        self.status_msg = "Loading…"
        self.lock = threading.Lock()

        self._build_ui()
        self._start_refresh_thread()

    # ── UI Build ────────────────────────────────────────────────────────────────
    def _build_ui(self):
        sw = self.root.winfo_screenwidth()
        sh = self.root.winfo_screenheight()

        # Fonts — pick sizes based on screen width
        scale = max(0.5, sw / 1280)
        self.fnt_title   = tkfont.Font(family="DejaVu Sans", size=int(24*scale), weight="bold")
        self.fnt_sub     = tkfont.Font(family="DejaVu Sans", size=int(12*scale))
        self.fnt_header  = tkfont.Font(family="DejaVu Sans", size=int(11*scale), weight="bold")
        self.fnt_route   = tkfont.Font(family="DejaVu Sans", size=int(14*scale), weight="bold")
        self.fnt_time    = tkfont.Font(family="DejaVu Sans", size=int(16*scale), weight="bold")
        self.fnt_min     = tkfont.Font(family="DejaVu Sans", size=int(11*scale))
        self.fnt_dest    = tkfont.Font(family="DejaVu Sans", size=int(13*scale))
        self.fnt_status  = tkfont.Font(family="DejaVu Sans", size=int(10*scale))

        # ── Header bar ──────────────────────────────────────────────────────────
        header = tk.Frame(self.root, bg=HEADER_COLOR, pady=int(12*scale))
        header.pack(fill="x")

        left = tk.Frame(header, bg=HEADER_COLOR)
        left.pack(side="left", padx=int(24*scale))

        tk.Label(left, text=STATION_NAME, font=self.fnt_title,
                 bg=HEADER_COLOR, fg=TEXT_PRIMARY).pack(anchor="w")
        tk.Label(left, text=f"{BOROUGH} · R train", font=self.fnt_sub,
                 bg=HEADER_COLOR, fg=TEXT_SECONDARY).pack(anchor="w")

        right = tk.Frame(header, bg=HEADER_COLOR)
        right.pack(side="right", padx=int(24*scale))

        self.clock_label = tk.Label(right, text="", font=self.fnt_time,
                                    bg=HEADER_COLOR, fg=TEXT_PRIMARY)
        self.clock_label.pack(anchor="e")
        self.status_label = tk.Label(right, text="", font=self.fnt_status,
                                     bg=HEADER_COLOR, fg=TEXT_SECONDARY)
        self.status_label.pack(anchor="e")

        # ── Column headers ───────────────────────────────────────────────────────
        col_frame = tk.Frame(self.root, bg=PANEL_BG, pady=int(6*scale))
        col_frame.pack(fill="x", padx=int(16*scale), pady=(int(10*scale), 0))

        col_frame.columnconfigure(0, minsize=int(60*scale))   # route badge
        col_frame.columnconfigure(1, weight=1)                # destination
        col_frame.columnconfigure(2, minsize=int(80*scale))   # direction
        col_frame.columnconfigure(3, minsize=int(120*scale))  # time

        headers = [("", 0), ("Destination", 1), ("Dir.", 2), ("Arrives", 3)]
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
                             pady=(int(4*scale), int(8*scale)))
        for c in [0, 1, 2, 3]:
            self.rows_frame.columnconfigure(c, weight=(0 if c in [0,2,3] else 1))
        self.rows_frame.columnconfigure(0, minsize=int(60*scale))
        self.rows_frame.columnconfigure(2, minsize=int(80*scale))
        self.rows_frame.columnconfigure(3, minsize=int(120*scale))

        # Pre-create row label sets (reuse, don't destroy/recreate every tick)
        self._row_widgets = []
        for i in range(MAX_TRAINS):
            bg = BG_COLOR if i % 2 == 0 else PANEL_BG
            row = {}

            # Route badge (Canvas circle)
            badge_canvas = tk.Canvas(self.rows_frame, width=int(40*scale),
                                     height=int(40*scale), bg=bg,
                                     highlightthickness=0, bd=0)
            badge_canvas.grid(row=i, column=0, sticky="nsew",
                              pady=int(3*scale), padx=int(8*scale))
            row["badge_canvas"] = badge_canvas
            row["badge_scale"]  = scale
            row["badge_bg"]     = bg

            # Destination
            dest_lbl = tk.Label(self.rows_frame, text="", font=self.fnt_dest,
                                bg=bg, fg=TEXT_PRIMARY, anchor="w", padx=int(8*scale))
            dest_lbl.grid(row=i, column=1, sticky="ew")
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

        # ── Footer ───────────────────────────────────────────────────────────────
        footer = tk.Frame(self.root, bg=HEADER_COLOR, pady=int(6*scale))
        footer.pack(fill="x", side="bottom")
        self.footer_label = tk.Label(footer, text="", font=self.fnt_status,
                                     bg=HEADER_COLOR, fg=TEXT_SECONDARY)
        self.footer_label.pack()

        self._tick_clock()

    # ── Clock ────────────────────────────────────────────────────────────────────
    def _tick_clock(self):
        now = datetime.now()
        self.clock_label.config(text=now.strftime("%I:%M:%S %p").lstrip("0"))
        if self.last_updated:
            age = int((now - self.last_updated).total_seconds())
            self.status_label.config(text=f"Updated {age}s ago")
        else:
            self.status_label.config(text=self.status_msg)
        self.root.after(1000, self._tick_clock)

    # ── Data Fetching (background thread) ────────────────────────────────────────
    def _start_refresh_thread(self):
        t = threading.Thread(target=self._refresh_loop, daemon=True)
        t.start()

    def _refresh_loop(self):
        while True:
            try:
                self._fetch_trains()
            except Exception as e:
                with self.lock:
                    self.status_msg = f"Error: {e}"
            self.root.after(0, self._update_ui)
            time.sleep(REFRESH_SECS)

    def _fetch_trains(self):
        feed = NYCTFeed(FEED_ID)
        now_ts = datetime.now().timestamp()

        arrivals = []
        for trip in feed.trips:
            for stop_time in trip.stop_time_updates:
                if stop_time.stop_id.startswith(STATION_STOP_ID):
                    direction = stop_time.stop_id[-1] if stop_time.stop_id[-1] in ("N", "S") else "?"
                    arrival_ts = stop_time.arrival or stop_time.departure
                    if arrival_ts is None:
                        continue
                    # arrival_ts is a datetime object
                    if hasattr(arrival_ts, "timestamp"):
                        arr_epoch = arrival_ts.timestamp()
                    else:
                        arr_epoch = float(arrival_ts)
                    mins_away = (arr_epoch - now_ts) / 60
                    if mins_away < -0.5:  # already departed
                        continue
                    route = trip.route_id
                    dest  = trip.trip.headsign or trip.nyct_trip_descriptor.train_id or "Unknown"
                    arrivals.append({
                        "route":     route,
                        "dest":      dest,
                        "direction": direction,
                        "mins":      mins_away,
                        "epoch":     arr_epoch,
                    })

        arrivals.sort(key=lambda x: x["mins"])

        with self.lock:
            self.trains = arrivals[:MAX_TRAINS]
            self.last_updated = datetime.now()
            self.status_msg = "Live"

    # ── UI Update (main thread) ───────────────────────────────────────────────────
    def _update_ui(self):
        with self.lock:
            trains = list(self.trains)
            last   = self.last_updated

        count = len(trains)

        for i, row in enumerate(self._row_widgets):
            if i < count:
                t = trains[i]
                mins  = t["mins"]
                route = t["route"]

                # Badge
                c = row["badge_canvas"]
                sc = row["badge_scale"]
                c.delete("all")
                color      = ROUTE_COLORS.get(route, "#666")
                text_color = ROUTE_TEXT_COLORS.get(route, "#000")
                pad = int(4*sc)
                c.create_oval(pad, pad, int(40*sc)-pad, int(40*sc)-pad, fill=color, outline="")
                c.create_text(int(20*sc), int(20*sc), text=route,
                              font=self.fnt_route, fill=text_color)

                # Destination
                dest = t["dest"]
                if len(dest) > 28:
                    dest = dest[:26] + "…"
                row["dest"].config(text=dest, fg=TEXT_PRIMARY)

                # Direction
                dir_text = DIRECTION_LABELS.get(t["direction"], t["direction"])
                row["dir"].config(text=dir_text)

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
                    color = GREEN_COLOR if mins > 5 else (AMBER_COLOR if mins > 2 else RED_COLOR)
                    row["mins"].config(text=str(int(mins)), fg=color)
                    row["mins_unit"].config(text="min")

                # Show row
                for widget in [row["dest"], row["dir"], row["mins"], row["mins_unit"]]:
                    widget.grid()
                row["badge_canvas"].grid()
            else:
                # Hide unused rows
                c = row["badge_canvas"]
                c.delete("all")
                row["dest"].config(text="")
                row["dir"].config(text="")
                row["mins"].config(text="")
                row["mins_unit"].config(text="")

        if last:
            self.footer_label.config(
                text=f"MTA GTFS-RT · Union St (R32) · Refreshes every {REFRESH_SECS}s · ESC to quit"
            )


# ── Entry Point ──────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    root = tk.Tk()
    app  = TraintimeApp(root)
    root.mainloop()
