"""
时权链 (Time-Rights Chain) - 交易系统实现
实现各种版权相关的交易类型
"""

import hashlib
import time
import json
import ecdsa
import base64
from typing import List, Dict, Any, Optional, Tuple
from utxo import UTXO, BlockchainUTXOManager, CopyrightPayload, TimeLockScript


class TransactionInput:
    """
    交易输入 - 引用之前的UTXO
    支持多签：每个输入可以由多个地址共同签名
    """
    
    def __init__(self, 
                 txid: str,                    # 引用的交易ID
                 vout: int,                    # 引用的输出索引
                 signature: Optional[str] = None,     # 签名（可选，可能还未签名）
                 public_key: Optional[str] = None,    # 公钥（可选，可能还未签名）
                 required_signers: Optional[List[str]] = None):  # 需要签名的地址列表
        """
        初始化交易输入
        
        Args:
            txid: 要花费的UTXO所在的交易ID
            vout: 要花费的UTXO在该交易中的输出索引
            signature: 对这个input的签名（单个签名，用于向后兼容）
            public_key: 签名者的公钥（单个公钥，用于向后兼容）
            required_signers: 需要签名的地址列表（用于多签场景）
        """
        self.txid = txid
        self.vout = vout
        self.signature = signature  # 向后兼容：单签
        self.public_key = public_key  # 向后兼容：单签
        
        # 多签支持：记录已有的签名
        self.signatures: Dict[str, str] = {}  # key: 地址（公钥），value: 签名
        
        # 记录需要签名的地址列表
        if required_signers is None:
            # 如果没有指定，则使用 public_key 作为单个签名者
            if public_key:
                self.required_signers = [public_key]
            else:
                self.required_signers = []
        else:
            self.required_signers = required_signers
        
        # 初始化签名表
        if signature and public_key:
            self.signatures[public_key] = signature
    
    def add_signature(self, address: str, signature: str):
        """
        添加一个签名
        
        Args:
            address: 签名者地址（公钥）
            signature: 签名
        """
        self.signatures[address] = signature
    
    def is_fully_signed(self) -> bool:
        """
        检查是否所有必要的地址都已签名
        
        Returns:
            True 如果所有 required_signers 都已签名
        """
        return all(signer in self.signatures for signer in self.required_signers)
    
    def get_unsigned_signers(self) -> List[str]:
        """
        获取还未签名的地址列表
        
        Returns:
            还未签名的地址列表
        """
        return [signer for signer in self.required_signers if signer not in self.signatures]
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            "txid": self.txid,
            "vout": self.vout,
            "signature": self.signature,  # 向后兼容
            "public_key": self.public_key,  # 向后兼容
            "signatures": self.signatures,  # 多签
            "required_signers": self.required_signers  # 多签
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]):
        """从字典创建"""
        inp = cls(
            txid=data["txid"],
            vout=data["vout"],
            signature=data.get("signature"),
            public_key=data.get("public_key"),
            required_signers=data.get("required_signers")
        )
        # 恢复多签信息
        if "signatures" in data:
            inp.signatures = data["signatures"]
        return inp


class TransactionOutput:
    """交易输出 - 创建新的UTXO"""
    
    def __init__(self,
                 amount: float,           # CPC数量
                 address: str,            # 接收地址
                 script_pubkey: str,      # 锁定脚本
                 utxo_type: str = "fuel",
                 payload: Optional[Dict] = None):
        """
        初始化交易输出
        
        Args:
            amount: CPC数量
            address: 接收地址
            script_pubkey: 锁定脚本
            utxo_type: UTXO类型
            payload: 版权信息等附加数据
        """
        self.amount = amount
        self.address = address
        self.script_pubkey = script_pubkey
        self.utxo_type = utxo_type
        self.payload = payload or {}
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            "amount": self.amount,
            "address": self.address,
            "script_pubkey": self.script_pubkey,
            "utxo_type": self.utxo_type,
            "payload": self.payload
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]):
        """从字典创建"""
        return cls(
            amount=data["amount"],
            address=data["address"],
            script_pubkey=data["script_pubkey"],
            utxo_type=data.get("utxo_type", "fuel"),
            payload=data.get("payload", {})
        )


