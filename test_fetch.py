"""Minimal fetch test."""
import sys, time
sys.path.insert(0, ".")

print("Importing scanner...", flush=True)
from scanner import fetch_markets, fetch_events, fetch_json
print("Import OK", flush=True)

print("\nTest 1: raw fetch_json", flush=True)
t0 = time.time()
data = fetch_json("https://gamma-api.polymarket.com/markets?limit=3&active=true&closed=false")
print(f"  fetch_json took {time.time()-t0:.2f}s, got {type(data)}", flush=True)
if isinstance(data, list):
    print(f"  len={len(data)}", flush=True)
    if data:
        print(f"  first question: {data[0].get('question','?')[:60]}", flush=True)

print("\nTest 2: fetch_markets", flush=True)
t0 = time.time()
m = fetch_markets(limit=5, offset=0)
print(f"  fetch_markets took {time.time()-t0:.2f}s, got {len(m)} markets", flush=True)

print("\nTest 3: fetch_events", flush=True)
t0 = time.time()
e = fetch_events(limit=5, offset=0)
print(f"  fetch_events took {time.time()-t0:.2f}s, got {len(e)} events", flush=True)

print("\nAll done!", flush=True)
