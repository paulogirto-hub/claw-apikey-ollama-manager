#!/usr/bin/env python3
"""
OpenClaw API Key Manager - Entry Point
Refatorado em módulos: db, health, auth, config, templates
"""

import os, json, threading
from flask import Flask, request, jsonify, make_response

# Imports dos módulos
from config import (APP_DIR, AUTH_FILE, OPENCLAW_FILE, DB_FILE, MODEL, PORT,
                    PANEL_PASSWORD, HEALTH_CHECK_INTERVAL, FAIL_THRESHOLD,
                    WHATSAPP_API, WHATSAPP_TARGET, SECRET_KEY, SESSION_COOKIE, SESSION_TTL)
from db import (init_db, db_add_key, db_list_keys, db_get_active_key, db_set_active,
                db_update_key_status, db_delete_key, db_get_config, db_set_config,
                db_get_next_alive_key, db_rename_key, db_get_key_name, db_log_fallback,
                db_get_fallback_log, db_get_last_fallback, db_set_config)
from health import (start_health_thread, do_fallback, run_health_check,
                    test_key_health, write_auth_profiles_from_db, write_openclaw_defaults,
                    restart_gateway, find_next_alive_key, _HC_INTERVAL, run_health_check_only)
from auth import validate_session, render_login_page, SESSIONS, generate_session_token, SESSION_COOKIE, SESSION_TTL
from templates import render_page, _MODAL_HTML

app = Flask(__name__)
app.secret_key = SECRET_KEY
_last_updated = None

# ── helpers JSON (legado, ainda usado) ────────────────────────────────────
def load_json(path, default=None):
    if not os.path.exists(path):
        return default
    try:
        with open(path) as f:
            return json.load(f)
    except:
        return default

def save_json(path, data):
    with open(path, "w") as f:
        json.dump(data, f, indent=2)

# ── migração de dados legados ──────────────────────────────────────────────
def migrate_legacy():
    profiles = load_json(AUTH_FILE, {})
    if not profiles:
        return
    for pid, pdata in profiles.get("profiles", {}).items():
        if pdata.get("type") == "api_key" and pdata.get("provider") == "ollama":
            key = pdata.get("key", "")
            if key:
                db_add_key(pid, key)

# ── routes ───────────────────────────────────────────────────────────────────

@app.route("/")
def index():
    if not validate_session(request):
        return render_login_page(), 401
    return render_page(request), 200, {"Content-Type": "text/html"}

@app.route("/api/login", methods=["POST"])
def api_login():
    from auth import do_login
    return do_login(
        request.form.get("username", ""),
        request.form.get("password", "")
    )

@app.route("/api/logout", methods=["POST"])
def api_logout():
    token = request.cookies.get(SESSION_COOKIE)
    if token in SESSIONS:
        del SESSIONS[token]
    resp = make_response(json.dumps({"ok": True}))
    resp.delete_cookie(SESSION_COOKIE)
    return resp

@app.route("/api/keys")
def api_keys_list():
    if not validate_session(request): return jsonify({"error": "Unauthorized"}), 401
    return jsonify({"keys": db_list_keys()})

@app.route("/api/keys", methods=["POST"])
def api_keys_action():
    if not validate_session(request): return jsonify({"error": "Unauthorized"}), 401
    data = request.get_json()
    action = data.get("action", "")

    if action == "add":
        key_val = data.get("key", "").strip()
        name = data.get("name", "").strip()
        if not key_val:
            return jsonify({"ok": False, "error": "Key vazia"})
        key_id = data.get("key_id", f"ollama:{key_val[:8]}")
        db_add_key(key_id, key_val, name=name)
        # Testa e atualiza status
        ok, lat, err = test_key_health(key_val)
        db_update_key_status(key_id, is_alive=1 if ok else 0, latency_ms=lat if ok else None, last_error=err)
        return jsonify({"ok": True, "key_id": key_id})

    elif action == "activate":
        key_id = data.get("key_id")
        if not key_id: return jsonify({"ok": False, "error": "key_id requerido"})
        do_fallback(key_id, reason="manual")
        return jsonify({"ok": True, "key_id": key_id})

    elif action == "delete":
        key_id = data.get("key_id")
        if not key_id: return jsonify({"ok": False, "error": "key_id requerido"})
        db_delete_key(key_id)
        return jsonify({"ok": True})

    elif action == "rename":
        key_id = data.get("key_id")
        name = data.get("name", "").strip()
        if not key_id: return jsonify({"ok": False, "error": "key_id requerido"})
        db_rename_key(key_id, name)
        return jsonify({"ok": True})

    elif action == "test":
        key_id = data.get("key_id")
        if not key_id: return jsonify({"ok": False, "error": "key_id requerido"})
        ok, lat, err = test_key_health(key_id)
        return jsonify({"ok": ok, "latency_ms": lat, "error": err})

    elif action == "import":
        keys = data.get("keys", [])
        imported = 0
        for ks in keys:
            db_add_key(ks.get("id", ""), ks.get("key", ""), name=ks.get("name"))
            imported += 1
        return jsonify({"ok": True, "imported": imported})

    return jsonify({"ok": False, "error": "action desconhecida"})

@app.route("/api/health_check", methods=["POST"])
def api_health_check():
    if not validate_session(request): return jsonify({"error": "Unauthorized"}), 401
    results = run_health_check_only()
    return jsonify({"ok": True, "results": results})

@app.route("/api/fallback", methods=["POST"])
def api_fallback():
    if not validate_session(request): return jsonify({"error": "Unauthorized"}), 401
    active_key_id, _ = db_get_active_key()
    next_id, next_key = find_next_alive_key(active_key_id or "")
    if not next_id:
        return jsonify({"ok": False, "error": "Nenhuma key viva disponível"})
    do_fallback(next_id, reason="manual")
    return jsonify({"ok": True, "new_key_id": next_id})

