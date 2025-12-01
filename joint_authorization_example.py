"""
联合授权锁定示例
演示作者和公司如何共同创建授权锁定交易，公司承担所有燃料费用
"""

from transaction import Transaction, TransactionInput, TransactionOutput
from utxo import CopyrightPayload, TimeLockScript


def create_joint_authorization_lock_tx(
    author_sovereignty_utxo: dict,
    author_public_key: str,
    company_fuel_utxo: dict,
    company_address: str,
    company_public_key: str,
    work_hash: str,
    work_title: str,
    rights_scope: list
) -> Transaction:
    """
    创建联合授权锁定交易（公司承担燃料费用）
    
    场景：
    - 作者提供：sovereignty UTXO (比如 1 CPC)
    - 公司提供：fuel UTXO (比如 0.02 CPC，包含手续费)
    - 输出1：instruction UTXO 给公司 (0.01 CPC)
    - 输出2：sovereignty UTXO 返还给作者 (1.0 CPC)
    - 手续费：0.01 CPC（由公司承担）
    
    Args:
        author_sovereignty_utxo: 作者的版权主权UTXO信息
            {"txid": "...", "vout": 0, "amount": 1.0, "address": "..."}
        author_public_key: 作者的公钥
        company_fuel_utxo: 公司的燃料UTXO信息
            {"txid": "...", "vout": 0, "amount": 0.02, "address": "..."}
        company_address: 公司的地址
        company_public_key: 公司的公钥
        work_hash: 作品哈希
        work_title: 作品标题
        rights_scope: 授权范围，如 ["复制权", "发行权"]
    
    Returns:
        未签名的交易对象（需要双方分别签名）
    """
    
    # 构建输入
    inputs = [
        # 输入1: 作者的 sovereignty UTXO
        TransactionInput(
            txid=author_sovereignty_utxo["txid"],
            vout=author_sovereignty_utxo["vout"],
            signature="",  # 待作者签名
            public_key=author_public_key
        ),
        # 输入2: 公司的 fuel UTXO
        TransactionInput(
            txid=company_fuel_utxo["txid"],
            vout=company_fuel_utxo["vout"],
            signature="",  # 待公司签名
            public_key=company_public_key
        )
    ]
    
    # 构建输出
    outputs = []
    
    # 输出1: 授权指令UTXO → 公司
    instruction_payload = CopyrightPayload(
        work_hash=work_hash,
        work_title=work_title,
        author=author_sovereignty_utxo["address"],
        copyright_type="instruction",
        rights_scope=rights_scope
    )
    
    instruction_script = TimeLockScript(
        script_type=TimeLockScript.SCRIPT_TYPE_P2PKH,
        addresses=[company_address]
    ).to_string()
    
    outputs.append(TransactionOutput(
        amount=0.01,  # 给公司的 instruction UTXO
        address=company_address,
        script_pubkey=instruction_script,
        utxo_type="copyright",
        payload=instruction_payload.to_dict()
    ))
    
    # 输出2: 重新铸造的 sovereignty UTXO → 作者（原路返回）
    sovereignty_payload = CopyrightPayload(
        work_hash=work_hash,
        work_title=work_title,
        author=author_sovereignty_utxo["address"],
        copyright_type="sovereignty",
        rights_scope=author_sovereignty_utxo["payload"]["rights_scope"]
    )
    
    sovereignty_script = TimeLockScript(
        script_type=TimeLockScript.SCRIPT_TYPE_P2PKH,
        addresses=[author_sovereignty_utxo["address"]]
    ).to_string()
    
    outputs.append(TransactionOutput(
        amount=author_sovereignty_utxo["amount"],  # 原路返回给作者
        address=author_sovereignty_utxo["address"],
        script_pubkey=sovereignty_script,
        utxo_type="copyright",
        payload=sovereignty_payload.to_dict()
    ))
    
    # 创建交易
    tx = Transaction(
        inputs=inputs,
        outputs=outputs,
        tx_type=Transaction.TYPE_AUTH_LOCK,
        metadata={
            "note": "联合授权锁定（公司承担燃料费用）",
            "author": author_sovereignty_utxo["address"],
            "licensee": company_address,
            "fuel_provider": company_address
        }
    )
    
    # 计算手续费
    input_total = author_sovereignty_utxo["amount"] + company_fuel_utxo["amount"]
    output_total = sum(out.amount for out in outputs)
    fee = input_total - output_total
    
    print(f"\n📝 交易详情:")
    print(f"   输入总额: {input_total} CPC")
    print(f"     - 作者提供: {author_sovereignty_utxo['amount']} CPC (sovereignty)")
    print(f"     - 公司提供: {company_fuel_utxo['amount']} CPC (fuel)")
    print(f"   输出总额: {output_total} CPC")
    print(f"     - 公司获得: 0.01 CPC (instruction)")
    print(f"     - 作者获得: {author_sovereignty_utxo['amount']} CPC (sovereignty, 返还)")
    print(f"   手续费: {fee} CPC (由公司承担)")
    print(f"   交易ID: {tx.txid}")
    
    return tx


