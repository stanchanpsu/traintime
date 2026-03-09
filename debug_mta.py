import time
from datetime import datetime
try:
    from nyct_gtfs import NYCTFeed
except ImportError:
    print("nyct-gtfs not found. Use pip to install.")
    exit(1)

STATIONS = {"R32": "Union St", "F23": "4 Av - 9 St"}
# We'll test if individual route letters work or if we need specific feed IDs
TEST_FEEDS = ["R", "F", "G"]

def run_debug():
    print(f"DEBUG: Starting MTA feed test at {datetime.now()}")
    now_ts = datetime.now().timestamp()
    
    found_any = False
    for feed_id in TEST_FEEDS:
        print(f"\n--- Checking Feed: {feed_id} ---")
        try:
            feed = NYCTFeed(feed_id)
            print(f"Feed fetched. Last generated: {getattr(feed, 'last_generated', 'Unknown')}")
            
            match_count = 0
            for trip in feed.trips:
                for stop_time in trip.stop_time_updates:
                    # stop_id is usually e.g. 'R32N'
                    stop_base = stop_time.stop_id[:-1] if stop_time.stop_id else ""
                    if stop_base in STATIONS:
                        match_count += 1
                        found_any = True
                        arrival_ts = stop_time.arrival or stop_time.departure
                        if arrival_ts:
                            arr_epoch = arrival_ts.timestamp()
                            mins = (arr_epoch - now_ts) / 60
                            print(f" MATCH: Route {trip.route_id} at {STATIONS[stop_base]} ({stop_time.stop_id}) in {mins:.1f} mins")
            
            if match_count == 0:
                print(" No matches found in this feed for current stations.")
            else:
                print(f" Found {match_count} station matches.")
                
        except Exception as e:
            print(f" Error fetching feed {feed_id}: {e}")

if __name__ == "__main__":
    run_debug()
