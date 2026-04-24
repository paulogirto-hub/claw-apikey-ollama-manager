import urllib.request, urllib.error, time, threading, json, subprocess, os
from datetime import datetime, timezone
from config import AUTH_FILE, OPENCLAW_FILE, MODEL, WHATSAPP_API, WHATSAPP_TARGET, FAIL_THRESHOLD, FALLBACK_COOLDOWN, HEALTH_CHECK_INTERVAL, TEST_COOLDOWN
from db import db_get_active_key, db_set_active, db_update_key_status, db_log_fallback, db_list_keys, db_get_config, db_set_config, db_get_next_alive_key, db_get_key_name, get_db

_health_thread = None
_stop_health_thread = False
_HC_INTERVAL = HEALTH_CHECK_INTERVAL

def test_key_via_api(key):
    """Testa uma key contra a API do Ollama com modelo configurado.
    Retorna (ok, latency_ms, error_msg)."""
    url = "https://ollama.com/api/generate"
    payload = json.dumps({"model": "minimax-m2.7:cloud", "prompt": "hi", "options": {"num_predict": 3}}).encode()
    try:
        req = urllib.request.Request(url, data=payload,
                             headers={"Content-Type": "application/json",
                                      "Authorization": f"Bearer {key}"}, method="POST")
        start = time.time()
        with urllib.request.urlopen(req, timeout=15) as resp:
            first_line = resp.readline()
            data = json.loads(first_line)
            latency = (time.time() - start) * 1000
            ok = resp.status == 200 and (data.get("response", "").strip() or data.get("thinking", "").strip())
            return (ok, latency, None)
    except urllib.error.HTTPError as e:
        err = f"HTTP {e.code}"
        try:
            err_body = e.read().decode()[:100]
            err = f"HTTP {e.code} {err_body}"
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
                return test_key_via_api(k["key"])
        return (False, 0, "Key not found")
    return test_key_via_api(key_id_or_key)

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
            test_ok = True
        else:
            print("[FALLBACK] Nenhuma key viva disponível")
            return

    active_key_id, _ = db_get_active_key()
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
    try:
        with open(AUTH_FILE) as f:
            auth = json.load(f)
    except:
        auth = {"profiles": {}}
    for profile_id, profile_data in auth.get("profiles", {}).items():
        if profile_data.get("type") == "api_key" and profile_data.get("provider") == "ollama":
            profile_data["key"] = active_key
    with open(AUTH_FILE, "w") as f:
        json.dump(auth, f, indent=2)

def write_openclaw_defaults():
    """Escreve openclaw.json com o modelo default."""
    data = {"model": MODEL}
    try:
        with open(OPENCLAW_FILE) as f:
            existing = json.load(f)
            existing.update(data)
            data = existing
    except:
        pass
    with open(OPENCLAW_FILE, "w") as f:
        json.dump(data, f, indent=2)

def restart_gateway():
    """Restart openclaw gateway."""
    try:
        subprocess.run(["openclaw", "gateway", "restart"], capture_output=True, timeout=30)
        print("[RESTART] Gateway restartado")
    except Exception as e:
        print(f"[RESTART] Erro: {e}")

def run_health_check():
    """Executa health check em todas as keys. Retorna (fallback_triggered, next_key_id)."""
    global _HC_INTERVAL
    from db import db_list_keys, db_get_active_key, db_update_key_status, db_set_config
    from datetime import datetime

    keys = db_list_keys()
    active_key_id, active_key = db_get_active_key()
    fallback_triggered = False
    next_key_id = None

    saved_interval = db_get_config("health_check_interval")
    if saved_interval:
        _HC_INTERVAL = int(saved_interval)

    for ks in keys:
        key_id = ks["id"]
        ok, latency, err = test_key_via_api(ks["key"])
        if ok:
            db_update_key_status(key_id, is_alive=1, consecutive_fails=0, last_error=None, latency_ms=latency)
        else:
            is_404 = isinstance(err, str) and err.startswith("HTTP 404")
            if not is_404:
                fails = (ks.get("consecutive_fails") or 0) + 1
                db_update_key_status(key_id, is_alive=0, consecutive_fails=fails, last_error=err)
                if key_id == active_key_id and fails >= FAIL_THRESHOLD and not fallback_triggered:
                    fallback_triggered = True
            else:
                db_update_key_status(key_id, is_alive=0, last_error=err)

    if fallback_triggered and active_key_id:
        next_id, next_key = db_get_next_alive_key(active_key_id)
        next_key_id = next_id

    db_set_config("last_full_check", datetime.now(timezone.utc).isoformat())
    return fallback_triggered, next_key_id

def run_health_check_only():
    """Executa health check em todas as keys SEM disparar fallback.
    Retorna dict com resultados de cada key."""
    from db import db_list_keys, db_update_key_status, db_set_config
    from datetime import datetime

    # Verifica cooldown de teste pra evitar banimento
    last_test = db_get_config("last_test_at")
    if last_test:
        try:
            last_ts = datetime.fromisoformat(last_test).timestamp()
            if time.time() - last_ts < TEST_COOLDOWN:
                remaining = int(TEST_COOLDOWN - (time.time() - last_ts))
                print(f"[TEST] Cooldown ativo, faltam {remaining}s")
                return {}
        except:
            pass

    keys = db_list_keys()
    results = {}

    for ks in keys:
        key_id = ks["id"]
        ok, latency, err = test_key_via_api(ks["key"])
        if ok:
            db_update_key_status(key_id, is_alive=1, consecutive_fails=0, last_error=None, latency_ms=latency)
        else:
            is_404 = isinstance(err, str) and err.startswith("HTTP 404")
            if not is_404:
                fails = (ks.get("consecutive_fails") or 0) + 1
                db_update_key_status(key_id, is_alive=0, consecutive_fails=fails, last_error=err)
            else:
                db_update_key_status(key_id, is_alive=0, last_error=err)
        results[key_id] = {"ok": ok, "latency": latency, "error": err}

    db_set_config("last_full_check", datetime.now(timezone.utc).isoformat())
    db_set_config("last_test_at", datetime.now(timezone.utc).isoformat())
    return results

def start_health_thread():
    global _health_thread, _stop_health_thread
    if _health_thread and _health_thread.is_alive():
        return
    _stop_health_thread = False
    def loop():
        while not _stop_health_thread:
            try:
                fb_triggered, next_id = run_health_check()
                if fb_triggered and next_id:
                    do_fallback(next_id, reason="auto")
            except Exception as e:
                print(f"[HEALTH] Erro: {e}")
            time.sleep(_HC_INTERVAL)
    _health_thread = threading.Thread(target=loop, daemon=True)
    _health_thread.start()

def stop_health_thread():
    global _stop_health_thread
    _stop_health_thread = True
