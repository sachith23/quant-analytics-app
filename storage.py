# storage.py – SQLite Storage + FirebaseStorage backend (choose in app.py)

import pandas as pd
from datetime import datetime, timedelta, timezone

# --- Optional SQLite backend (kept for local-only mode) ---
import sqlite3

class Storage:
    def __init__(self, db_path="ticks.sqlite"):
        self.db_path = db_path
        self._init_db()

    def _connect(self):
        return sqlite3.connect(self.db_path, check_same_thread=False)

    def _init_db(self):
        con = self._connect()
        cur = con.cursor()
        # raw ticks table (from WebSocket ingestion)
        cur.execute("""
            CREATE TABLE IF NOT EXISTS ticks (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                symbol TEXT,
                ts TEXT,
                price REAL,
                qty REAL
            )
        """)
        cur.execute("CREATE INDEX IF NOT EXISTS idx_ticks_symbol_ts ON ticks(symbol, ts)")

        # OHLC table (for uploaded bars or externally provided candles)
        cur.execute("""
            CREATE TABLE IF NOT EXISTS ohlc (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                symbol TEXT,
                ts TEXT,
                open REAL,
                high REAL,
                low REAL,
                close REAL,
                volume REAL
            )
        """)
        cur.execute("CREATE INDEX IF NOT EXISTS idx_ohlc_symbol_ts ON ohlc(symbol, ts)")

        con.commit()
        con.close()

    # ---------- Insertion helpers with validation ----------
    def insert_tick(self, symbol, ts_iso, price, qty):
        if price <= 0 or qty < 0:
            return
        con = self._connect()
        cur = con.cursor()
        try:
            cur.execute(
                "INSERT INTO ticks(symbol, ts, price, qty) VALUES (?, ?, ?, ?)",
                (symbol, ts_iso, float(price), float(qty))
            )
            con.commit()
        except Exception as e:
            print(f"Error inserting tick: {e}")
        finally:
            con.close()

    def insert_tick_iso(self, symbol, dt_obj, price, qty):
        if dt_obj.tzinfo is None:
            dt_obj = dt_obj.replace(tzinfo=timezone.utc)
        dt_norm = dt_obj.astimezone(timezone.utc).isoformat(timespec='microseconds')
        self.insert_tick(symbol, dt_norm, price, qty)

    def insert_ohlc_bar(self, symbol, dt_obj, o, h, l, c, v):
        try:
            o, h, l, c, v = float(o), float(h), float(l), float(c), float(v)
            if o <= 0 or h <= 0 or l <= 0 or c <= 0:
                return
            if h < max(o, c) or l > min(o, c):
                h = max(o, h, l, c)
                l = min(o, h, l, c)
            if v < 0:
                v = 0.0
        except (ValueError, TypeError):
            return

        if dt_obj.tzinfo is None:
            dt_obj = dt_obj.replace(tzinfo=timezone.utc)
        dt_norm = dt_obj.astimezone(timezone.utc).isoformat(timespec='microseconds')

        con = self._connect()
        cur = con.cursor()
        try:
            cur.execute(
                "INSERT INTO ohlc(symbol, ts, open, high, low, close, volume) VALUES (?, ?, ?, ?, ?, ?, ?)",
                (symbol, dt_norm, o, h, l, c, v)
            )
            con.commit()
        except Exception as e:
            print(f"Error inserting OHLC: {e}")
        finally:
            con.close()

    # ---------- Fetch helpers with validation ----------
    def fetch_recent_ticks(self, minutes=60):
        since = datetime.utcnow().replace(tzinfo=timezone.utc) - timedelta(minutes=minutes)
        since_iso = since.isoformat()
        con = self._connect()
        df = pd.read_sql_query(
            "SELECT symbol, ts, price, qty FROM ticks WHERE ts >= ? ORDER BY ts ASC",
            con, params=(since_iso,)
        )
        con.close()

        if df.empty:
            return df

        df['ts'] = pd.to_datetime(df['ts'], utc=True, errors='coerce')
        df = df.dropna(subset=['ts'])
        if df.empty:
            return pd.DataFrame()

        df['price'] = pd.to_numeric(df['price'], errors='coerce')
        df['qty'] = pd.to_numeric(df['qty'], errors='coerce')
        df = df[(df['price'] > 0) & (df['qty'] >= 0)]
        df = df.dropna(subset=['price', 'qty'])
        if df.empty:
            return pd.DataFrame()

        df = df.set_index('ts').sort_index()
        return df

    def fetch_recent_ohlc(self, minutes=60):
        since = datetime.utcnow().replace(tzinfo=timezone.utc) - timedelta(minutes=minutes)
        since_iso = since.isoformat()
        con = self._connect()
        df = pd.read_sql_query(
            "SELECT symbol, ts, open, high, low, close, volume "
            "FROM ohlc WHERE ts >= ? ORDER BY ts ASC",
            con, params=(since_iso,)
        )
        con.close()

        if df.empty:
            return df

        df['ts'] = pd.to_datetime(df['ts'], utc=True, errors='coerce')
        df = df.dropna(subset=['ts'])
        if df.empty:
            return pd.DataFrame()

        for col in ['open', 'high', 'low', 'close', 'volume']:
            df[col] = pd.to_numeric(df[col], errors='coerce')

        df = df[(df['open'] > 0) & (df['high'] > 0) &
                (df['low'] > 0) & (df['close'] > 0)]
        df = df.dropna(subset=['close'])
        if df.empty:
            return pd.DataFrame()

        df['high'] = df[['open', 'high', 'low', 'close']].max(axis=1)
        df['low'] = df[['open', 'high', 'low', 'close']].min(axis=1)

        df = df.set_index('ts').sort_index()
        return df

    def count_rows(self):
        con = self._connect()
        cur = con.cursor()
        cur.execute("SELECT COUNT(*) FROM ticks")
        n = cur.fetchone()[0]
        con.close()
        return n

    def last_timestamp(self):
        con = self._connect()
        cur = con.cursor()
        cur.execute("SELECT ts FROM ticks ORDER BY ts DESC LIMIT 1")
        r = cur.fetchone()
        con.close()
        return r[0] if r else None


