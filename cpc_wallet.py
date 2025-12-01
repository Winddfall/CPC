"""
时权链 (Time-Rights Chain) - CPC钱包
支持版权注册、授权管理等功能
"""

import requests
import time
import base64
import ecdsa
import json
import hashlib
import os
from typing import Optional, List, Dict
from urllib.parse import quote

from utxo import CopyrightPayload, TimeLockScript
from transaction import Transaction, TransactionInput, TransactionOutput


# CPC节点URL
NODE_URL = "http://localhost:5001"


class CPCWallet:
    """CPC钱包类"""
    
    def __init__(self, private_key: str, public_key: str):
        """
        初始化钱包
        
        Args:
            private_key: 私钥（hex格式）
            public_key: 公钥（base64格式）
        """
        self.private_key = private_key
        self.public_key = public_key
        self.address = public_key  # 简化版本：公钥即地址
    
    def get_balance(self) -> float:
        """查询钱包余额"""
        try:
            # 使用 query parameter 方式，避免 URL 路径中的特殊字符问题
            response = requests.get(f"{NODE_URL}/utxo", params={"address": self.address})
            if response.status_code == 200:
                data = response.json()
                return data.get("balance", 0)
            else:
                print("查询余额失败")
                return 0
        except Exception as e:
            print(f"网络错误: {e}")
            return 0
    
    def get_utxos(self) -> List[Dict]:
        """获取钱包的所有UTXO"""
        try:
            # 使用 query parameter 方式，避免 URL 路径中的特殊字符问题
            response = requests.get(f"{NODE_URL}/utxo", params={"address": self.address})
            if response.status_code == 200:
                data = response.json()
                return data.get("utxos", [])
            else:
                return []
        except Exception as e:
            print(f"网络错误: {e}")
            return []
    
    def sign_message(self, message: str) -> str:
        """对消息签名"""
        sk = ecdsa.SigningKey.from_string(
            bytes.fromhex(self.private_key),
            curve=ecdsa.SECP256k1
        )
        signature = sk.sign(message.encode())
        return base64.b64encode(signature).decode()
    
    # 注意：已移除用户间转账功能（send_cpc方法）
    # 原因：CPC是功能性凭证，只有矿工可以用CPC换取法币（需要身份证明）
    # 普通用户之间转账没有意义，CPC主要用于版权管理操作
    
    def register_copyright(self, work_file_path: str, work_title: str) -> Optional[str]:
        """
        注册版权（阶段一）
        
        Args:
            work_file_path: 作品文件路径
            work_title: 作品标题
            
        Returns:
            交易ID或None
        """
        # 计算作品哈希
        try:
            with open(work_file_path, 'rb') as f:
                work_data = f.read()
                work_hash = hashlib.sha256(work_data).hexdigest()
        except Exception as e:
            print(f"✗ 读取文件失败: {e}")
            return None
        
        print(f"作品哈希: {work_hash}")
        
        # 获取燃料UTXO
        utxos = self.get_utxos()
        fuel_utxo = None
        
        for utxo in utxos:
            if utxo["utxo_type"] == "fuel" and utxo["amount"] >= 0.1:
                fuel_utxo = utxo
                break
        
        if not fuel_utxo:
            print("✗ 需要至少0.1 CPC作为燃料，请先使用水龙头获取")
            return None
        
        # 构建交易
        inputs = []
        outputs = []
        
        # 输入：燃料UTXO
        tx_input = TransactionInput(
            txid=fuel_utxo["txid"],
            vout=fuel_utxo["vout"],
            signature="",
            public_key=self.public_key
        )
        inputs.append(tx_input)
        
        # 输出1：版权主权UTXO
        copyright_payload = CopyrightPayload(
            work_hash=work_hash,
            work_title=work_title,
            author=self.address,
            copyright_type="sovereignty",
            rights_scope=["复制权", "发行权", "改编权", "表演权", "放映权", "广播权"]
        )
        
        copyright_script = TimeLockScript(
            script_type=TimeLockScript.SCRIPT_TYPE_P2PKH,
            addresses=[self.address]
        ).to_string()
        
        outputs.append(TransactionOutput(
            amount=1.0,  # 版权主权UTXO固定1 CPC
            address=self.address,
            script_pubkey=copyright_script,
            utxo_type="copyright",
            payload=copyright_payload.to_dict()
        ))
        
        # 输出2：找零
        change = fuel_utxo["amount"] - 1.0 - 0.01  # 扣除版权UTXO和手续费
        if change > 0:
            change_script = TimeLockScript(
                script_type=TimeLockScript.SCRIPT_TYPE_P2PKH,
                addresses=[self.address]
            ).to_string()
            
            outputs.append(TransactionOutput(
                amount=change,
                address=self.address,
                script_pubkey=change_script,
                utxo_type="fuel"
            ))
        
        # 创建交易
        tx = Transaction(
            inputs=inputs,
            outputs=outputs,
            tx_type=Transaction.TYPE_COPYRIGHT_REG,
            metadata={"work_title": work_title}
        )
        
        # 签名
        for inp in tx.inputs:
            signature = self.sign_message(tx.txid)
            inp.signature = signature
            inp.add_signature(self.address, signature)
        
        # 提交
        return self._submit_transaction(tx, "版权注册")
    
    def lock_authorization(self,
                          work_hash: str,
                          licensee_address: str,
                          rights_scope: List[str],
                          create_multisig: bool = True) -> Optional[str]:
        """
        授权锁定（阶段二）
        支持多方签名：作者提供主权UTXO，公司提供燃料UTXO支付手续费
        
        多签工作流:
        1. 作者: create_multisig=True 创建不完整的多签交易
        2. 保存为临时文件，发送给被授权人
        3. 被授权人: 调用 prepare_multisig_authorization() 添加自己的UTXO
        4. 被授权人: 调用 sign_pending_transaction() 签名交易
        5. 交易完全签名后自动提交
        
        注意：授权期限固定为3个月，从UTXO创建时间开始计算
        
        Args:
            work_hash: 作品哈希
            licensee_address: 被授权人地址
            rights_scope: 授权的权利范围
            create_multisig: 是否创建多签交易
            
        Returns:
            交易ID（单签）或临时文件名（多签）
        """
        # 查找版权主权UTXO（作者的）
        utxos = self.get_utxos()
        sovereignty_utxo = None
        
        for utxo in utxos:
            if (utxo["utxo_type"] == "copyright" and 
                utxo["payload"].get("copyright_type") == "sovereignty" and
                utxo["payload"].get("work_hash") == work_hash):
                sovereignty_utxo = utxo
                break
        
        if not sovereignty_utxo:
            print("✗ 未找到该作品的版权主权UTXO")
            return None
        
        # 在多签模式下，仅由作者提供sovereignty，燃料由被授权人提供
        # 在单签模式下，作者提供燃料
        if not create_multisig:
            # 查找燃料UTXO（作者的）
            fuel_utxo = None
            for utxo in utxos:
                if utxo["utxo_type"] == "fuel" and utxo["amount"] >= 0.1:
                    fuel_utxo = utxo
                    break
            
            if not fuel_utxo:
                print("✗ 需要燃料UTXO用于支付手续费")
                return None
        else:
            fuel_utxo = None  # 多签模式下稍后由被授权人添加
        
        # 构建交易输入
        # 输入1：作者的版权主权UTXO（只需要作者签名）
        author_input = TransactionInput(
            txid=sovereignty_utxo["txid"],
            vout=sovereignty_utxo["vout"],
            public_key=self.address,
            required_signers=[self.address]
        )
        
        inputs = [author_input]
        
        # 在单签模式下添加燃料输入
        if not create_multisig and fuel_utxo:
            fuel_input = TransactionInput(
                txid=fuel_utxo["txid"],
                vout=fuel_utxo["vout"],
                public_key=self.address,
                required_signers=[self.address]
            )
            inputs.append(fuel_input)
        
        # 构建交易输出
        outputs = []
        
        # 输出1：授权指令UTXO给被授权人
        instruction_payload = CopyrightPayload(
            work_hash=work_hash,
            work_title=sovereignty_utxo["payload"]["work_title"],
            author=self.address,
            copyright_type="instruction",
            rights_scope=rights_scope
        )
        
        instruction_script = TimeLockScript(
            script_type=TimeLockScript.SCRIPT_TYPE_P2PKH,
            addresses=[licensee_address]
        ).to_string()
        
        outputs.append(TransactionOutput(
            amount=0.04,
            address=licensee_address,
            script_pubkey=instruction_script,
            utxo_type="copyright",
            payload=instruction_payload.to_dict()
        ))
        
        # 输出2：重新铸造版权主权UTXO给作者
        sovereignty_payload = CopyrightPayload(
            work_hash=work_hash,
            work_title=sovereignty_utxo["payload"]["work_title"],
            author=self.address,
            copyright_type="sovereignty",
            rights_scope=sovereignty_utxo["payload"]["rights_scope"]
        )
        
        sovereignty_script = TimeLockScript(
            script_type=TimeLockScript.SCRIPT_TYPE_P2PKH,
            addresses=[self.address]
        ).to_string()
        
        outputs.append(TransactionOutput(
            amount=1.0,
            address=self.address,
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
                "licensee": licensee_address,
                "multisig": create_multisig,
                "author": self.address,
                "note": "授权期限固定为3个月"
            }
        )
        
        # 作者签名自己的输入
        author_signature = self.sign_message(tx.txid)
        for i, inp in enumerate(tx.inputs):
            if self.address in inp.required_signers:
                inp.add_signature(self.address, author_signature)
        
        # 如果是多签模式，保存交易供被授权人继续
        if create_multisig:
            # 保存临时交易文件
            temp_tx_file = f"pending_auth_{tx.txid[:8]}.json"
            with open(temp_tx_file, 'w', encoding='utf-8') as f:
                json.dump(tx.to_dict(), f, indent=2, ensure_ascii=False)
            
            print(f"\n✓ 多签授权交易已创建（第一步）")
            print(f"  交易ID: {tx.txid[:16]}...")
            print(f"  临时文件: {temp_tx_file}")
            print(f"\n📝 请将以下信息发送给被授权人({licensee_address}):")
            print(f"  1. 临时文件: {temp_tx_file}")
            print(f"\n💡 被授权人需要执行以下步骤:")
            print(f"  1. 调用: wallet.prepare_multisig_authorization('{temp_tx_file}')")
            print(f"     (这会添加被授权人的燃料UTXO作为第二个输入)")
            print(f"  2. 调用: wallet.sign_pending_transaction('{temp_tx_file}')")
            print(f"     (这会签名交易并自动提交)")
            
            return temp_tx_file
        else:
            # 单签模式：直接提交
            if fuel_utxo:
                # 添加找零输出
                change = fuel_utxo["amount"] - 0.04 - 0.01  # 0.01手续费
                if change > 0:
                    outputs.append(TransactionOutput(
                        amount=change,
                        address=self.address,
                        script_pubkey=sovereignty_script,
                        utxo_type="fuel"
                    ))
            
            return self._submit_transaction(tx, "授权锁定（单签）")
    
    def sign_pending_transaction(self, tx_file: str) -> Optional[str]:
        """
        签名待签交易
        用于多签场景中，第二个签名者签名交易
        
        Args:
            tx_file: 临时交易文件路径
            
        Returns:
            交易ID（如果完全签名）或None
        """
        try:
            with open(tx_file, 'r', encoding='utf-8') as f:
                tx_dict = json.load(f)
        except FileNotFoundError:
            print(f"✗ 文件不存在: {tx_file}")
            return None
        except Exception as e:
            print(f"✗ 读取交易文件失败: {e}")
            return None
        
        # 从字典重建交易对象
        tx = Transaction.from_dict(tx_dict)
        
        # 找出需要当前钱包签名的输入
        unsigned_signers = tx.get_unsigned_signers()
        if not unsigned_signers:
            print("✓ 交易已完全签名")
            return self._submit_transaction(tx, "完全签名的授权交易")
        
        # 检查当前钱包地址是否需要签名
        wallet_address = self.address
        
        inputs_to_sign = []
        for i, inp in enumerate(tx.inputs):
            if wallet_address in inp.required_signers and wallet_address not in inp.signatures:
                inputs_to_sign.append(i)
        
        if not inputs_to_sign:
            print(f"✗ 当前钱包地址({wallet_address})不需要签名此交易")
            print(f"需要签名的地址: {unsigned_signers}")
            return None
        
        # 签名所有需要当前钱包签名的输入
        signature = self.sign_message(tx.txid)
        for inp_idx in inputs_to_sign:
            tx.inputs[inp_idx].add_signature(wallet_address, signature)
        
        print(f"✓ 已签名 {len(inputs_to_sign)} 个输入")
        print(f"  钱包地址: {wallet_address}")
        
        # 检查是否完全签名
        if tx.is_fully_signed():
            print(f"\n✅ 交易已完全签名，可以提交")
            result = self._submit_transaction(tx, "完全签名的授权交易")
            # 删除临时文件
            try:
                os.remove(tx_file)
            except:
                pass
            return result
        else:
            # 保存更新的交易文件
            with open(tx_file, 'w', encoding='utf-8') as f:
                json.dump(tx.to_dict(), f, indent=2, ensure_ascii=False)
            
            unsigned = tx.get_unsigned_signers()
            print(f"\n⏳ 交易仍需签名，等待以下地址签名:")
            for inp_idx, addrs in unsigned:
                print(f"  输入{inp_idx+1}: {addrs}")
            print(f"\n📝 交易已保存，等待其他签名者操作: {tx_file}")
            return None
    
    def prepare_multisig_authorization(self, tx_file: str) -> Optional[str]:
        """
        为多签授权交易添加被授权人的燃料UTXO
        这是被授权人在第一步接收交易后需要执行的操作
        
        Args:
            tx_file: 临时交易文件路径
            
        Returns:
            更新后的文件路径，或None if失败
        """
        # 读取交易文件
        try:
            with open(tx_file, 'r', encoding='utf-8') as f:
                tx_dict = json.load(f)
        except FileNotFoundError:
            print(f"✗ 文件不存在: {tx_file}")
            return None
        except Exception as e:
            print(f"✗ 读取交易文件失败: {e}")
            return None
        
        # 从字典重建交易对象
        tx = Transaction.from_dict(tx_dict)
        
        # 检查这是否是多签授权交易
        if not tx.metadata.get("multisig"):
            print("✗ 这不是一个多签授权交易")
            return None
        
        # 检查当前钱包是否是被授权人
        licensee = tx.metadata.get("licensee")
        if self.address != licensee:
            print(f"✗ 当前钱包({self.address})不是被授权人({licensee})")
            return None
        
        # 查找被授权人的燃料UTXO
        utxos = self.get_utxos()
        fuel_utxo = None
        for utxo in utxos:
            if utxo["utxo_type"] == "fuel" and utxo["amount"] >= 0.1:
                fuel_utxo = utxo
                break
        
        if not fuel_utxo:
            print("✗ 当前钱包中没有足够的燃料UTXO（需要至少0.1 CPC）")
            return None
        
        # 添加被授权人的燃料UTXO作为第二个输入
        fuel_input = TransactionInput(
            txid=fuel_utxo["txid"],
            vout=fuel_utxo["vout"],
            public_key=self.address,
            required_signers=[self.address]  # 被授权人签名
        )
        tx.inputs.append(fuel_input)
        
        # 添加找零输出
        outputs = tx.outputs
        # 找到原始作者的主权脚本（用于找零）
        author_script = None
        for out in outputs:
            # Transaction.from_dict 会返回 TransactionOutput 对象
            if isinstance(out, TransactionOutput):
                out_address = out.address
                out_script = out.script_pubkey
            else:
                out_address = out.get("address")
                out_script = out.get("script_pubkey")
            if out_address == tx.metadata.get("author"):
                author_script = out_script
                break
        
        if not author_script:
            # 如果找不到，使用被授权人的脚本
            author_script = TimeLockScript(
                script_type=TimeLockScript.SCRIPT_TYPE_P2PKH,
                addresses=[self.address]
            ).to_string()
        
        # 被授权人支付授权指令金额(0.04) + 手续费(0.01)
        change = fuel_utxo["amount"] - 0.04 - 0.01
        if change > 0:
            outputs.append(TransactionOutput(
                amount=change,
                address=self.address,
                script_pubkey=author_script,
                utxo_type="fuel"
            ))
        
        # 保存更新的交易
        with open(tx_file, 'w', encoding='utf-8') as f:
            json.dump(tx.to_dict(), f, indent=2, ensure_ascii=False)
        
        print(f"✓ 已添加被授权人的燃料UTXO")
        print(f"  燃料数量: {fuel_utxo['amount']} CPC")
        print(f"  手续费: 0.01 CPC")
        print(f"  找零: {change:.4f} CPC")
        print(f"\n✅ 交易已更新，可以进行签名")
        print(f"  请调用: sign_pending_transaction('{tx_file}')")
        
        return tx_file
    
    def activate_authorization(self, instruction_txid: str, instruction_vout: int) -> Optional[str]:
        """
        激活授权（阶段三）
        在时间锁到期后，被授权人激活授权
        
        Args:
            instruction_txid: 授权指令UTXO的交易ID
            instruction_vout: 授权指令UTXO的输出索引
            
        Returns:
            交易ID或None
        """
        # 查找授权指令UTXO
        utxos = self.get_utxos()
        instruction_utxo = None
        
        for utxo in utxos:
            if (utxo["txid"] == instruction_txid and 
                utxo["vout"] == instruction_vout and
                utxo["utxo_type"] == "copyright" and
                utxo["payload"].get("copyright_type") == "instruction"):
                instruction_utxo = utxo
                break
        
        if not instruction_utxo:
            print("✗ 未找到授权指令UTXO")
            return None
        
        # 检查授权是否已过期（动态计算，固定3个月）
        from utxo import CopyrightPayload
        instruction_payload = CopyrightPayload.from_dict(instruction_utxo["payload"])
        if instruction_payload.is_expired():
            print(f"✗ 授权已过期（授权期限固定为3个月）")
            return None
        
        # 构建交易
        inputs = [TransactionInput(
            txid=instruction_utxo["txid"],
            vout=instruction_utxo["vout"],
            signature="",
            public_key=self.public_key
        )]
        
        # 输出：证明UTXO（继承instruction的created_at，授权期限固定为3个月）
        proof_payload = CopyrightPayload(
            work_hash=instruction_utxo["payload"]["work_hash"],
            work_title=instruction_utxo["payload"]["work_title"],
            author=instruction_utxo["payload"]["author"],
            copyright_type="proof",
            rights_scope=instruction_utxo["payload"]["rights_scope"]
        )
        # 继承instruction的created_at（授权期限从instruction创建时开始计算）
        proof_payload.created_at = instruction_payload.created_at
        
        # 简化设计：不需要赎回机制，到期后自动失效
        proof_script = TimeLockScript(
            script_type=TimeLockScript.SCRIPT_TYPE_P2PKH,
            addresses=[self.address]
        ).to_string()
        
        outputs = [TransactionOutput(
            amount=0.01,
            address=self.address,
            script_pubkey=proof_script,
            utxo_type="copyright",
            payload=proof_payload.to_dict()
        )]
        
        # 创建交易
        tx = Transaction(
            inputs=inputs,
            outputs=outputs,
            tx_type=Transaction.TYPE_AUTH_ACTIVATE
        )
        
        # 签名
        for inp in tx.inputs:
            signature = self.sign_message(tx.txid)
            inp.signature = signature
            inp.add_signature(self.address, signature)
        
        return self._submit_transaction(tx, "授权激活")
    
    def _submit_transaction(self, tx: Transaction, operation_name: str) -> Optional[str]:
        """提交交易的通用方法"""
        try:
            response = requests.post(
                f"{NODE_URL}/transaction",
                json=tx.to_dict(),
                headers={"Content-Type": "application/json"}
            )
            
            if response.status_code == 200:
                result = response.json()
                if result.get("success"):
                    print(f"✓ {operation_name}交易提交成功！")
                    print(f"  交易ID: {result.get('txid')}")
                    return result.get('txid')
                else:
                    print(f"✗ {operation_name}失败: {result.get('message')}")
                    return None
            else:
                print(f"✗ 提交失败: {response.text}")
                return None
                
        except Exception as e:
            print(f"✗ 网络错误: {e}")
            return None


