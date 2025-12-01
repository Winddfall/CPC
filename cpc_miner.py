"""
时权链 (Time-Rights Chain) - CPC矿工节点
基于SimpleCoin扩展，支持UTXO模型和版权交易
"""

import time
import hashlib
import json
import threading
from flask import Flask, request, jsonify


from utxo import UTXO, BlockchainUTXOManager, CopyrightPayload, TimeLockScript
from transaction import Transaction, TransactionInput, TransactionOutput, TransactionValidator

# 导入矿工配置
try:
    from cpc_config import MINER_ADDRESS, MINER_NODE_URL, PEER_NODES
except ImportError:
    # 默认配置
    MINER_ADDRESS = "default-miner-address"
    MINER_NODE_URL = "http://localhost:5001"
    PEER_NODES = []

node = Flask(__name__)


class CPCBlock:
    """
    CPC区块类
    每个区块包含多个交易，并维护UTXO状态
    """
    
    def __init__(self, index, timestamp, transactions, previous_hash, nonce=0):
        """
        初始化区块
        
        Args:
            index: 区块索引
            timestamp: 时间戳
            transactions: 交易列表
            previous_hash: 前一个区块的哈希
            nonce: 工作量证明的随机数
        """
        self.index = index
        self.timestamp = timestamp
        self.transactions = transactions  # List[Transaction]
        self.previous_hash = previous_hash
        self.nonce = nonce
        self.hash = self.calculate_hash()
    
    def calculate_hash(self):
        """计算区块哈希"""
        block_data = {
            "index": self.index,
            "timestamp": self.timestamp,
            "transactions": [tx.to_dict() for tx in self.transactions],
            "previous_hash": self.previous_hash,
            "nonce": self.nonce
        }
        block_string = json.dumps(block_data, sort_keys=True)
        return hashlib.sha256(block_string.encode()).hexdigest()
    
    def to_dict(self):
        """转换为字典"""
        return {
            "index": self.index,
            "timestamp": self.timestamp,
            "transactions": [tx.to_dict() for tx in self.transactions],
            "previous_hash": self.previous_hash,
            "nonce": self.nonce,
            "hash": self.hash
        }
    
    @classmethod
    def from_dict(cls, data):
        """从字典创建区块"""
        transactions = [Transaction.from_dict(tx) for tx in data["transactions"]]
        block = cls(
            index=data["index"],
            timestamp=data["timestamp"],
            transactions=transactions,
            previous_hash=data["previous_hash"],
            nonce=data.get("nonce", 0)
        )
        block.hash = data.get("hash", block.calculate_hash())
        return block


def create_genesis_block():
    """
    创建创世区块
    包含初始水龙头交易，为矿工提供初始CPC
    """
    # 创建水龙头交易
    faucet_output = TransactionOutput(
        amount=100.0,  # 初始100 CPC
        address=MINER_ADDRESS,
        script_pubkey=TimeLockScript(
            script_type=TimeLockScript.SCRIPT_TYPE_P2PKH,
            addresses=[MINER_ADDRESS]
        ).to_string(),
        utxo_type="fuel"
    )
    
    genesis_tx = Transaction(
        inputs=[],
        outputs=[faucet_output],
        tx_type=Transaction.TYPE_FAUCET,
        metadata={"note": "创世区块水龙头"}
    )
    
    # 创建创世区块
    genesis_block = CPCBlock(
        index=0,
        timestamp=time.time(),
        transactions=[genesis_tx],
        previous_hash="0",
        nonce=0
    )
    
    return genesis_block


# 全局变量
BLOCKCHAIN = [create_genesis_block()]
NODE_PENDING_TRANSACTIONS = []


def proof_of_work(last_block, transactions, difficulty=4):
    """
    工作量证明
    寻找符合难度要求的nonce
    
    Args:
        last_block: 上一个区块
        transactions: 要打包的交易列表（Transaction对象）
        difficulty: 难度（哈希前导0的数量）
    
    Returns:
        nonce值
    """
    nonce = 0
    target = "0" * difficulty
    
    while True:
        # 创建候选区块
        candidate_block = CPCBlock(
            index=last_block.index + 1,
            timestamp=time.time(),
            transactions=transactions,
            previous_hash=last_block.hash,
            nonce=nonce
        )
        
        # 检查哈希是否满足难度要求
        if candidate_block.hash.startswith(target):
            return nonce
        
        nonce += 1
        
        # 每1000次检查一次是否有新区块
        if nonce % 1000 == 0:
            # TODO: 检查共识
            pass


