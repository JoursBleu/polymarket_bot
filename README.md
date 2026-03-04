# Polymarket 套利机器人

用 AI 发现预测市场中的无风险套利机会，自动买入对冲，赚取确定性利润。

## 原理

在 Polymarket 预测市场中:
- 每个事件有 **Yes/No** 两个结果
- 理论上 `Yes价格 + No价格 = $1.00`
- **但如果 Yes + No < $1.00 → 同时买入两边 → 无论结果如何都赚钱!**

```
例: Yes=$0.55, No=$0.40
    总成本 = $0.95
    无论结果 → 其中一个变 $1.00
    保证赚 $1.00 - $0.95 = $0.05 (5.3% 无风险)
```

多结果事件同理:
- 谁赢选举? 有 A/B/C/D 四个选项
- 如果所有 Yes 之和 < $1.00 → 全买 → 必有一个变 $1.00

## 快速开始

### 1. 安装依赖

```bash
cd polymarket_bot
pip install -r requirements.txt
```

### 2. 先扫描看看 (无需配置)

```bash
# 扫描一次, 看看有没有机会
python main.py --once
```

### 3. 配置钱包 (实盘交易)

```bash
# 设置环境变量
export POLY_PRIVATE_KEY="你的Polygon钱包私钥"
export POLY_FUNDER_ADDRESS="你的钱包地址"
export POLY_DRY_RUN="false"

# 可选: 通知
export POLY_WEBHOOK_URL="https://open.feishu.cn/open-apis/bot/v2/hook/xxx"
```

### 4. 持续运行

```bash
# 持续扫描 + 自动执行
python main.py

# 查看仓位
python main.py --status
```

## 资金规划 (¥2000 / $275 USDC)

| 指标 | 值 |
|------|---|
| 本金 | $275 USDC (Polygon) |
| 单笔投入 | $5 ~ $50 |
| 套利利润率 | 1% ~ 5% (扣费后) |
| 月预期收入 | $5 ~ $30 |
| ChatGPT Plus | $20/月 |
| Break-even | 每月捕获 2-4 次好机会 |

## 文件结构

```
polymarket_bot/
├── config.py       # 配置 (API、风控参数)
├── scanner.py      # 市场扫描器 (发现套利机会)
├── executor.py     # 交易执行器 (下单、仓位管理)
├── notifier.py     # 通知模块 (飞书/Slack)
├── main.py         # 主入口 (循环扫描+执行)
├── requirements.txt
└── positions.json  # 仓位记录 (自动生成)
```

## 风控

- ✅ 最低利润率阈值 (默认 >1%)
- ✅ 单笔投入上限 ($50)
- ✅ 总敞口上限 ($500)
- ✅ 最大同时仓位数 (10)
- ✅ 订单簿深度检查
- ✅ 流动性/交易量过滤
- ✅ DRY-RUN 模式 (默认开启)

## 注意事项

1. **手续费**: Polymarket taker fee ~1-2%, 吃掉大部分小套利
2. **竞争**: 高频机器人通常在毫秒级抢走机会
3. **等待**: 需要等事件结束才能收到赔付 (可能几天~几个月)
4. **资金效率**: 资金锁定到事件结束, 周转率是关键
5. **合规**: 请确认所在地区允许使用 Polymarket

## 补充策略: 提高收入

纯套利机会稀缺时, 可结合以下策略:

1. **信息套利**: 利用 AI 分析新闻, 在市场反应前买入被低估的 Yes/No
2. **做市**: 在 bid-ask 两边挂单赚 spread (需要更大资金)
3. **跨平台套利**: Polymarket vs Kalshi 等其他预测市场的价差
