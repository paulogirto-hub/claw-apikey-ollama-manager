import sqlite3, os
from datetime import datetime, timezone
from config import DB_FILE

def get_db():
    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    """Cria tabelas se não existirem."""
    conn = get_db()
    try:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS keys (
                id TEXT PRIMARY KEY,
                key TEXT NOT NULL,
                name TEXT,
                is_active INTEGER DEFAULT 0,
                is_alive INTEGER DEFAULT 1,
                consecutive_fails INTEGER DEFAULT 0,
                latency_ms INTEGER DEFAULT 0,
                last_tested TEXT,
                last_error TEXT,
                created_at TEXT NOT NULL
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS config (
                key TEXT PRIMARY KEY,
                value TEXT
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS fallback_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                from_key_id TEXT,
                to_key_id TEXT,
                reason TEXT,
                triggered_at TEXT NOT NULL
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS principal_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                principal_key_id TEXT NOT NULL,
                replaced_at TEXT NOT NULL,
                was_auto_fallback INTEGER DEFAULT 0
            )
        """)
        # Migration: adicionar colunas se não existirem
        for col, dtype in [("name", "TEXT"), ("latency_ms", "INTEGER DEFAULT 0")]:
            try:
                conn.execute(f"ALTER TABLE keys ADD COLUMN {col} {dtype}")
            except sqlite3.OperationalError:
                pass
        conn.commit()
    finally:
        conn.close()

def db_add_key(key_id, key_value, name=None):
    now = datetime.now(timezone.utc).isoformat()
    conn = get_db()
    try:
        conn.execute("""
            INSERT OR IGNORE INTO keys (id, key, name, is_active, is_alive, consecutive_fails, last_tested, last_error, created_at)
            VALUES (?, ?, ?, 0, 1, 0, NULL, NULL, ?)
        """, (key_id, key_value, name, now))
        conn.commit()
    finally:
        conn.close()

def db_update_key_status(key_id, is_alive=None, consecutive_fails=None, last_error=None, latency_ms=None):
    conn = get_db()
    try:
        now = datetime.now(timezone.utc).isoformat()
        if is_alive is not None:
            conn.execute("UPDATE keys SET is_alive=?, last_tested=? WHERE id=?", (is_alive, now, key_id))
        if consecutive_fails is not None:
            conn.execute("UPDATE keys SET consecutive_fails=? WHERE id=?", (consecutive_fails, key_id))
        # Sempre atualiza last_error (pode ser vazio pra limpar)
        conn.execute("UPDATE keys SET last_error=? WHERE id=?", (last_error or "", key_id))
        if latency_ms is not None:
            conn.execute("UPDATE keys SET latency_ms=? WHERE id=?", (latency_ms, key_id))
        conn.commit()
    finally:
        conn.close()

def db_set_active(key_id):
    conn = get_db()
    try:
        conn.execute("UPDATE keys SET is_active=0")
        if key_id:
            conn.execute("UPDATE keys SET is_active=1 WHERE id=?", (key_id,))
        conn.commit()
    finally:
        conn.close()

def db_get_active_key():
    conn = get_db()
    try:
        cur = conn.execute("SELECT id, key FROM keys WHERE is_active=1 LIMIT 1")
        row = cur.fetchone()
        return (row["id"], row["key"]) if row else (None, None)
    finally:
        conn.close()

def db_list_keys():
    conn = get_db()
    try:
        cur = conn.execute("SELECT id, key, name, is_active, is_alive, consecutive_fails, last_tested, last_error, latency_ms, created_at FROM keys ORDER BY id")
        rows = cur.fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()

def db_delete_key(key_id):
    conn = get_db()
    try:
        conn.execute("DELETE FROM keys WHERE id=?", (key_id,))
        conn.commit()
    finally:
        conn.close()

def db_get_config(key_name):
    conn = get_db()
    try:
        cur = conn.execute("SELECT value FROM config WHERE key=?", (key_name,))
        row = cur.fetchone()
        return row["value"] if row else None
    finally:
        conn.close()

def db_set_config(key_name, value):
    conn = get_db()
    try:
        conn.execute("INSERT OR REPLACE INTO config (key, value) VALUES (?, ?)", (key_name, value))
        conn.commit()
    finally:
        conn.close()

def db_get_next_alive_key(current_key_id):
    conn = get_db()
    try:
        cur = conn.execute("SELECT id, key FROM keys WHERE is_alive=1 AND is_active=0 LIMIT 1")
        row = cur.fetchone()
        return (row["id"], row["key"]) if row else (None, None)
    finally:
        conn.close()

def db_rename_key(key_id, name):
    conn = get_db()
    try:
        conn.execute("UPDATE keys SET name=? WHERE id=?", (name, key_id))
        conn.commit()
    finally:
        conn.close()

def db_get_key_name(key_id):
    conn = get_db()
    try:
        cur = conn.execute("SELECT name FROM keys WHERE id=?", (key_id,))
        row = cur.fetchone()
        return row["name"] if row else None
    finally:
        conn.close()

def db_log_fallback(from_key_id, to_key_id, reason):
    now = datetime.now(timezone.utc).isoformat()
    conn = get_db()
    try:
        conn.execute("INSERT INTO fallback_log (from_key_id, to_key_id, reason, triggered_at) VALUES (?, ?, ?, ?)",
                     (from_key_id, to_key_id, reason, now))
        conn.commit()
    finally:
        conn.close()

def db_get_fallback_log(limit=20):
    conn = get_db()
    try:
        cur = conn.execute("SELECT * FROM fallback_log ORDER BY id DESC LIMIT ?", (limit,))
        return [dict(r) for r in cur.fetchall()]
    finally:
        conn.close()

def db_get_last_fallback():
    conn = get_db()
    try:
        cur = conn.execute("SELECT * FROM fallback_log ORDER BY id DESC LIMIT 1")
        row = cur.fetchone()
        return dict(row) if row else None
    finally:
        conn.close()
