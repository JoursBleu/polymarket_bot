"""
Polymarket 钱包设置工具
========================
首次使用前运行, 完成:
  1. 检查钱包余额
  2. 设置 Token Allowance (授权合约使用你的 USDC)
  3. 验证 CLOB API 连接

用法:
  # 设置环境变量后运行
  export POLY_PRIVATE_KEY="0x..."
  export POLY_FUNDER_ADDRESS="0x..."
  python setup_wallet.py
"""

import os
import sys
import json
import logging

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

# Polygon Mainnet 合约地址
USDC_ADDRESS = "0x2791Bca1f2de4661ED88A30C99A7a9449Aa84174"
CTF_ADDRESS = "0x4D97DCd97eC945f40cF65F87097ACe5EA0476045"  # Conditional Token Framework

# Polymarket Exchange 合约 (需要授权这些地址)
EXCHANGE_ADDRESS = "0x4bFb41d5B3570DeFd03C39a9A4D8dE6Bd8B8982E"
NEG_RISK_EXCHANGE = "0xC5d563A36AE78145C45a50134d48A1215220f80a"
NEG_RISK_ADAPTER = "0xd91E80cF2E7be2e162c6513ceD06f1dD0dA35296"

APPROVE_TARGETS = [EXCHANGE_ADDRESS, NEG_RISK_EXCHANGE, NEG_RISK_ADAPTER]
APPROVE_TOKENS = [USDC_ADDRESS, CTF_ADDRESS]

# ERC20 approve ABI (最小)
ERC20_ABI = json.loads('[{"constant":false,"inputs":[{"name":"spender","type":"address"},{"name":"amount","type":"uint256"}],"name":"approve","outputs":[{"name":"","type":"bool"}],"type":"function"},{"constant":true,"inputs":[{"name":"owner","type":"address"},{"name":"spender","type":"address"}],"name":"allowance","outputs":[{"name":"","type":"uint256"}],"type":"function"},{"constant":true,"inputs":[{"name":"account","type":"address"}],"name":"balanceOf","outputs":[{"name":"","type":"uint256"}],"type":"function"}]')

MAX_UINT256 = 2**256 - 1
POLYGON_RPC = "https://polygon-rpc.com"


def check_deps():
    """检查依赖"""
    missing = []
    try:
        from py_clob_client.client import ClobClient
    except ImportError:
        missing.append("py-clob-client")

    try:
        from web3 import Web3
    except ImportError:
        missing.append("web3")

    if missing:
        print(f"\n❌ 缺少依赖: {', '.join(missing)}")
        print(f"   运行: pip install {' '.join(missing)}")
        return False
    return True


def check_env():
    """检查环境变量"""
    pk = os.getenv("POLY_PRIVATE_KEY", "")
    addr = os.getenv("POLY_FUNDER_ADDRESS", "")

    if not pk:
        print("\n❌ 未设置 POLY_PRIVATE_KEY")
        print("   export POLY_PRIVATE_KEY=\"0x你的私钥\"")
        return False

    if not addr:
        # 可以从私钥推导
        try:
            from web3 import Web3, Account
            acct = Account.from_key(pk)
            addr = acct.address
            os.environ["POLY_FUNDER_ADDRESS"] = addr
            print(f"  ℹ️ 从私钥推导出地址: {addr}")
        except Exception:
            print("\n❌ 未设置 POLY_FUNDER_ADDRESS 且无法从私钥推导")
            return False

    print(f"  钱包地址: {addr}")
    return True


def check_balance():
    """检查 MATIC 和 USDC 余额"""
    from web3 import Web3

    w3 = Web3(Web3.HTTPProvider(POLYGON_RPC))
    if not w3.is_connected():
        print("❌ 无法连接 Polygon RPC")
        return False

    addr = os.getenv("POLY_FUNDER_ADDRESS")
    addr = Web3.to_checksum_address(addr)

    # MATIC 余额 (用于 gas)
    matic = w3.eth.get_balance(addr)
    matic_val = w3.from_wei(matic, "ether")
    print(f"  MATIC 余额: {matic_val:.4f} MATIC")

    if matic_val < 0.1:
        print("  ⚠️ MATIC 余额过低, 需要至少 0.1 MATIC 用于 gas 费")

    # USDC 余额
    usdc_contract = w3.eth.contract(
        address=Web3.to_checksum_address(USDC_ADDRESS),
        abi=ERC20_ABI,
    )
    usdc_raw = usdc_contract.functions.balanceOf(addr).call()
    usdc_val = usdc_raw / 1e6  # USDC 6位小数
    print(f"  USDC 余额: ${usdc_val:.2f}")

    if usdc_val < 5:
        print("  ⚠️ USDC 余额不足, 需要充入 USDC (Polygon 网络)")

    return True


