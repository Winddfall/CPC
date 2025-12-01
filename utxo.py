"""
时权链 (Time-Rights Chain) - UTXO模型实现
CPC (Copyright Proof Coin) - 版权凭证币

这个模块实现了基于UTXO模型的核心数据结构
"""

import time
from typing import Optional, List, Dict, Any

# 授权期限常量：固定3个月（90天）
AUTHORIZATION_DURATION_SECONDS = 90 * 24 * 3600  # 3个月 = 90天

# 锁定脚本类型常量
SCRIPT_TYPE_P2PKH = "P2PKH"          # Pay-to-Public-Key-Hash（单签）
SCRIPT_TYPE_MULTISIG = "MULTISIG"    # 多重签名
SCRIPT_TYPE_TIME_LOCK = "TIMELOCK"   # 时间锁


class UTXO:
    """
    UTXO (未花费交易输出) 类
    每个UTXO代表一个可花费的输出，可以是fuel（系统分发的CPC）或copyright（版权UTXO）
    """
    
    def __init__(self, 
                 txid: str,           # 交易ID
                 vout: int,           # 输出索引
                 amount: float,       # CPC数量
                 address: str,        # 锁定地址
                 script_pubkey: str,  # 锁定脚本字符串
                 utxo_type: str = "fuel",  # UTXO类型: fuel（系统分发的CPC）, copyright（版权UTXO）
                 payload: Optional[Dict] = None):  # 附加数据（版权信息等）
        """
        初始化UTXO
        
        Args:
            txid: 所属交易的ID
            vout: 在交易输出中的索引（一笔交易可能有许多UTXO）
            amount: CPC数量
            address: 接收地址
            script_pubkey: 锁定脚本（可包含时间锁等条件）
            utxo_type: UTXO类型
            payload: 版权信息等附加数据
        """
        self.txid = txid
        self.vout = vout
        self.amount = amount
        self.address = address
        self.script_pubkey = script_pubkey
        self.utxo_type = utxo_type
        self.payload = payload or {}
        self.created_time = time.time() # 创建时间
        
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            "txid": self.txid,
            "vout": self.vout,
            "amount": self.amount,
            "address": self.address,
            "script_pubkey": self.script_pubkey,
            "utxo_type": self.utxo_type,
            "payload": self.payload,
            "created_time": self.created_time
        }
    
    @classmethod # 类方法，用于从字典创建UTXO对象
    def from_dict(cls, data: Dict[str, Any]):
        """从字典创建UTXO对象"""
        utxo = cls(
            txid=data["txid"],
            vout=data["vout"],
            amount=data["amount"],
            address=data["address"],
            script_pubkey=data["script_pubkey"],
            utxo_type=data.get("utxo_type", "fuel"),
            payload=data.get("payload", {})
        )
        utxo.created_time = data.get("created_time", time.time())
        return utxo
    
    def get_identifier(self) -> str:
        """获取UTXO的唯一标识符"""
        return f"{self.txid}:{self.vout}" # 交易id:输出索引


class CopyrightPayload:
    """
    版权Payload - 存储在版权UTXO中的数据，版权信息等附加数据
    
    注意：授权期限固定为3个月，从UTXO创建时间（created_at）开始计算
    """
    
    def __init__(self,
                 work_hash: str,           # 作品唯一哈希
                 work_title: str,          # 作品标题
                 author: str,              # 原作者地址
                 copyright_type: str,      # 版权类型: sovereignty, instruction, proof, secondary
                 rights_scope: Optional[List[str]] = None,  # 权利范围
                 parent_utxo: Optional[str] = None, # 父级UTXO标识（次级授权用）
                 metadata: Optional[Dict] = None):  # 其他元数据
        """
        初始化版权Payload
        
        Args:
            work_hash: 作品文件的SHA256哈希值
            work_title: 作品名称
            author: 原作者钱包地址
            copyright_type: 版权UTXO类型
                - sovereignty: 版权主权 所有权（原作者持有，完整权利）
                - instruction: 授权指令 承诺（未生效的授权，带时间锁）
                - proof: 版权证明 凭证（已生效的授权，可证明）
                - secondary: 次级授权 转授权（第三方从被授权人获得的部分权利）
            该属性变化遵循矿工状态机（Miner State Machine），矿工根据当前状态和UTXO类型决定如何处理。
            rights_scope: 授权的权利范围列表，如["复制权", "发行权", "改编权"]
            parent_utxo: 父级UTXO（用于次级授权的继承关系）
            metadata: 其他元数据
        """
        self.work_hash = work_hash
        self.work_title = work_title
        self.author = author
        self.copyright_type = copyright_type
        self.rights_scope = rights_scope or ["复制权", "发行权", "改编权", "表演权"]
        self.parent_utxo = parent_utxo
        self.metadata = metadata or {}
        self.created_at = time.time()
        
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            "work_hash": self.work_hash,
            "work_title": self.work_title,
            "author": self.author,
            "copyright_type": self.copyright_type,
            "rights_scope": self.rights_scope,
            "parent_utxo": self.parent_utxo,
            "metadata": self.metadata,
            "created_at": self.created_at
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]):
        """从字典创建Payload对象"""
        payload = cls(
            work_hash=data["work_hash"],
            work_title=data["work_title"],
            author=data["author"],
            copyright_type=data["copyright_type"],
            rights_scope=data.get("rights_scope"),
            parent_utxo=data.get("parent_utxo"),
            metadata=data.get("metadata", {})
        )
        payload.created_at = data.get("created_at", time.time())
        return payload
    
    def get_end_time(self) -> int:
        """
        计算授权到期时间（动态计算）
        
        Returns:
            授权到期时间戳（created_at + 3个月）
        """
        return int(self.created_at) + AUTHORIZATION_DURATION_SECONDS
    
    def is_expired(self, current_time: Optional[int] = None) -> bool:
        """
        检查授权是否已过期
        
        Args:
            current_time: 当前时间戳，如果为None则使用系统时间
            
        Returns:
            True如果已过期，False否则
        """
        if current_time is None:
            current_time = int(time.time())
        return current_time >= self.get_end_time()