def mine_block(blockchain, pending_transactions):
    """
    挖矿函数
    验证交易并挖掘新区块
    使用基于区块扫描的UTXO管理器，而不是全局UTXO池
    """
    validator = TransactionValidator(blockchain)
    
    # 验证所有待处理的交易，并计算总手续费
    valid_transactions = []
    total_fees = 0.0  # 累计所有交易的手续费
    
    for tx_data in pending_transactions:
        try:
            tx = Transaction.from_dict(tx_data)
            is_valid, error_msg = validator.validate_transaction(tx)
            if is_valid:
                valid_transactions.append(tx)
                
                # 计算该交易的手续费（输入总额 - 输出总额）
                # 只有有输入的交易才会产生手续费
                if len(tx.inputs) > 0:  # 水龙头交易没有输入
                    input_amount = 0.0
                    for inp in tx.inputs:
                        utxo = validator.utxo_manager.get_utxo(inp.txid, inp.vout, scan_months=3)
                        if utxo:
                            input_amount += utxo.amount
                    
                    output_amount = sum(out.amount for out in tx.outputs)
                    fee = input_amount - output_amount
                    total_fees += fee
                    
                    if fee > 0:
                        print(f"  交易 {tx.txid[:8]}... 手续费: {fee:.4f} CPC")
            else:
                print(f"交易 {tx.txid} 验证失败: {error_msg}")
        except Exception as e:
            print(f"交易解析失败: {e}")
    
    # 添加挖矿奖励交易（区块奖励 + 所有交易手续费）
    block_reward = 1.0  # 固定区块奖励
    total_reward = block_reward + total_fees  # 总奖励 = 区块奖励 + 手续费
    
    mining_reward_output = TransactionOutput(
        amount=total_reward,
        address=MINER_ADDRESS,
        script_pubkey=TimeLockScript(
            script_type=TimeLockScript.SCRIPT_TYPE_P2PKH,
            addresses=[MINER_ADDRESS]
        ).to_string(),
        utxo_type="fuel"
    )
    
    reward_tx = Transaction(
        inputs=[],
        outputs=[mining_reward_output],
        tx_type=Transaction.TYPE_FAUCET,
        metadata={
            "note": "挖矿奖励",
            "block_reward": block_reward,
            "fees": total_fees,
            "total": total_reward
        }
    )
    
    valid_transactions.append(reward_tx)
    
    if total_fees > 0:
        print(f"💰 本区块总手续费: {total_fees:.4f} CPC")
    
    # 执行工作量证明
    last_block = blockchain[-1]
    print(f"开始挖矿区块 #{last_block.index + 1}，包含 {len(valid_transactions)} 笔交易...")
    nonce = proof_of_work(last_block, valid_transactions, difficulty=4)
    
    # 创建新区块
    new_block = CPCBlock(
        index=last_block.index + 1,
        timestamp=time.time(),
        transactions=valid_transactions,
        previous_hash=last_block.hash,
        nonce=nonce
    )
    
    # 注意：不再需要手动更新UTXO池
    # UTXO状态通过扫描区块自动重建
    
    blockchain.append(new_block)
    
    print(f"✓ 成功挖出区块 #{new_block.index}")
    print(f"  哈希: {new_block.hash}")
    print(f"  交易数: {len(new_block.transactions)}")
    print(f"  Nonce: {nonce}\n")
    
    return new_block


def mine_loop():
    """
    持续挖矿的循环（后台线程）
    定期检查待处理交易并挖矿
    """
    global BLOCKCHAIN, NODE_PENDING_TRANSACTIONS
    
    while True:
        try:
            # 检查是否有待处理交易
            if len(NODE_PENDING_TRANSACTIONS) > 0:
                # 复制待处理交易列表，避免在挖矿过程中被修改
                pending_txs = NODE_PENDING_TRANSACTIONS.copy()
                new_block = mine_block(BLOCKCHAIN, pending_txs)
                
                # 清空待处理队列
                NODE_PENDING_TRANSACTIONS.clear()
            else:
                time.sleep(1)  # 没有交易时休眠1秒后重新检查
        except Exception as e:
            print(f"挖矿循环错误: {e}")
            time.sleep(1)


# ============ Flask API 路由 ============

@node.route('/blocks', methods=['GET'])
def get_blocks():
    """获取区块链"""
    global BLOCKCHAIN
    
    # 返回区块链
    chain_to_send = [block.to_dict() for block in BLOCKCHAIN]
    return jsonify(chain_to_send)


@node.route('/transaction', methods=['POST'])
def submit_transaction():
    """
    提交交易
    接收并验证交易，添加到待处理队列
    """
    try:
        tx_data = request.get_json()
        
        # 验证交易格式
        tx = Transaction.from_dict(tx_data)
        
        # 初步验证
        validator = TransactionValidator(BLOCKCHAIN)
        is_valid, error_msg = validator.validate_transaction(tx)
        
        if not is_valid:
            return jsonify({
                "success": False,
                "message": f"交易验证失败: {error_msg}"
            }), 400
        
        # 添加到待处理队列
        NODE_PENDING_TRANSACTIONS.append(tx_data)
        
        print(f"✓ 收到新交易: {tx.tx_type}")
        print(f"  交易ID: {tx.txid}")
        print(f"  输入数: {len(tx.inputs)}, 输出数: {len(tx.outputs)}\n")
        
        return jsonify({
            "success": True,
            "message": "交易已提交，等待矿工确认",
            "txid": tx.txid
        })
        
    except Exception as e:
        return jsonify({
            "success": False,
            "message": f"交易提交失败: {str(e)}"
        }), 400