# --- Firebase-based backend (option C) ---

try:
    import firebase_admin
    from firebase_admin import credentials, db
except ImportError:
    firebase_admin = None


class FirebaseStorage:
    """
    Firebase Realtime Database backend with the SAME interface as Storage.
    Structure in RTDB (under root):
      root/
        ticks/{autoid: {symbol, ts, price, qty}}
        ohlc/{autoid: {symbol, ts, open, high, low, close, volume}}
    """

    def __init__(self, database_url, service_account_path, root="quant_live"):
        if firebase_admin is None:
            raise ImportError(
                "firebase_admin not installed. Run: pip install firebase-admin"
            )

        if not firebase_admin._apps:
            cred = credentials.Certificate(service_account_path)
            firebase_admin.initialize_app(cred, {"databaseURL": database_url})

        self.root = root
        self.ticks_ref = db.reference(f"{root}/ticks")
        self.ohlc_ref = db.reference(f"{root}/ohlc")

    # ---------- Insert ----------
    def insert_tick(self, symbol, ts_iso, price, qty):
        if price <= 0 or qty < 0:
            return
        try:
            self.ticks_ref.push({
                "symbol": str(symbol).lower(),
                "ts": ts_iso,
                "price": float(price),
                "qty": float(qty),
            })
        except Exception as e:
            print(f"[FirebaseStorage] Error inserting tick: {e}")

    def insert_tick_iso(self, symbol, dt_obj, price, qty):
        if dt_obj.tzinfo is None:
            dt_obj = dt_obj.replace(tzinfo=timezone.utc)
        dt_norm = dt_obj.astimezone(timezone.utc).isoformat(timespec='microseconds')
        self.insert_tick(symbol, dt_norm, price, qty)

    def insert_ohlc_bar(self, symbol, dt_obj, o, h, l, c, v):
        try:
            o, h, l, c, v = float(o), float(h), float(l), float(c), float(v)
            if o <= 0 or h <= 0 or l <= 0 or c <= 0:
                return
            if h < max(o, c) or l > min(o, c):
                h = max(o, h, l, c)
                l = min(o, h, l, c)
            if v < 0:
                v = 0.0
        except (ValueError, TypeError):
            return

        if dt_obj.tzinfo is None:
            dt_obj = dt_obj.replace(tzinfo=timezone.utc)
        dt_norm = dt_obj.astimezone(timezone.utc).isoformat(timespec='microseconds')

        try:
            self.ohlc_ref.push({
                "symbol": str(symbol).lower(),
                "ts": dt_norm,
                "open": o,
                "high": h,
                "low": l,
                "close": c,
                "volume": v,
            })
        except Exception as e:
            print(f"[FirebaseStorage] Error inserting OHLC: {e}")

    # ---------- Fetch ----------
    def fetch_recent_ticks(self, minutes=60):
        since = datetime.utcnow().replace(tzinfo=timezone.utc) - timedelta(minutes=minutes)
        since_iso = since.isoformat()

        try:
            snap = (
                self.ticks_ref
                .order_by_child("ts")
                .start_at(since_iso)
                .get()
            )
        except Exception as e:
            print(f"[FirebaseStorage] Error fetching ticks: {e}")
            return pd.DataFrame()

        if not snap:
            return pd.DataFrame()

        rows = []
        for _, v in snap.items():
            try:
                rows.append({
                    "symbol": v.get("symbol"),
                    "ts": v.get("ts"),
                    "price": v.get("price"),
                    "qty": v.get("qty"),
                })
            except Exception:
                continue

        df = pd.DataFrame(rows)
        if df.empty:
            return df

        df['ts'] = pd.to_datetime(df['ts'], utc=True, errors='coerce')
        df = df.dropna(subset=['ts'])
        if df.empty:
            return pd.DataFrame()

        df['price'] = pd.to_numeric(df['price'], errors='coerce')
        df['qty'] = pd.to_numeric(df['qty'], errors='coerce')
        df = df[(df['price'] > 0) & (df['qty'] >= 0)]
        df = df.dropna(subset=['price', 'qty'])
        if df.empty:
            return pd.DataFrame()

        df = df.set_index('ts').sort_index()
        return df

    def fetch_recent_ohlc(self, minutes=60):
        since = datetime.utcnow().replace(tzinfo=timezone.utc) - timedelta(minutes=minutes)
        since_iso = since.isoformat()

        try:
            snap = (
                self.ohlc_ref
                .order_by_child("ts")
                .start_at(since_iso)
                .get()
            )
        except Exception as e:
            print(f"[FirebaseStorage] Error fetching OHLC: {e}")
            return pd.DataFrame()

        if not snap:
            return pd.DataFrame()

        rows = []
        for _, v in snap.items():
            try:
                rows.append({
                    "symbol": v.get("symbol"),
                    "ts": v.get("ts"),
                    "open": v.get("open"),
                    "high": v.get("high"),
                    "low": v.get("low"),
                    "close": v.get("close"),
                    "volume": v.get("volume", 0.0),
                })
            except Exception:
                continue

        df = pd.DataFrame(rows)
        if df.empty:
            return df

        df['ts'] = pd.to_datetime(df['ts'], utc=True, errors='coerce')
        df = df.dropna(subset=['ts'])
        if df.empty:
            return pd.DataFrame()

        for col in ['open', 'high', 'low', 'close', 'volume']:
            df[col] = pd.to_numeric(df[col], errors='coerce')

        df = df[(df['open'] > 0) & (df['high'] > 0) &
                (df['low'] > 0) & (df['close'] > 0)]
        df = df.dropna(subset=['close'])
        if df.empty:
            return pd.DataFrame()

        df['high'] = df[['open', 'high', 'low', 'close']].max(axis=1)
        df['low'] = df[['open', 'high', 'low', 'close']].min(axis=1)

        df = df.set_index('ts').sort_index()
        return df

    # ---------- Misc ----------
    def count_rows(self):
        try:
            snap = self.ticks_ref.get(shallow=True)
            if not snap:
                return 0
            return len(snap)
        except Exception as e:
            print(f"[FirebaseStorage] Error counting rows: {e}")
            return 0

    def last_timestamp(self):
        try:
            snap = (
                self.ticks_ref
                .order_by_child("ts")
                .limit_to_last(1)
                .get()
            )
        except Exception as e:
            print(f"[FirebaseStorage] Error getting last timestamp: {e}")
            return None

        if not snap:
            return None

        # snap is a dict with a single key
        v = list(snap.values())[0]
        return v.get("ts")
