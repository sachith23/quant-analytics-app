# analytics.py (fixed resampling to prevent zero prices and data quality issues)
import pandas as pd
import numpy as np
from statsmodels.regression.linear_model import OLS
from statsmodels.tools import add_constant
from statsmodels.tsa.stattools import adfuller
import plotly.graph_objects as go
import plotly.express as px

class AnalyticsEngine:
    def __init__(self, storage):
        self.storage = storage

    def _ohlc_from_ticks(self, symbols, timeframe, lookback_minutes=24*60):
        """
        Build per-symbol resampled OHLC from raw ticks if there's no ohlc table data.
        Fixed to handle data quality issues and prevent zero prices.
        """
        df = self.storage.fetch_recent_ticks(minutes=lookback_minutes)
        if df.empty:
            return pd.DataFrame()
        
        out_frames = []
        for s in symbols:
            d = df[df['symbol'] == s].copy()
            if d.empty:
                continue
            
            # Ensure positive prices only
            d = d[d['price'] > 0].copy()
            if d.empty:
                continue
                
            d.index.name = 'ts'
            d = d[['price','qty']].astype(float)
            
            # Map timeframe to pandas resample rule
            rule = {"1s":"1S","1min":"1T","5min":"5T"}[timeframe]
            
            # Resample with proper aggregation
            r = d.resample(rule).agg({
                'price': ['first', 'max', 'min', 'last'],
                'qty': 'sum'
            })
            r.columns = ['open', 'high', 'low', 'close', 'volume']
            
            # Drop completely empty bars
            r = r.dropna(subset=['close'])
            if r.empty:
                continue
            
            # Forward fill close prices for bars with trades
            r['close'] = r['close'].ffill()
            
            # For bars with a close but no OHLC (shouldn't happen but safety check)
            r['open'] = r['open'].fillna(r['close'])
            r['high'] = r['high'].fillna(r['close'])
            r['low'] = r['low'].fillna(r['close'])
            
            # Ensure high is highest and low is lowest
            r['high'] = r[['open', 'high', 'low', 'close']].max(axis=1)
            r['low'] = r[['open', 'high', 'low', 'close']].min(axis=1)
            
            # Fill volume with 0 for bars with no trades
            r['volume'] = r['volume'].fillna(0.0)
            
            # Final sanity check: remove any bars with zero or negative prices
            r = r[(r['open'] > 0) & (r['high'] > 0) & (r['low'] > 0) & (r['close'] > 0)]
            
            if r.empty:
                continue
            
            r = r.reset_index()
            r['symbol'] = s
            out_frames.append(r)
        
        if not out_frames:
            return pd.DataFrame()
        
        combined = pd.concat(out_frames, axis=0, ignore_index=True).sort_values('ts').set_index('ts')
        return combined[['symbol','open','high','low','close','volume']]

    def _ohlc_from_table(self, symbols, timeframe, lookback_minutes=24*60):
        """
        Use stored OHLC bars (inserted via upload). Return bars aggregated to requested timeframe if needed.
        """
        df = self.storage.fetch_recent_ohlc(minutes=lookback_minutes)
        if df.empty:
            return pd.DataFrame()
        
        out_frames = []
        for s in symbols:
            d = df[df['symbol'] == s].copy()
            if d.empty:
                continue
            
            # Filter out invalid prices
            d = d[(d['open'] > 0) & (d['high'] > 0) & (d['low'] > 0) & (d['close'] > 0)]
            if d.empty:
                continue
                
            d = d[['open','high','low','close','volume']].copy()
            d.index.name = 'ts'
            
            # Determine resample rule
            rule = {"1s":"1S","1min":"1T","5min":"5T"}[timeframe]
            
            # Resample with proper OHLC aggregation
            r = d.resample(rule).agg({
                'open': 'first',
                'high': 'max',
                'low': 'min',
                'close': 'last',
                'volume': 'sum'
            })
            
            # Drop bars with no close price
            r = r.dropna(subset=['close'])
            if r.empty:
                continue
            
            # Ensure OHLC consistency
            r['high'] = r[['open', 'high', 'low', 'close']].max(axis=1)
            r['low'] = r[['open', 'high', 'low', 'close']].min(axis=1)
            
            # Final validation
            r = r[(r['open'] > 0) & (r['high'] > 0) & (r['low'] > 0) & (r['close'] > 0)]
            if r.empty:
                continue
            
            r = r.reset_index()
            r['symbol'] = s
            out_frames.append(r)
        
        if not out_frames:
            return pd.DataFrame()
        
        combined = pd.concat(out_frames, axis=0, ignore_index=True).sort_values('ts').set_index('ts')
        return combined[['symbol','open','high','low','close','volume']]

    def get_resampled_ohlc(self, symbols, timeframe):
        """
        Main entry. Prefer stored OHLC table (uploaded), fallback to ticks aggregation.
        Lookback is 24 hours by default to satisfy analytics without requiring >1 day.
        """
        lookback = 24*60
        ohlc_table = self._ohlc_from_table(symbols, timeframe, lookback_minutes=lookback)
        if not ohlc_table.empty:
            return ohlc_table
        # fallback to ticks aggregation
        return self._ohlc_from_ticks(symbols, timeframe, lookback_minutes=lookback)

    def compute_pair_analytics(self, s1, s2, timeframe="1min", rolling=30):
        """
        Compute hedge, spread, zscore. Return None if not enough reliable data.
        """
        ohlc = self.get_resampled_ohlc([s1, s2], timeframe)
        if ohlc.empty:
            return None

        p1 = ohlc[ohlc['symbol'] == s1]['close'].rename(s1)
        p2 = ohlc[ohlc['symbol'] == s2]['close'].rename(s2)
        df = pd.concat([p1, p2], axis=1).dropna()

        # require at least `rolling` bars (or at least 10) to compute stable rolling stats
        min_bars = max(rolling, 10)
        if len(df) < min_bars:
            return None

        # Filter out any zero or negative prices
        df = df[(df[s1] > 0) & (df[s2] > 0)]
        if len(df) < min_bars:
            return None

        # OLS hedge on the overlapping dataframe
        y = df[s1].values
        x = df[[s2]].values
        x_const = add_constant(x)
        model = OLS(y, x_const).fit()
        hedge = float(model.params[1])

        # compute spread
        spread = df[s1] - hedge * df[s2]

        # rolling mean/std with min_periods=rolling -> avoids tiny-sample std issues
        mean = spread.rolling(window=rolling, min_periods=rolling).mean()
        std = spread.rolling(window=rolling, min_periods=rolling).std()

        # if std is zero replace with NaN (prevents divide-by-zero)
        std = std.replace(0, np.nan)

        zscore = (spread - mean) / std

        # drop rows where zscore is NaN (these are early rows with not enough rolling data)
        df_z = pd.DataFrame({"spread": spread, "zscore": zscore}).dropna()
        if df_z.empty:
            return None

        rolling_corr = df[s1].rolling(window=rolling, min_periods=rolling).corr(df[s2])

        adf_p = None
        try:
            spread_clean = spread.dropna()
            if len(spread_clean) >= rolling:
                adf_p = adfuller(spread_clean)[1]
        except Exception:
            adf_p = None

        return {
            "df": df_z,
            "hedge": hedge,
            "rolling_corr": rolling_corr,
            "adf_p": adf_p
        }

    def plot_prices(self, df_ohlc):
        df = df_ohlc.reset_index().rename(columns={'ts':'ts'})
        df['ts'] = pd.to_datetime(df['ts'])
        fig = px.line(df, x='ts', y='close', color='symbol', title='Price')
        fig.update_layout(margin=dict(l=40, r=20, t=40, b=40))
        return fig

    def plot_spread_zscore(self, df):
        fig = go.Figure()
        fig.add_trace(go.Scatter(x=df.index, y=df['spread'], name='spread'))
        fig.add_trace(go.Scatter(x=df.index, y=df['zscore'], name='zscore', yaxis='y2'))
        fig.update_layout(title="Spread & Z-score", yaxis2=dict(overlaying='y', side='right', title='zscore'))
        return fig