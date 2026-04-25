# 📁 Files Manager

Bot Flask de armazenamento de arquivos via Telegram com interface web.

## Funcionalidades
- 📤 Upload de arquivos (até 20MB via web, até 50MB via Telegram)
- 🔗 Download via link `/f/<token>`
- 📁 Gestão de pastas e sub-pastas
- ✏️ Renomear arquivos
- 🗑️ Deletar arquivos
- 📁 Mover arquivos entre pastas
- 🌐 Interface web responsiva (dark theme)
- 📱 Bot Telegram integrado

## Setup

### 1. Configure o Bot
Edite `docker-compose.yml` e defina as variáveis:
```yaml
environment:
  - BOT_TOKEN=seu_token_do_bot
  - BASE_URL=https://seu-dominio.com
  - ALLOWED_USER=seu_telegram_user_id
```

### 2. Suba com Docker Swarm
```bash
docker stack deploy -c docker-compose.yml files_stack
```

### 3. Configure o Traefik
O `docker-compose.yml` já inclui labels do Traefik. Adjust `DOMAIN` no seu ambiente.

## API Endpoints

| Método | Endpoint | Descrição |
|--------|----------|-----------|
| `GET` | `/files` | Interface web |
| `GET` | `/f/<token>` | Download arquivo |
| `GET` | `/files/api/list` | Lista arquivos |
| `GET` | `/files/api/folders` | Lista pastas |
| `POST` | `/files/api/upload` | Upload arquivo |
| `POST` | `/files/api/folders` | Criar pasta |
| `POST` | `/files/api/files/<token>/move` | Mover arquivo |
| `POST` | `/files/api/files/<token>/rename` | Renomear |
| `DELETE` | `/files/api/files/<token>` | Deletar arquivo |
| `DELETE` | `/files/api/folders/<id>` | Deletar pasta |

## Database Schema

### Tabela `files`
```sql
CREATE TABLE files (
    id TEXT PRIMARY KEY,
    filename TEXT NOT NULL,
    folder TEXT DEFAULT '/',
    size INTEGER,
    mime_type TEXT,
    uploaded_at TEXT,
    file_id TEXT,
    token TEXT UNIQUE,
    user_id TEXT,
    parent_folder TEXT
);
```

### Tabela `folders`
```sql
CREATE TABLE folders (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    parent_id TEXT,
    created_at TEXT,
    user_id TEXT
);
```

## Variáveis de Ambiente

| Variável | Descrição | Padrão |
|----------|-----------|--------|
| `BOT_TOKEN` | Token do bot Telegram | (obrigatório) |
| `BASE_URL` | URL base pública | https://seu-dominio.com |
| `ALLOWED_USER` | Telegram user ID permitido | (obrigatório) |
| `DB_FILE` | Caminho do banco SQLite | /root/files.db |
