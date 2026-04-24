# 🦜 Claw Key Manager

Painel Flask para gerenciar API keys do Ollama com **health check automático**, **fallback inteligente** e **SQLite como fonte de verdade**.

---

## Problema

API keys de provedores de IA expiram, atingem quota, ou param de responder no meio de uma conversa. Trocar manualmente é chato e quebra o fluxo.

## Solução

O Claw Key Manager monitora todas as suas keys, detecta quando uma morre, e faz o **fallback automático** pra próxima — sem você precisar fazer nada.

---

## Funcionalidades

- 💚 **Health Check Automático** — testa todas as keys em intervalos de 1/2/5/10 min
- 🔄 **Fallback Inteligente** — ativa próxima key viva quando a principal morre
- 🗄️ **SQLite como Source of Truth** — banco local leve, sem dependências externas
- 🌐 **Interface Web** — painel moderno com status em tempo real
- ⏱️ **Cooldown Anti-Spam** — não troca de key mais que uma vez a cada 5 min
- 🧪 **Teste Manual** — teste keys individuais com um clique
- 📥 **Import/Export JSON** — exporte suas keys, importe quando precisar
- 🐌 **Detecção de Keys Lentas** — marca keys com latência > 3s
- 📊 **Histórico de Fallbacks** — registro de todas as trocas de key

---

## Stack

```
Flask  ·  SQLite  ·  Python 3  ·  Docker Swarm  ·  Traefik
```

---

## Instalação

### 1. Clone o repo

```bash
git clone https://github.com/paulogirto-hub/claw-apikey-ollama-manager.git
cd claw-apikey-ollama-manager
```

### 2. Configuração

Edite `config.py` com suas configurações:

```python
PANEL_PASSWORD = "sua_senha_aqui"    # Senha do painel web
PORT = 20130                         # Porta do servidor
HEALTH_CHECK_INTERVAL = 300          # Intervalo em segundos (default: 5 min)
FAIL_THRESHOLD = 3                   # Falhas antes de acionar fallback
FALLBACK_COOLDOWN = 300              # Cooldown entre fallbacks em segundos
MODEL = "minimax-m2.7:cloud"         # Modelo para health check
```

### 3. Execute

```bash
pip install flask -q
python3 panel_vps.py 20130
```

Acesse `http://localhost:20130` — login com `admin` + a senha do `config.py`.

---

## Docker Swarm

Deploy com Docker Swarm + Traefik:

```bash
docker stack deploy -c traefik.yaml haasgrow
```

O `traefik.yaml` já vem configurado com:
- Imagem `python:3-alpine`
- Volumes montados do host (módulos + DB)
- Rotas Traefik para HTTPS em `clawpanel.haasgrow.cloud`
- Health check_interval configurável (1/2/5/10 min)

---

## API Endpoints

### Autenticação

| Método | Endpoint | Descrição |
|--------|----------|-----------|
| POST | `/api/login` | Login (username/password) |
| POST | `/api/logout` | Logout |

### Keys

| Método | Endpoint | Descrição |
|--------|----------|-----------|
| GET | `/api/keys` | Lista todas as keys |
| POST | `/api/keys` | Ações: add, test, activate, delete, rename, import |

### Configuração

| Método | Endpoint | Descrição |
|--------|----------|-----------|
| GET | `/api/config` | Mostra configuração atual |
| POST | `/api/config` | Atualiza configuração |

### Sistema

| Método | Endpoint | Descrição |
|--------|----------|-----------|
| POST | `/api/health_check` | Força health check |
| POST | `/api/fallback` | Força fallback manual |
| GET | `/api/fallback_log` | Histórico de trocas |
| POST | `/api/restart_gateway` | Reinicia OpenClaw |

---

## Estrutura do Projeto

```
claw-key-manager/
├── config.py       # Configurações do painel
├── db.py           # Camada de dados (SQLite)
├── health.py       # Health check e fallback
├── auth.py         # Autenticação e sessões
├── templates.py    # HTML/CSS/JS do frontend
├── panel_vps.py    # Entry point (rotas Flask)
├── index.html     # Landing page pública
├── traefik.yaml   # Docker Stack config
└── README.md       # Este arquivo
```

---

## Landing Page

Página pública disponível em `/lp` — sem necessidade de login. Ideal pra compartilhar o projeto.

---

## Autor

**Paulo Girto** — [GitHub](https://github.com/paulogirto-hub)

---

## Licença

MIT