#!/usr/bin/env python3
"""深入分析多结果事件: 哪些是真正互斥的, 哪些不是"""
import requests, json, time

GAMMA = 'https://gamma-api.polymarket.com'
sess = requests.Session()
sess.headers['User-Agent'] = 'Mozilla/5.0'

events = []
for page in range(5):
    data = sess.get(f'{GAMMA}/events?limit=100&offset={page*100}&active=true&closed=false', timeout=15).json()
    if not data: break
    events.extend(data)
    time.sleep(0.3)

print(f'总事件: {len(events)}')
print()

# 找出 Yes_sum < 1.05 的多结果事件并分析细节
interesting = []
for ev in events:
    subs = ev.get('markets', [])
    if len(subs) < 3: continue
    yes_sum = 0
    sub_details = []
    valid = True
    for m in subs:
        outcome_prices = m.get('outcomePrices')
        p = 0
        if outcome_prices and isinstance(outcome_prices, list) and len(outcome_prices) >= 1:
            p = float(outcome_prices[0])
        elif outcome_prices and isinstance(outcome_prices, str):
            try:
                parsed = json.loads(outcome_prices)
                p = float(parsed[0])
            except:
                valid = False
                continue
        else:
            valid = False
            continue
        yes_sum += p
        sub_details.append({
            'q': m.get('question', '')[:70],
            'yes': p,
            'neg_risk': m.get('negRisk', False),
            'vol': float(m.get('volume', 0) or 0),
            'liq': float(m.get('liquidity', 0) or 0),
        })

    if valid and len(subs) >= 3 and yes_sum < 1.05:
        interesting.append({
            'title': ev.get('title', '')[:70],
            'slug': ev.get('slug', ''),
            'neg_risk': ev.get('negRisk', False),
            'n': len(subs),
            'yes_sum': yes_sum,
            'gap_pct': (yes_sum - 1.0) * 100,
            'subs': sub_details,
        })

interesting.sort(key=lambda x: x['yes_sum'])

print(f'Yes_sum < 1.05 的多结果事件: {len(interesting)}')
print()

for ev in interesting[:15]:
    neg_tag = '[NEG-RISK]' if ev['neg_risk'] else '[NORMAL]'
    arb_tag = ' *** POTENTIAL ARB' if ev['yes_sum'] < 1.0 else ''
    print(f'=== {neg_tag} {ev["title"]}{arb_tag} ===')
    print(f'  {ev["n"]}选项, Yes_sum=${ev["yes_sum"]:.4f}, gap={ev["gap_pct"]:+.2f}%')
    print(f'  子市场:')
    for s in ev['subs']:
        nr = ' [neg_risk]' if s['neg_risk'] else ''
        print(f'    Y=${s["yes"]:.3f} vol=${s["vol"]:>10,.0f} liq=${s["liq"]:>8,.0f}{nr} | {s["q"]}')
    print()

# 检查 neg-risk 分布
print('=== neg-risk 标记分布 ===')
all_neg = sum(1 for ev in interesting if ev['neg_risk'])
all_normal = len(interesting) - all_neg
print(f'  neg-risk: {all_neg}, normal: {all_normal}')

# 也检查所有多选事件的 neg-risk 分布
print()
print('=== 所有多选事件 neg-risk 统计 ===')
all_multi = [ev for ev in events if len(ev.get('markets', [])) >= 3]
neg_count = sum(1 for ev in all_multi if ev.get('negRisk', False))
print(f'  总多选事件: {len(all_multi)}, neg-risk: {neg_count}, normal: {len(all_multi)-neg_count}')
