"""
Polymarket 套利机器人 — 市场扫描器
====================================
从 Gamma API + CLOB API 获取市场数据, 发现套利机会

套利类型:
  1. 单市场套利: Yes + No < $1.00
  2. 多结果事件套利: 所有互斥选项的 Yes 之和 < $1.00
  3. 跨时间套利: 同一事件在不同到期日的价格差
"""

import json
import logging
import time
import urllib.request
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

try:
    import requests as _requests
    HAS_REQUESTS = True
except ImportError:
    HAS_REQUESTS = False

import config

logger = logging.getLogger(__name__)


# ══════════════════════════════════════════════════
#   数据结构
# ══════════════════════════════════════════════════

@dataclass
class TokenInfo:
    """一个市场中的单个 token (Yes 或 No)"""
    token_id: str
    outcome: str  # "Yes" / "No"
    price: float  # 当前中间价
    winner: bool = False


@dataclass
class MarketInfo:
    """一个二元市场"""
    condition_id: str
    question: str
    slug: str
    tokens: List[TokenInfo] = field(default_factory=list)
    volume: float = 0.0
    liquidity: float = 0.0
    end_date: str = ""
    active: bool = True
    neg_risk: bool = False  # 是否属于 neg-risk 事件组


@dataclass
class ArbOpportunity:
    """一个套利机会"""
    arb_type: str  # "single" / "multi_yes" / "multi_no"
    description: str
    markets: List[MarketInfo]
    tokens_to_buy: List[Tuple[str, str, float]]  # [(token_id, outcome, price), ...]
    total_cost: float  # 买入所有 token 的总成本 (per $1 赔付)
    guaranteed_payout: float  # 保证赔付
    gross_profit_pct: float  # 扣费前利润率
    net_profit_pct: float  # 扣费后利润率
    total_volume: float = 0.0
    total_liquidity: float = 0.0
    event_title: str = ""
    timestamp: float = 0.0

    def __post_init__(self):
        self.timestamp = time.time()


# ══════════════════════════════════════════════════
#   HTTP 工具
# ══════════════════════════════════════════════════

_session = None


def _get_session():
    """获取 HTTP 会话 (requests 优先, 回退 urllib)"""
    global _session
    if _session is not None:
        return _session

    if HAS_REQUESTS:
        _session = _requests.Session()
        _session.headers.update({
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "Accept": "application/json",
        })
        if config.HTTP_PROXY:
            _session.proxies = {
                "http": config.HTTP_PROXY,
                "https": config.HTTP_PROXY,
            }
    return _session


def fetch_json(url: str, timeout: int = 15) -> Optional[any]:
    """发送 GET 请求, 返回 JSON (requests 优先, 回退 urllib)"""
    # 优先用 requests
    if HAS_REQUESTS:
        try:
            sess = _get_session()
            resp = sess.get(url, timeout=timeout)
            resp.raise_for_status()
            return resp.json()
        except Exception as e:
            logger.warning(f"请求失败: {url[:80]}... → {e}")
            return None

    # 回退 urllib
    try:
        opener = urllib.request.build_opener()
        if config.HTTP_PROXY:
            proxy_handler = urllib.request.ProxyHandler({
                "http": config.HTTP_PROXY,
                "https": config.HTTP_PROXY,
            })
            opener = urllib.request.build_opener(proxy_handler)

        req = urllib.request.Request(url, headers={
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "Accept": "application/json",
        })
        with opener.open(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode())
    except Exception as e:
        logger.warning(f"请求失败: {url[:80]}... → {e}")
        return None


# ══════════════════════════════════════════════════
#   市场数据获取
# ══════════════════════════════════════════════════

def fetch_markets(limit: int = 100, offset: int = 0) -> List[dict]:
    """从 Gamma API 获取活跃市场列表"""
    url = (f"{config.GAMMA_HOST}/markets?"
           f"limit={limit}&offset={offset}"
           f"&active=true&closed=false")
    data = fetch_json(url)
    return data if isinstance(data, list) else []


def fetch_events(limit: int = 100, offset: int = 0) -> List[dict]:
    """从 Gamma API 获取活跃事件 (包含多个子市场)"""
    url = (f"{config.GAMMA_HOST}/events?"
           f"limit={limit}&offset={offset}"
           f"&active=true&closed=false")
    data = fetch_json(url)
    return data if isinstance(data, list) else []


