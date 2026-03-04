"""
Polymarket 套利机器人 — 配置
============================
所有敏感信息通过环境变量加载, 也可手动填入下方字段

设置步骤:
  1. 注册 Polymarket 账户 (polymarket.com)
  2. 导出/创建 EOA 钱包私钥 (Polygon 网络)
  3. 往钱包充入 USDC (Polygon)
  4. 填入下方 PRIVATE_KEY 和 FUNDER_ADDRESS
"""

import os

# ══════════════════════════════════════════════════
#   Polymarket CLOB API
# ══════════════════════════════════════════════════
CLOB_HOST = "https://clob.polymarket.com"
GAMMA_HOST = "https://gamma-api.polymarket.com"
CHAIN_ID = 137  # Polygon Mainnet

# 钱包配置 (优先从环境变量读取)
PRIVATE_KEY = os.getenv("POLY_PRIVATE_KEY", "")
FUNDER_ADDRESS = os.getenv("POLY_FUNDER_ADDRESS", "")

# 签名类型: 0=EOA(MetaMask), 1=Email/Magic, 2=Browser proxy
SIGNATURE_TYPE = int(os.getenv("POLY_SIG_TYPE", "0"))

# ══════════════════════════════════════════════════
#   套利参数
# ══════════════════════════════════════════════════

# 最低利润率阈值 (扣除手续费后), 低于此值不执行
MIN_PROFIT_PCT = 1.0  # %

# Polymarket 手续费估算 (买入手续费约 0~2%, 取决于价格)
# Polymarket 费用: maker 0%, taker ~1-2% (根据价格不同)
# 保守估计双边总费用
ESTIMATED_FEE_PCT = 2.0  # %

# 单笔最大投入 (USDC)
MAX_BET_SIZE = 50.0

# 单笔最小投入 (USDC)  — 太小没意义
MIN_BET_SIZE = 5.0

# 总资金上限 (防止超额使用)
MAX_TOTAL_EXPOSURE = 500.0

# 最大同时持仓数
MAX_OPEN_POSITIONS = 10

# ══════════════════════════════════════════════════
#   订单簿过滤
# ══════════════════════════════════════════════════

# 最小流动性要求 ($)  — 流动性太低买不进去
MIN_LIQUIDITY = 500.0

# 最小交易量要求 ($)  — 量太小的市场不碰
MIN_VOLUME = 1000.0

# 订单簿深度检查: ask 的可用数量必须 >= 我们的买入量
CHECK_ORDERBOOK_DEPTH = True

# ══════════════════════════════════════════════════
#   扫描频率
# ══════════════════════════════════════════════════

# 扫描循环间隔 (秒)
SCAN_INTERVAL = 30

# API 请求间隔 (秒)  — 避免被限速
API_COOLDOWN = 0.3

# ══════════════════════════════════════════════════
#   通知 (可选)
# ══════════════════════════════════════════════════

# 飞书/Slack Webhook (留空则不发通知)
WEBHOOK_URL = os.getenv("POLY_WEBHOOK_URL", "")

# ══════════════════════════════════════════════════
#   运行模式
# ══════════════════════════════════════════════════

# dry_run=True 时只扫描不下单 (调试用)
DRY_RUN = os.getenv("POLY_DRY_RUN", "true").lower() == "true"

# 日志级别
LOG_LEVEL = os.getenv("POLY_LOG_LEVEL", "INFO")

# ══════════════════════════════════════════════════
#   网络代理 (中国大陆访问需要)
# ══════════════════════════════════════════════════

# HTTP/HTTPS 代理 (留空则直连)
# 格式: http://ip:port 或 socks5://ip:port
# 可用本机 SSH 隧道: ssh -D 1080 proxy → socks5://127.0.0.1:1080
# 或 SSH 端口转发:   ssh -L 8080:gamma-api.polymarket.com:443 proxy
HTTP_PROXY = os.getenv("POLY_HTTP_PROXY", os.getenv("https_proxy", os.getenv("http_proxy", "")))