# ============ 命令行交互界面 ============

def generate_wallet():
    """生成新钱包"""
    print("\n" + "="*50)
    print("生成新的CPC钱包")
    print("="*50)
    
    # 生成密钥对
    sk = ecdsa.SigningKey.generate(curve=ecdsa.SECP256k1)
    private_key = sk.to_string().hex()
    vk = sk.get_verifying_key()
    public_key = base64.b64encode(vk.to_string()).decode()
    
    # 保存到文件
    filename = input("\n钱包文件名（不含后缀）: ") + ".json"
    
    wallet_data = {
        "private_key": private_key,
        "public_key": public_key,
        "address": public_key
    }
    
    with open(filename, "w") as f:
        json.dump(wallet_data, f, indent=2)
    
    print(f"\n✓ 钱包已保存到 {filename}")
    print(f"\n地址: {public_key}")
    print("\n⚠️  请妥善保管钱包文件，丢失将无法找回！")
    print("="*50)


def load_wallet() -> Optional[CPCWallet]:
    """加载钱包"""
    filename = input("\n钱包文件名: ")
    
    try:
        with open(filename, "r") as f:
            wallet_data = json.load(f)
        
        return CPCWallet(
            private_key=wallet_data["private_key"],
            public_key=wallet_data["public_key"]
        )
    except Exception as e:
        print(f"✗ 加载钱包失败: {e}")
        return None