def fetch_all_markets(max_pages: int = 10) -> List[dict]:
    """分页获取所有活跃市场"""
    all_markets = []
    for page in range(max_pages):
        batch = fetch_markets(limit=100, offset=page * 100)
        if not batch:
            break
        all_markets.extend(batch)
        logger.debug(f"已获取 {len(all_markets)} 个市场 (page {page+1})")
        time.sleep(config.API_COOLDOWN)
    return all_markets


def fetch_all_events(max_pages: int = 10) -> List[dict]:
    """分页获取所有活跃事件"""
    all_events = []
    for page in range(max_pages):
        batch = fetch_events(limit=100, offset=page * 100)
        if not batch:
            break
        all_events.extend(batch)
        logger.debug(f"已获取 {len(all_events)} 个事件 (page {page+1})")
        time.sleep(config.API_COOLDOWN)
    return all_events


# ══════════════════════════════════════════════════
#   解析市场数据
# ══════════════════════════════════════════════════

def parse_market(raw: dict) -> Optional[MarketInfo]:
    """将 Gamma API 的市场原始数据解析为 MarketInfo"""
    try:
        tokens_raw = raw.get("tokens", [])
        if len(tokens_raw) < 2:
            return None

        tokens = []
        for t in tokens_raw:
            price = float(t.get("price", 0))
            if price <= 0 or price >= 1:
                return None
            tokens.append(TokenInfo(
                token_id=t.get("token_id", ""),
                outcome=t.get("outcome", ""),
                price=price,
                winner=t.get("winner", False),
            ))

        return MarketInfo(
            condition_id=raw.get("condition_id", raw.get("conditionId", "")),
            question=raw.get("question", ""),
            slug=raw.get("slug", ""),
            tokens=tokens,
            volume=float(raw.get("volume", 0) or 0),
            liquidity=float(raw.get("liquidity", 0) or 0),
            end_date=raw.get("endDate", raw.get("end_date_iso", "")),
            active=raw.get("active", True),
            neg_risk=raw.get("neg_risk", raw.get("negRisk", False)),
        )
    except (ValueError, TypeError, KeyError) as e:
        logger.debug(f"解析市场失败: {e}")
        return None


# ══════════════════════════════════════════════════
#   套利扫描
# ══════════════════════════════════════════════════

def scan_single_market_arb(markets: List[dict]) -> List[ArbOpportunity]:
    """
    类型1: 单市场套利
    Yes + No < $1.00 → 同时买入双方 → 保证赚差价
    """
    opps = []

    for raw in markets:
        market = parse_market(raw)
        if not market:
            continue

        # 过滤流动性和交易量
        if market.volume < config.MIN_VOLUME:
            continue
        if market.liquidity < config.MIN_LIQUIDITY:
            continue

        yes_token = None
        no_token = None
        for t in market.tokens:
            if t.outcome.lower() == "yes":
                yes_token = t
            elif t.outcome.lower() == "no":
                no_token = t

        if not yes_token or not no_token:
            continue

        total_cost = yes_token.price + no_token.price
        if total_cost >= 1.0:
            continue

        spread = 1.0 - total_cost
        gross_pct = (spread / total_cost) * 100
        net_pct = gross_pct - config.ESTIMATED_FEE_PCT

        if net_pct < config.MIN_PROFIT_PCT:
            continue

        opp = ArbOpportunity(
            arb_type="single",
            description=f"[单市场] {market.question[:50]}",
            markets=[market],
            tokens_to_buy=[
                (yes_token.token_id, "Yes", yes_token.price),
                (no_token.token_id, "No", no_token.price),
            ],
            total_cost=total_cost,
            guaranteed_payout=1.0,
            gross_profit_pct=gross_pct,
            net_profit_pct=net_pct,
            total_volume=market.volume,
            total_liquidity=market.liquidity,
        )
        opps.append(opp)
        logger.info(f"🎯 单市场套利: Yes={yes_token.price:.3f} No={no_token.price:.3f} "
                     f"净利润={net_pct:+.2f}% | {market.question[:40]}")

    return opps


