#!/usr/bin/env python3
"""Quick debug: check raw market data structure"""
import requests, json
sess = requests.Session()
sess.headers['User-Agent'] = 'Mozilla/5.0'
data = sess.get('https://gamma-api.polymarket.com/markets?limit=3&active=true&closed=false', timeout=15).json()
for m in data[:2]:
    print('tokens:', json.dumps(m.get('tokens'), indent=2)[:300])
    print('outcomePrices:', m.get('outcomePrices'))
    print('clobTokenIds:', m.get('clobTokenIds'))
    print('question:', m.get('question','')[:60])
    print('volume:', m.get('volume'))
    print('liquidity:', m.get('liquidity'))
    print('---')
