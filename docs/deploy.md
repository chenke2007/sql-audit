# 部署指南

## 环境要求

- Python 3.9+
- RedHat 8 / CentOS 8 / Ubuntu 20.04+ / macOS 12+
- 网络访问目标 Oracle 数据库
- 可选：OpenAI 兼容的 LLM API 访问

## 部署方式

### 方式一：直接部署（推荐）

#### 1. 下载代码

```bash
git clone --branch v1.2.0 https://github.com/chenke2007/sql-audit.git
cd sql-audit
```

#### 2. 创建虚拟环境

```bash
python3 -m venv venv
source venv/bin/activate
```

#### 3. 安装依赖

```bash
pip install -r requirements.txt
```

#### 4. 检查 Oracle Instant Client

Linux 版本已包含在仓库中，位于 `oracle_instantclient/linux_x64/`。

如需手动放置（从 zip 包）：

```bash
mkdir -p oracle_instantclient/linux_x64
unzip downloads/instantclient-basiclite-linux.x64-19.30.0.0.0dbru.zip -d /tmp/ic/
cp -R /tmp/ic/instantclient_19_30/* oracle_instantclient/linux_x64/
rm -rf /tmp/ic
```

#### 5. 配置环境变量

```bash
cp .env.example .env
vim .env
```

最小配置示例：

```env
# Oracle 默认数据源
ORACLE_HOST=192.168.13.82
ORACLE_PORT=1522
ORACLE_SERVICE_NAME=omdb
ORACLE_USERNAME=sqlaudit
ORACLE_PASSWORD=your_password

# LLM API（可选，不配置则 LLM 分析不可用）
LLM_BASE_URL=https://api.scnet.cn/api/llm/v1
LLM_MODEL_NAME=MiniMax-M2.5
LLM_API_KEY=your_api_key
```

#### 6. 启动服务

前台运行（调试）：

```bash
python -m uvicorn app.main:app --host 0.0.0.0 --port 8000
```

后台运行：

```bash
nohup python -m uvicorn app.main:app --host 0.0.0.0 --port 8000 > /var/log/sql-audit.log 2>&1 &
```

#### 7. 验证

```bash
curl http://localhost:8000/health
```

### 方式二：Systemd 服务部署

创建服务文件 `/etc/systemd/system/sql-audit.service`：

```ini
[Unit]
Description=SQL Audit System
After=network.target

[Service]
Type=simple
User=sqlaudit
Group=sqlaudit
WorkingDirectory=/opt/sql-audit
Environment="PATH=/opt/sql-audit/venv/bin:/usr/local/bin:/usr/bin"
Environment="PYTHONPATH=/opt/sql-audit"
ExecStart=/opt/sql-audit/venv/bin/uvicorn app.main:app --host 0.0.0.0 --port 8000
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
```

启用并启动：

```bash
sudo systemctl daemon-reload
sudo systemctl enable sql-audit
sudo systemctl start sql-audit
sudo systemctl status sql-audit
```

### 方式三：Nginx 反向代理

Nginx 配置示例：

```nginx
server {
    listen 80;
    server_name sql-audit.example.com;

    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    }
}
```

## 生产环境检查清单

- [ ] `.env` 文件已配置正确的 Oracle 连接信息
- [ ] `oracle_instantclient/linux_x64/` 目录存在且文件完整
- [ ] 防火墙放行应用端口（默认 8000）
- [ ] Oracle 数据库用户具有所需权限
- [ ] LLM API 密钥有效（如使用智能分析）
- [ ] 日志目录有写入权限
- [ ] 配置了 systemd 自动重启

## 故障排查

### 启动失败：找不到 Oracle Instant Client

确保 `oracle_instantclient/linux_x64/` 目录存在。如缺失，从 `downloads/` 解压。

### 连接 Oracle 报 DPY-3010

数据库版本太旧（低于 12.1），需要 thick 模式。确保 Instant Client 文件已放置到位。

### LLM 分析无响应

检查 `LLM_BASE_URL` 和 `LLM_API_KEY` 配置是否正确，以及网络是否可达。