def scan_multi_outcome_arb(events: List[dict]) -> List[ArbOpportunity]:
    """
    类型2: 多结果事件套利
    
    正向: 所有互斥结果的 Yes 之和 < $1.00
        → 全买 Yes → 必有一个变 $1.00 → 赚差价
    
    反向: 所有互斥结果的 No 之和 < $(N-1)
        → 全买 No → N-1 个变 $1.00 → 赚差价
    """
    opps = []

    for event in events:
        try:
            sub_markets_raw = event.get("markets", [])
            if len(sub_markets_raw) < 2:
                continue

            event_title = event.get("title", "???")
            total_volume = 0

            # 解析所有子市场
            sub_markets = []
            all_valid = True
            for raw_m in sub_markets_raw:
                m = parse_market(raw_m)
                if not m:
                    all_valid = False
                    break
                sub_markets.append(m)
                total_volume += m.volume

            if not all_valid or len(sub_markets) < 2:
                continue

            # ── 正向: 全买 Yes ──
            yes_tokens = []
            total_yes_cost = 0
            for m in sub_markets:
                for t in m.tokens:
                    if t.outcome.lower() == "yes":
                        yes_tokens.append((t.token_id, f"Yes@{m.question[:20]}", t.price))
                        total_yes_cost += t.price
                        break

            if len(yes_tokens) == len(sub_markets) and total_yes_cost > 0 and total_yes_cost < 1.0:
                spread = 1.0 - total_yes_cost
                gross_pct = (spread / total_yes_cost) * 100
                # 多结果需要买 N 个 token, 手续费乘以参与数量
                effective_fee = config.ESTIMATED_FEE_PCT
                net_pct = gross_pct - effective_fee

                if net_pct >= config.MIN_PROFIT_PCT:
                    opp = ArbOpportunity(
                        arb_type="multi_yes",
                        description=f"[多结果正向] {event_title[:50]}",
                        markets=sub_markets,
                        tokens_to_buy=yes_tokens,
                        total_cost=total_yes_cost,
                        guaranteed_payout=1.0,
                        gross_profit_pct=gross_pct,
                        net_profit_pct=net_pct,
                        total_volume=total_volume,
                        event_title=event_title,
                    )
                    opps.append(opp)
                    logger.info(f"🎯 多结果正向: {len(sub_markets)}选项 "
                                 f"Yes总和={total_yes_cost:.3f} 净利润={net_pct:+.2f}% "
                                 f"| {event_title[:40]}")

            # ── 反向: 全买 No ──
            no_tokens = []
            total_no_cost = 0
            for m in sub_markets:
                for t in m.tokens:
                    if t.outcome.lower() == "no":
                        no_tokens.append((t.token_id, f"No@{m.question[:20]}", t.price))
                        total_no_cost += t.price
                        break

            n = len(sub_markets)
            payout_no = n - 1  # N-1 个 No 会变成 $1.00

            if len(no_tokens) == n and total_no_cost > 0 and total_no_cost < payout_no:
                spread_no = payout_no - total_no_cost
                gross_pct_no = (spread_no / total_no_cost) * 100
                effective_fee = config.ESTIMATED_FEE_PCT
                net_pct_no = gross_pct_no - effective_fee

                if net_pct_no >= config.MIN_PROFIT_PCT:
                    opp = ArbOpportunity(
                        arb_type="multi_no",
                        description=f"[多结果反向] {event_title[:50]}",
                        markets=sub_markets,
                        tokens_to_buy=no_tokens,
                        total_cost=total_no_cost,
                        guaranteed_payout=float(payout_no),
                        gross_profit_pct=gross_pct_no,
                        net_profit_pct=net_pct_no,
                        total_volume=total_volume,
                        event_title=event_title,
                    )
                    opps.append(opp)
                    logger.info(f"🎯 多结果反向: {n}选项 "
                                 f"No总和={total_no_cost:.3f} 赔付=${payout_no} "
                                 f"净利润={net_pct_no:+.2f}% | {event_title[:40]}")

        except (ValueError, TypeError, KeyError) as e:
            logger.debug(f"扫描事件失败: {e}")
            continue

    return opps


def scan_all() -> List[ArbOpportunity]:
    """执行完整扫描, 返回所有套利机会 (按净利润率排序)"""
    logger.info("开始扫描 Polymarket 套利机会...")

    # 并行获取数据
    all_markets = fetch_all_markets()
    all_events = fetch_all_events()

    logger.info(f"数据: {len(all_markets)} 市场, {len(all_events)} 事件")

    # 扫描两种类型
    single_opps = scan_single_market_arb(all_markets)
    multi_opps = scan_multi_outcome_arb(all_events)

    all_opps = single_opps + multi_opps
    all_opps.sort(key=lambda x: x.net_profit_pct, reverse=True)

    logger.info(f"扫描完成: 发现 {len(all_opps)} 个套利机会 "
                f"(单市场={len(single_opps)}, 多结果={len(multi_opps)})")

    return all_opps
