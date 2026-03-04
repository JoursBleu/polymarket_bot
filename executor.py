"""
Polymarket 套利机器人 — 交易执行器
====================================
使用 py-clob-client 官方 SDK 执行套利下单

依赖: pip install py-clob-client

功能:
  - 验证订单簿深度 (确保能买到足够数量)
  - 限价单 / 市价单下单
  - 仓位跟踪
  - 订单状态监控
"""

import json
import logging
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import config
from scanner import ArbOpportunity

logger = logging.getLogger(__name__)

# 尝试导入 py-clob-client (如果未安装则降级到 dry-run)
try:
    from py_clob_client.client import ClobClient
    from py_clob_client.clob_types import (
        MarketOrderArgs,
        OrderArgs,
        OrderType,
        BookParams,
        OpenOrderParams,
    )
    from py_clob_client.order_builder.constants import BUY
    HAS_CLOB_CLIENT = True
except ImportError:
    HAS_CLOB_CLIENT = False
    logger.warning("py-clob-client 未安装, 将以 dry-run 模式运行")
    logger.warning("安装: pip install py-clob-client")


# ══════════════════════════════════════════════════
#   仓位记录
# ══════════════════════════════════════════════════

@dataclass
class Position:
    """一个套利仓位 (买入的所有 token)"""
    id: str  # 唯一标识
    arb_type: str
    description: str
    tokens: List[Dict]  # [{"token_id", "outcome", "target_price", "amount", "order_id", "filled"}]
    invested: float = 0.0  # 实际投入 (USDC)
    guaranteed_payout: float = 0.0
    expected_profit: float = 0.0
    status: str = "pending"  # pending / filled / settled / failed
    created_at: float = 0.0
    settled_at: float = 0.0

    def __post_init__(self):
        self.created_at = time.time()


# ══════════════════════════════════════════════════
#   持久化 (JSON 文件存储)
# ══════════════════════════════════════════════════

POSITIONS_FILE = Path(__file__).parent / "positions.json"


def save_positions(positions: List[Position]):
    """保存仓位到文件"""
    data = []
    for p in positions:
        data.append({
            "id": p.id,
            "arb_type": p.arb_type,
            "description": p.description,
            "tokens": p.tokens,
            "invested": p.invested,
            "guaranteed_payout": p.guaranteed_payout,
            "expected_profit": p.expected_profit,
            "status": p.status,
            "created_at": p.created_at,
            "settled_at": p.settled_at,
        })
    POSITIONS_FILE.write_text(json.dumps(data, indent=2, ensure_ascii=False))


def load_positions() -> List[Position]:
    """从文件加载仓位"""
    if not POSITIONS_FILE.exists():
        return []
    try:
        data = json.loads(POSITIONS_FILE.read_text())
        positions = []
        for d in data:
            p = Position(
                id=d["id"],
                arb_type=d["arb_type"],
                description=d["description"],
                tokens=d["tokens"],
                invested=d.get("invested", 0),
                guaranteed_payout=d.get("guaranteed_payout", 0),
                expected_profit=d.get("expected_profit", 0),
                status=d.get("status", "pending"),
            )
            p.created_at = d.get("created_at", 0)
            p.settled_at = d.get("settled_at", 0)
            positions.append(p)
        return positions
    except Exception as e:
        logger.error(f"加载仓位失败: {e}")
        return []


# ══════════════════════════════════════════════════
#   交易执行器
# ══════════════════════════════════════════════════