@app.route("/api/restart", methods=["POST"])
def api_restart():
    if not validate_session(request): return jsonify({"error": "Unauthorized"}), 401
    threading.Thread(target=restart_gateway, daemon=True).start()
    return jsonify({"ok": True})

@app.route("/api/config", methods=["GET", "POST"])
def api_config():
    if not validate_session(request): return jsonify({"error": "Unauthorized"}), 401
    if request.method == "POST":
        data = request.get_json()
        for k, v in data.items():
            db_set_config(k, str(v))
        # Atualiza interval no health se mudou
        if "health_check_interval" in data:
            from health import _HC_INTERVAL
            import time as time_mod
            global _HC_INTERVAL
            _HC_INTERVAL = int(data["health_check_interval"])
        return jsonify({"ok": True})
    # GET
    interval = db_get_config("health_check_interval")
    return jsonify({"health_check_interval": int(interval) if interval else HEALTH_CHECK_INTERVAL})

@app.route("/api/cooldown_status")
def api_cooldown_status():
    if not validate_session(request): return jsonify({"error": "Unauthorized"}), 401
    last = db_get_config("last_fallback_at")
    in_cooldown = False
    remaining = 0
    if last:
        try:
            from datetime import datetime
            ts = datetime.fromisoformat(last).timestamp()
            elapsed = time_mod.time() - ts
            if elapsed < FALLBACK_COOLDOWN:
                in_cooldown = True
                remaining = int(FALLBACK_COOLDOWN - elapsed)
        except:
            pass
    return jsonify({"in_cooldown": in_cooldown, "remaining_seconds": remaining})

@app.route("/api/fallback_log")
def api_fallback_log():
    if not validate_session(request): return jsonify({"error": "Unauthorized"}), 401
    return jsonify({"log": db_get_fallback_log(50)})

@app.route("/api/export")
def api_export():
    if not validate_session(request): return jsonify({"error": "Unauthorized"}), 401
    return jsonify({"keys": db_list_keys()})

@app.route("/api/check_principal_return")
def api_check_principal_return():
    if not validate_session(request): return jsonify({"error": "Unauthorized"}), 401
    from datetime import datetime
    from db import get_db
    conn = get_db()
    try:
        # Acha histórico mais recente da principal que teve fallback automático
        cur = conn.execute("""
            SELECT principal_key_id, replaced_at FROM principal_history
            WHERE was_auto_fallback = 1
            ORDER BY id DESC LIMIT 1
        """)
        row = cur.fetchone()
        if not row:
            return jsonify({"should_suggest_return": False})
        # Verifica se ela está viva agora
        principal_id = row["principal_key_id"]
        cur2 = conn.execute("SELECT is_alive, consecutive_fails FROM keys WHERE id=?", (principal_id,))
        krow = cur2.fetchone()
        if krow and krow["is_alive"] and krow["consecutive_fails"] == 0:
            replaced_at = datetime.fromisoformat(row["replaced_at"])
            minutes_ago = (datetime.now(timezone.utc) - replaced_at).total_seconds() / 60
            if minutes_ago >= 10:
                return jsonify({"should_suggest_return": True, "principal_key_id": principal_id, "minutes_ago": int(minutes_ago)})
        return jsonify({"should_suggest_return": False})
    finally:
        conn.close()

@app.route("/api/return_to_principal", methods=["POST"])
def api_return_to_principal():
    if not validate_session(request): return jsonify({"error": "Unauthorized"}), 401
    from db import get_db
    from datetime import datetime
    conn = get_db()
    try:
        cur = conn.execute("""
            SELECT principal_key_id FROM principal_history
            WHERE was_auto_fallback = 1 ORDER BY id DESC LIMIT 1
        """)
        row = cur.fetchone()
        if not row:
            return jsonify({"ok": False, "error": "Nenhum histórico de fallback"})
        principal_id = row["principal_key_id"]
        conn.execute("DELETE FROM principal_history WHERE principal_key_id=? AND was_auto_fallback=1", (principal_id,))
        conn.commit()
    finally:
        conn.close()
    do_fallback(principal_id, reason="manual")
    return jsonify({"ok": True, "key_id": principal_id})

@app.route("/api/test_key_single/<key_id>")
def api_test_key_single(key_id):
    if not validate_session(request): return jsonify({"error": "Unauthorized"}), 401
    ok, lat, err = test_key_health(key_id)
    return jsonify({"ok": ok, "latency_ms": lat, "error": err})

if __name__ == "__main__":
    import time as time_mod
    from datetime import timezone

    os.makedirs(APP_DIR, exist_ok=True)
    init_db()
    print(f"[DB] SQLite inicializado em {DB_FILE}")
    migrate_legacy()

    active_id, _ = db_get_active_key()
    if not active_id and os.path.exists(AUTH_FILE):
        profiles = load_json(AUTH_FILE, {})
        active_key_id = None
        active_key = None
        for pid, pdata in profiles.get("profiles", {}).items():
            if pdata.get("type") == "api_key" and pdata.get("provider") == "ollama":
                key = pdata.get("key", "")
                if not key:
                    continue
                db_add_key(pid, key)
                if not active_key:
                    active_key_id = pid
                    active_key = key
        if active_key_id:
            db_set_active(active_key_id)
            print(f"[INIT] Key ativa: {active_key_id}")

    start_health_thread()
    print(f"🦜 Claw Key Manager — http://localhost:{PORT}")
    print(f"   Senha: {PANEL_PASSWORD}")
    app.run(host="0.0.0.0", port=PORT, debug=False)