class TimeLockScript:
    """
    锁定脚本类
    """
    
    # 脚本类型常量
    SCRIPT_TYPE_P2PKH = "P2PKH"          # Pay-to-Public-Key-Hash（单签）
    SCRIPT_TYPE_MULTISIG = "MULTISIG"    # 多重签名
    SCRIPT_TYPE_TIME_LOCK = "TIMELOCK"   # 时间锁
    
    def __init__(self, 
                 script_type: str,
                 addresses: List[str],
                 required_sig_num: int = 1,
                 time_lock: Optional[int] = None,
                 ):
        """
        初始化锁定脚本
        
        Args:
            script_type: 脚本类型
            addresses: 可以解锁的地址列表
            required_sig_num: 多重签名需要的签名数量
            time_lock: 时间锁（只能在此时间之后花费）
        """
        self.script_type = script_type
        self.addresses = addresses
        self.required_sig_num = required_sig_num
        self.time_lock = time_lock
        
    def can_spend(self, current_time: int, signers: List[str], end_time: Optional[int] = None) -> bool:
        """
        检查是否可以花费UTXO
        
        Args:
            current_time: 当前时间戳
            signers: 签名者地址列表
            end_time: 授权到期时间（如果提供，到期后自动失效）
            
        Returns:
            是否可以花费
        """
        # 检查授权是否已过期（自动失效，无需赎回）
        if end_time and current_time >= end_time:
            return False  # 授权已过期，自动失效
        
        # 检查时间锁
        if self.time_lock and current_time < self.time_lock:
            return False
        
        # 检查签名数量和地址
        valid_signers = [s for s in signers if s in self.addresses]
        return len(valid_signers) >= self.required_sig_num
    
    def to_string(self) -> str:
        """转换为脚本字符串（简化版本）"""
        parts = [self.script_type] # 脚本类型
        
        # 如果有时间锁
        if self.time_lock: 
            parts.append(f"CHECKLOCKTIMEVERIFY:{self.time_lock}")
        
        # 如果有多重签名
        if self.required_sig_num > 1:
            parts.append(f"MULTISIG:{self.required_sig_num}:{len(self.addresses)}")
        
        parts.extend(self.addresses)
        
        return "|".join(parts)
    
    @classmethod
    def from_string(cls, script_str: str):
        """从脚本字符串解析为一个锁定脚本对象"""
        parts = script_str.split("|")
        script_type = parts[0] # 脚本类型
        
        time_lock = None
        required_sig_num = 1
        addresses = []
        
        for part in parts[1:]:
            if part.startswith("CHECKLOCKTIMEVERIFY:"): # 时间锁
                time_lock = int(part.split(":")[1])
            elif part.startswith("MULTISIG:"): # 多重签名
                _, req, total = part.split(":")
                required_sig_num = int(req)
            else:
                addresses.append(part) # 地址
        
        return cls(
            script_type=script_type,
            addresses=addresses,
            required_sig_num=required_sig_num,
            time_lock=time_lock,
        )


