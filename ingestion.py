import threading
import time
import json
from websocket import WebSocketApp
from collections import deque
from datetime import datetime, timezone
import traceback

from firebase_ticks import FirebaseTickStore


class Ingestor:
    def __init__(self, storage, max_buffer=20000):
        self.storage = storage
        self.threads = []
        self.ws_clients = []
        self.running = False
        self.firebase_store = FirebaseTickStore()

    def _ws_thread(self, symbol):
        url = f"wss://fstream.binance.com/ws/{symbol}@trade"

        def on_message(ws, message):
            try:
                j = json.loads(message)
                if j.get("e") == "trade":
                    ts = int(j.get("T", j.get("E", 0)))
                    price = float(j.get("p", 0.0))
                    qty = float(j.get("q", 0.0))
                    sym = j.get("s", symbol).lower()
                    t = datetime.fromtimestamp(ts / 1000.0, tz=timezone.utc)
                    ts_iso = t.isoformat()
                    self.storage.insert_tick(sym, ts_iso, price, qty)
                    if self.firebase_store is not None:
                        self.firebase_store.insert_tick(sym, ts_iso, price, qty)
            except:
                traceback.print_exc()

        def on_error(ws, err):
            pass

        def on_close(ws, code, reason):
            pass

        def on_open(ws):
            pass

        ws = WebSocketApp(
            url,
            on_message=on_message,
            on_error=on_error,
            on_close=on_close,
            on_open=on_open,
        )
        self.ws_clients.append(ws)
        while self.running:
            try:
                ws.run_forever(ping_interval=20, ping_timeout=10)
            except:
                time.sleep(1)

    def start(self, symbols):
        self.stop()
        self.running = True
        for s in symbols:
            t = threading.Thread(target=self._ws_thread, args=(s,), daemon=True)
            t.start()
            self.threads.append(t)

    def stop(self):
        self.running = False
        try:
            for ws in self.ws_clients:
                try:
                    ws.close()
                except:
                    pass
        except:
            pass
        self.ws_clients = []
        self.threads = []
