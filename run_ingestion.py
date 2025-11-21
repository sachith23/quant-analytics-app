# run_ingestion.py
import time
import signal
import sys
from storage import Storage
from ingestion import Ingestor

# Symbols to ingest (comma-separated). Adjust if you want different symbols.
SYMBOLS = ["btcusdt", "ethusdt"]

def main():
    storage = Storage("ticks.sqlite")   # uses the same DB file as your app
    ingestor = Ingestor(storage=storage)
    ingestor.start(SYMBOLS)
    print(f"Started ingestion for: {', '.join(SYMBOLS)}. Press Ctrl+C to stop.")

    # Keep the script alive until interrupted
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("Stopping ingestion...")
        ingestor.stop()
        print("Stopped.")
        sys.exit(0)

if __name__ == "__main__":
    main()
