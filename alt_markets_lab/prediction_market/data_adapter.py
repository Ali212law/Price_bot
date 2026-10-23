import requests
import pandas as pd
import json
import os

def fetch_markets(limit=200):
    url = f"https://gamma-api.polymarket.com/markets?limit={limit}&active=true&closed=false&order=volume24hr&ascending=false"
    try:
        r = requests.get(url, timeout=20)
        if r.status_code == 200:
            return r.json() if isinstance(r.json(), list) else []
        return []
    except Exception as e:
        print(f"Error: {e}")
        return []

def get_token_ids(market):
    """Returns a list of both token_ids (Yes and No) if available."""
    tokens = []
    clob = market.get('clobTokenIds')
    if clob:
        try:
            ids = json.loads(clob) if isinstance(clob, str) else clob
            if isinstance(ids, list):
                tokens.extend(ids)
        except: pass
    
    tok = market.get('tokens')
    if tok:
        try:
            if isinstance(tok, str): tok = json.loads(tok)
            if isinstance(tok, list):
                for t in tok:
                    if isinstance(t, dict) and t.get('token_id'):
                        tokens.append(t['token_id'])
        except: pass
    
    return list(set(tokens))  # Remove duplicates

def fetch_price_history(token_id, interval='max', fidelity=60):
    url = f"https://clob.polymarket.com/prices-history?market={token_id}&interval={interval}&fidelity={fidelity}"
    try:
        r = requests.get(url, timeout=30)
        if r.status_code == 200:
            data = r.json()
            if isinstance(data, dict):
                return data.get("history", [])
            elif isinstance(data, list):
                return data
        return []
    except: return []

def analyze_volatility(history):
    """Returns price range and std to determine if token is tradeable."""
    if len(history) < 20:
        return None
    prices = [float(p.get('p', 0)) for p in history]
    prices = [p for p in prices if 0.01 < p < 0.99]  # Filter extremes
    if len(prices) < 20:
        return None
    import statistics
    return {
        "min": min(prices),
        "max": max(prices),
        "mean": statistics.mean(prices),
        "std": statistics.stdev(prices) if len(prices) > 1 else 0,
        "count": len(prices)
    }

def main():
    os.makedirs("data", exist_ok=True)
    print("=== Polymarket Data Adapter (Volatility-Aware) ===")
    
    print("\nStep 1: Fetching top markets by 24h volume...")
    markets = fetch_markets(limit=200)
    print(f"Received {len(markets)} markets.")
    
    if not markets:
        print("No markets.")
        return
    
    print("\nStep 2: Searching for a market with active price movement...")
    best_candidate = None
    best_std = -1
    
    # Check top 30 markets to avoid rate limits
    for i, m in enumerate(markets[:30]):
        question = m.get('question', 'Unknown')[:60]
        token_ids = get_token_ids(m)
        if not token_ids:
            continue
        
        print(f"  [{i+1}/30] Checking: {question}...")
        
        for token_id in token_ids:
            history = fetch_price_history(token_id)
            stats = analyze_volatility(history)
            if stats and stats['std'] > best_std and stats['count'] >= 50:
                best_std = stats['std']
                best_candidate = {
                    "market": m,
                    "token_id": token_id,
                    "history": history,
                    "stats": stats
                }
                print(f"       → New best: std={stats['std']:.4f}, range=[{stats['min']:.3f}, {stats['max']:.3f}]")
            break  # Only check first token per market to save API calls
    
    if not best_candidate:
        print("\nNo market with sufficient volatility found.")
        return
    
    m = best_candidate["market"]
    history = best_candidate["history"]
    stats = best_candidate["stats"]
    
    print(f"\n✅ Selected: {m.get('question')}")
    print(f"   Slug: {m.get('slug')}")
    print(f"   Token: {best_candidate['token_id'][:30]}...")
    print(f"   Price Range: [{stats['min']:.4f}, {stats['max']:.4f}]")
    print(f"   Mean: {stats['mean']:.4f} | Std: {stats['std']:.4f}")
    print(f"   Data Points: {stats['count']}")
    
    # Build DataFrame
    df = pd.DataFrame(history)
    df['t'] = pd.to_datetime(df['t'], unit='s', utc=True)
    df.set_index('t', inplace=True)
    df.rename(columns={'p': 'close'}, inplace=True)
    
    # Use lowercase 'h' (avoids deprecation warning)
    resampled = df['close'].resample('4h').agg(['first', 'max', 'min', 'last'])
    resampled.columns = ['open', 'high', 'low', 'close']
    resampled['volume'] = 0
    resampled.dropna(inplace=True)
    resampled.reset_index(inplace=True)
    resampled.rename(columns={'t': 'timestamp'}, inplace=True)
    resampled['timestamp'] = (resampled['timestamp'].astype('int64') // 10**6)
    
    safe_slug = m.get('slug', 'unknown').replace('/', '_').replace('?', '_')[:50]
    output_file = f"data/{safe_slug}.csv"
    resampled.to_csv(output_file, index=False)
    print(f"\n✅ Saved {len(resampled)} candles to {output_file}")

if __name__ == "__main__":
    main()
