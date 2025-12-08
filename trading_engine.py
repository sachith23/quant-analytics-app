import threading
import time
import hmac
import hashlib
import requests
from datetime import datetime, timezone
from typing import Optional, Dict, List
from enum import Enum
import json

class OrderSide(Enum):
    BUY = "BUY"
    SELL = "SELL"

class PositionSide(Enum):
    LONG = "LONG"
    SHORT = "SHORT"
    BOTH = "BOTH"

class OrderType(Enum):
    MARKET = "MARKET"
    LIMIT = "LIMIT"

class TradingEngine:
    """
    Automated trading engine that monitors analytics alerts and executes
    trades on Binance Futures Testnet based on statistical arbitrage signals.
    """
    
    def __init__(self, api_key: str, api_secret: str, storage, analytics, alert_engine):
        self.api_key = api_key
        self.api_secret = api_secret
        self.storage = storage
        self.analytics = analytics
        self.alert_engine = alert_engine
        
        # Binance Futures Testnet endpoints
        self.base_url = "https://testnet.binancefuture.com"
        
        # Trading configuration
        self.running = False
        self.monitoring_thread = None
        self.position_size_usd = 100.0  # Dollar value per leg
        self.max_positions = 2  # Maximum concurrent positions
        self.stop_loss_pct = 0.02  # 2% stop loss
        self.take_profit_pct = 0.03  # 3% take profit
        
        # Minimum order quantities for different symbols (Binance Futures requirements)
        self.min_quantities = {
            'BTCUSDT': 0.001,
            'ETHUSDT': 0.01,
            'BNBUSDT': 0.01,
            'XRPUSDT': 2.5,  # 2.5 XRP minimum
            'SOLUSDT': 1.0,  # 1.0 SOL minimum
            'ADAUSDT': 1.0,
            'DOGEUSDT': 1.0,
            'MATICUSDT': 1.0,
            'DOTUSDT': 0.1,
            'AVAXUSDT': 0.1,
        }
        
        # Quantity precision for different symbols
        self.quantity_precision = {
            'BTCUSDT': 3,
            'ETHUSDT': 3,
            'BNBUSDT': 2,
            'XRPUSDT': 1,  # 1 decimal place
            'SOLUSDT': 0,  # 0 decimal places (whole numbers)
            'ADAUSDT': 0,
            'DOGEUSDT': 0,
            'MATICUSDT': 0,
            'DOTUSDT': 1,
            'AVAXUSDT': 1,
        }
        
        # State tracking
        self.active_positions = {}  # {symbol: position_info}
        self.last_alert_check = None
        self.trade_history = []
        self.failed_orders = []  # Track failed orders for debugging
        
        # Risk management
        self.max_drawdown = 0.10  # 10% max drawdown
        self.daily_loss_limit = 0.05  # 5% daily loss limit
        self.initial_balance = None
        self.current_balance = None
        
    def _generate_signature(self, query_string: str) -> str:
        """Generate HMAC SHA256 signature for Binance API"""
        return hmac.new(
            self.api_secret.encode('utf-8'),
            query_string.encode('utf-8'),
            hashlib.sha256
        ).hexdigest()
    
    def _send_signed_request(self, method: str, endpoint: str, params: Dict = None) -> Dict:
        """Send signed request to Binance API"""
        if params is None:
            params = {}
        
        params['timestamp'] = int(time.time() * 1000)
        query_string = '&'.join([f"{k}={v}" for k, v in params.items()])
        signature = self._generate_signature(query_string)
        
        url = f"{self.base_url}{endpoint}?{query_string}&signature={signature}"
        headers = {'X-MBX-APIKEY': self.api_key}
        
        try:
            if method == "GET":
                response = requests.get(url, headers=headers, timeout=10)
            elif method == "POST":
                response = requests.post(url, headers=headers, timeout=10)
            elif method == "DELETE":
                response = requests.delete(url, headers=headers, timeout=10)
            else:
                raise ValueError(f"Unsupported method: {method}")
            
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as e:
            error_msg = f"API request failed: {e}"
            if hasattr(e, 'response') and e.response is not None:
                try:
                    error_data = e.response.json()
                    error_msg += f" | Response: {error_data}"
                except:
                    error_msg += f" | Status: {e.response.status_code}"
            print(error_msg)
            return None
    
    def get_symbol_info(self, symbol: str) -> Optional[Dict]:
        """Get exchange info for a symbol to determine min quantity and precision"""
        try:
            response = requests.get(f"{self.base_url}/fapi/v1/exchangeInfo")
            if response.status_code == 200:
                data = response.json()
                for s in data.get('symbols', []):
                    if s['symbol'] == symbol.upper():
                        return s
        except Exception as e:
            print(f"Failed to get symbol info: {e}")
        return None
    
    def get_min_quantity(self, symbol: str) -> float:
        """Get minimum order quantity for a symbol"""
        symbol_upper = symbol.upper()
        
        # Try cached values first
        if symbol_upper in self.min_quantities:
            return self.min_quantities[symbol_upper]
        
        # Fetch from exchange if not cached
        info = self.get_symbol_info(symbol)
        if info:
            for f in info.get('filters', []):
                if f['filterType'] == 'LOT_SIZE':
                    min_qty = float(f['minQty'])
                    self.min_quantities[symbol_upper] = min_qty
                    return min_qty
        
        # Default fallback
        return 0.001
    
    def get_quantity_precision(self, symbol: str) -> int:
        """Get quantity precision (decimal places) for a symbol"""
        symbol_upper = symbol.upper()
        
        # Try cached values first
        if symbol_upper in self.quantity_precision:
            return self.quantity_precision[symbol_upper]
        
        # Fetch from exchange if not cached
        info = self.get_symbol_info(symbol)
        if info:
            for f in info.get('filters', []):
                if f['filterType'] == 'LOT_SIZE':
                    step_size = float(f['stepSize'])
                    # Calculate precision from step size
                    precision = 0
                    if step_size < 1:
                        precision = len(str(step_size).rstrip('0').split('.')[-1])
                    self.quantity_precision[symbol_upper] = precision
                    return precision
        
        # Default fallback
        return 3
    
    def round_quantity(self, symbol: str, quantity: float) -> float:
        """Round quantity to proper precision for the symbol"""
        precision = self.get_quantity_precision(symbol)
        return round(quantity, precision)
    
    def get_account_balance(self) -> Optional[float]:
        """Get current account balance"""
        result = self._send_signed_request("GET", "/fapi/v2/balance")
        if result:
            for asset in result:
                if asset['asset'] == 'USDT':
                    return float(asset['balance'])
        return None
    
    def get_position_info(self, symbol: str = None) -> List[Dict]:
        """Get current positions"""
        params = {}
        if symbol:
            params['symbol'] = symbol.upper()
        
        result = self._send_signed_request("GET", "/fapi/v2/positionRisk", params)
        if result:
            return [p for p in result if float(p['positionAmt']) != 0]
        return []
    
    def place_market_order(self, symbol: str, side: OrderSide, quantity: float, 
                          reduce_only: bool = False) -> Optional[Dict]:
        """Place a market order with proper validation"""
        symbol_upper = symbol.upper()
        
        # Get minimum quantity for this symbol
        min_qty = self.get_min_quantity(symbol)
        
        # Round quantity to proper precision
        quantity = self.round_quantity(symbol, quantity)
        
        # Validate minimum quantity
        if quantity < min_qty:
            error_msg = f"❌ Order rejected: {symbol_upper} quantity {quantity} below minimum {min_qty}"
            print(error_msg)
            self.failed_orders.append({
                'timestamp': datetime.now(timezone.utc).isoformat(),
                'symbol': symbol_upper,
                'side': side.value,
                'quantity': quantity,
                'min_quantity': min_qty,
                'reason': 'Below minimum quantity'
            })
            return None
        
        params = {
            'symbol': symbol_upper,
            'side': side.value,
            'type': OrderType.MARKET.value,
            'quantity': quantity
        }
        
        if reduce_only:
            params['reduceOnly'] = 'true'
        
        print(f"\n🔄 Placing order on Binance Testnet:")
        print(f"   URL: {self.base_url}/fapi/v1/order")
        print(f"   Symbol: {symbol_upper}")
        print(f"   Side: {side.value}")
        print(f"   Quantity: {quantity}")
        print(f"   Type: MARKET")
        
        result = self._send_signed_request("POST", "/fapi/v1/order", params)
        
        if result:
            print(f"✅ Order placed successfully!")
            print(f"   Order ID: {result.get('orderId')}")
            print(f"   Status: {result.get('status')}")
            print(f"   Executed Qty: {result.get('executedQty')}")
            print(f"   Avg Price: {result.get('avgPrice', 'N/A')}")
            
            self.trade_history.append({
                'timestamp': datetime.now(timezone.utc).isoformat(),
                'symbol': symbol_upper,
                'side': side.value,
                'quantity': quantity,
                'type': 'MARKET',
                'order_id': result.get('orderId'),
                'status': result.get('status'),
                'executed_qty': result.get('executedQty'),
                'avg_price': result.get('avgPrice'),
                'response': 'SUCCESS'
            })
        else:
            print(f"❌ Order FAILED!")
            print(f"   Check your API keys and testnet balance")
            print(f"   Make sure you're using FUTURES testnet keys from:")
            print(f"   https://testnet.binancefuture.com")
            
            self.failed_orders.append({
                'timestamp': datetime.now(timezone.utc).isoformat(),
                'symbol': symbol_upper,
                'side': side.value,
                'quantity': quantity,
                'reason': 'API error - check logs above'
            })
        
        return result
    
    def close_position(self, symbol: str, position_amt: float) -> bool:
        """Close an existing position"""
        if position_amt == 0:
            return True
        
        side = OrderSide.SELL if position_amt > 0 else OrderSide.BUY
        quantity = abs(position_amt)
        
        result = self.place_market_order(symbol, side, quantity, reduce_only=True)
        return result is not None
    
    def calculate_position_size(self, symbol: str, price: float) -> float:
        """
        Calculate position size based on fixed USD value per leg
        Ensures minimum quantity requirements are met
        """
        symbol_upper = symbol.upper()
        
        # Calculate base quantity from USD value
        quantity = self.position_size_usd / price
        
        # Round to proper precision
        quantity = self.round_quantity(symbol, quantity)
        
        # Get minimum quantity
        min_qty = self.get_min_quantity(symbol)
        
        # Ensure we meet minimum
        if quantity < min_qty:
            quantity = min_qty
            print(f"⚠️ Adjusting {symbol_upper} quantity to minimum: {quantity}")
        
        return quantity
    
    def check_risk_limits(self) -> bool:
        """Check if risk limits are breached"""
        if not self.initial_balance or not self.current_balance:
            return True
        
        total_pnl_pct = (self.current_balance - self.initial_balance) / self.initial_balance
        
        # Check max drawdown
        if total_pnl_pct < -self.max_drawdown:
            print(f"⚠️ Max drawdown breached: {total_pnl_pct:.2%}")
            return False
        
        # Check if we have too many positions
        if len(self.active_positions) >= self.max_positions:
            print(f"⚠️ Max positions reached: {len(self.active_positions)}")
            return False
        
        return True
    
    def execute_spread_trade(self, s1: str, s2: str, zscore: float, hedge_ratio: float,
                            entry_threshold: float):
        """
        Execute a pairs trade based on z-score signal
        
        Logic:
        - If z > entry_threshold: SHORT spread (short s1, long s2)
        - If z < -entry_threshold: LONG spread (long s1, short s2)
        """
        if not self.check_risk_limits():
            print("⚠️ Risk limits breached, skipping trade")
            return
        
        # Get current prices
        df_ohlc = self.analytics.get_resampled_ohlc([s1, s2], "1min")
        if df_ohlc.empty:
            print("⚠️ No OHLC data available")
            return
        
        price_s1 = df_ohlc[df_ohlc['symbol'] == s1]['close'].iloc[-1]
        price_s2 = df_ohlc[df_ohlc['symbol'] == s2]['close'].iloc[-1]
        
        # Calculate position sizes (using fixed USD value per leg)
        qty_s1 = self.calculate_position_size(s1, price_s1)
        qty_s2 = self.calculate_position_size(s2, price_s2)
        
        if qty_s1 == 0 or qty_s2 == 0:
            print("⚠️ Invalid position sizes calculated")
            return
        
        print(f"\n{'='*60}")
        print(f"📊 TRADE SIGNAL DETECTED")
        print(f"{'='*60}")
        print(f"Z-Score: {zscore:.2f} (Threshold: ±{entry_threshold})")
        print(f"Hedge Ratio: {hedge_ratio:.4f}")
        print(f"Prices: {s1.upper()}=${price_s1:.4f} | {s2.upper()}=${price_s2:.4f}")
        print(f"Quantities: {s1.upper()}={qty_s1} | {s2.upper()}={qty_s2}")
        print(f"Position Value: ~${qty_s1*price_s1:.2f} + ${qty_s2*price_s2:.2f}")
        
        # Determine trade direction and execute
        success = True
        
        if zscore >= entry_threshold:
            # SHORT spread: short s1, long s2
            print(f"\n📉 Opening SHORT SPREAD")
            print(f"  → SHORT {qty_s1} {s1.upper()} @ ${price_s1:.4f}")
            print(f"  → LONG {qty_s2} {s2.upper()} @ ${price_s2:.4f}")
            
            result1 = self.place_market_order(s1, OrderSide.SELL, qty_s1)
            result2 = self.place_market_order(s2, OrderSide.BUY, qty_s2)
            
            if result1 and result2:
                self.active_positions[f"{s1}_{s2}"] = {
                    'type': 'SHORT_SPREAD',
                    'entry_zscore': zscore,
                    'entry_time': datetime.now(timezone.utc).isoformat(),
                    'qty_s1': qty_s1,
                    'qty_s2': qty_s2,
                    'entry_price_s1': price_s1,
                    'entry_price_s2': price_s2,
                    'hedge_ratio': hedge_ratio
                }
                print("✅ SHORT SPREAD position opened successfully")
            else:
                success = False
                print("❌ Failed to open SHORT SPREAD - orders failed")
            
        elif zscore <= -entry_threshold:
            # LONG spread: long s1, short s2
            print(f"\n📈 Opening LONG SPREAD")
            print(f"  → LONG {qty_s1} {s1.upper()} @ ${price_s1:.4f}")
            print(f"  → SHORT {qty_s2} {s2.upper()} @ ${price_s2:.4f}")
            
            result1 = self.place_market_order(s1, OrderSide.BUY, qty_s1)
            result2 = self.place_market_order(s2, OrderSide.SELL, qty_s2)
            
            if result1 and result2:
                self.active_positions[f"{s1}_{s2}"] = {
                    'type': 'LONG_SPREAD',
                    'entry_zscore': zscore,
                    'entry_time': datetime.now(timezone.utc).isoformat(),
                    'qty_s1': qty_s1,
                    'qty_s2': qty_s2,
                    'entry_price_s1': price_s1,
                    'entry_price_s2': price_s2,
                    'hedge_ratio': hedge_ratio
                }
                print("✅ LONG SPREAD position opened successfully")
            else:
                success = False
                print("❌ Failed to open LONG SPREAD - orders failed")
        
        print(f"{'='*60}\n")
    
    def check_exit_conditions(self, symbols: List[str], exit_threshold: float = 0.0):
        """Check if any positions should be closed"""
        if len(symbols) < 2:
            return
        
        s1, s2 = symbols[0], symbols[1]
        pair_key = f"{s1}_{s2}"
        
        if pair_key not in self.active_positions:
            return
        
        # Get current analytics
        pair_res = self.analytics.compute_pair_analytics(s1, s2, timeframe="1min", rolling=30)
        if not pair_res or pair_res.get('df') is None or pair_res['df'].empty:
            return
        
        current_zscore = pair_res['df']['zscore'].iloc[-1]
        position = self.active_positions[pair_key]
        
        # Exit logic based on position type
        should_exit = False
        reason = ""
        
        if position['type'] == 'SHORT_SPREAD':
            # Exit when z-score crosses below exit threshold (mean reversion)
            if current_zscore <= exit_threshold:
                should_exit = True
                reason = f"Mean reversion: z={current_zscore:.2f}"
        
        elif position['type'] == 'LONG_SPREAD':
            # Exit when z-score crosses above exit threshold (mean reversion)
            if current_zscore >= exit_threshold:
                should_exit = True
                reason = f"Mean reversion: z={current_zscore:.2f}"
        
        # Additional exit: stop loss on extreme moves
        if abs(current_zscore) > abs(position['entry_zscore']) * 1.5:
            should_exit = True
            reason = f"Stop loss: z={current_zscore:.2f}"
        
        if should_exit:
            print(f"\n🔄 Closing {position['type']}: {reason}")
            
            # Close both legs
            if position['type'] == 'SHORT_SPREAD':
                self.place_market_order(s1, OrderSide.BUY, position['qty_s1'], reduce_only=True)
                self.place_market_order(s2, OrderSide.SELL, position['qty_s2'], reduce_only=True)
            else:
                self.place_market_order(s1, OrderSide.SELL, position['qty_s1'], reduce_only=True)
                self.place_market_order(s2, OrderSide.BUY, position['qty_s2'], reduce_only=True)
            
            del self.active_positions[pair_key]
            self.current_balance = self.get_account_balance()
            print(f"✅ Position closed. New balance: ${self.current_balance:.2f}\n")
    
    def monitoring_loop(self, symbols: List[str], entry_threshold: float, 
                       exit_threshold: float, check_interval: int = 10):
        """Main monitoring loop that checks for trading signals"""
        print(f"🤖 Trading engine started. Monitoring: {symbols}")
        print(f"   Entry threshold: ±{entry_threshold}")
        print(f"   Exit threshold: {exit_threshold}")
        print(f"   Check interval: {check_interval}s")
        print(f"   Position size: ${self.position_size_usd} per leg\n")
        
        while self.running:
            try:
                # Update balance
                self.current_balance = self.get_account_balance()
                
                if len(symbols) >= 2:
                    s1, s2 = symbols[0], symbols[1]
                    
                    # Check exit conditions for existing positions
                    self.check_exit_conditions(symbols, exit_threshold)
                    
                    # Check for new entry signals (only if no position)
                    pair_key = f"{s1}_{s2}"
                    if pair_key not in self.active_positions:
                        pair_res = self.analytics.compute_pair_analytics(
                            s1, s2, timeframe="1min", rolling=30
                        )
                        
                        if pair_res and pair_res.get('df') is not None and not pair_res['df'].empty:
                            current_zscore = pair_res['df']['zscore'].iloc[-1]
                            hedge_ratio = pair_res.get('hedge')
                            
                            # Check for entry signal
                            if abs(current_zscore) >= entry_threshold:
                                self.execute_spread_trade(
                                    s1, s2, current_zscore, hedge_ratio, entry_threshold
                                )
                
                time.sleep(check_interval)
                
            except Exception as e:
                print(f"❌ Error in monitoring loop: {e}")
                import traceback
                traceback.print_exc()
                time.sleep(check_interval)
    
    def start(self, symbols: List[str], entry_threshold: float = 2.0, 
              exit_threshold: float = 0.0, check_interval: int = 10):
        """Start the trading engine"""
        if self.running:
            print("⚠️ Trading engine already running")
            return
        
        # Verify connection to Binance testnet
        print("🔍 Verifying connection to Binance Futures Testnet...")
        print(f"   Endpoint: {self.base_url}")
        
        # Test connection by getting account info
        test_result = self._send_signed_request("GET", "/fapi/v2/account")
        if not test_result:
            print("❌ Failed to connect to Binance testnet!")
            print("   Please verify:")
            print("   1. API Key and Secret are correct")
            print("   2. Keys are from: https://testnet.binancefuture.com (NOT mainnet)")
            print("   3. Keys have 'Enable Futures' permission")
            return
        
        print("✅ Connection verified!")
        print(f"   Account created: {test_result.get('updateTime', 'N/A')}")
        
        # Initialize balance tracking
        self.initial_balance = self.get_account_balance()
        self.current_balance = self.initial_balance
        
        if not self.initial_balance:
            print("❌ Failed to get account balance")
            return
        
        print(f"💰 Initial balance: {self.initial_balance:.2f} USDT")
        print(f"\n⚠️  IMPORTANT: Check your testnet positions at:")
        print(f"   https://testnet.binancefuture.com/en/futures/BTCUSDT")
        print(f"   Go to 'Positions' and 'Order History' tabs to verify trades\n")
        
        self.running = True
        self.monitoring_thread = threading.Thread(
            target=self.monitoring_loop,
            args=(symbols, entry_threshold, exit_threshold, check_interval),
            daemon=True
        )
        self.monitoring_thread.start()
    
    def stop(self):
        """Stop the trading engine"""
        print("🛑 Stopping trading engine...")
        self.running = False
        
        if self.monitoring_thread:
            self.monitoring_thread.join(timeout=5)
        
        print("✅ Trading engine stopped")
    
    def get_status(self) -> Dict:
        """Get current trading engine status"""
        return {
            'running': self.running,
            'initial_balance': self.initial_balance,
            'current_balance': self.current_balance,
            'pnl': self.current_balance - self.initial_balance if self.initial_balance and self.current_balance else 0,
            'pnl_pct': ((self.current_balance - self.initial_balance) / self.initial_balance * 100) if self.initial_balance and self.current_balance else 0,
            'active_positions': len(self.active_positions),
            'total_trades': len(self.trade_history),
            'failed_orders': len(self.failed_orders),
            'positions': self.active_positions
        }
    
    def emergency_close_all(self):
        """Emergency close all positions"""
        print("🚨 EMERGENCY: Closing all positions")
        
        positions = self.get_position_info()
        for pos in positions:
            symbol = pos['symbol']
            position_amt = float(pos['positionAmt'])
            self.close_position(symbol, position_amt)
        
        self.active_positions = {}
        print("✅ All positions closed")