def sign_and_submit_joint_transaction(tx: Transaction, author_wallet, company_wallet):
    """
    签名并提交联合交易
    
    流程：
    1. 作者签名 inputs[0]
    2. 公司签名 inputs[1]
    3. 提交交易到网络
    """
    
    print(f"\n🔐 签名流程:")
    
    # 作者签名自己的输入
    print(f"   1. 作者签名 inputs[0]...")
    tx.inputs[0].signature = author_wallet.sign(tx.txid)
    print(f"      ✓ 作者签名完成")
    
    # 公司签名自己的输入
    print(f"   2. 公司签名 inputs[1]...")
    tx.inputs[1].signature = company_wallet.sign(tx.txid)
    print(f"      ✓ 公司签名完成")
    
    # 提交交易
    print(f"   3. 提交交易到网络...")
    # submit_transaction_to_node(tx)
    print(f"      ✓ 交易已提交")
    
    return tx


# 使用示例
if __name__ == "__main__":
    print("""
    ========================================
    联合授权锁定示例
    ========================================
    
    场景：
    - Alice（作者）拥有《红楼梦》的版权
    - 公司想获得授权
    - 公司愿意承担所有燃料费用
    
    交易结构：
    输入1: Alice的 sovereignty UTXO (1 CPC)
    输入2: 公司的 fuel UTXO (0.02 CPC)
    输出1: 公司的 instruction UTXO (0.01 CPC)
    输出2: Alice的 sovereignty UTXO (1 CPC, 返还)
    手续费: 0.01 CPC (由公司承担)
    ========================================
    """)
    
    # 模拟数据
    author_sovereignty_utxo = {
        "txid": "abc123...",
        "vout": 0,
        "amount": 1.0,
        "address": "Alice的地址",
        "payload": {
            "work_hash": "作品哈希",
            "work_title": "红楼梦",
            "copyright_type": "sovereignty",
            "rights_scope": ["复制权", "发行权", "改编权", "表演权"]
        }
    }
    
    company_fuel_utxo = {
        "txid": "def456...",
        "vout": 0,
        "amount": 0.02,
        "address": "公司地址"
    }
    
    # 创建交易
    tx = create_joint_authorization_lock_tx(
        author_sovereignty_utxo=author_sovereignty_utxo,
        author_public_key="Alice公钥",
        company_fuel_utxo=company_fuel_utxo,
        company_address="公司地址",
        company_public_key="公司公钥",
        work_hash="作品哈希",
        work_title="红楼梦",
        rights_scope=["复制权", "发行权"]
    )
    
    print(f"\n✅ 交易创建成功！")
    print(f"   下一步：作者和公司分别签名")


