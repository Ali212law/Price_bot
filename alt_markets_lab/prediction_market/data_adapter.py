import requests
import pandas as pd
import json
import time
import os
from datetime import datetime, timezone

def find_active_market(min_volume=10000):
    """Auto-discovers a high-volume active market."""
    url = "https://gamma-api.polymarket.com/markets?limit=50&active=true&closed=false&order=volume&ascending=false"
    try:
        r = requests.get(url, timeout=15)
        if r.status_code == 200:
            markets = r.json()
            for m in markets:
                vol = float(m.get('volume', 0))
                if vol >= min_volume and m.get('tokens'):
                    return m
        return None
    except Exception as e:
        print(f"Error fetching markets: {e}")
        return None

def fetch_market_info(slug):
    """Fallback: fetch market info by slug."""
    url = f"https://gamma-api.polymarket.com/markets?slug={slug}"
    try:
        r = requests.get(url, timeout=15)
        if r.status_code == 200:
            data = r.json()
            if data and isinstance(data, list) and len(data) > 0:
                return data[0]
        return None
    except Exception as e:
        print(f"Error: {e}")
        return None

def fetch_price_history(token_id, interval='max', fidelity=60):
    """Fetch price history for a token. FIXED: response has 'history' field."""
    url = f"https://clob.polymarket.com/prices-history?market={token_id}&interval={interval}&fidelity={fidelity}"
    try:
        r = requests.get(url, timeout=30)
        if r.status_code == 200:
            data = r.json()
            # FIX: The response is {"history": [{"t":..., "p":...}, ...]}
            return data.get("history", [])
        else:
            print(f"HTTP {r.status_code}: {r.text[:200]}")
            return None
    except Exception as e:
        print(f"Error fetching history: {e}")
        return None

def main():
    print("Auto-discovering an active market on Polymarket...")
    market = find_active_market(min_volume=10000)
    
    if not market:
        print("Could not find any active market. Trying fallback slug...")
        market = fetch_market_info("will-trump-win-2028")
    
    if not market:
        print("No active market found. Please try again later.")
        return
    
    slug = market.get('slug', 'unknown')
    question = market.get('question', 'Unknown')
    volume = market.get('volume', 0)
    tokens = market.get('tokens', [])
    
    print(f"Selected market: {question}")
    print(f"Slug: {slug}")
    print(f"Volume: ${float(volume):,.0f}")
    print(f"Tokens: {len(tokens)}")
    
    if not tokens:
        print("No tokens available for this market.")
        return
    
    # Pick the first token (usually "Yes")
    token_id = tokens[0].get('token_id')
    if not token_id:
        print("No token_id found.")
        return
    
    print(f"Token ID: {token_id}")
    print("Fetching price history...")
    history = fetch_price_history(token_id, interval='max', fidelity=60)
    
    if not history or len(history) < 10:
        print(f"Not enough price history (got {len(history) if history else 0} points).")
        return
    
    print(f"Received {len(history)} price points.")
    
    # Convert to DataFrame
    df = pd.DataFrame(history)
    df['t'] = pd.to_datetime(df['t'], unit='s', utc=True)
    df.set_index('t', inplace=True)
    df.rename(columns={'p': 'close'}, inplace=True)
    
    # Resample to 4H candles (OHLC = close for prediction markets)
    resampled = df['close'].resample('4H').agg(['first', 'max', 'min', 'last'])
    resampled.columns = ['open', 'high', 'low', 'close']
    resampled['volume'] = 0
    resampled.dropna(inplace=True)
    resampled.reset_index(inplace=True)
    resampled.rename(columns={'t': 'timestamp'}, inplace=True)
    resampled['timestamp'] = (resampled['timestamp'].astype('int64') // 10**6)
    
    # Save to CSV
    os.makedirs("data", exist_ok=True)
    safe_slug = slug.replace('/', '_').replace('?', '_')[:50]
    output_file = f"data/{safe_slug}.csv"
    resampled.to_csv(output_file, index=False)
    
    print(f"\nSaved {len(resampled)} candles to {output_file}")
    print(f"Date range: {resampled['timestamp'].iloc[0]} to {resampled['timestamp'].iloc[-1]}")
    print(f"Price range: {resampled['close'].min():.4f} to {resampled['close'].max():.4f}")
    print("\nFirst 3 rows:")
    print(resampled.head(3))
    print("\nLast 3 rows:")
    print(resampled.tail(3))

if __name__ == "__main__":
    main()