class BlockchainUTXOManager:
    """
    基于区块链扫描的UTXO管理器
    通过扫描区块来重建UTXO状态，而不是维护全局UTXO池
    这是真正的区块链UTXO管理方式
    """
    
    def __init__(self, blockchain: List):
        """
        初始化UTXO管理器
        
        Args:
            blockchain: 区块链列表（CPCBlock对象列表）
        """
        self.blockchain = blockchain
    
    def scan_blockchain(self, start_time: Optional[int] = None) -> Dict[str, UTXO]:
        """
        扫描区块链，重建所有UTXO状态
        
        Args:
            start_time: 起始时间戳（可选，用于只扫描最近N个月的区块）
            
        Returns:
            UTXO字典，key为"txid:vout"
        """
        utxos: Dict[str, UTXO] = {}
        
        # 从创世区块开始扫描
        for block in self.blockchain:
            # 如果指定了起始时间，跳过早于该时间的区块
            if start_time and block.timestamp < start_time:
                continue
            
            # 扫描区块中的所有交易
            for tx in block.transactions:
                # 消耗输入（移除被花费的UTXO）
                for inp in tx.inputs:
                    identifier = f"{inp.txid}:{inp.vout}"
                    if identifier in utxos:
                        del utxos[identifier]
                
                # 创建输出（添加新的UTXO）
                for vout, output in enumerate(tx.outputs):
                    utxo = UTXO(
                        txid=tx.txid,
                        vout=vout,
                        amount=output.amount,
                        address=output.address,
                        script_pubkey=output.script_pubkey,
                        utxo_type=output.utxo_type,
                        payload=output.payload
                    )
                    identifier = utxo.get_identifier()
                    utxos[identifier] = utxo
        
        return utxos
    
    def get_utxo(self, txid: str, vout: int, scan_months: int = 3) -> Optional[UTXO]:
        """
        通过扫描区块获取指定key的UTXO
        
        Args:
            txid: 交易ID
            vout: 输出索引
            scan_months: 扫描最近N个月的区块（默认3个月）
            
        Returns:
            UTXO对象或None
        """
        # 计算起始时间（N个月前）
        start_time = int(time.time()) - (scan_months * 30 * 24 * 3600)
        
        # 扫描区块，得到所有还未花费的UTXO
        utxos = self.scan_blockchain(start_time=start_time)
        
        identifier = f"{txid}:{vout}"
        return utxos.get(identifier)
    
    def get_utxos_by_address(self, address: str, scan_months: int = 3) -> List[UTXO]:
        """
        获取某个地址的所有UTXO
        
        Args:
            address: 钱包地址
            scan_months: 扫描最近N个月的区块（默认3个月）
            
        Returns:
            UTXO列表
        """
        import time
        start_time = int(time.time()) - (scan_months * 30 * 24 * 3600)
        
        utxos = self.scan_blockchain(start_time=start_time)
        return [utxo for utxo in utxos.values() if utxo.address == address]
    
    def get_balance(self, address: str, scan_months: int = 3) -> float:
        """
        计算某个地址的CPC余额
        
        Args:
            address: 钱包地址
            scan_months: 扫描最近N个月的区块（默认3个月）
            
        Returns:
            余额
        """
        utxos = self.get_utxos_by_address(address, scan_months)
        return sum(utxo.amount for utxo in utxos)
    
    def get_copyright_utxos(self, address: str, scan_months: int = 3) -> List[UTXO]:
        """
        获取某个地址的所有版权UTXO（最近N个月）
        
        Args:
            address: 钱包地址
            scan_months: 扫描最近N个月的区块（默认3个月）
            
        Returns:
            版权UTXO列表
        """
        utxos = self.get_utxos_by_address(address, scan_months)
        return [utxo for utxo in utxos if utxo.utxo_type == "copyright"]
    
    def verify_copyright_proof(self, address: str, work_hash: str, scan_months: int = 3) -> Optional[UTXO]:
        """
        验证某个地址是否有某作品的有效的版权证明UTXO（最近N个月）
        
        Args:
            address: 公司地址
            work_hash: 作品哈希
            scan_months: 扫描最近N个月的区块（默认3个月）
            
        Returns:
            有效的版权证明UTXO，如果不存在则返回None
        """
        # 获取该地址的所有版权UTXO
        copyright_utxos = self.get_copyright_utxos(address, scan_months)
        
        for utxo in copyright_utxos:
            # 检查是否是证明类型的UTXO
            if (utxo.payload and 
                utxo.payload.get("copyright_type") == "proof" and
                utxo.payload.get("work_hash") == work_hash):
                    return utxo  # 找到有效的证明UTXO
        
        return None  # 未找到有效的证明
