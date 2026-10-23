import requests
import pandas as pd
import json
import os

def fetch_markets(limit=100):
    """Fetches a list of active markets from Polymarket."""
    url = f"https://gamma-api.polymarket.com/markets?limit={limit}&active=true&closed=false"
    try:
        r = requests.get(url, timeout=20)
        if r.status_code == 200:
            data = r.json()
            if isinstance(data, list):
                return data
        print(f"Unexpected response: HTTP {r.status_code} - {r.text[:200]}")
        return []
    except Exception as e:
        print(f"Error fetching markets: {e}")
        return []

def get_token_id(market):
    """Extracts token_id from various possible fields."""
    # Try clobTokenIds first (JSON-encoded string)
    clob = market.get('clobTokenIds')
    if clob:
        try:
            tokens = json.loads(clob) if isinstance(clob, str) else clob
            if tokens and len(tokens) > 0:
                return tokens[0]
        except: pass
    
    # Try tokens field
    tokens = market.get('tokens')
    if tokens:
        try:
            if isinstance(tokens, str):
                tokens = json.loads(tokens)
            if isinstance(tokens, list) and len(tokens) > 0:
                if isinstance(tokens[0], dict):
                    return tokens[0].get('token_id')
                return tokens[0]
        except: pass
    return None

def select_best_market(markets):
    """Selects the market with highest volume that has a valid token."""
    best = None
    best_vol = -1
    for m in markets:
        vol = float(m.get('volume', 0) or 0)
        token_id = get_token_id(m)
        if token_id and vol > best_vol:
            best = m
            best_vol = vol
    return best

def fetch_price_history(token_id, interval='max', fidelity=60):
    """Fetch price history for a token."""
    url = f"https://clob.polymarket.com/prices-history?market={token_id}&interval={interval}&fidelity={fidelity}"
    try:
        r = requests.get(url, timeout=30)
        if r.status_code == 200:
            data = r.json()
            if isinstance(data, dict):
                return data.get("history", [])
            elif isinstance(data, list):
                return data
        print(f"HTTP {r.status_code}: {r.text[:200]}")
        return []
    except Exception as e:
        print(f"Error fetching history: {e}")
        return []

def main():
    os.makedirs("data", exist_ok=True)
    print("=== Polymarket Data Adapter (Robust Mode) ===")
    
    print("\nStep 1: Fetching active markets...")
    markets = fetch_markets(limit=100)
    print(f"Received {len(markets)} markets.")
    
    if not markets:
        print("No markets. Exiting.")
        return
    
    print("\nStep 2: Selecting best market...")
    best = select_best_market(markets)
    if not best:
        print("No market with valid token. Dumping first market for inspection:")
        print(json.dumps(markets[0], indent=2)[:2000])
        return
    
    slug = best.get('slug', 'unknown')
    question = best.get('question', 'Unknown')
    volume = float(best.get('volume', 0) or 0)
    token_id = get_token_id(best)
    
    print(f"\nSelected: {question}")
    print(f"Slug: {slug} | Volume: ${volume:,.0f} | Token: {token_id}")
    
    print("\nStep 3: Fetching price history...")
    history = fetch_price_history(token_id)
    print(f"Received {len(history)} price points.")
    
    if len(history) < 10:
        print("Not enough data. Exiting.")
        return
    
    print("\nStep 4: Resampling to 4H candles...")
    df = pd.DataFrame(history)
    df['t'] = pd.to_datetime(df['t'], unit='s', utc=True)
    df.set_index('t', inplace=True)
    df.rename(columns={'p': 'close'}, inplace=True)
    
    resampled = df['close'].resample('4H').agg(['first', 'max', 'min', 'last'])
    resampled.columns = ['open', 'high', 'low', 'close']
    resampled['volume'] = 0
    resampled.dropna(inplace=True)
    resampled.reset_index(inplace=True)
    resampled.rename(columns={'t': 'timestamp'}, inplace=True)
    resampled['timestamp'] = (resampled['timestamp'].astype('int64') // 10**6)
    
    safe_slug = slug.replace('/', '_').replace('?', '_')[:50]
    output_file = f"data/{safe_slug}.csv"
    resampled.to_csv(output_file, index=False)
    print(f"\n✅ Saved {len(resampled)} candles to {output_file}")
    print(f"First: {resampled.iloc[0].to_dict()}")
    print(f"Last:  {resampled.iloc[-1].to_dict()}")

if __name__ == "__main__":
    main()
