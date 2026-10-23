import ccxt
import sys

try:
    import ccxt
    print("ccxt version:", ccxt.__version__)
except ImportError:
    print("Please install ccxt-ir first: pip install ccxt-ir")
    sys.exit(1)

def test_arzplus_ccxt():
    exchange = ccxt.arzplus({
        'enableRateLimit': True,
    })
    
    # تلاش برای فرمت‌های مختلف نماد
    symbols = ['BTC/IRT', 'BTCIRT', 'BTC/RLS']
    timeframe = '4h'
    
    for symbol in symbols:
        print(f"\n--- Testing symbol: {symbol} ---")
        try:
            # دریافت ۱۰۰ کندل آخر
            ohlcv = exchange.fetch_ohlcv(symbol, timeframe, limit=100)
            if ohlcv:
                print(f"✅ SUCCESS! Got {len(ohlcv)} candles.")
                print("First candle (timestamp, open, high, low, close, volume):")
                print(ohlcv[0])
                print("Last candle:")
                print(ohlcv[-1])
                return
            else:
                print("❌ No data returned.")
        except Exception as e:
            print(f"❌ Error: {e}")

if __name__ == "__main__":
    test_arzplus_ccxt()
