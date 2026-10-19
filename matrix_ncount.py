# matrix_ncount.py - Audit n per matrix cell + PF/Expectancy gate
import json

MIN_N = 15
PF_MIN = 1.2

def main():
    try:
        with open("walkforward_results.json", "r", encoding="utf-8") as f:
            results = json.load(f)
    except FileNotFoundError:
        print("MISSING: walkforward_results.json not found. Run walkforward_m8.py first.")
        return

    print("Symbol | Win | n | WR% | Net% | PF | MaxDD% | Status")
    for sym, info in results.items():
        for idx, w in enumerate(info.get("windows", [])):
            n, wr, netp, pf, dd = w.get("n", 0), w.get("wr", 0), w.get("net_pct", 0), w.get("pf", 0), w.get("max_dd_pct", 0)
            
            if n < MIN_N: status = "INVALID_n<15"
            elif pf < PF_MIN: status = "WEAK_PF"
            else: status = "VALID" if netp > 0 else "VALID_NEG"
            
            print(f"{sym} W{idx+1} | {info['signal']} | {n} | {wr} | {netp} | {pf} | {dd} | {status}")

if __name__ == "__main__":
    main()
