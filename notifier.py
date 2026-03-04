"""
Polymarket 套利机器人 — 通知模块
==================================
支持飞书 / Slack / 控制台通知
"""

import json
import logging
import urllib.request
from typing import Optional

import config

logger = logging.getLogger(__name__)


def send_webhook(message: str, title: str = "Polymarket 套利机器人"):
    """发送 Webhook 通知 (飞书/Slack/Discord 通用)"""
    if not config.WEBHOOK_URL:
        return

    url = config.WEBHOOK_URL

    # 自动适配格式
    if "feishu" in url or "lark" in url:
        # 飞书格式
        payload = {
            "msg_type": "text",
            "content": {"text": f"[{title}]\n{message}"},
        }
    elif "slack" in url:
        # Slack 格式
        payload = {"text": f"*{title}*\n{message}"}
    elif "discord" in url:
        # Discord 格式
        payload = {"content": f"**{title}**\n{message}"}
    else:
        # 通用 JSON
        payload = {"title": title, "message": message}

    try:
        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            url,
            data=data,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            if resp.status == 200:
                logger.debug("通知发送成功")
            else:
                logger.warning(f"通知发送异常: HTTP {resp.status}")
    except Exception as e:
        logger.warning(f"通知发送失败: {e}")


def notify_opportunity(opp, action: str = "发现"):
    """通知发现套利机会"""
    msg = (
        f"💰 {action}套利机会\n"
        f"类型: {opp.arb_type}\n"
        f"{opp.description}\n"
        f"总成本: ${opp.total_cost:.4f}\n"
        f"保证赔付: ${opp.guaranteed_payout:.2f}\n"
        f"净利润率: {opp.net_profit_pct:+.2f}%\n"
        f"交易量: ${opp.total_volume:,.0f}"
    )
    send_webhook(msg, "套利机会")
    logger.info(msg)


def notify_execution(position):
    """通知交易执行结果"""
    msg = (
        f"📋 套利仓位建立\n"
        f"ID: {position.id}\n"
        f"投入: ${position.invested:.2f}\n"
        f"预期赔付: ${position.guaranteed_payout:.2f}\n"
        f"预期利润: ${position.expected_profit:.2f}\n"
        f"状态: {position.status}"
    )
    send_webhook(msg, "交易执行")


def notify_error(error_msg: str):
    """通知错误"""
    send_webhook(f"⚠️ 错误: {error_msg}", "错误警报")


def notify_daily_summary(summary: str):
    """发送每日摘要"""
    send_webhook(summary, "每日报告")
