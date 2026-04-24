import urllib.request, urllib.error, time, threading, json, subprocess, os
from datetime import datetime, timezone
from config import AUTH_FILE, OPENCLAW_FILE, MODEL, WHATSAPP_API, WHATSAPP_TARGET, FAIL_THRESHOLD, FALLBACK_COOLDOWN, HEALTH_CHECK_INTERVAL
from db import db_get_active_key, db_set_active, db_update_key_status, db_log_fallback, db_list_keys, db_get_config, db_set_config, db_get_next_alive_key, db_get_key_name, get_db

_health_thread = None
_stop_health_thread = False
_HC_INTERVAL = HEALTH_CHECK_INTERVAL

def test_key_via_api(key):
    """Testa uma key contra a API do Ollama SEM modelo fixo (prompt mínimo genérico).
    Retorna (ok, latency_ms, error_msg)."""
    url = "https://ollama.com/api/generate"
    payload = json.dumps({"prompt": "hi", "options": {"num_predict": 3}}).encode()
    try:
        req = urllib.request.Request(url, data=payload,
                             headers={"Content-Type": "application/json",
                                      "Authorization": f"Bearer {key}"}, method="POST")
        start = time.time()
        with urllib.request.urlopen(req, timeout=15) as resp:
            latency = int((time.time() - start) * 1000)
            # Streaming response — ler só a primeira linha JSON
            first_line = resp.readline()
            data = json.loads(first_line)
            ok = resp.status == 200 and data.get("response", "").strip()
            return (ok, latency, None)
    except urllib.error.HTTPError as e:
        err = f"HTTP {e.code}"
        try:
            err = f"HTTP {e.code} {e.read().decode()[:50]}"
        except:
            pass
        return (False, 0, err)
    except Exception as e:
        return (False, 0, str(e)[:80])

def test_key_health(key_id_or_key):
    """Testa uma key pelo ID ou pela key direta."""
    if key_id_or_key.startswith("ollama:"):
        from db import db_list_keys
        keys = db_list_keys()
        for k in keys:
            if k["id"] == key_id_or_key:
                ok, latency, err = test_key_via_api(k["key"])
                db_update_key_status(k["id"], is_alive=1 if ok else 0,
                                     consecutive_fails=0 if ok else k.get("consecutive_fails", 0) + 1,
                                     last_error=err, latency_ms=latency if ok else None)
                return ok, latency, err
        return False, 0, "Key não encontrada"
    else:
        return test_key_via_api(key_id_or_key)

def send_whatsapp_alert(message):
    """Envia alerta via WhatsApp (opcional)."""
    try:
        data = json.dumps({"number": WHATSAPP_TARGET, "message": message}).encode()
        req = urllib.request.Request(WHATSAPP_API + "/send", data=data,
                                     headers={"Content-Type": "application/json"}, method="POST")
        with urllib.request.urlopen(req, timeout=5):
            pass
    except:
        pass

def run_health_check():
    """Executa health check em todas as keys. Retorna (fallback_triggered, next_key_id)."""
    global _HC_INTERVAL
    from db import db_list_keys, db_get_active_key, db_update_key_status, db_set_config
    from datetime import datetime

    keys = db_list_keys()
    active_key_id, active_key = db_get_active_key()
    fallback_triggered = False
    next_key_id = None

    # Atualiza intervalo da config se mudou
    saved_interval = db_get_config("health_check_interval")
    if saved_interval:
        _HC_INTERVAL = int(saved_interval)

    for ks in keys:
        key_id = ks["id"]
        ok, latency, err = test_key_via_api(ks["key"])
        if ok:
            db_update_key_status(key_id, is_alive=1, consecutive_fails=0, last_error=None, latency_ms=latency)
        else:
            # HTTP 404 = modelo não suportado, não marca key como morta
            is_404 = isinstance(err, str) and err.startswith("HTTP 404")
            fails = ks.get("consecutive_fails", 0) + (0 if is_404 else 1)
            db_update_key_status(key_id, is_alive=0,
                                 consecutive_fails=fails if not is_404 else ks.get("consecutive_fails", 0),
                                 last_error=err)
            if key_id == active_key_id and not is_404 and fails >= FAIL_THRESHOLD and not fallback_triggered:
                fallback_triggered = True

    # Se key ativa falhou, achar próxima viva
    if fallback_triggered and active_key_id:
        next_id, next_key = db_get_next_alive_key(active_key_id)
        next_key_id = next_id

    db_set_config("last_full_check", datetime.now(timezone.utc).isoformat())
    return fallback_triggered, next_key_id

def find_next_alive_key(current_key_id):
    """Acha próxima key viva (testa antes de retornar)."""
    keys = db_list_keys()
    for ks in keys:
        if ks["id"] != current_key_id and ks.get("is_alive"):
            ok, _, _ = test_key_via_api(ks["key"])
            if ok:
                return ks["id"], ks["key"]
    return None, None

