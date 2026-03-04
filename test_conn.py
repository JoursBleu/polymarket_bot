"""Quick connectivity test for Polymarket APIs."""
import sys
try:
    import requests
    print("requests OK")
except ImportError:
    print("requests NOT installed")
    sys.exit(1)

urls = [
    "https://gamma-api.polymarket.com/markets?limit=2&active=true&closed=false",
    "https://gamma-api.polymarket.com/events?limit=2&active=true&closed=false",
    "https://clob.polymarket.com/time",
]

for url in urls:
    try:
        r = requests.get(url, timeout=15)
        body = r.text[:120].replace("\n", " ")
        print(f"[{r.status_code}] {url[:60]}... => {body}")
    except Exception as e:
        print(f"[ERR] {url[:60]}... => {e}")
