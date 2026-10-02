import requests
import json
import time
from datetime import datetime

WALLEX_API = "https://api.wallex.ir"
BINANCE_API = "https://api.binance.com"


def fetch_wallex():
    """BTC/TMN و USDT/TMN از والکس"""
    try:
        r = requests.get(f"{WALLEX_API}/v1/markets", timeout=15)
        if r.status_code != 200:
            print(f"WALLEX: {r.status_code}")
            return {}

        data = r.json()
        symbols = data.get("result", {}).get("symbols", {})

        result = {}
        for sym in ["BTCTMN", "USDT TMN", "USDTTMN", "BTCTMN", "USDTIRT"]:
            sym_clean = sym.replace(" ", "")
            if sym_clean in symbols:
                s = symbols[sym_clean]
                stats = s.get("stats", {})
                result[sym_clean] = {
                    "last": float(stats.get("lastPrice", 0)),
                    "bid": float(stats.get("bidPrice", 0)),
                    "ask": float(stats.get("askPrice", 0)),
                }

        # لیست همه‌ی symbolها برای پیدا کردن USDT
        usdt_symbols = [k for k in symbols.keys() if "USDT" in k and "TMN" in k]
        if usdt_symbols and not any("USDT" in k for k in result.keys()):
            print(f"Available USDT symbols: {usdt_symbols}")

        return result
    except Exception as e:
        print(f"WALLEX ERROR: {e}")
        return {}


def fetch_binance():
    """BTC/USDT از Binance"""
    try:
        r = requests.get(
            f"{BINANCE_API}/api/v3/ticker/bookTicker",
            params={"symbol": "BTCUSDT"},
            timeout=15,
        )
        if r.status_code != 200:
            print(f"BINANCE: {r.status_code}")
            return {}

        data = r.json()
        bid = float(data.get("bidPrice", 0))
        ask = float(data.get("askPrice", 0))
        mid = (bid + ask) / 2

        return {
            "BTCUSDT": {
                "last": mid,
                "bid": bid,
                "ask": ask,
            }
        }
    except Exception as e:
        print(f"BINANCE ERROR: {e}")
        return {}


def fetch_coingecko():
    """BTC/USDT از CoinGecko (fallback)"""
    try:
        r = requests.get(
            "https://api.coingecko.com/api/v3/simple/price",
            params={"ids": "bitcoin", "vs_currencies": "usd"},
            timeout=15,
        )
        if r.status_code != 200:
            return {}

        data = r.json()
        price = float(data.get("bitcoin", {}).get("usd", 0))
        return {"BTCUSDT": {"last": price, "bid": price, "ask": price}}
    except Exception as e:
        print(f"COINGECKO ERROR: {e}")
        return {}


def main():
    print("=" * 60)
    print("  TEST PRICE COMPONENTS")
    print("=" * 60)
    print(f"Time: {datetime.now().isoformat()}")

    # Wallex
    wallex = fetch_wallex()
    print(f"\nWALLEX ({len(wallex)}):")
    for k, v in wallex.items():
        print(f"  {k}: last={v['last']:,.0f} | bid={v['bid']:,.0f} | ask={v['ask']:,.0f}")

    # Binance
    binance = fetch_binance()
    if not binance:
        print("\nBinance failed, trying CoinGecko...")
        binance = fetch_coingecko()
    print(f"\nBTC/USDT ({len(binance)}):")
    for k, v in binance.items():
        print(f"  {k}: {v['last']:,.2f}")

    # ═══ محاسبه‌ی اجزای قیمت ═══
    print("\n" + "=" * 60)
    print("  RELATIONSHIP ANALYSIS")
    print("=" * 60)

    btc_tmn = wallex.get("BTCTMN", {}).get("last", 0)
    usdt_tmn = wallex.get("USDTTMN", {}).get("last", 0)
    btc_usdt = binance.get("BTCUSDT", {}).get("last", 0)

    print(f"\nBTC/TMN:  {btc_tmn:,.0f} تومان")
    print(f"USDT/TMN: {usdt_tmn:,.0f} تومان")
    print(f"BTC/USDT: {btc_usdt:,.2f}")

    if btc_usdt > 0 and usdt_tmn > 0:
        implied_btc_tmn = btc_usdt * usdt_tmn
        diff = btc_tmn - implied_btc_tmn
        diff_pct = (diff / implied_btc_tmn) * 100 if implied_btc_tmn else 0

        print(f"\n📊 Implied BTC/TMN (BTC/USDT × USDT/TMN):")
        print(f"  {implied_btc_tmn:,.0f} تومان")
        print(f"  اختلاف با قیمت واقعی: {diff:+,.0f} ({diff_pct:+.2f}%)")

        if abs(diff_pct) < 1:
            print(f"  ✅ قیمت‌ها هماهنگ هستن")
        else:
            print(f"  ⚠️ اختلاف قابل توجه - فرصت آربیتراژ؟")

    # ═══ ذخیره ═══
    output = {
        "time": datetime.now().isoformat(),
        "wallex": wallex,
        "binance": binance,
        "btc_tmn": btc_tmn,
        "usdt_tmn": usdt_tmn,
        "btc_usdt": btc_usdt,
    }

    with open("price_components_output.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    print(f"\n✅ Saved: price_components_output.json")


if __name__ == "__main__":
    main()
