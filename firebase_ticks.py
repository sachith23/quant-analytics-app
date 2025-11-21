import json
from datetime import datetime
import pandas as pd

import firebase_admin
from firebase_admin import credentials, db


def _get_firebase_config():
    try:
        import streamlit as st
        cfg = st.secrets.get("firebase", None)
        if not cfg:
            return None
        return {
            "service_account_json": cfg.get("service_account_json"),
            "database_url": cfg.get("database_url"),
        }
    except Exception:
        return None


def _get_firebase_app():
    cfg = _get_firebase_config()
    if not cfg:
        return None
    if not firebase_admin._apps:
        sa_str = cfg["service_account_json"]
        sa_info = json.loads(sa_str)
        cred = credentials.Certificate(sa_info)
        firebase_admin.initialize_app(cred, {"databaseURL": cfg["database_url"]})
    return firebase_admin.get_app()


class FirebaseTickStore:
    def __init__(self):
        app = _get_firebase_app()
        if app is None:
            self.enabled = False
            self.root_ref = None
        else:
            self.enabled = True
            self.root_ref = db.reference("ticks")

    def insert_tick(self, symbol, ts_iso, price, qty):
        if not self.enabled:
            return
        try:
            ts = datetime.fromisoformat(ts_iso.replace("Z", "+00:00"))
        except Exception:
            return
        key = f"{symbol}_{ts_iso}"
        self.root_ref.child(symbol).child(key).set(
            {
                "symbol": symbol,
                "ts": ts.isoformat(),
                "price": float(price),
                "qty": float(qty),
            }
        )

    def fetch_recent_ticks(self, minutes=60):
        if not self.enabled:
            return pd.DataFrame(columns=["symbol", "ts", "price", "qty"])
        all_data = self.root_ref.get() or {}
        rows = []
        cutoff = datetime.utcnow().timestamp() - minutes * 60
        for sym, items in all_data.items():
            for _, row in items.items():
                try:
                    ts = pd.to_datetime(row["ts"], utc=True)
                    if ts.timestamp() < cutoff:
                        continue
                    rows.append(
                        {
                            "symbol": row["symbol"],
                            "ts": ts,
                            "price": float(row["price"]),
                            "qty": float(row["qty"]),
                        }
                    )
                except Exception:
                    continue
        if not rows:
            return pd.DataFrame(columns=["symbol", "ts", "price", "qty"])
        df = pd.DataFrame(rows)
        df = df.sort_values("ts")
        return df
