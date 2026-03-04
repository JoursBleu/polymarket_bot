"""Debug: test scanner fetch step by step."""
import sys
sys.path.insert(0, ".")
import config
import scanner

print("=== fetch_markets page 0 ===")
m = scanner.fetch_markets(limit=5, offset=0)
print(f"Got {len(m)} markets")
if m:
    for x in m[:2]:
        q = x.get("question", "?")[:60]
        t = x.get("tokens", [])
        print(f"  Q: {q}  tokens: {len(t)}")

print("\n=== fetch_events page 0 ===")
e = scanner.fetch_events(limit=5, offset=0)
print(f"Got {len(e)} events")
if e:
    for x in e[:2]:
        title = x.get("title", "?")[:60]
        mk = x.get("markets", [])
        print(f"  T: {title}  markets: {len(mk)}")

print("\n=== scan_single_market_arb ===")
all_m = scanner.fetch_markets(limit=20, offset=0)
print(f"Fetched {len(all_m)} markets for single arb scan")
opps = scanner.scan_single_market_arb(all_m)
print(f"Found {len(opps)} single-market arb opportunities")

print("\n=== Done ===")
