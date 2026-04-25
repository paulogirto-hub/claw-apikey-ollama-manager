# 🦜 Claw Panel

Conjunto de serviços para gerenciar API keys e arquivos via Telegram + Web.

---

## 📦 Serviços

### 1. 🦜 Claw Key Manager (`/key`)
Painel Flask para gerenciar API keys de múltiplos provedores de IA com **health check automático**, **fallback inteligente** e **SQLite como fonte de verdade**.

**Funcionalidades:**
- 💚 Health check automático
- 🔄 Fallback inteligente
- 🌐 Interface web moderna
- ⏱️ Cooldown anti-spam
- 🧪 Teste manual de keys
- 📥 Import/Export JSON
- 🐌 Detecção de keys lentas
- 📱 Notificação WhatsApp (gateway)

---

### 2. 📁 Files Manager (`/files`)
Bot Flask de armazenamento de arquivos via Telegram com interface web para upload, download e **gestão de pastas**.

**Funcionalidades:**
- 📤 Upload de arquivos (até 20MB)
- 🔗 Download via link `/f/<token>`
- 📁 Pastas e sub-pastas
- ✏️ Renomear arquivos
- 🗑️ Deletar arquivos
- 📁 Mover arquivos entre pastas
- 🌐 Interface web responsiva
- 📱 Bot Telegram integrado

---

## 🚀 Quick Start

### Pré-requisitos
- Docker + Docker Swarm
- Traefik (ou NGINX) como proxy reverso
- Python 3.11+ (desenvolvimento)

### 1. Clone o repositório
```bash
git clone https://github.com/paulogirto-hub/claw-apikey-ollama-manager.git
cd claw-apikey-ollama-manager
```

### 2. Configure
```bash
cp config.py.example config.py
# Edite config.py com suas credenciais
```

### 3. Suba com Docker
```bash
# Key Manager
docker compose up -d

# Files Manager
cd files_manager
docker compose up -d
```

### 4. Acesse
- Key Manager: `http://localhost:20130/`
- Files Manager: `http://localhost:20131/files`

---

## 🔑 Key Manager — Configuração

### Variáveis de Ambiente (config.py)

| Variável | Descrição | Padrão |
|----------|-----------|--------|
| `PANEL_PASSWORD` | Senha do painel | `SUA_SENHA` |
| `MODEL` | Modelo pra health check | `ollama/minimax-m2.7:cloud` |
| `PORT` | Porta do servidor | `20130` |
| `HEALTH_CHECK_INTERVAL` | Intervalo de check (seg) | `300` |
| `FAIL_THRESHOLD` | Falhas antes de marcar dead | `3` |
| `FALLBACK_COOLDOWN` | Cooldown após fallback (seg) | `300` |
| `TEST_COOLDOWN` | Cooldown entre testes manuais | `60` |
| `SECRET_KEY` | Chave para sessões (gere aleatória!) | `MUDE_AQUI` |

### Health Check
- Testa todas as keys ativas automaticamente
- Marca como `dead` após `FAIL_THRESHOLD` falhas consecutivas
- Fallback automático para próxima key viva
- Detecta keys lentas (>3s de latência)

### Telegram Integration
O bot responde aos comandos:
- `/start` — mensagem inicial
- `/keys` — lista todas as keys com status
- `/add <nome> <key>` — adiciona nova key
- `/delete <nome>` — remove key
- `/test <nome>` — testa key específica
- `/export` — exporta JSON com todas as keys

---

## 📁 Files Manager — API

### Endpoints

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

### Estrutura de Pastas
- Pasta raiz: `parent_id = NULL`
- Sub-pastas: `parent_id = <id_da_pai>`
- Arquivos: `folder = '/'` (raiz) ou `folder = <id_da_pasta>`

### Docker Labels (Traefik)
```
traefik.http.routers.filesbot.rule=Host(`seu-dominio.com`) && PathPrefix(`/files`)
traefik.http.routers.filesbot.service=filesbot
traefik.http.routers.filesbot.entrypoints=websecure
traefik.http.routers.filesbot.tls=true
traefik.http.services.filesbot.loadbalancer.server.port=20131
```

---

## 🏗️ Arquitetura

```
                    ┌─────────────┐
                    │   Traefik   │
                    │ (proxy web) │
                    └──────┬──────┘
                           │
            ┌──────────────┼──────────────┐
            │              │              │
      ┌─────┴─────┐  ┌─────┴─────┐  ┌─────┴─────┐
      │ Key Mgr   │  │ Files Mgr │  │  NGINX    │
      │ :20130    │  │ :20131    │  │ :20132   │
      └───────────┘  └───────────┘  └───────────┘
```

---

## 📂 Estrutura do Projeto

```
claw-panel/
├── claw-key-manager/     # Key Manager (Flask)
│   ├── panel_vps.py       # Servidor principal
│   ├── auth.py            # Autenticação
│   ├── db.py              # Banco SQLite
│   ├── health.py          # Health check
│   ├── config.py.example  # Configuração exemplo
│   └── templates.py       # HTML templates
├── files_manager/         # Files Manager (Flask)
│   ├── bot/
│   │   ├── file_bot.py   # Bot + API
│   │   └── files_ui.html # Interface web
│   └── docker-compose.yml
└── clawpanel-nginx/       # NGINX (opcional)
    ├── nginx/default.conf
    └── docker-compose.yml
```

---

## ⚙️ Desenvolvimento

```bash
# Setup ambiente
python3 -m venv venv
source venv/bin/activate
pip install flask requests

# Rode localmente
python3 claw-key-manager/panel_vps.py

# Testes
python3 -m pytest claw-key-manager/test_health.py
```

---

## 🔒 Segurança

- **NUNCA** commite `config.py` ou `*.db`
- Use variáveis de ambiente para secrets em produção
- O banco SQLite (`*.db`) contém suas API keys — mantenha seguro
- HTTPS é obrigatório em produção (use Traefik com TLS)

---

## 📝 Licença

MIT
