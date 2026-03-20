#!/usr/bin/env python3
"""分析 Polymarket 市场定价效率和潜在机会"""
import json, time, sys, statistics

try:
    import requests
except ImportError:
    print('need requests'); sys.exit(1)

GAMMA = 'https://gamma-api.polymarket.com'
sess = requests.Session()
sess.headers['User-Agent'] = 'Mozilla/5.0'

# 拉取活跃市场
markets = []
for page in range(5):
    data = sess.get(f'{GAMMA}/markets?limit=100&offset={page*100}&active=true&closed=false', timeout=15).json()
    if not data: break
    markets.extend(data)
    time.sleep(0.3)

print(f'总市场数: {len(markets)}')
print()

# 分析 Yes+No 价差分布
spreads = []
for m in markets:
    try:
        # 方式1: outcomePrices 字段 (字符串数组 ["0.55", "0.45"])
        outcome_prices = m.get('outcomePrices')
        if outcome_prices and isinstance(outcome_prices, list) and len(outcome_prices) >= 2:
            yes_p = float(outcome_prices[0])
            no_p = float(outcome_prices[1])
        elif outcome_prices and isinstance(outcome_prices, str):
            # 有时是 JSON 字符串
            parsed = json.loads(outcome_prices)
            if len(parsed) >= 2:
                yes_p = float(parsed[0])
                no_p = float(parsed[1])
            else:
                continue
        else:
            # 方式2: tokens 字段
            tokens = m.get('tokens', [])
            if not tokens or len(tokens) < 2:
                continue
            prices = {t['outcome'].lower(): float(t.get('price', 0)) for t in tokens}
            if 'yes' not in prices or 'no' not in prices:
                continue
            yes_p = prices['yes']
            no_p = prices['no']

        if yes_p <= 0 or no_p <= 0:
            continue
        total = yes_p + no_p
        vol = float(m.get('volume', 0) or 0)
        liq = float(m.get('liquidity', 0) or 0)
        spread_pct = (total - 1.0) * 100
        spreads.append({
            'q': m.get('question', '')[:60],
            'yes': yes_p,
            'no': no_p,
            'total': total,
            'spread_pct': spread_pct,
            'vol': vol,
            'liq': liq,
        })
    except:
        continue

spreads.sort(key=lambda x: x['total'])

print('=== Yes+No 价差分布 ===')
below_1 = [s for s in spreads if s['total'] < 1.0]
at_1 = [s for s in spreads if abs(s['total'] - 1.0) < 0.005]
above_1 = [s for s in spreads if s['total'] > 1.0]
print(f'  Yes+No < $1.00:  {len(below_1)} ({len(below_1)/len(spreads)*100:.1f}%)')
print(f'  Yes+No ~ $1.00:  {len(at_1)} ({len(at_1)/len(spreads)*100:.1f}%)')
print(f'  Yes+No > $1.00:  {len(above_1)} ({len(above_1)/len(spreads)*100:.1f}%)')
print()

# 最便宜的 (最接近套利)
print('=== 最接近套利的市场 (Yes+No 最低) ===')
for s in spreads[:10]:
    print(f'  ${s["total"]:.4f} (Y={s["yes"]:.3f} N={s["no"]:.3f}) spread={s["spread_pct"]:+.2f}% vol=${s["vol"]:,.0f} liq=${s["liq"]:,.0f}')
    print(f'    {s["q"]}')

print()
print('=== 溢价最高的市场 (Yes+No 最高) ===')
for s in spreads[-5:]:
    print(f'  ${s["total"]:.4f} (Y={s["yes"]:.3f} N={s["no"]:.3f}) spread={s["spread_pct"]:+.2f}% vol=${s["vol"]:,.0f} liq=${s["liq"]:,.0f}')
    print(f'    {s["q"]}')

# 分析多结果事件
print()
print('=== 多结果事件分析 ===')
events = []
for page in range(5):
    data = sess.get(f'{GAMMA}/events?limit=100&offset={page*100}&active=true&closed=false', timeout=15).json()
    if not data: break
    events.extend(data)
    time.sleep(0.3)

multi_events = []
for ev in events:
    subs = ev.get('markets', [])
    if len(subs) < 3: continue
    yes_sum = 0
    valid = True
    for m in subs:
        # 尝试 outcomePrices
        outcome_prices = m.get('outcomePrices')
        found = False
        if outcome_prices and isinstance(outcome_prices, list) and len(outcome_prices) >= 1:
            p = float(outcome_prices[0])
            if p > 0:
                yes_sum += p
                found = True
        elif outcome_prices and isinstance(outcome_prices, str):
            try:
                parsed = json.loads(outcome_prices)
                if len(parsed) >= 1:
                    p = float(parsed[0])
                    if p > 0:
                        yes_sum += p
                        found = True
            except:
                pass
        if not found:
            tokens = m.get('tokens', [])
            for t in tokens:
                if t.get('outcome','').lower() == 'yes':
                    p = float(t.get('price', 0))
                    if p <= 0: valid = False
                    yes_sum += p
                    found = True
                    break
        if not found:
            valid = False
    if valid and len(subs) >= 3:
        multi_events.append({
            'title': ev.get('title', '')[:60],
            'n': len(subs),
            'yes_sum': yes_sum,
            'gap': yes_sum - 1.0,
            'gap_pct': (yes_sum - 1.0) * 100,
        })

multi_events.sort(key=lambda x: x['yes_sum'])
print(f'多结果事件 (>=3选项): {len(multi_events)}')
print()
print('--- Yes总和最低 (越低越接近正向套利) ---')
for e in multi_events[:10]:
    marker = ' *** ARB!' if e['yes_sum'] < 1.0 else ''
    print(f'  {e["n"]}选项 Yes_sum=${e["yes_sum"]:.4f} gap={e["gap_pct"]:+.2f}%{marker}')
    print(f'    {e["title"]}')

print()
print('--- Yes总和最高 (高溢价=高maker利润) ---')
for e in multi_events[-5:]:
    print(f'  {e["n"]}选项 Yes_sum=${e["yes_sum"]:.4f} gap={e["gap_pct"]:+.2f}%')
    print(f'    {e["title"]}')

# 统计分布
if spreads:
    totals = [s['total'] for s in spreads]
    print(f'\n=== 统计摘要 ===')
    print(f'  二元市场 Yes+No: mean={statistics.mean(totals):.4f} median={statistics.median(totals):.4f} stdev={statistics.stdev(totals):.4f}')
    print(f'  范围: [{min(totals):.4f}, {max(totals):.4f}]')
if multi_events:
    ys = [e['yes_sum'] for e in multi_events]
    print(f'  多结果 Yes_sum: mean={statistics.mean(ys):.4f} median={statistics.median(ys):.4f} stdev={statistics.stdev(ys):.4f}')
    print(f'  范围: [{min(ys):.4f}, {max(ys):.4f}]')
