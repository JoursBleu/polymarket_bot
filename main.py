"""
Polymarket 套利机器人 — 主入口
==================================
持续扫描 + 自动执行 + 监控通知

用法:
  # 仅扫描 (dry-run, 默认)
  python main.py

  # 扫描一次并退出
  python main.py --once

  # 实盘交易 (需要配置私钥)
  POLY_DRY_RUN=false python main.py

  # 查看当前仓位
  python main.py --status

启动前:
  1. pip install py-clob-client
  2. 配置 config.py 或环境变量
  3. 先用 --once 模式测试扫描
  4. 确认无误后关闭 DRY_RUN
"""

import argparse
import logging
import signal
import sys
import time
from datetime import datetime

import config
from scanner import scan_all, ArbOpportunity
from executor import Executor
from notifier import (
    notify_opportunity,
    notify_execution,
    notify_error,
    notify_daily_summary,
)

# ── 日志配置 ──

logging.basicConfig(
    level=getattr(logging, config.LOG_LEVEL, logging.INFO),
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%H:%M:%S",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler("polymarket_bot.log", encoding="utf-8"),
    ],
)
logger = logging.getLogger("main")

# 优雅退出
_running = True


def signal_handler(sig, frame):
    global _running
    logger.info("收到退出信号, 正在停止...")
    _running = False


signal.signal(signal.SIGINT, signal_handler)
signal.signal(signal.SIGTERM, signal_handler)


# ══════════════════════════════════════════════════
#   核心循环
# ══════════════════════════════════════════════════

def run_scan_once(executor: Executor) -> int:
    """
    执行一次完整的扫描+执行循环
    返回: 发现的机会数
    """
    try:
        opportunities = scan_all()

        if not opportunities:
            logger.info("本轮未发现套利机会")
            return 0

        logger.info(f"发现 {len(opportunities)} 个套利机会")

        executed = 0
        for opp in opportunities:
            # 再次验证利润率
            if opp.net_profit_pct < config.MIN_PROFIT_PCT:
                continue

            notify_opportunity(opp)

            if config.DRY_RUN:
                logger.info(f"[DRY-RUN] 跳过执行: {opp.description} "
                             f"(净利润 {opp.net_profit_pct:+.2f}%)")
                continue

            # 计算合适的下注金额
            # 按利润率动态调整: 利润越高投越多
            if opp.net_profit_pct >= 5.0:
                bet_size = config.MAX_BET_SIZE
            elif opp.net_profit_pct >= 3.0:
                bet_size = config.MAX_BET_SIZE * 0.7
            elif opp.net_profit_pct >= 2.0:
                bet_size = config.MAX_BET_SIZE * 0.5
            else:
                bet_size = config.MIN_BET_SIZE

            position = executor.execute_arb(opp, bet_size=bet_size)

            if position:
                notify_execution(position)
                executed += 1

            # 每笔交易之间间隔
            time.sleep(2)

        logger.info(f"本轮执行 {executed} 笔交易")
        return len(opportunities)

    except Exception as e:
        logger.error(f"扫描循环异常: {e}", exc_info=True)
        notify_error(str(e))
        return 0


def run_loop(executor: Executor):
    """持续运行主循环"""
    global _running

    logger.info("=" * 70)
    logger.info("  Polymarket 套利机器人启动")
    logger.info(f"  模式: {'🔴 DRY-RUN (仅扫描)' if config.DRY_RUN else '🟢 实盘交易'}")
    logger.info(f"  扫描间隔: {config.SCAN_INTERVAL}s")
    logger.info(f"  最低利润率: {config.MIN_PROFIT_PCT}%")
    logger.info(f"  单笔上限: ${config.MAX_BET_SIZE}")
    logger.info(f"  总敞口上限: ${config.MAX_TOTAL_EXPOSURE}")
    logger.info("=" * 70)

    cycle = 0
    daily_opps = 0
    last_summary_date = ""

    while _running:
        cycle += 1
        now = datetime.now()
        logger.info(f"─── 第 {cycle} 轮扫描 ({now.strftime('%H:%M:%S')}) ───")

        count = run_scan_once(executor)
        daily_opps += count

        # 每日摘要 (每天 00:00 发送)
        today = now.strftime("%Y-%m-%d")
        if today != last_summary_date and now.hour == 0:
            summary = executor.summary()
            summary += f"\n今日发现机会: {daily_opps}"
            notify_daily_summary(summary)
            last_summary_date = today
            daily_opps = 0

        # 等待下一轮
        for _ in range(config.SCAN_INTERVAL):
            if not _running:
                break
            time.sleep(1)

    logger.info("机器人已停止")
    logger.info(executor.summary())


# ══════════════════════════════════════════════════
#   CLI
# ══════════════════════════════════════════════════

def print_status(executor: Executor):
    """打印当前状态"""
    print()
    print("=" * 70)
    print("  Polymarket 套利机器人 — 状态")
    print("=" * 70)
    print()
    print(executor.summary())
    print()


def print_scan_result():
    """执行一次扫描并打印结果"""
    print()
    print("=" * 70)
    print("  Polymarket 套利扫描 (单次)")
    print("=" * 70)
    print()

    opportunities = scan_all()

    if not opportunities:
        print("  未发现套利机会")
        print()
        print("  这很正常 — 做市商和机器人通常会确保 Yes+No >= $1.00")
        print("  机器人会持续监控, 在出现机会时自动捕捉")
        print()
        return

    print(f"  发现 {len(opportunities)} 个机会:\n")

    for i, opp in enumerate(opportunities[:20]):
        print(f"  [{i+1}] {opp.description}")
        print(f"      成本: ${opp.total_cost:.4f} → 赔付: ${opp.guaranteed_payout:.2f}")
        print(f"      毛利率: {opp.gross_profit_pct:+.2f}%  净利率: {opp.net_profit_pct:+.2f}%")
        print(f"      交易量: ${opp.total_volume:,.0f}")
        print(f"      买入 token:")
        for tid, outcome, price in opp.tokens_to_buy:
            print(f"        {outcome}: ${price:.4f}  (token: {tid[:16]}...)")
        print()

    # 收益试算
    print("  ─── 收益试算 ($275 USDC / ¥2000 本金) ───")
    best = opportunities[0]
    invest = 275.0
    est_profit = invest * best.net_profit_pct / 100
    print(f"  最佳机会净利率: {best.net_profit_pct:+.2f}%")
    print(f"  投入 ${invest:.0f} → 预期净赚 ${est_profit:.2f}")
    print(f"  (等事件结束后自动赔付)")
    print()


def main():
    parser = argparse.ArgumentParser(
        description="Polymarket 套利机器人",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  python main.py              持续扫描 (dry-run)
  python main.py --once       扫描一次
  python main.py --status     查看仓位
  
环境变量:
  POLY_PRIVATE_KEY        钱包私钥
  POLY_FUNDER_ADDRESS     资金地址
  POLY_DRY_RUN=false      开启实盘
  POLY_WEBHOOK_URL        通知Webhook
        """,
    )
    parser.add_argument("--once", action="store_true", help="扫描一次后退出")
    parser.add_argument("--status", action="store_true", help="查看当前仓位状态")
    parser.add_argument("--dry-run", action="store_true", default=None,
                        help="强制 dry-run 模式")

    args = parser.parse_args()

    if args.dry_run:
        config.DRY_RUN = True

    if args.status:
        executor = Executor()
        print_status(executor)
        return

    if args.once:
        print_scan_result()
        return

    executor = Executor()
    run_loop(executor)


if __name__ == "__main__":
    main()
