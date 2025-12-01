#!/usr/bin/env python3
"""
多签授权工作流测试
演示完整的多签交易流程：作者创建 -> 被授权人添加UTXO -> 双方签名 -> 提交
"""

import sys
import os
import time
import json
import threading
import requests
from cpc_wallet import CPCWallet

def print_section(title):
    """打印分隔符"""
    print(f"\n{'='*60}")
    print(f"  {title}")
    print(f"{'='*60}\n")

def test_multisig_authorization():
    """测试多签授权工作流"""
    
    print_section("💼 多签授权工作流测试")
    print("工作流: 作者创建 → 被授权人添加UTXO → 双方签名 → 提交\n")
    
    # ========== 第1步: 启动矿工 ==========
    print("1️⃣  启动矿工节点...")
    import subprocess
    # 在后台启动矿工进程
    miner_process = subprocess.Popen(
        [sys.executable, "cpc_miner.py"],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        cwd=os.path.dirname(os.path.abspath(__file__))
    )
    time.sleep(3)
    print("✅ 矿工已启动\n")
    
    # ========== 第2步: 创建作者钱包 ==========
    print("2️⃣  作者创建钱包并领取水龙头...")
    author = CPCWallet()
    author_address = author.address
    print(f"  作者地址: {author_address}")
    
    # 领取水龙头
    faucet_txid = author.claim_faucet(10)
    if not faucet_txid:
        print("❌ 水龙头领取失败")
        return False
    print(f"  ✓ 领取10 CPC，交易ID: {faucet_txid[:16]}...\n")
    time.sleep(2)
    
    # ========== 第3步: 创建被授权人钱包 ==========
    print("3️⃣  被授权人创建钱包并领取水龙头...")
    licensee = CPCWallet()
    licensee_address = licensee.address
    print(f"  被授权人地址: {licensee_address}")
    
    # 领取水龙头
    faucet_txid = licensee.claim_faucet(10)
    if not faucet_txid:
        print("❌ 水龙头领取失败")
        return False
    print(f"  ✓ 领取10 CPC，交易ID: {faucet_txid[:16]}...\n")
    time.sleep(2)
    
    # ========== 第4步: 作者注册版权 ==========
    print("4️⃣  作者注册版权...")
    work_hash = "hash_example_work_001"
    work_title = "我的创意作品"
    rights_scope = ["print", "distribute"]
    
    register_txid = author.register_copyright(work_hash, work_title, rights_scope)
    if not register_txid:
        print("❌ 版权注册失败")
        return False
    print(f"  ✓ 版权注册成功，交易ID: {register_txid[:16]}...\n")
    time.sleep(2)
    
    # ========== 第5步: 作者创建多签授权交易 ==========
    print("5️⃣  作者创建多签授权交易（第一步）...")
    print(f"  授权给: {licensee_address}")
    print(f"  作品: {work_title}")
    
    # 创建多签交易（返回临时文件名）
    temp_file = author.lock_authorization(
        work_hash=work_hash,
        licensee_address=licensee_address,
        rights_scope=rights_scope,
        create_multisig=True
    )
    
    if not temp_file:
        print("❌ 多签授权交易创建失败")
        return False
    
    print(f"\n✅ 已创建临时交易文件: {temp_file}")
    
    # 显示交易状态
    try:
        with open(temp_file, 'r', encoding='utf-8') as f:
            tx_dict = json.load(f)
        print(f"\n📋 交易状态:")
        print(f"  交易ID: {tx_dict['txid'][:16]}...")
        print(f"  输入数: {len(tx_dict['inputs'])}")
        for i, inp in enumerate(tx_dict['inputs']):
            required = inp['required_signers']
            signed = list(inp['signatures'].keys())
            status = "已签名" if required == signed else "未签名"
            print(f"    输入{i+1}: 需要{required} | {status}")
    except Exception as e:
        print(f"⚠️  无法读取交易详情: {e}")
    
    # ========== 第6步: 被授权人添加燃料UTXO ==========
    print(f"\n6️⃣  被授权人接收交易并添加燃料UTXO...")
    result = licensee.prepare_multisig_authorization(temp_file)
    
    if not result:
        print("❌ 添加燃料UTXO失败")
        return False
    
    print(f"\n✅ 燃料UTXO已添加")
    
    # 显示更新后的交易状态
    try:
        with open(temp_file, 'r', encoding='utf-8') as f:
            tx_dict = json.load(f)
        print(f"\n📋 更新后的交易状态:")
        print(f"  交易ID: {tx_dict['txid'][:16]}...")
        print(f"  输入数: {len(tx_dict['inputs'])}")
        for i, inp in enumerate(tx_dict['inputs']):
            required = inp['required_signers']
            signed = list(inp['signatures'].keys())
            status = "已签名" if required == signed else "未签名"
            print(f"    输入{i+1}: 需要{required} | {status}")
    except Exception as e:
        print(f"⚠️  无法读取交易详情: {e}")
    
    # ========== 第7步: 被授权人签名交易 ==========
    print(f"\n7️⃣  被授权人签名交易...")
    
    result = licensee.sign_pending_transaction(temp_file)
    
    if not result:
        print("❌ 交易签名失败")
        return False
    
    print(f"✅ 授权交易已完全签名并提交")
    print(f"  交易ID: {result[:16]}...\n")
    
    # 等待挖矿完成
    time.sleep(3)
    
    # ========== 第8步: 验证交易 ==========
    print("8️⃣  验证授权结果...")
    
    # 检查被授权人是否有新的UTXO
    licensee_utxos = licensee.get_utxos()
    copyright_utxos = [u for u in licensee_utxos if u.get("utxo_type") == "copyright"]
    
    print(f"  被授权人版权UTXO数: {len(copyright_utxos)}")
    for utxo in copyright_utxos:
        payload = utxo.get("payload", {})
        print(f"    - {payload.get('copyright_type')}: {payload.get('work_title')}")
    
    # 检查作者的余额
    author_balance = author.get_balance()
    licensee_balance = licensee.get_balance()
    
    print(f"\n  作者余额: {author_balance} CPC")
    print(f"  被授权人余额: {licensee_balance} CPC")
    
    if len(copyright_utxos) > 0:
        print(f"\n✅ 多签授权工作流完成!")
        return True
    else:
        print(f"\n⚠️  被授权人未收到UTXO，检查交易是否被正确验证")
        return False

if __name__ == "__main__":
    import subprocess
    
    # 在后台启动矿工进程
    miner_process = subprocess.Popen(
        [sys.executable, "cpc_miner.py"],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        cwd=os.path.dirname(os.path.abspath(__file__))
    )
    time.sleep(3)
    
    try:
        success = test_multisig_authorization()
        
        if success:
            print("\n" + "="*60)
            print("  🎉 所有测试通过!")
            print("="*60)
            sys.exit(0)
        else:
            print("\n" + "="*60)
            print("  ❌ 测试失败")
            print("="*60)
            sys.exit(1)
    finally:
        # 关闭矿工进程
        miner_process.terminate()
        miner_process.wait(timeout=5)