class Transaction:
    """
    CPC交易类
    支持多种版权相关的交易类型
    """
    
    # 交易类型常量
    # 注意：CPC是功能性凭证，不是通用货币
    # UTXO类型只有两种：fuel（系统分发的CPC）和copyright（版权UTXO）
    TYPE_FAUCET = "faucet"                         # 水龙头（系统分发CPC）
    TYPE_COPYRIGHT_REG = "copyright_register"      # 版权注册（阶段一）
    TYPE_AUTH_LOCK = "authorization_lock"          # 授权锁定（阶段二）
    TYPE_AUTH_ACTIVATE = "authorization_activate"  # 授权激活（阶段三）
    TYPE_RENEWAL = "renewal"                       # 续期（阶段四）
    TYPE_REDEMPTION = "redemption"                 # 赎回（阶段四）
    TYPE_SUB_LICENSE = "sub_license"               # 次级授权（阶段五）
    
    def __init__(self,
                 inputs: List[TransactionInput],
                 outputs: List[TransactionOutput],
                 tx_type: str = TYPE_FAUCET,  # 默认类型，但通常需要明确指定
                 metadata: Optional[Dict] = None):
        """
        初始化交易
        
        Args:
            inputs: 交易输入列表
            outputs: 交易输出列表
            tx_type: 交易类型
            metadata: 交易元数据
        """
        self.inputs = inputs
        self.outputs = outputs
        self.tx_type = tx_type
        self.metadata = metadata or {}
        self.timestamp = time.time() # 创建时间
        self.txid = self.calculate_txid() # 交易ID
    
    def calculate_txid(self) -> str:
        """计算交易ID"""
        tx_data = {
            "inputs": [inp.to_dict() for inp in self.inputs],
            "outputs": [out.to_dict() for out in self.outputs],
            "tx_type": self.tx_type,
            "timestamp": self.timestamp,
            "metadata": self.metadata
        }
        tx_string = json.dumps(tx_data, sort_keys=True)
        return hashlib.sha256(tx_string.encode()).hexdigest()
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            "txid": self.txid,
            "inputs": [inp.to_dict() for inp in self.inputs],
            "outputs": [out.to_dict() for out in self.outputs],
            "tx_type": self.tx_type,
            "timestamp": self.timestamp,
            "metadata": self.metadata
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]):
        """从字典创建交易"""
        tx = cls(
            inputs=[TransactionInput.from_dict(inp) for inp in data["inputs"]],
            outputs=[TransactionOutput.from_dict(out) for out in data["outputs"]],
            tx_type=data.get("tx_type", cls.TYPE_FAUCET),
            metadata=data.get("metadata", {})
        )
        tx.timestamp = data["timestamp"]
        tx.txid = data["txid"]
        return tx
    
    def is_fully_signed(self) -> bool:
        """
        检查交易是否已被所有参与方签名
        
        Returns:
            True 如果所有输入都已被完全签名
        """
        return all(inp.is_fully_signed() for inp in self.inputs if inp.required_signers)
    
    def get_unsigned_signers(self) -> List[tuple]:
        """
        获取还未签名的地址列表
        
        Returns:
            List of (input_index, unsigned_addresses)
        """
        unsigned = []
        for i, inp in enumerate(self.inputs):
            if inp.required_signers:
                unsigned_addrs = inp.get_unsigned_signers()
                if unsigned_addrs:
                    unsigned.append((i, unsigned_addrs))
        return unsigned
    
    def add_signature(self, input_index: int, signer_address: str, signature: str):
        """
        为特定输入添加签名
        
        Args:
            input_index: 输入的索引
            signer_address: 签名者地址（公钥）
            signature: 签名
        """
        if input_index < len(self.inputs):
            self.inputs[input_index].add_signature(signer_address, signature)
            # 重新计算交易ID
            self.txid = self.calculate_txid()