def check_allowances():
    """检查并设置 Token Allowance"""
    from web3 import Web3

    w3 = Web3(Web3.HTTPProvider(POLYGON_RPC))
    addr = Web3.to_checksum_address(os.getenv("POLY_FUNDER_ADDRESS"))
    pk = os.getenv("POLY_PRIVATE_KEY")

    token_names = {USDC_ADDRESS: "USDC", CTF_ADDRESS: "ConditionalToken"}
    spender_names = {
        EXCHANGE_ADDRESS: "Exchange",
        NEG_RISK_EXCHANGE: "NegRiskExchange",
        NEG_RISK_ADAPTER: "NegRiskAdapter",
    }

    need_approve = []

    for token_addr in APPROVE_TOKENS:
        contract = w3.eth.contract(
            address=Web3.to_checksum_address(token_addr),
            abi=ERC20_ABI,
        )
        for spender in APPROVE_TARGETS:
            allowance = contract.functions.allowance(
                addr, Web3.to_checksum_address(spender)
            ).call()

            tname = token_names.get(token_addr, token_addr[:10])
            sname = spender_names.get(spender, spender[:10])

            if allowance > 10**18:
                print(f"  ✅ {tname} → {sname}: 已授权")
            else:
                print(f"  ❌ {tname} → {sname}: 未授权")
                need_approve.append((token_addr, spender, tname, sname))

    if not need_approve:
        print("\n  所有授权已完成! ✅")
        return True

    print(f"\n  需要 {len(need_approve)} 个授权, 是否执行? (y/N) ", end="")
    choice = input().strip().lower()
    if choice != "y":
        print("  跳过授权")
        return False

    for token_addr, spender, tname, sname in need_approve:
        try:
            contract = w3.eth.contract(
                address=Web3.to_checksum_address(token_addr),
                abi=ERC20_ABI,
            )
            nonce = w3.eth.get_transaction_count(addr)
            tx = contract.functions.approve(
                Web3.to_checksum_address(spender),
                MAX_UINT256,
            ).build_transaction({
                "from": addr,
                "nonce": nonce,
                "gas": 80000,
                "gasPrice": w3.eth.gas_price,
                "chainId": 137,
            })
            signed = w3.eth.account.sign_transaction(tx, pk)
            tx_hash = w3.eth.send_raw_transaction(signed.raw_transaction)
            receipt = w3.eth.wait_for_transaction_receipt(tx_hash, timeout=60)

            if receipt.status == 1:
                print(f"  ✅ {tname} → {sname}: 授权成功 (tx: {tx_hash.hex()[:16]}...)")
            else:
                print(f"  ❌ {tname} → {sname}: 授权失败")
        except Exception as e:
            print(f"  ❌ {tname} → {sname}: 授权异常: {e}")

    return True


def check_clob_connection():
    """测试 CLOB API 连接"""
    from py_clob_client.client import ClobClient

    try:
        # 先测试公开 API
        client = ClobClient("https://clob.polymarket.com")
        ok = client.get_ok()
        server_time = client.get_server_time()
        print(f"  CLOB API 连接: ✅ (服务器时间: {server_time})")

        # 测试认证
        pk = os.getenv("POLY_PRIVATE_KEY")
        funder = os.getenv("POLY_FUNDER_ADDRESS")
        if pk:
            auth_client = ClobClient(
                "https://clob.polymarket.com",
                key=pk,
                chain_id=137,
                signature_type=0,
                funder=funder,
            )
            creds = auth_client.create_or_derive_api_creds()
            auth_client.set_api_creds(creds)
            print(f"  CLOB 认证: ✅")
        return True

    except Exception as e:
        print(f"  CLOB API 连接失败: {e}")
        return False


def main():
    print()
    print("=" * 60)
    print("  Polymarket 钱包设置工具")
    print("=" * 60)
    print()

    # Step 1: 依赖
    print("📦 [1/4] 检查依赖...")
    if not check_deps():
        sys.exit(1)
    print()

    # Step 2: 环境变量
    print("🔑 [2/4] 检查钱包配置...")
    if not check_env():
        sys.exit(1)
    print()

    # Step 3: 余额
    print("💰 [3/4] 检查余额...")
    try:
        check_balance()
    except Exception as e:
        print(f"  ⚠️ 余额检查失败: {e}")
        print("  (如果网络受限，可以在 MetaMask 中手动确认)")
    print()

    # Step 4: Allowance
    print("🔓 [4/4] 检查 Token 授权...")
    try:
        check_allowances()
    except Exception as e:
        print(f"  ⚠️ 授权检查失败: {e}")
    print()

    # Step 5: CLOB 连接
    print("🌐 [Bonus] 测试 CLOB API...")
    try:
        check_clob_connection()
    except Exception as e:
        print(f"  ⚠️ CLOB 测试失败: {e}")
    print()

    print("=" * 60)
    print("  设置完成! 接下来:")
    print("    1. python main.py --once   # 测试扫描")
    print("    2. python main.py          # 持续运行")
    print("=" * 60)


if __name__ == "__main__":
    main()
