import os

APP_DIR = os.path.expanduser("~/.openclaw/agents/main/agent")
AUTH_FILE = os.path.join(APP_DIR, "auth-profiles.json")
OPENCLAW_FILE = os.path.join(APP_DIR, "openclaw.json")
KEYS_STATUS_FILE = os.path.join(APP_DIR, "keys_status.json")
DB_FILE = os.path.join(APP_DIR, "panel_keys.db")
MODEL = "ollama/minimax-m2.7:cloud"
PORT = 20130
PANEL_PASSWORD = "CHANGE_ME"
HEALTH_CHECK_INTERVAL = 300  # 5 minutos
FAIL_THRESHOLD = 3
FALLBACK_COOLDOWN = 300
WHATSAPP_API = "http://localhost:18789"
WHATSAPP_TARGET = "+55XXXXXXXXX"
SESSION_COOKIE = "claw_session"
SESSION_TTL = 86400  # 24 hours
SECRET_KEY = "REPLACE_WITH_RANDOM_32_CHARS"
