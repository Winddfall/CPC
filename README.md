# CPC
一种创新型的版权凭证币（CPC）
首先安装所需要的依赖：

```bash
pip install -r requirements.txt
```

系统可以通过以下命令启动矿工节点：

```bash
python cpc_miner.py
```

启动后，节点将在默认端口 (5001) 监听，接收来自钱包客户端的交易请求，并自动进行挖矿打包。

成功启动矿工节点：

```bash
    =========================================
        时权链 CPC v1.0.0 - 矿工节点
        Time-Rights Chain - CPC Miner
    =========================================

    基于UTXO模型的版权管理区块链系统

    节点地址: http://localhost:5001
    矿工地址: your-miner-wallet-address-here

    正在启动矿工节点...
    =========================================

 * Serving Flask app 'cpc_miner'
 * Debug mode: off
WARNING: This is a development server. Do not use it in a production deployment. Use a production WSGI server instead.
 * Running on all addresses (0.0.0.0)
 * Running on http://127.0.0.1:5001
 * Running on http://198.18.0.1:5001
```

系统可以通过以下命令启动用户钱包：

```bash
python cpc_wallet.py
```

成功启动钱包：

```
    =========================================
        时权链 CPC 钱包 v1.0.0
        Time-Rights Chain Wallet
    =========================================
    

请选择操作：
1. 生成新钱包
2. 加载钱包
0. 退出

请输入选项: 
```
