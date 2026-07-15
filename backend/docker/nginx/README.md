# Nginx HTTPS 反向代理

## 部署模式

项目提供两种 Docker Compose 部署模式：

### 模式一：生产模式（HTTPS + Nginx 反向代理）

```bash
cd backend/docker
# 1. 初始化密钥和证书
./init-production.ps1 -GenerateCert   # Windows
./init-production.sh --generate-cert   # Linux/macOS

# 2. 启动（自动使用 --env-file .env.docker）
./start-stack.ps1 -Mode production     # Windows
# 或手动：
docker compose --env-file .env.docker \
  -f docker-compose.yml \
  -f docker-compose.production.yml \
  up -d
```

访问地址：
- `https://服务器地址/` — 前端页面
- `https://服务器地址/api/` — API
- `https://服务器地址/health/ready` — 健康检查

### 模式二：演示/本地开发模式（HTTP 直连）

```bash
cd backend/docker
# 1. 初始化密钥（不需要证书）
./init-production.ps1                  # Windows
./init-production.sh                   # Linux/macOS

# 2. 启动
./start-stack.ps1 -Mode demo           # Windows
# 或手动：
docker compose --env-file .env.docker \
  -f docker-compose.yml \
  -f docker-compose.demo.yml \
  up -d
```

访问地址：
- `http://127.0.0.1:8081` — 前端页面
- `http://127.0.0.1:8000` — 后端 API

> 演示模式不启动 Nginx，直接映射后端和前端端口，不需要 TLS 证书。

## 证书配置（生产模式）

将 TLS 证书文件放入：

```
certs/
├── fullchain.pem    # 证书链（包含域名证书 + 中间证书）
└── privkey.pem      # 私钥
```

### 获取证书的方式

#### 方式一：自动生成自签名证书（演示）

```bash
# 使用初始化脚本自动生成
./init-production.ps1 -GenerateCert   # Windows
./init-production.sh --generate-cert   # Linux/macOS
```

#### 方式二：Let's Encrypt（公网域名，推荐）

```bash
# 安装 certbot 后
certbot certonly --standalone -d your-domain.com

# 复制证书到 nginx/certs/
cp /etc/letsencrypt/live/your-domain.com/fullchain.pem certs/
cp /etc/letsencrypt/live/your-domain.com/privkey.pem certs/
```

#### 方式三：校园网内部 CA

联系学校信息中心获取内部 CA 签发的证书，将 CA 证书同时部署到：
- Nginx 服务器（用于出示证书）
- 客户端机器（用于验证证书链）

> **桌面客户端注意：** 使用自签名证书时，桌面端需要信任该证书或将其 CA 导入系统证书存储。
> 正式部署应使用受信任 CA 签发的证书。

## Nginx 配置说明

- 仅在 `docker-compose.production.yml` 中定义 `nginx` 服务
- HTTP (80) 自动重定向到 HTTPS (443)
- `/api/*` 和 `/health/*` 代理到后端
- 其余请求代理到前端 SPA
- 已配置安全头：HSTS、X-Frame-Options、X-Content-Type-Options 等
