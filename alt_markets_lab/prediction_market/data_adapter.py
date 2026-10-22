import requests
import pandas as pd
import json
import time
from datetime import datetime, timezone

def fetch_market_info(slug):
    """Fetch market info from Gamma API to get token IDs."""
    url = f"https://gamma-api.polymarket.com/markets?slug={slug}"
    try:
        r = requests.get(url, timeout=15)
        if r.status_code == 200:
            data = r.json()
            if data and isinstance(data, list) and len(data) > 0:
                market = data[0]
                tokens = market.get('tokens', [])
                if tokens:
                    # Return the first token (usually 'Yes')
                    return tokens[0].get('token_id')
        return None
    except Exception as e:
        print(f"Error fetching market info: {e}")
        return None

def fetch_price_history(token_id, interval='max', fidelity=60):
    """Fetch price history for a token."""
    url = f"https://clob.polymarket.com/prices-history?market={token_id}&interval={interval}&fidelity={fidelity}"
    try:
        r = requests.get(url, timeout=30)
        if r.status_code == 200:
            data = r.json()
            # The response is a list of dicts with 't' (timestamp) and 'p' (price)
            return data
        else:
            print(f"HTTP {r.status_code}: {r.text}")
            return None
    except Exception as e:
        print(f"Error fetching price history: {e}")
        return None

def main():
    # Example market slug: "will-bitcoin-hit-100k-by-december-2024"
    # You can change this to any active market on Polymarket
    market_slug = "will-bitcoin-hit-100k-by-december-2024"
    
    print(f"Fetching market info for: {market_slug}")
    token_id = fetch_market_info(market_slug)
    if not token_id:
        print("Could not find token ID. Market may not exist or be inactive.")
        return
        
    print(f"Token ID: {token_id}")
    print("Fetching price history (this may take a moment)...")
    history = fetch_price_history(token_id, interval='max', fidelity=60)
    if not history:
        print("Failed to fetch price history.")
        return
        
    # Convert to DataFrame
    df = pd.DataFrame(history)
    df['t'] = pd.to_datetime(df['t'], unit='s', utc=True)
    df.set_index('t', inplace=True)
    df.rename(columns={'p': 'close'}, inplace=True)
    
    # Resample to 4H candles
    # Since we only have close prices, we set open=high=low=close and volume=0
    resampled = df['close'].resample('4H').agg(['first', 'max', 'min', 'last'])
    resampled.columns = ['open', 'high', 'low', 'close']
    resampled['volume'] = 0
    resampled.dropna(inplace=True)
    resampled.reset_index(inplace=True)
    resampled.rename(columns={'t': 'timestamp'}, inplace=True)
    resampled['timestamp'] = resampled['timestamp'].astype('int64') // 10**6  # ms
    
    # Save to CSV
    output_file = f"data/{market_slug.replace('/', '_')}.csv"
    import os
    os.makedirs("data", exist_ok=True)
    resampled.to_csv(output_file, index=False)
    print(f"Saved {len(resampled)} candles to {output_file}")
    print(resampled.head())
    print(resampled.tail())

if __name__ == "__main__":
    main()
