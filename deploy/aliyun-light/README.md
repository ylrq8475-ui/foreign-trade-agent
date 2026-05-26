# 阿里云轻量应用服务器部署说明

适用场景：

- 2 到 3 人小范围使用
- 当前功能以 `simple_server` 版本为准
- 单机部署
- 当前数据使用 `SQLite`

## 1. 推荐服务器规格

- 阿里云轻量应用服务器
- `Ubuntu 24.04 LTS`
- `1 vCPU / 2GB RAM`
- 系统盘 `40GB` 及以上

## 2. 域名和端口

建议准备一个域名或二级域名，例如：

- `crm.yourdomain.com`

阿里云轻量应用服务器控制台里需要放行：

- `22`：SSH
- `80`：HTTP
- `443`：HTTPS

参考：

- 阿里云轻量应用服务器入门文档  
  https://www.alibabacloud.com/help/en/simple-application-server/getting-started/getting-started

## 3. 服务器初始化

登录服务器后执行：

```bash
sudo apt update
sudo apt install -y python3 python3-venv python3-pip rsync curl debian-keyring debian-archive-keyring apt-transport-https
```

创建应用目录：

```bash
sudo mkdir -p /opt/customer-workspace
sudo chown -R $USER:$USER /opt/customer-workspace
```

## 4. 上传项目

把本地项目上传到服务器，例如用 `scp` 或 `rsync`。

本地示例：

```bash
rsync -av --delete ./ root@your-server-ip:/opt/customer-workspace/
```

上传后，服务器上确认：

```bash
cd /opt/customer-workspace
ls
```

## 5. 配置 `.env`

服务器上的 `.env` 至少要确认这些值：

```env
APP_HOST=127.0.0.1
APP_PORT=8000
APP_DB_PATH=/opt/customer-workspace/data/team_workspace.sqlite3
APP_DB_JOURNAL_MODE=MEMORY
APP_DB_SYNCHRONOUS=OFF
ADMIN_USERNAME=admin
ADMIN_PASSWORD=改成你自己的强密码
```

说明：

- `APP_DB_PATH` 建议写服务器绝对路径
- 你当前是小范围使用，`SQLite + MEMORY journal` 可以接受

## 6. 安装 Python 依赖并启动应用

```bash
cd /opt/customer-workspace
python3 -m venv .venv
.venv/bin/pip install --upgrade pip
.venv/bin/pip install -r requirements.txt
```

测试本地启动：

```bash
APP_HOST=127.0.0.1 APP_PORT=8000 .venv/bin/python run_workspace.py
```

如果看到程序监听成功，就按 `Ctrl+C` 停掉，继续做 systemd。

## 7. 配置 systemd

复制服务文件：

```bash
sudo cp deploy/aliyun-light/customer-workspace.service /etc/systemd/system/customer-workspace.service
```

如果服务器用户名不是 `www-data`，先修改服务文件中的：

- `User=`
- `Group=`
- `WorkingDirectory=`
- `ExecStart=`

然后执行：

```bash
sudo systemctl daemon-reload
sudo systemctl enable customer-workspace
sudo systemctl restart customer-workspace
sudo systemctl status customer-workspace
```

看日志：

```bash
sudo journalctl -u customer-workspace -f
```

## 8. 安装 Caddy

官方文档：

- Caddy 自动 HTTPS  
  https://caddyserver.com/docs/automatic-https

## 14. Token API for third-party access

If you want third parties to call your agent with a token, keep the admin website and the API as two local services on the same server:

1. Admin website: `127.0.0.1:8000`
2. Token API: `127.0.0.1:8001`
3. Caddy public route: `/api/* -> 8001`

When both services share the same SQLite file, use these server-side `.env` values:

```env
APP_DB_PATH=/opt/customer-workspace/data/team_workspace.sqlite3
APP_DB_JOURNAL_MODE=WAL
APP_DB_SYNCHRONOUS=NORMAL
```

Install and start the API service:

```bash
sudo cp deploy/aliyun-light/customer-api.service /etc/systemd/system/customer-api.service
sudo systemctl daemon-reload
sudo systemctl enable customer-api
sudo systemctl restart customer-api
sudo systemctl status customer-api
```

Create a token:

```bash
cd /opt/customer-workspace
.venv/bin/python scripts/create_api_token.py --name "partner-a" --scopes "leads:search,customers:import,customers:analyze"
```

Test endpoints:

```bash
curl https://your-domain.example.com/api/v1/health
```

```bash
curl https://your-domain.example.com/api/v1/tokens/me \
  -H "Authorization: Bearer YOUR_TOKEN"
```

```bash
curl https://your-domain.example.com/api/v1/leads/search \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"query":"housewares importer","country":"United States","limit":5,"search_mode":"balanced","import_to_workspace":true}'
```

```bash
curl -X POST https://your-domain.example.com/api/v1/customers/1/analyze \
  -H "Authorization: Bearer YOUR_TOKEN"
```

安装：

```bash
sudo apt install -y debian-keyring debian-archive-keyring apt-transport-https curl
curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/gpg.key' | sudo gpg --dearmor -o /usr/share/keyrings/caddy-stable-archive-keyring.gpg
curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/debian.deb.txt' | sudo tee /etc/apt/sources.list.d/caddy-stable.list
sudo apt update
sudo apt install -y caddy
```

复制 Caddyfile：

```bash
sudo cp deploy/aliyun-light/Caddyfile /etc/caddy/Caddyfile
```

把其中的：

- `your-domain.example.com`

改成你自己的域名。

检查配置并重启：

```bash
sudo caddy validate --config /etc/caddy/Caddyfile
sudo systemctl restart caddy
sudo systemctl status caddy
```

## 9. 域名解析

在域名服务商后台增加 A 记录，指向阿里云轻量服务器公网 IP。

例如：

- 主机记录：`crm`
- 记录值：`你的服务器公网IP`

等解析生效后，访问：

```text
https://crm.yourdomain.com
```

## 10. 备份

先给脚本执行权限：

```bash
chmod +x deploy/aliyun-light/backup_sqlite.sh
```

手动测试：

```bash
./deploy/aliyun-light/backup_sqlite.sh
```

建议加 `cron` 每天备份：

```bash
crontab -e
```

加入：

```cron
0 3 * * * /opt/customer-workspace/deploy/aliyun-light/backup_sqlite.sh >> /opt/customer-workspace/backups/backup.log 2>&1
```

## 11. 上线后检查

上线前确认：

1. 首页能打开
2. 管理员登录正常
3. 客户列表能读取
4. 搜索客户能写入数据库
5. SMTP 页面能打开
6. 数据库文件在服务器固定路径
7. 备份脚本能成功执行

## 12. 当前这版的边界

这版适合你现在的小范围使用，但要知道：

1. 当前完整管理员功能依赖 `run_workspace.py -> web.simple_server`
2. 如果以后要扩大使用范围，建议下一步把这些管理功能统一迁到 `FastAPI`
3. 如果以后并发增大，再考虑从 `SQLite` 升级到 `PostgreSQL`

## 13. 官方参考

- 阿里云轻量应用服务器入门  
  https://www.alibabacloud.com/help/en/simple-application-server/getting-started/getting-started
- FastAPI 部署文档  
  https://fastapi.tiangolo.com/deployment/manually/
- Uvicorn 部署文档  
  https://www.uvicorn.org/deployment/
- Caddy 自动 HTTPS  
  https://caddyserver.com/docs/automatic-https
