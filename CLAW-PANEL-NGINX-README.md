# 🦜 Claw Panel — NGINX Config

NGINX reverse proxy para expor os serviços na porta 20132.

## Files
- `docker-compose.yml` — sobe NGINX nas portas 20131 (HTTP) e 20132 (HTTPS)
- `nginx/default.conf` — configuração de proxy

## Setup
```bash
cd clawpanel-nginx
docker compose up -d
```

## ⚠️ Importante
O SSL está configurado com certificados auto-assinados (`ssl/server.crt/server.key`).
Para produção, substitua por certificados reais (Let's Encrypt, etc.).