class Executor:
    """套利交易执行器"""

    def __init__(self):
        self.client: Optional[ClobClient] = None
        self.positions: List[Position] = load_positions()
        self._order_counter = len(self.positions)

        if not config.DRY_RUN:
            self._init_client()

    def _init_client(self):
        """初始化 CLOB 交易客户端"""
        if not HAS_CLOB_CLIENT:
            logger.error("py-clob-client 未安装, 无法初始化交易客户端")
            return

        if not config.PRIVATE_KEY:
            logger.error("未配置 PRIVATE_KEY, 无法交易")
            return

        try:
            kwargs = {
                "host": config.CLOB_HOST,
                "key": config.PRIVATE_KEY,
                "chain_id": config.CHAIN_ID,
                "signature_type": config.SIGNATURE_TYPE,
            }
            if config.FUNDER_ADDRESS:
                kwargs["funder"] = config.FUNDER_ADDRESS

            self.client = ClobClient(**kwargs)
            self.client.set_api_creds(self.client.create_or_derive_api_creds())
            logger.info("✅ CLOB 客户端初始化成功")
        except Exception as e:
            logger.error(f"CLOB 客户端初始化失败: {e}")
            self.client = None

    # ── 订单簿验证 ──

    def check_orderbook_depth(self, token_id: str, amount_usd: float) -> Tuple[bool, float]:
        """
        检查订单簿是否有足够深度
        返回: (可行?, 预估平均成交价)
        """
        if not self.client:
            return True, 0.0  # dry-run 模式跳过

        try:
            book = self.client.get_order_book(token_id)
            if not book or not book.asks:
                logger.warning(f"订单簿为空: {token_id[:16]}...")
                return False, 0.0

            # 模拟吃单: 从最低 ask 开始累积
            total_cost = 0.0
            total_shares = 0.0

            for ask in book.asks:
                ask_price = float(ask.price)
                ask_size = float(ask.size)
                ask_value = ask_price * ask_size

                if total_cost + ask_value >= amount_usd:
                    # 这一档部分成交
                    remaining = amount_usd - total_cost
                    shares_here = remaining / ask_price
                    total_shares += shares_here
                    total_cost = amount_usd
                    break
                else:
                    total_cost += ask_value
                    total_shares += ask_size

            if total_cost < amount_usd * 0.95:
                logger.warning(f"订单簿深度不足: 需要${amount_usd:.2f}, 可用${total_cost:.2f}")
                return False, 0.0

            avg_price = total_cost / total_shares if total_shares > 0 else 0
            return True, avg_price

        except Exception as e:
            logger.error(f"检查订单簿失败: {e}")
            return False, 0.0

    # ── 下单 ──

    def place_market_buy(self, token_id: str, amount_usd: float) -> Optional[str]:
        """
        市价买入指定金额的 token
        返回: order_id 或 None
        """
        if config.DRY_RUN or not self.client:
            logger.info(f"[DRY-RUN] 市价买入 ${amount_usd:.2f} → token {token_id[:16]}...")
            return f"dry-run-{int(time.time())}"

        try:
            order_args = MarketOrderArgs(
                token_id=token_id,
                amount=amount_usd,
                side=BUY,
                order_type=OrderType.FOK,  # Fill-or-Kill
            )
            signed_order = self.client.create_market_order(order_args)
            resp = self.client.post_order(signed_order, OrderType.FOK)

            order_id = resp.get("orderID", resp.get("id", ""))
            if order_id:
                logger.info(f"✅ 市价单成功: ${amount_usd:.2f} → {token_id[:16]}... "
                             f"order_id={order_id}")
            else:
                logger.warning(f"下单响应异常: {resp}")

            return order_id

        except Exception as e:
            logger.error(f"❌ 市价单失败: {e}")
            return None

    def place_limit_buy(self, token_id: str, price: float, size: float) -> Optional[str]:
        """
        限价买入
        :param price: 买入价格 (0~1)
        :param size: 买入数量 (shares)
        返回: order_id 或 None
        """
        if config.DRY_RUN or not self.client:
            logger.info(f"[DRY-RUN] 限价买入 {size:.2f}份 @ ${price:.4f} → {token_id[:16]}...")
            return f"dry-run-{int(time.time())}"

        try:
            order_args = OrderArgs(
                token_id=token_id,
                price=price,
                size=size,
                side=BUY,
            )
            signed_order = self.client.create_order(order_args)
            resp = self.client.post_order(signed_order, OrderType.GTC)

            order_id = resp.get("orderID", resp.get("id", ""))
            if order_id:
                logger.info(f"✅ 限价单成功: {size:.2f}份 @ ${price:.4f} → {token_id[:16]}... "
                             f"order_id={order_id}")
            return order_id

        except Exception as e:
            logger.error(f"❌ 限价单失败: {e}")
            return None

    # ── 套利执行 ──

    def execute_arb(self, opp: ArbOpportunity, bet_size: float = None) -> Optional[Position]:
        """
        执行一笔套利交易
        
        :param opp: 套利机会
        :param bet_size: 总投入金额 (USDC), 默认使用 config.MAX_BET_SIZE
        :return: Position 或 None (失败时)
        """
        bet_size = bet_size or config.MAX_BET_SIZE
        bet_size = min(bet_size, config.MAX_BET_SIZE)
        bet_size = max(bet_size, config.MIN_BET_SIZE)

        # 检查仓位限制
        open_count = sum(1 for p in self.positions if p.status in ("pending", "filled"))
        if open_count >= config.MAX_OPEN_POSITIONS:
            logger.warning(f"已达最大仓位数 ({config.MAX_OPEN_POSITIONS}), 跳过")
            return None

        # 检查总敞口
        total_exposure = sum(p.invested for p in self.positions if p.status in ("pending", "filled"))
        if total_exposure + bet_size > config.MAX_TOTAL_EXPOSURE:
            logger.warning(f"总敞口将超限: ${total_exposure:.2f} + ${bet_size:.2f} > ${config.MAX_TOTAL_EXPOSURE}")
            remaining = config.MAX_TOTAL_EXPOSURE - total_exposure
            if remaining < config.MIN_BET_SIZE:
                return None
            bet_size = remaining

        n_tokens = len(opp.tokens_to_buy)
        if n_tokens == 0:
            return None

        # 计算每个 token 的买入金额 (按价格比例分配)
        per_token_usd = bet_size / opp.total_cost  # 每 $1 赔付投入的份数

        logger.info(f"{'='*60}")
        logger.info(f"执行套利: {opp.description}")
        logger.info(f"投入: ${bet_size:.2f} | 预估净利润: {opp.net_profit_pct:+.2f}%")
        logger.info(f"需要买入 {n_tokens} 个 token")

        # 检查订单簿深度
        if config.CHECK_ORDERBOOK_DEPTH and not config.DRY_RUN:
            for token_id, outcome, price in opp.tokens_to_buy:
                token_usd = price * per_token_usd
                ok, avg_price = self.check_orderbook_depth(token_id, token_usd)
                if not ok:
                    logger.warning(f"订单簿深度不足, 放弃执行: {outcome}")
                    return None
                # 如果实际成交价明显高于预期, 重新计算利润
                if avg_price > 0 and avg_price > price * 1.02:
                    logger.warning(f"实际价格 ${avg_price:.4f} > 预期 ${price:.4f}, 放弃")
                    return None

        # 创建仓位
        self._order_counter += 1
        position = Position(
            id=f"arb-{self._order_counter}-{int(time.time())}",
            arb_type=opp.arb_type,
            description=opp.description,
            tokens=[],
            guaranteed_payout=opp.guaranteed_payout * per_token_usd,
        )

        # 逐个买入
        total_invested = 0.0
        all_success = True

        for token_id, outcome, price in opp.tokens_to_buy:
            token_usd = price * per_token_usd  # 这个 token 要花多少钱

            order_id = self.place_market_buy(token_id, token_usd)

            if order_id:
                position.tokens.append({
                    "token_id": token_id,
                    "outcome": outcome,
                    "target_price": price,
                    "amount_usd": token_usd,
                    "order_id": order_id,
                    "filled": True if config.DRY_RUN else False,
                })
                total_invested += token_usd
            else:
                all_success = False
                logger.error(f"❌ 买入失败: {outcome} ${token_usd:.2f}")
                break

            time.sleep(config.API_COOLDOWN)

        position.invested = total_invested
        position.expected_profit = position.guaranteed_payout - total_invested
        position.status = "filled" if all_success else "partial"

        # 如果部分失败, 记录但不回滚 (套利仓位部分买入仍有价值)
        if not all_success:
            logger.warning(f"⚠️ 套利仅部分完成, 已投入 ${total_invested:.2f}")

        self.positions.append(position)
        save_positions(self.positions)

        logger.info(f"{'='*60}")
        logger.info(f"仓位建立: {position.id}")
        logger.info(f"  投入: ${position.invested:.2f}")
        logger.info(f"  预期赔付: ${position.guaranteed_payout:.2f}")
        logger.info(f"  预期利润: ${position.expected_profit:.2f}")
        logger.info(f"{'='*60}")

        return position

    # ── 查询 ──

    def get_open_positions(self) -> List[Position]:
        """获取未结算仓位"""
        return [p for p in self.positions if p.status in ("pending", "filled", "partial")]

    def get_total_exposure(self) -> float:
        """获取总敞口"""
        return sum(p.invested for p in self.get_open_positions())

    def get_total_expected_profit(self) -> float:
        """获取预期总利润"""
        return sum(p.expected_profit for p in self.get_open_positions())

    def summary(self) -> str:
        """生成仓位摘要"""
        open_pos = self.get_open_positions()
        settled = [p for p in self.positions if p.status == "settled"]

        lines = [
            "═══ 仓位摘要 ═══",
            f"  活跃仓位: {len(open_pos)}",
            f"  已结算: {len(settled)}",
            f"  总敞口: ${self.get_total_exposure():.2f}",
            f"  预期利润: ${self.get_total_expected_profit():.2f}",
        ]

        if open_pos:
            lines.append("  ── 活跃仓位 ──")
            for p in open_pos:
                lines.append(f"    [{p.id}] {p.description}")
                lines.append(f"      投入=${p.invested:.2f} 预期赔付=${p.guaranteed_payout:.2f} "
                             f"利润=${p.expected_profit:.2f}")

        if settled:
            total_realized = sum(p.expected_profit for p in settled)
            lines.append(f"  ── 已实现利润: ${total_realized:.2f} ──")

        return "\n".join(lines)