def request_faucet(wallet: CPCWallet):
    """从水龙头领取CPC"""
    print("\n" + "="*50)
    print("从水龙头领取CPC")
    print("="*50)
    
    try:
        response = requests.post(
            f"{NODE_URL}/faucet",
            json={"address": wallet.address},
            headers={"Content-Type": "application/json"}
        )
        
        if response.status_code == 200:
            result = response.json()
            if result.get("success"):
                print(f"\n✓ 领取成功！")
                print(f"  数量: {result.get('amount')} CPC")
                print(f"  交易ID: {result.get('txid')}")
                print(f"\n等待矿工确认...")
            else:
                print(f"\n✗ 领取失败: {result.get('message')}")
        else:
            print(f"\n✗ 请求失败: {response.text}")
    except Exception as e:
        print(f"\n✗ 网络错误: {e}")
    
    print("="*50)


def main_menu():
    """主菜单"""
    print("""
    =========================================
        时权链 CPC 钱包 v1.0.0
        Time-Rights Chain Wallet
    =========================================
    """)
    
    wallet = None
    
    while True:
        print("\n请选择操作：")
        print("1. 生成新钱包")
        print("2. 加载钱包")
        if wallet:
            print("3. 查看余额")
            print("4. 从水龙头领取CPC")
            print("5. 注册版权")
            print("6. 授权锁定")
            print("7. 激活授权")
            print("8. 查看我的UTXO")
            print("9. 被授权方导入多签交易")
            print("10. 被授权方签名/提交多签交易")
        print("0. 退出")
        
        choice = input("\n请输入选项: ").strip()
        
        if choice == "1":
            generate_wallet()
        elif choice == "2":
            wallet = load_wallet()
            if wallet:
                print(f"\n✓ 钱包加载成功！")
                print(f"地址: {wallet.address}")
        elif choice == "3" and wallet:
            balance = wallet.get_balance()
            print(f"\n余额: {balance} CPC")
        elif choice == "4" and wallet:
            request_faucet(wallet)
        elif choice == "5" and wallet:
            work_file = input("作品文件路径: ")
            work_title = input("作品标题: ")
            wallet.register_copyright(work_file, work_title)
        elif choice == "6" and wallet:
            work_hash = input("作品哈希: ")
            licensee = input("被授权人地址: ")
            
            print("授权权利范围（逗号分隔）: ")
            rights = input("例如：复制权,发行权,改编权\n").split(",")
            rights = [r.strip() for r in rights]
            
            # 注意：授权期限固定为3个月，从UTXO创建时间开始计算
            print("ℹ️  授权期限固定为3个月")
            wallet.lock_authorization(work_hash, licensee, rights)
        elif choice == "7" and wallet:
            txid = input("授权指令UTXO的交易ID: ")
            vout = int(input("输出索引: "))
            wallet.activate_authorization(txid, vout)
        elif choice == "8" and wallet:
            utxos = wallet.get_utxos()
            print(f"\n共有 {len(utxos)} 个UTXO:")
            for utxo in utxos:
                print(f"\n  {utxo['txid']}:{utxo['vout']}")
                print(f"  类型: {utxo['utxo_type']}")
                print(f"  数量: {utxo['amount']} CPC")
                if utxo['utxo_type'] == 'copyright':
                    print(f"  版权类型: {utxo['payload'].get('copyright_type')}")
                    print(f"  作品: {utxo['payload'].get('work_title')}")
        elif choice == "9" and wallet:
            tx_file = input("输入作者提供的多签交易文件路径: ").strip()
            wallet.prepare_multisig_authorization(tx_file)
        elif choice == "10" and wallet:
            tx_file = input("输入需要签名的多签交易文件路径: ").strip()
            wallet.sign_pending_transaction(tx_file)
        elif choice == "0":
            print("\n再见！")
            break
        else:
            print("\n无效选项")


if __name__ == '__main__':
    main_menu()