@node.route('/utxo', methods=['GET'])
@node.route('/utxo/<address>', methods=['GET'])
def get_utxos(address=None):
    """
    查询地址的UTXO
    支持两种调用方式：
    1. GET /utxo?address=xxx（推荐，避免URL编码问题）
    2. GET /utxo/xxx（兼容旧版本）
    """
    try:
        # 首先尝试从 query parameter 获取地址
        if address is None:
            address = request.args.get("address")
        
        if not address:
            return jsonify({
                "success": False,
                "message": "缺少 address 参数"
            }), 400
        
        # 使用基于区块扫描的UTXO管理器
        utxo_manager = BlockchainUTXOManager(BLOCKCHAIN)
        utxos = utxo_manager.get_utxos_by_address(address, scan_months=3)
        balance = utxo_manager.get_balance(address, scan_months=3)
        copyright_utxos = utxo_manager.get_copyright_utxos(address, scan_months=3)
        
        return jsonify({
            "success": True,
            "address": address,
            "balance": balance,
            "utxo_count": len(utxos),
            "copyright_count": len(copyright_utxos),
            "utxos": [utxo.to_dict() for utxo in utxos]
        })
    except Exception as e:
        return jsonify({
            "success": False,
            "message": str(e)
        }), 400


@node.route('/faucet', methods=['POST'])
def faucet():
    """
    水龙头接口
    为新用户提供免费的CPC燃料
    """
    try:
        data = request.get_json()
        address = data.get("address")
        
        if not address:
            return jsonify({
                "success": False,
                "message": "缺少地址参数"
            }), 400
        
        # 创建水龙头交易
        faucet_output = TransactionOutput(
            amount=5.0,  # 每次发放5 CPC
            address=address,
            script_pubkey=TimeLockScript(
                script_type=TimeLockScript.SCRIPT_TYPE_P2PKH,
                addresses=[address]
            ).to_string(),
            utxo_type="fuel"
        )
        
        faucet_tx = Transaction(
            inputs=[],
            outputs=[faucet_output],
            tx_type=Transaction.TYPE_FAUCET,
            metadata={"note": "水龙头领取"}
        )
        
        # 添加到待处理队列
        NODE_PENDING_TRANSACTIONS.append(faucet_tx.to_dict())
        
        return jsonify({
            "success": True,
            "message": "水龙头交易已提交，5 CPC 正在路上",
            "txid": faucet_tx.txid,
            "amount": 5.0
        })
        
    except Exception as e:
        return jsonify({
            "success": False,
            "message": str(e)
        }), 400


@node.route('/copyright/<work_hash>', methods=['GET'])
def query_copyright(work_hash):
    """
    查询版权信息
    通过作品哈希查询版权UTXO
    """
    try:
        # 通过扫描区块查找匹配的版权UTXO
        utxo_manager = BlockchainUTXOManager(BLOCKCHAIN)
        all_copyright_utxos = utxo_manager.scan_blockchain()
        
        copyright_utxos = []
        for utxo in all_copyright_utxos.values():
            if utxo.utxo_type == "copyright":
                if utxo.payload and utxo.payload.get("work_hash") == work_hash:
                    copyright_utxos.append(utxo.to_dict())
        
        if len(copyright_utxos) == 0:
            return jsonify({
                "success": False,
                "message": "未找到该作品的版权信息"
            }), 404
        
        return jsonify({
            "success": True,
            "work_hash": work_hash,
            "copyright_utxos": copyright_utxos
        })
        
    except Exception as e:
        return jsonify({
            "success": False,
            "message": str(e)
        }), 400


@node.route('/status', methods=['GET'])
def get_status():
    """获取节点状态"""
    return jsonify({
        "success": True,
        "blockchain_height": len(BLOCKCHAIN),
        "pending_transactions": len(NODE_PENDING_TRANSACTIONS),
        "miner_address": MINER_ADDRESS,
        "note": "UTXO状态通过扫描区块重建，不维护全局UTXO池"
    })


def welcome_msg():
    """欢迎信息"""
    print("""
    =========================================
        时权链 CPC v1.0.0 - 矿工节点
        Time-Rights Chain - CPC Miner
    =========================================
    
    基于UTXO模型的版权管理区块链系统
    
    节点地址: {}
    矿工地址: {}
    
    正在启动矿工节点...
    =========================================
    """.format(MINER_NODE_URL, MINER_ADDRESS))


if __name__ == '__main__':
    welcome_msg()
    
    # 启动后台挖矿线程
    mining_thread = threading.Thread(target=mine_loop, daemon=True)
    mining_thread.start()
    
    # 启动 Flask 服务器（主线程）
    node.run(host='0.0.0.0', port=5001, debug=False)

