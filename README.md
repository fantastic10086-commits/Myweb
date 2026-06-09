# PI Manager — 外贸形式发票管理系统

基于 Python Flask + SQLite 的简易外贸 PI（Proforma Invoice）管理系统。

## 功能

- **客户管理**：增删改查，支持搜索
- **商品管理**：增删改查，支持搜索
- **PI 生成**：选择客户 + 勾选商品 + 设置数量 → 自动计算总金额 → 一键生成 PDF
- **PI 模板**：外贸通用格式，含公司抬头、客户信息、商品明细、金额合计、付款条款、签章区域
- **PDF 下载**：所有生成的 PDF 保存在 `pdf/` 目录，可从页面直接下载

## 项目结构

```
okki/
├── app.py                 # Flask 主应用
├── models.py              # 数据库模型
├── pdf_generator.py       # PDF 生成引擎 (ReportLab)
├── templates/             # HTML 页面模板
│   ├── base.html          # 基础布局
│   ├── index.html         # 仪表盘
│   ├── customers.html     # 客户列表
│   ├── customer_form.html # 客户表单
│   ├── products.html      # 商品列表
│   ├── product_form.html  # 商品表单
│   ├── create_pi.html     # 创建 PI
│   ├── pi_list.html       # PI 列表
│   └── pi_detail.html     # PI 详情
├── static/style.css       # 样式
├── pdf/                   # 生成的 PDF 存放目录（自动创建）
├── instance/              # SQLite 数据库存放目录（自动创建）
├── requirements.txt       # Python 依赖
├── start.sh               # 启动脚本
├── stop.sh                # 停止脚本
└── README.md              # 本文件
```

---

## 在 NAS 上部署（完整步骤）

### 1. 将项目复制到 NAS

```bash
# 假设项目在本地 /Users/fantastic/Desktop/jj
# 复制到 NAS 的 /home/姜姜/okki

# 方式 A：scp
scp -r /Users/fantastic/Desktop/jj/* 姜姜@<NAS_IP>:/home/姜姜/okki/

# 方式 B：U盘 / 网络共享直接拷贝整个 jj 文件夹到 /home/姜姜/okki
```

### 2. SSH 登录 NAS 并安装 Python 依赖

```bash
ssh 姜姜@<NAS_IP>

# 进入项目目录
cd /home/姜姜/okki

# 确认 Python3 可用
python3 --version   # 需要 Python 3.9+

# 安装依赖（推荐使用虚拟环境）
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt

# 如果 NAS 上没有 pip，先安装：
# sudo apt install python3-pip   (Debian/Ubuntu NAS)
# 或 sudo yum install python3-pip (CentOS NAS)
```

### 3. 修改公司信息（可选）

编辑 `pdf_generator.py` 顶部的 `COMPANY_INFO`：

```python
COMPANY_INFO = {
    'name': '你的公司名称',
    'address': '你的公司地址',
    'phone': '你的电话',
    'email': '你的邮箱',
    'website': '你的网站',
}
```

同时也编辑 `app.py` 顶部的 `COMPANY_CONFIG`。

### 4. 修改 Secret Key（重要）

编辑 `app.py`，将 `SECRET_KEY` 改为随机字符串：

```python
app.config['SECRET_KEY'] = 'your-random-secret-key-here'
```

### 5. 手动测试运行

```bash
cd /home/姜姜/okki
source venv/bin/activate
python app.py
```

访问 `http://<NAS_IP>:5000`，确认页面能打开。

按 `Ctrl+C` 停止测试。

### 6. 后台运行

```bash
# 赋予脚本执行权限
chmod +x /home/姜姜/okki/start.sh
chmod +x /home/姜姜/okki/stop.sh

# 启动
bash /home/姜姜/okki/start.sh

# 查看日志
tail -f /home/姜姜/okki/pi_manager.log

# 停止
bash /home/姜姜/okki/stop.sh
```

### 7. 设置 NAS 开机自启

#### 方式 A：Crontab（推荐，简单）

```bash
crontab -e

# 添加一行：
@reboot sleep 10 && bash /home/姜姜/okki/start.sh
```

#### 方式 B：Systemd（如果 NAS 支持）

```bash
sudo nano /etc/systemd/system/pi-manager.service
```

写入：
```ini
[Unit]
Description=PI Manager Web App
After=network.target

[Service]
Type=forking
User=姜姜
WorkingDirectory=/home/姜姜/okki
ExecStart=/bin/bash /home/姜姜/okki/start.sh
ExecStop=/bin/bash /home/姜姜/okki/stop.sh
Restart=on-failure
RestartSec=10

[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl daemon-reload
sudo systemctl enable pi-manager
sudo systemctl start pi-manager
sudo systemctl status pi-manager
```

### 8. 访问使用

浏览器打开：`http://<NAS_IP>:5000`

---

## 使用流程

1. **添加客户**：点击 "Customers" → "Add Customer"，填写客户信息
2. **添加商品**：点击 "Products" → "Add Product"，填写商品信息和单价
3. **创建 PI**：点击 "New PI" →
   - 选择客户
   - 设置付款条款和银行信息
   - 勾选商品并输入数量
   - 系统自动计算总金额
   - 点击 "Generate PI & PDF"
4. **查看/下载**：在 PI List 中查看详情或下载 PDF 文件

---

## 数据库备份

数据库文件位于 `instance/pi_manager.db`，定期备份此文件即可：

```bash
cp /home/姜姜/okki/instance/pi_manager.db /home/姜姜/okki/backup/pi_manager_$(date +%Y%m%d).db
```

## 端口修改

如需修改端口，编辑 `start.sh` 中的 `PORT=5000`，以及 `app.py` 中的 `app.run()` 参数。

---

## 技术栈

- **后端**：Python 3.9+, Flask, Flask-SQLAlchemy
- **数据库**：SQLite（零配置，单文件）
- **PDF 生成**：ReportLab（纯 Python，无需系统依赖）
- **前端**：Bootstrap 5 CDN, Jinja2 模板
- **部署**：Gunicorn + nohup（NAS 后台运行）