def do_fallback(new_key_id, reason="manual"):
    """Aplica fallback: ativa key no SQLite e escreve auth-profiles.json."""
    global _HC_INTERVAL
    last_fb = db_get_config("last_fallback_at")
    if last_fb:
        try:
            last_ts = datetime.fromisoformat(last_fb).timestamp()
            if time.time() - last_ts < FALLBACK_COOLDOWN:
                print(f"[FALLBACK] Cooldown ativo, ignorando. Faltam {FALLBACK_COOLDOWN - (time.time()-last_ts):.0f}s")
                return
        except:
            pass

    # Testa a new key antes de ativar
    conn = get_db()
    try:
        row = conn.execute("SELECT key FROM keys WHERE id=?", (new_key_id,)).fetchone()
        if not row:
            return
        new_key = row["key"]
    finally:
        conn.close()

    test_ok, latency, err = test_key_via_api(new_key)
    if not test_ok:
        nid, nk = find_next_alive_key(new_key_id)
        if nid:
            new_key_id = nid
            new_key = nk
            test_ok, latency, err = test_key_via_api(new_key)
        if not test_ok:
            print("[FALLBACK] Nenhuma key viva disponível")
            return

    active_key_id, _ = db_get_active_key()
    # Salva histórico da principal se foi automático
    if reason == "auto" and active_key_id:
        conn = get_db()
        try:
            conn.execute("INSERT INTO principal_history (principal_key_id, replaced_at, was_auto_fallback) VALUES (?, ?, 1)",
                         (active_key_id, datetime.now(timezone.utc).isoformat()))
            conn.commit()
        finally:
            conn.close()

    db_set_active(new_key_id)
    db_log_fallback(active_key_id, new_key_id, reason)
    write_auth_profiles_from_db()
    write_openclaw_defaults()
    db_set_config("active_key_id", new_key_id)
    db_set_config("last_fallback_at", datetime.now(timezone.utc).isoformat())
    threading.Thread(target=restart_gateway, daemon=True).start()

def write_auth_profiles_from_db():
    """Lê keys do SQLite e escreve em auth-profiles.json."""
    from config import AUTH_FILE, MODEL
    from db import db_get_active_key
    active_key_id, active_key = db_get_active_key()
    profiles = {}
    if active_key_id and active_key:
        profiles[active_key_id] = {"type": "api_key", "provider": "ollama", "key": active_key}
    os.makedirs(os.path.dirname(AUTH_FILE), exist_ok=True)
    with open(AUTH_FILE, "w") as f:
        json.dump(profiles, f, indent=2)

def write_openclaw_defaults():
    """Escreve openclaw.json com o modelo default."""
    from config import OPENCLAW_FILE, MODEL
    data = {"model": MODEL}
    os.makedirs(os.path.dirname(OPENCLAW_FILE), exist_ok=True)
    with open(OPENCLAW_FILE, "w") as f:
        json.dump(data, f, indent=2)

def restart_gateway():
    """Restart no gateway via systemctl."""
    try:
        subprocess.run(["systemctl", "restart", "openclaw"], check=True)
        print("[GATEWAY] Restart via systemctl")
    except Exception as e:
        print(f"[GATEWAY] systemctl falhou: {e}")
        try:
            subprocess.run(["openclaw", "gateway", "restart"], check=True)
            print("[GATEWAY] Restart via openclaw cli")
        except Exception as e2:
            print(f"[GATEWAY] openclaw cli também falhou: {e2}")

def health_check_loop():
    """Thread loop de health check."""
    global _stop_health_thread, _HC_INTERVAL
    while not _stop_health_thread:
        try:
            fallback_triggered, next_key_id = run_health_check()
            if fallback_triggered and next_key_id:
                from_name = db_get_key_name(db_get_active_key()[0]) or db_get_active_key()[0]
                to_name = db_get_key_name(next_key_id) or next_key_id
                do_fallback(next_key_id, reason="auto")
                send_whatsapp_alert(f"🔄 Fallback: key {from_name} morreu, trocou para {to_name}")
        except Exception as e:
            print(f"[HEALTH] Erro no health check: {e}")
        finally:
            for _ in range(_HC_INTERVAL):
                if _stop_health_thread:
                    break
                time.sleep(1)

def start_health_thread():
    """Inicia thread de health check em background."""
    global _health_thread, _stop_health_thread, _HC_INTERVAL
    _stop_health_thread = False
    saved = db_get_config("health_check_interval")
    if saved:
        _HC_INTERVAL = int(saved)
    _health_thread = threading.Thread(target=health_check_loop, daemon=True)
    _health_thread.start()
    print("[APP] Health check thread iniciado")
