# storage.py (enhanced with data validation to prevent zero/invalid prices)
import sqlite3
import pandas as pd
from datetime import datetime, timedelta, timezone

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
        """Insert a tick with validation to prevent zero/negative prices"""
        # Validate price and quantity
        if price <= 0 or qty < 0:
            return  # Skip invalid data
        
        con = self._connect()
        cur = con.cursor()
        try:
            cur.execute("INSERT INTO ticks(symbol, ts, price, qty) VALUES (?, ?, ?, ?)",
                        (symbol, ts_iso, float(price), float(qty)))
            con.commit()
        except Exception as e:
            print(f"Error inserting tick: {e}")
        finally:
            con.close()

    def insert_tick_iso(self, symbol, dt_obj, price, qty):
        """Insert tick with datetime object"""
        if dt_obj.tzinfo is None:
            dt_obj = dt_obj.replace(tzinfo=timezone.utc)
        dt_norm = dt_obj.astimezone(timezone.utc).isoformat(timespec='microseconds')
        self.insert_tick(symbol, dt_norm, price, qty)

    def insert_ohlc_bar(self, symbol, dt_obj, o, h, l, c, v):
        """
        Insert a true OHLC bar into the ohlc table with validation.
        dt_obj is a datetime (preferably tz-aware).
        This is the mandatory upload path required by the assignment.
        """
        # Validate OHLC values
        try:
            o, h, l, c, v = float(o), float(h), float(l), float(c), float(v)
            
            # Check for invalid prices
            if o <= 0 or h <= 0 or l <= 0 or c <= 0:
                return  # Skip invalid bars
            
            # Validate OHLC logic: high should be highest, low should be lowest
            if h < max(o, c) or l > min(o, c):
                # Fix the data
                h = max(o, h, l, c)
                l = min(o, h, l, c)
            
            if v < 0:
                v = 0.0
                
        except (ValueError, TypeError):
            return  # Skip if conversion fails
        
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
        """Fetch recent ticks with data quality filtering"""
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
        
        # Parse timestamps
        df['ts'] = pd.to_datetime(df['ts'], utc=True, infer_datetime_format=True, errors='coerce')
        df = df.dropna(subset=['ts'])
        
        if df.empty:
            return pd.DataFrame()
        
        # Convert to numeric and validate
        df['price'] = pd.to_numeric(df['price'], errors='coerce')
        df['qty'] = pd.to_numeric(df['qty'], errors='coerce')
        
        # Filter out invalid data
        df = df[(df['price'] > 0) & (df['qty'] >= 0)]
        df = df.dropna(subset=['price', 'qty'])
        
        if df.empty:
            return pd.DataFrame()
        
        df = df.set_index('ts').sort_index()
        return df

    def fetch_recent_ohlc(self, minutes=60):
        """
        Returns OHLC rows from the ohlc table for the last `minutes` with validation.
        If empty, caller can fall back to aggregating ticks.
        """
        since = datetime.utcnow().replace(tzinfo=timezone.utc) - timedelta(minutes=minutes)
        since_iso = since.isoformat()
        con = self._connect()
        df = pd.read_sql_query(
            "SELECT symbol, ts, open, high, low, close, volume FROM ohlc WHERE ts >= ? ORDER BY ts ASC",
            con, params=(since_iso,)
        )
        con.close()
        
        if df.empty:
            return df
        
        # Parse timestamps
        df['ts'] = pd.to_datetime(df['ts'], utc=True, infer_datetime_format=True, errors='coerce')
        df = df.dropna(subset=['ts'])
        
        if df.empty:
            return pd.DataFrame()
        
        # Convert to numeric
        for col in ['open','high','low','close','volume']:
            df[col] = pd.to_numeric(df[col], errors='coerce')
        
        # Validate OHLC data
        df = df[(df['open'] > 0) & (df['high'] > 0) & (df['low'] > 0) & (df['close'] > 0)]
        df = df.dropna(subset=['close'])
        
        if df.empty:
            return pd.DataFrame()
        
        # Ensure OHLC consistency
        df['high'] = df[['open', 'high', 'low', 'close']].max(axis=1)
        df['low'] = df[['open', 'high', 'low', 'close']].min(axis=1)
        
        df = df.set_index('ts').sort_index()
        return df

    def count_rows(self):
        """Count total ticks in database"""
        con = self._connect()
        cur = con.cursor()
        cur.execute("SELECT COUNT(*) FROM ticks")
        n = cur.fetchone()[0]
        con.close()
        return n

    def last_timestamp(self):
        """Get the timestamp of the most recent tick"""
        con = self._connect()
        cur = con.cursor()
        cur.execute("SELECT ts FROM ticks ORDER BY ts DESC LIMIT 1")
        r = cur.fetchone()
        con.close()
        return r[0] if r else None