class TransactionValidator:
    """
    交易验证器
    验证交易的合法性
    包含版权类型状态机验证，防止非法状态转换
    """
    
    # 版权类型状态机：定义合法的状态转换
    COPYRIGHT_STATE_MACHINE = {
        # 合法的状态转换
        "sovereignty": ["instruction"],  # 主权 -> 指令（授权锁定）
        "instruction": ["proof"],        # 指令 -> 证明（授权激活）
        "proof": ["proof", "secondary"], # 证明 -> 证明（续期）或 证明 -> 次级（次级授权）
        "secondary": []                 # 次级不能转换（终端状态）
    }
    
    def __init__(self, blockchain: List):
        """
        初始化验证器
        
        Args:
            blockchain: 区块链列表（CPCBlock对象列表）
        """
        # 使用基于区块扫描的UTXO管理器，而不是全局UTXO池
        self.utxo_manager = BlockchainUTXOManager(blockchain)
    
    def _validate_copyright_state_transition(self, 
                                            input_copyright_type: str,
                                            output_copyright_type: str) -> Tuple[bool, str]:
        """
        验证版权类型状态转换是否符合状态机规则
        
        规则：
        1. 允许重新铸造（相同类型）：sovereignty -> sovereignty, proof -> proof
        2. 允许状态转换：sovereignty -> instruction, instruction -> proof, proof -> secondary
        3. 禁止逆向转换：proof -> sovereignty, secondary -> proof 等
        
        Args:
            input_copyright_type: 输入UTXO的版权类型
            output_copyright_type: 输出UTXO的版权类型
            
        Returns:
            (是否合法, 错误信息)
        """

        # 允许重新铸造（相同类型）
        # sovereignty 和 proof 都可以重新铸造，secondary 不能
        if input_copyright_type == output_copyright_type:
            if input_copyright_type in ["sovereignty", "proof"]:
                return True, ""
            else:
                return False, f"{input_copyright_type} 不能重新铸造"
        
        # 检查是否允许的状态转换
        allowed_transitions = self.COPYRIGHT_STATE_MACHINE.get(input_copyright_type, [])
        
        if output_copyright_type not in allowed_transitions:
            return False, (
                f"非法的版权状态转换: {input_copyright_type} -> {output_copyright_type}. "
                f"允许的转换: {allowed_transitions} 或重新铸造（相同类型）"
            )
        
        return True, ""
    
    def _validate_address_ownership(self,
                                   tx_type: str,
                                   inputs: List[TransactionInput],
                                   outputs: List[TransactionOutput]) -> Tuple[bool, str]:
        """
        验证交易中的地址所有权约束
        
        根据 UTXO 模型文档的矿工验证共识规则：
        - 交易 B（授权锁定）：sovereignty UTXO 的输入地址必须等于输出地址
        - 交易 D（续期）：sovereignty 和 proof UTXO 的输入地址必须分别等于对应的输出地址
        - 交易 E（次级授权）：proof UTXO 的输入地址必须等于输出地址（公司1的权利被保护）
        - 交易 C（激活）：instruction 到 proof 的转换，输入地址必须等于输出地址
        
        Args:
            tx_type: 交易类型
            inputs: 交易输入列表
            outputs: 交易输出列表
            
        Returns:
            (是否有效, 错误信息)
        """
        if tx_type == Transaction.TYPE_AUTH_LOCK:
            # 交易 B：授权锁定
            # 验证 sovereignty 输入地址 == sovereignty 输出地址
            sovereignty_inputs = {}
            for inp in inputs:
                utxo = self.utxo_manager.get_utxo(inp.txid, inp.vout, scan_months=3)
                if utxo and utxo.utxo_type == "copyright":
                    payload = utxo.payload
                    if payload.get("copyright_type") == "sovereignty":
                        # 记录 sovereignty 输入的地址
                        sovereignty_inputs[utxo.payload.get("work_hash")] = utxo.address
            
            # 检查 sovereignty 输出的地址是否匹配
            for out in outputs:
                if out.utxo_type == "copyright":
                    payload = out.payload
                    if payload.get("copyright_type") == "sovereignty":
                        work_hash = payload.get("work_hash")
                        if work_hash in sovereignty_inputs:
                            if out.address != sovereignty_inputs[work_hash]:
                                return False, (
                                    f"交易 B（授权锁定）：sovereignty UTXO 地址变化被禁止。"
                                    f"输入地址: {sovereignty_inputs[work_hash]}, 输出地址: {out.address}"
                                )
            
            return True, ""
        
        elif tx_type == Transaction.TYPE_RENEWAL:
            # 交易 D：续期
            # 验证 sovereignty 和 proof 输入地址分别等于对应的输出地址
            sovereignty_inputs = {}
            proof_inputs = {}
            
            for inp in inputs:
                utxo = self.utxo_manager.get_utxo(inp.txid, inp.vout, scan_months=3)
                if utxo and utxo.utxo_type == "copyright":
                    payload = utxo.payload
                    copyright_type = payload.get("copyright_type")
                    work_hash = payload.get("work_hash")
                    
                    if copyright_type == "sovereignty":
                        sovereignty_inputs[work_hash] = utxo.address
                    elif copyright_type == "proof":
                        proof_inputs[work_hash] = utxo.address
            
            # 检查输出地址
            for out in outputs:
                if out.utxo_type == "copyright":
                    payload = out.payload
                    copyright_type = payload.get("copyright_type")
                    work_hash = payload.get("work_hash")
                    
                    if copyright_type == "sovereignty":
                        if work_hash in sovereignty_inputs:
                            if out.address != sovereignty_inputs[work_hash]:
                                return False, (
                                    f"交易 D（续期）：sovereignty UTXO 地址变化被禁止。"
                                    f"输入地址: {sovereignty_inputs[work_hash]}, 输出地址: {out.address}"
                                )
                    elif copyright_type == "proof":
                        if work_hash in proof_inputs:
                            if out.address != proof_inputs[work_hash]:
                                return False, (
                                    f"交易 D（续期）：proof UTXO 地址变化被禁止。"
                                    f"输入地址: {proof_inputs[work_hash]}, 输出地址: {out.address}"
                                )
            
            return True, ""
        
        elif tx_type == Transaction.TYPE_SUB_LICENSE:
            # 交易 E：次级授权
            # 验证 proof UTXO（C1）的输入地址等于输出地址
            proof_inputs = {}
            
            for inp in inputs:
                utxo = self.utxo_manager.get_utxo(inp.txid, inp.vout, scan_months=3)
                if utxo and utxo.utxo_type == "copyright":
                    payload = utxo.payload
                    if payload.get("copyright_type") == "proof":
                        work_hash = payload.get("work_hash")
                        proof_inputs[work_hash] = utxo.address
            
            # 检查 proof 输出地址是否匹配（C1 重新铸造）
            for out in outputs:
                if out.utxo_type == "copyright":
                    payload = out.payload
                    if payload.get("copyright_type") == "proof" and not payload.get("parent_utxo"):
                        # C1 重新铸造的 proof UTXO
                        work_hash = payload.get("work_hash")
                        if work_hash in proof_inputs:
                            if out.address != proof_inputs[work_hash]:
                                return False, (
                                    f"交易 E（次级授权）：C1 proof UTXO 地址变化被禁止。"
                                    f"输入地址: {proof_inputs[work_hash]}, 输出地址: {out.address}"
                                )
            
            return True, ""
        
        elif tx_type == Transaction.TYPE_AUTH_ACTIVATE:
            # 交易 C：授权激活
            # 验证 instruction 到 proof 的转换，输入地址必须等于输出地址
            instruction_inputs = {}
            
            for inp in inputs:
                utxo = self.utxo_manager.get_utxo(inp.txid, inp.vout, scan_months=3)
                if utxo and utxo.utxo_type == "copyright":
                    payload = utxo.payload
                    if payload.get("copyright_type") == "instruction":
                        work_hash = payload.get("work_hash")
                        instruction_inputs[work_hash] = utxo.address
            
            # 检查 proof 输出地址是否匹配
            for out in outputs:
                if out.utxo_type == "copyright":
                    payload = out.payload
                    if payload.get("copyright_type") == "proof":
                        work_hash = payload.get("work_hash")
                        if work_hash in instruction_inputs:
                            if out.address != instruction_inputs[work_hash]:
                                return False, (
                                    f"交易 C（激活）：instruction 转换为 proof 时地址必须保持不变。"
                                    f"输入地址: {instruction_inputs[work_hash]}, 输出地址: {out.address}"
                                )
            
            return True, ""
        
        # 其他交易类型不需要地址所有权检查
        return True, ""
    
    
    def validate_transaction(self, transaction: Transaction) -> Tuple[bool, str]:
        """
        验证交易
        
        验证步骤：
        0. 多签完整性检查 - 确保所有需要签名的地址都已签名
        1. 签名和时间锁验证 - 验证所有输入的解锁脚本是否被发起者正确满足
        2. Input/Output 数量和价值检查 - 检查金额有效性
        3. 交易类别匹配和 Payload 一致性 - 验证版权 UTXO 的 payload 数据完整性
        4. 强制地址所有权检查（关键） - 确保主权和已证明的权利不会被非法转移
        
        Returns:
            (是否有效, 错误信息)
        """
        # 0. 检查多签完整性（如果有多签需求）
        if not transaction.is_fully_signed():
            unsigned_signers = transaction.get_unsigned_signers()
            if unsigned_signers:
                error_msg = "交易还未被所有参与方签名。还需要以下地址签名：\n"
                for input_idx, unsigned_addrs in unsigned_signers:
                    error_msg += f"  Input #{input_idx}: {', '.join(unsigned_addrs[:20])}...\n"
                return False, error_msg
        
        # 水龙头交易特殊处理
        if transaction.tx_type == Transaction.TYPE_FAUCET:
            return self._validate_faucet_transaction(transaction)
        
        # 版权注册交易特殊处理（可以没有输入）
        if transaction.tx_type == Transaction.TYPE_COPYRIGHT_REG:
            return self._validate_copyright_register(transaction)
        
        input_amount = 0
        # 遍历所有的交易输入
        for inp in transaction.inputs:
            # 1. 验证输入是否存在且未花费
            utxo = self.utxo_manager.get_utxo(inp.txid, inp.vout, scan_months=3) # 一笔待花费UTXO
            if not utxo:
                return False, f"UTXO {inp.txid}:{inp.vout} 不存在或已被花费"
            
            # 2. 验证签名
            if not self._verify_signature(inp, transaction):
                return False, f"输入 {inp.txid}:{inp.vout} 的签名验证失败"
            
            # 3. 验证锁定脚本
            script = TimeLockScript.from_string(utxo.script_pubkey) # 锁定脚本
            address = self._public_key_to_address(inp.public_key) # 锁定地址
            
            # 获取授权到期时间（如果是版权UTXO，动态计算）
            end_time = None
            if utxo.utxo_type == "copyright" and utxo.payload: # 如果是版权交易
                # 从CopyrightPayload动态计算到期时间（固定3个月）
                from utxo import CopyrightPayload
                payload = CopyrightPayload.from_dict(utxo.payload)
                end_time = payload.get_end_time() # 到期时间
            
            if not script.can_spend(int(time.time()), [address], end_time=end_time):
                return False, f"UTXO {inp.txid}:{inp.vout} 的锁定条件未满足（可能已过期）"
            
            input_amount += utxo.amount
        
        # 4. 验证输入输出金额
        output_amount = sum(out.amount for out in transaction.outputs) # 输出金额
        
        # 允许有小额手续费消耗
        if output_amount > input_amount:
            return False, f"输出金额({output_amount})超过输入金额({input_amount})"
        
        # 5. 根据交易类型进行特定验证（包含状态机验证）
        if transaction.tx_type == Transaction.TYPE_AUTH_LOCK:
            is_valid, error_msg = self._validate_authorization_lock(transaction)
            if not is_valid:
                return False, error_msg
            
            # 强制地址所有权检查
            is_valid, error_msg = self._validate_address_ownership(
                transaction.tx_type, transaction.inputs, transaction.outputs
            )
            if not is_valid:
                return False, error_msg
        
        elif transaction.tx_type == Transaction.TYPE_AUTH_ACTIVATE:
            is_valid, error_msg = self._validate_authorization_activate(transaction)
            if not is_valid:
                return False, error_msg
            
            # 强制地址所有权检查
            is_valid, error_msg = self._validate_address_ownership(
                transaction.tx_type, transaction.inputs, transaction.outputs
            )
            if not is_valid:
                return False, error_msg
        
        elif transaction.tx_type == Transaction.TYPE_RENEWAL:
            is_valid, error_msg = self._validate_renewal(transaction)
            if not is_valid:
                return False, error_msg
            
            # 强制地址所有权检查
            is_valid, error_msg = self._validate_address_ownership(
                transaction.tx_type, transaction.inputs, transaction.outputs
            )
            if not is_valid:
                return False, error_msg
        
        elif transaction.tx_type == Transaction.TYPE_SUB_LICENSE:
            is_valid, error_msg = self._validate_sub_license(transaction)
            if not is_valid:
                return False, error_msg
            
            # 强制地址所有权检查
            is_valid, error_msg = self._validate_address_ownership(
                transaction.tx_type, transaction.inputs, transaction.outputs
            )
            if not is_valid:
                return False, error_msg
        
        return True, "交易验证成功"
    
    def _validate_faucet_transaction(self, transaction: Transaction) -> Tuple[bool, str]:
        """验证水龙头交易"""
        # 水龙头交易没有输入
        if len(transaction.inputs) != 0:
            return False, "水龙头交易不应有输入"
        
        # 每次最多领取10 CPC
        total_output = sum(out.amount for out in transaction.outputs)
        if total_output > 10:
            return False, "水龙头单次最多发放10 CPC"
        
        # TODO: 可以添加地址领取频率限制
        
        return True, "水龙头交易验证成功"
    
    def _validate_copyright_register(self, transaction: Transaction) -> Tuple[bool, str]:
        """验证版权注册交易"""
        # 版权注册需要消耗燃料UTXO
        if len(transaction.inputs) == 0:
            return False, "版权注册需要消耗燃料UTXO"
        
        # 必须有版权UTXO输出
        copyright_outputs = [out for out in transaction.outputs if out.utxo_type == "copyright"]
        if len(copyright_outputs) == 0:
            return False, "版权注册交易必须包含版权UTXO输出"
        
        # 验证版权payload
        for out in copyright_outputs:
            if "work_hash" not in out.payload:
                return False, "版权UTXO必须包含作品哈希值"
            if "copyright_type" not in out.payload or out.payload["copyright_type"] != "sovereignty":
                return False, "注册交易必须创建主权UTXO"
        
        return True, "版权注册交易验证成功"
    
    def _validate_authorization_lock(self, transaction: Transaction) -> Tuple[bool, str]:
        """验证授权锁定交易"""
        # 必须包含版权主权UTXO作为输入
        sovereignty_input = None
        for inp in transaction.inputs:
            utxo = self.utxo_manager.get_utxo(inp.txid, inp.vout, scan_months=3)
            if utxo and utxo.utxo_type == "copyright":
                payload = utxo.payload
                if payload.get("copyright_type") == "sovereignty":
                    sovereignty_input = payload.get("copyright_type")
                    break
        
        if not sovereignty_input:
            return False, "授权锁定交易必须包含版权主权UTXO作为输入"
        
        # 必须创建授权指令UTXO
        instruction_outputs = [out for out in transaction.outputs 
                             if out.utxo_type == "copyright" 
                             and out.payload.get("copyright_type") == "instruction"]
        
        if len(instruction_outputs) == 0:
            return False, "授权锁定交易必须创建授权指令UTXO"
        
        # 检查是否有重新铸造的sovereignty UTXO
        sovereignty_outputs = [out for out in transaction.outputs
                               if out.utxo_type == "copyright"
                               and out.payload.get("copyright_type") == "sovereignty"]
        
        # 状态机验证：sovereignty -> instruction
        for out in instruction_outputs:
            output_type = out.payload.get("copyright_type")
            is_valid, error_msg = self._validate_copyright_state_transition(
                sovereignty_input, output_type
            )
            if not is_valid:
                return False, error_msg
        
        # 状态机验证：sovereignty -> sovereignty（重新铸造，允许）
        for out in sovereignty_outputs:
            output_type = out.payload.get("copyright_type")
            is_valid, error_msg = self._validate_copyright_state_transition(
                sovereignty_input, output_type
            )
            if not is_valid:
                return False, f"重新铸造sovereignty验证失败: {error_msg}"
        
        # 注意：授权期限固定为3个月，从UTXO创建时间开始计算
        # 不再需要时间锁，授权期限由created_at + 3个月动态计算
        
        return True, "授权锁定交易验证成功"
    
    def _validate_authorization_activate(self, transaction: Transaction) -> Tuple[bool, str]:
        """验证授权激活交易"""
        # 必须包含授权指令UTXO作为输入
        instruction_input = None
        work_hash = None
        
        for inp in transaction.inputs:
            utxo = self.utxo_manager.get_utxo(inp.txid, inp.vout, scan_months=3)
            if utxo and utxo.utxo_type == "copyright":
                payload = utxo.payload
                if payload.get("copyright_type") == "instruction":
                    instruction_input = payload.get("copyright_type")
                    work_hash = payload.get("work_hash")
                    
                    # 检查授权是否已过期（动态计算，固定3个月）
                    from utxo import CopyrightPayload
                    instruction_payload = CopyrightPayload.from_dict(payload)
                    if instruction_payload.is_expired():
                        return False, "授权指令UTXO已过期（授权期限固定为3个月）"
                    break
        
        if not instruction_input:
            return False, "授权激活交易必须包含授权指令UTXO作为输入"
        
        # 必须创建证明UTXO，且作品哈希必须继承
        proof_outputs = [out for out in transaction.outputs 
                        if out.utxo_type == "copyright" 
                        and out.payload.get("copyright_type") == "proof"]
        
        if len(proof_outputs) == 0:
            return False, "授权激活交易必须创建证明UTXO"
        
        # 状态机验证：instruction -> proof
        for out in proof_outputs:
            output_type = out.payload.get("copyright_type")
            is_valid, error_msg = self._validate_copyright_state_transition(
                instruction_input, output_type
            )
            if not is_valid:
                return False, error_msg
            
            # 验证作品哈希继承
            if out.payload.get("work_hash") != work_hash:
                return False, "证明UTXO必须继承授权指令UTXO的作品哈希"
        
        return True, "授权激活交易验证成功"
    
    def _validate_renewal(self, transaction: Transaction) -> Tuple[bool, str]:
        """验证续期交易"""
        # 必须包含旧的证明UTXO
        proof_input = None
        
        for inp in transaction.inputs:
            utxo = self.utxo_manager.get_utxo(inp.txid, inp.vout, scan_months=3)
            if utxo and utxo.utxo_type == "copyright":
                payload = utxo.payload
                if payload.get("copyright_type") == "proof":
                    proof_input = payload.get("copyright_type")
                    
                    # 验证是否在到期前续期（动态计算，固定3个月）
                    from utxo import CopyrightPayload
                    copyright_payload = CopyrightPayload.from_dict(payload)
                    if copyright_payload.is_expired():
                        return False, "证明UTXO已过期，无法续期"
                    break
        
        if not proof_input:
            return False, "续期交易必须包含证明UTXO作为输入"
        
        # 必须创建新的证明UTXO
        new_proof_outputs = [out for out in transaction.outputs 
                           if out.utxo_type == "copyright" 
                           and out.payload.get("copyright_type") == "proof"]
        
        if len(new_proof_outputs) == 0:
            return False, "续期交易必须创建新的证明UTXO"
        
        # 状态机验证：proof -> proof（续期保持proof状态）
        for out in new_proof_outputs:
            output_type = out.payload.get("copyright_type")
            is_valid, error_msg = self._validate_copyright_state_transition(
                proof_input, output_type
            )
            if not is_valid:
                return False, error_msg
        
        return True, "续期交易验证成功"
    
    def _validate_sub_license(self, transaction: Transaction) -> Tuple[bool, str]:
        """验证次级授权交易"""
        # 必须包含C1的证明UTXO
        c1_proof_input = None
        c1_proof_payload = None
        
        for inp in transaction.inputs:
            utxo = self.utxo_manager.get_utxo(inp.txid, inp.vout, scan_months=3)
            if utxo and utxo.utxo_type == "copyright":
                payload = utxo.payload
                if payload.get("copyright_type") == "proof":
                    c1_proof_input = payload.get("copyright_type")
                    c1_proof_payload = payload
                    break
        
        if not c1_proof_input:
            return False, "次级授权交易必须包含主授权的证明UTXO"
        
        # 必须重新铸造C1的UTXO和创建C2的UTXO
        c1_outputs = []  # C1重新铸造的proof UTXO
        c2_outputs = []   # C2的secondary UTXO
        
        for out in transaction.outputs:
            if out.utxo_type == "copyright":
                output_type = out.payload.get("copyright_type")
                if output_type == "proof" and not out.payload.get("parent_utxo"):
                    # C1重新铸造的proof UTXO（没有parent_utxo）
                    c1_outputs.append(out)
                elif output_type == "secondary":
                    # C2的secondary UTXO
                    c2_outputs.append(out)
        
        if len(c1_outputs) == 0:
            return False, "次级授权必须重新铸造C1的证明UTXO"
        
        if len(c2_outputs) == 0:
            return False, "次级授权必须创建C2的次级UTXO"
        
        # 状态机验证：proof -> proof（C1重新铸造）
        for out in c1_outputs:
            output_type = out.payload.get("copyright_type")
            is_valid, error_msg = self._validate_copyright_state_transition(
                c1_proof_input, output_type
            )
            if not is_valid:
                return False, f"C1重新铸造验证失败: {error_msg}"
        
        # 状态机验证：proof -> secondary（C2创建次级授权）
        for out in c2_outputs:
            output_type = out.payload.get("copyright_type")
            is_valid, error_msg = self._validate_copyright_state_transition(
                c1_proof_input, output_type
            )
            if not is_valid:
                return False, f"C2次级授权验证失败: {error_msg}"
        
        # 验证C2的权利范围是C1的子集
        c1_rights = set(c1_proof_payload.get("rights_scope", []))
        for c2_out in c2_outputs:
            c2_rights = set(c2_out.payload.get("rights_scope", []))
            if not c2_rights.issubset(c1_rights):
                return False, "C2的权利范围必须是C1的子集"
        
        return True, "次级授权交易验证成功"
    
    def _verify_signature(self, inp: TransactionInput, transaction: Transaction) -> bool:
        """
        验证交易输入的签名
        支持单签和多签
        
        返回：True 如果所有必要的签名都有效
        """
        try:
            # 获取UTXO
            utxo = self.utxo_manager.get_utxo(inp.txid, inp.vout, scan_months=3)
            if not utxo:
                return False
            
            # 如果有多签信息，验证多签
            if inp.signatures:
                # 多签验证：验证所有已签名的地址都对应有效的签名
                for signer_address, signature_str in inp.signatures.items():
                    if not self._verify_single_signature(signer_address, signature_str, transaction):
                        return False
                
                # 检查是否所有必要的地址都已签名
                if not inp.is_fully_signed():
                    return False
                
                return True
            
            # 否则，验证单签（向后兼容）
            if not inp.public_key or not inp.signature:
                return False
            
            # 验证公钥对应的地址是否匹配
            address = self._public_key_to_address(inp.public_key)
            if address != utxo.address:
                return False
            
            # 验证签名
            return self._verify_single_signature(address, inp.signature, transaction)
        
        except Exception as e:
            print(f"签名验证异常: {e}")
            return False
    
    def _verify_single_signature(self, signer_address: str, signature_str: str, transaction: Transaction) -> bool:
        """
        验证单个签名
        
        Args:
            signer_address: 签名者地址（公钥）
            signature_str: 签名字符串（base64）
            transaction: 交易对象
            
        Returns:
            True 如果签名有效
        """
        try:
            public_key_bytes = base64.b64decode(signer_address)
            signature_bytes = base64.b64decode(signature_str)
            
            vk = ecdsa.VerifyingKey.from_string(public_key_bytes, curve=ecdsa.SECP256k1)
            message = transaction.txid.encode()
            
            return vk.verify(signature_bytes, message)
        except Exception as e:
            print(f"单个签名验证异常: {e}")
            return False
    
    def _public_key_to_address(self, public_key: str) -> str:
        """将公钥转换为地址（简化版）"""
        # 实际应用中应该使用更复杂的地址生成算法
        return public_key

