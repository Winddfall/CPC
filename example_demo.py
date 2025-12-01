"""
时权链 (Time-Rights Chain) - 完整示例演示
展示版权注册到授权的完整流程
"""

import time
import hashlib
import json
import os

# 模拟演示，实际使用时需要启动矿工节点

def print_section(title):
    """打印章节标题"""
    print("\n" + "="*60)
    print(f"  {title}")
    print("="*60 + "\n")


def demo_scenario():
    """演示完整的版权授权场景"""
    
    print("""
    ╔══════════════════════════════════════════════════════════╗
    ║                                                          ║
    ║      时权链 (Time-Rights Chain) 完整示例演示               ║
    ║                                                          ║
    ║  场景：音乐人Alice将歌曲授权给唱片公司Bob                  ║
    ║                                                          ║
    ╚══════════════════════════════════════════════════════════╝
    """)
    
    # ========== 阶段0：准备工作 ==========
    print_section("阶段0：准备工作")
    
    print("1. 启动矿工节点")
    print("   $ python cpc_miner.py")
    print("   ✓ 矿工节点运行在 http://localhost:5001\n")
    
    print("2. Alice生成钱包")
    print("   $ python cpc_wallet.py")
    print("   > 选择 1. 生成新钱包")
    print("   > 文件名: alice_wallet")
    print("   ✓ 钱包地址: alice_public_key_base64...")
    print()
    
    print("3. Bob生成钱包")
    print("   > 选择 1. 生成新钱包")
    print("   > 文件名: bob_wallet")
    print("   ✓ 钱包地址: bob_public_key_base64...")
    print()
    
    print("4. Alice和Bob从水龙头领取CPC")
    print("   > 选择 4. 从水龙头领取CPC")
    print("   ✓ Alice领取 5 CPC")
    print("   ✓ Bob领取 5 CPC")
    print()
    
    input("按回车继续...")
    
    # ========== 阶段一：版权注册 ==========
    print_section("阶段一：版权注册（资产的首次铸造）")
    
    print("Alice创作了一首原创歌曲《星空之下》")
    print()
    
    # 创建示例文件
    song_content = """
    《星空之下》
    作词作曲：Alice
    
    在那星空之下
    我们相遇相知
    时光流转不息
    爱意永不褪色
    """
    
    song_file = "star_song.txt"
    with open(song_file, "w", encoding="utf-8") as f:
        f.write(song_content)
    
    # 计算哈希
    work_hash = hashlib.sha256(song_content.encode()).hexdigest()
    print(f"作品内容: {song_content[:50]}...")
    print(f"作品哈希: {work_hash}\n")
    
    print("Alice通过钱包注册版权：")
    print("   > 选择 6. 注册版权")
    print(f"   > 作品文件路径: {song_file}")
    print("   > 作品标题: 星空之下")
    print()
    
    print("交易详情：")
    print("   类型: copyright_register")
    print("   输入: ")
    print("     - [0] Alice的燃料UTXO (5.0 CPC)")
    print("   输出:")
    print("     - [0] 版权主权UTXO (1.0 CPC) → Alice")
    print("          └─ Payload:")
    print(f"             ├─ work_hash: {work_hash[:32]}...")
    print("             ├─ work_title: 星空之下")
    print("             ├─ author: Alice")
    print("             ├─ copyright_type: sovereignty")
    print("             └─ rights_scope: [复制权, 发行权, 改编权, 表演权, ...]")
    print("     - [1] 找零UTXO (3.99 CPC) → Alice")
    print()
    
    print("✓ 矿工验证并打包交易")
    print("✓ Alice获得版权主权UTXO，拥有作品的最高级身份凭证")
    print()
    
    input("按回车继续...")
    
    # ========== 阶段二：授权锁定 ==========
    print_section("阶段二：授权锁定（延迟生效的承诺）")
    
    print("Alice和唱片公司Bob达成协议：")
    print("  - 授权Bob发行和复制该歌曲")
    print("  - 授权7天后生效（合同审核期）")
    print("  - 授权期限1年")
    print("  - 授权范围：复制权、发行权")
    print()
    
    current_time = int(time.time())
    start_time = current_time + 7 * 86400  # 7天后
    end_time = start_time + 365 * 86400    # 1年期限
    
    print(f"当前时间: {time.ctime(current_time)}")
    print(f"生效时间: {time.ctime(start_time)}")
    print(f"到期时间: {time.ctime(end_time)}")
    print()
    
    print("Alice创建授权锁定交易：")
    print("   > 选择 7. 授权锁定")
    print(f"   > 作品哈希: {work_hash}")
    print("   > 被授权人地址: Bob的地址")
    print("   > 几天后生效: 7")
    print("   > 授权期限（天）: 365")
    print("   > 授权权利范围: 复制权,发行权")
    print()
    
    print("交易详情：")
    print("   类型: authorization_lock")
    print("   输入:")
    print("     - [0] Alice的版权主权UTXO (1.0 CPC)")
    print("     - [1] Alice的燃料UTXO (3.99 CPC)")
    print("   输出:")
    print("     - [0] 授权指令UTXO (0.01 CPC) → Bob")
    print("          ├─ 锁定脚本: TIMELOCK + REDEMPTION")
    print(f"          │  ├─ 时间锁: {start_time}")
    print("          │  ├─ 解锁地址: Bob")
    print(f"          │  └─ 赎回条件: {end_time}后Alice可赎回")
    print("          └─ Payload:")
    print(f"             ├─ work_hash: {work_hash[:32]}...")
    print("             ├─ copyright_type: instruction")
    print("             ├─ rights_scope: [复制权, 发行权]")
    print(f"             ├─ start_time: {start_time}")
    print(f"             └─ end_time: {end_time}")
    print("     - [1] 重新铸造的版权主权UTXO (1.0 CPC) → Alice")
    print("     - [2] 找零UTXO (2.97 CPC) → Alice")
    print()
    
    print("关键点：")
    print("  ⚠️  Bob此时无法花费授权指令UTXO（时间锁未到期）")
    print("  ⚠️  Bob无法向外界证明自己拥有版权")
    print("  ✓  Alice保留了版权主权UTXO")
    print()
    
    input("按回车继续...")
    
    # ========== 模拟时间流逝 ==========
    print_section("⏰ 7天过去了...")
    
    print(f"当前时间: {time.ctime(start_time)} （模拟）")
    print("✓ 授权时间锁到期！")
    print()
    
    input("按回车继续...")
    
    # ========== 阶段三：授权激活 ==========
    print_section("阶段三：授权激活（版权证明的生成）")
    
    print("Bob现在可以激活授权，获得版权证明：")
    print("   > 选择 8. 激活授权")
    print("   > 授权指令UTXO的交易ID: <上一步的txid>")
    print("   > 输出索引: 0")
    print()
    
    print("交易详情：")
    print("   类型: authorization_activate")
    print("   输入:")
    print("     - [0] 授权指令UTXO (0.01 CPC)")
    print("   输出:")
    print("     - [0] 版权证明UTXO (0.01 CPC) → Bob")
    print("          ├─ 锁定脚本: P2PKH + REDEMPTION")
    print("          │  ├─ 解锁地址: Bob")
    print(f"          │  └─ 赎回条件: {end_time}后Alice可赎回")
    print("          └─ Payload:")
    print(f"             ├─ work_hash: {work_hash[:32]}... (继承)")
    print("             ├─ copyright_type: proof")
    print("             ├─ rights_scope: [复制权, 发行权]")
    print(f"             ├─ start_time: {start_time}")
    print(f"             └─ end_time: {end_time}")
    print()
    
    print("矿工验证：")
    print("  ✓ 时间锁已到期")
    print("  ✓ Bob的签名有效")
    print("  ✓ 作品哈希正确继承")
    print()
    
    print("结果：")
    print("  ✓ Bob获得了可花费、可证明的版权凭证")
    print("  ✓ 授权正式生效")
    print("  ✓ Bob可以向流媒体平台等证明自己有权发行该歌曲")
    print()
    
    input("按回车继续...")
    
    # ========== 阶段四：授权维持 ==========
    print_section("阶段四：授权维持与失效")
    
    print("情况1：续期（在到期前）")
    print("-" * 60)
    print("如果Alice和Bob希望继续合作：")
    print()
    print("续期交易：")
    print("   类型: renewal")
    print("   输入:")
    print("     - [0] Bob的旧证明UTXO (0.01 CPC)")
    print("     - [1] Alice的燃料UTXO")
    print("     - [2] Bob的燃料UTXO")
    print("   签名要求: Alice和Bob共同签名（多重签名）")
    print("   输出:")
    print("     - [0] 新的证明UTXO (0.01 CPC) → Bob")
    print(f"          └─ end_time: {end_time + 365*86400} (延长1年)")
    print()
    print("  ✓ 续期费用由双方共同承担")
    print("  ✓ 单方面无法强制续期")
    print()
    
    print("\n情况2：自动失效（到期后未续签）")
    print("-" * 60)
    print(f"时间到达: {time.ctime(end_time)}")
    print()
    print("赎回交易：")
    print("   类型: redemption")
    print("   输入:")
    print("     - [0] Bob的过期证明UTXO (0.01 CPC)")
    print("   签名要求: Alice单方签名即可")
    print("   输出:")
    print("     - [0] 燃料UTXO (0.01 CPC) → Alice")
    print()
    print("  ✓ 授权自动终止")
    print("  ✓ Bob的证明UTXO失效")
    print("  ✓ Alice收回授权")
    print()
    
    input("按回车继续...")
    
    # ========== 阶段五：次级授权 ==========
    print_section("阶段五：次级授权与转让")
    
    print("场景：Bob希望授权给流媒体平台Carol，但仅授予复制权")
    print()
    
    print("次级授权交易：")
    print("   类型: sub_license")
    print("   输入:")
    print("     - [0] Bob的证明UTXO (0.01 CPC)")
    print("     - [1] Carol的燃料UTXO (5.0 CPC) ← Carol承担费用")
    print("     - [2] Carol的授权费UTXO (10.0 CPC)")
    print("   输出:")
    print("     - [0] Bob的新证明UTXO (0.01 CPC)")
    print("          └─ Payload更新，记录已授权给Carol")
    print("     - [1] Carol的次级证明UTXO (0.01 CPC)")
    print("          └─ Payload:")
    print("             ├─ copyright_type: secondary")
    print("             ├─ rights_scope: [复制权] ← 仅复制权")
    print("             ├─ parent_utxo: Bob的证明UTXO标识")
    print(f"             └─ end_time: {end_time} (继承)")
    print("     - [2] 授权费收入 (10.0 CPC) → Bob")
    print("     - [3] 找零 → Carol")
    print()
    
    print("矿工验证：")
    print("  ✓ Carol的权利范围 [复制权] ⊆ Bob的权利范围 [复制权, 发行权]")
    print("  ✓ Carol的授权不能超过Bob的到期时间")
    print("  ✓ Bob的证明UTXO被正确更新")
    print()
    
    print("结果：")
    print("  ✓ Bob获得授权费收入，并保留自己的完整权利")
    print("  ✓ Carol获得受限的次级版权证明")
    print("  ✓ 形成清晰的授权链条：Alice → Bob → Carol")
    print()
    
    input("按回车继续...")
    
    # ========== 总结 ==========
    print_section("总结：时权链的核心优势")
    
    print("""
    1. 📝 不可篡改的版权记录
       - 作品哈希永久记录在区块链上
       - 授权历史完整可追溯
    
    2. ⏰ 时间锁强制执行
       - 授权生效和到期由协议层面保证
       - 无需第三方监督，自动执行
    
    3. 🔒 多重签名保护
       - 续期需要双方确认
       - 防止单方面违约
    
    4. 🌳 清晰的授权层级
       - UTXO模型追踪每个授权状态
       - 次级授权形成树状结构
    
    5. 💰 灵活的价值流转
       - CPC承载版权状态
       - 授权费直接在链上结算
    
    6. 🔍 透明可验证
       - 任何人都可以验证版权证明的真实性
       - 通过作品哈希查询授权链条
    """)
    
    print("\n" + "="*60)
    print("  感谢体验时权链 (Time-Rights Chain)！")
    print("  用区块链技术守护创作价值")
    print("="*60 + "\n")
    
    # 清理示例文件
    if os.path.exists(song_file):
        os.remove(song_file)


if __name__ == '__main__':
    try:
        demo_scenario()
    except KeyboardInterrupt:
        print("\n\n演示已中断")


