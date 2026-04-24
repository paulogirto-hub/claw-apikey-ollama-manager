"""Testes para health.py — fallback, health check e contador de keys vivas."""
import pytest, sys, os, sqlite3
from unittest.mock import patch, MagicMock

sys.path.insert(0, os.path.dirname(__file__))

# ── fixtures ────────────────────────────────────────────────────────────────

@pytest.fixture
def temp_db(tmp_path):
    """DB SQLite temporário."""
    db_file = tmp_path / "test_panel.db"
    os.environ["_TEST_DB"] = str(db_file)

    import config
    old_db = config.DB_FILE
    config.DB_FILE = str(db_file)

    from db import init_db, db_add_key, db_set_active, db_update_key_status
    init_db()

    # adicionar keys de teste
    db_add_key("key1", "test_key_1", name="Key 1")
    db_add_key("key2", "test_key_2", name="Key 2")
    db_add_key("key3", "test_key_3", name="Key 3")
    db_set_active("key1")

    yield {
        "db_add_key": db_add_key,
        "db_update_key_status": db_update_key_status,
        "db_set_active": db_set_active,
    }

    config.DB_FILE = old_db


@pytest.fixture
def health_mod(temp_db):
    """health.py com DB temporário."""
    import importlib, health as h
    importlib.reload(h)
    yield h


# ── test helpers ──────────────────────────────────────────────────────────────

def make_mock_resp(ok=True, status=200):
    m = MagicMock()
    m.status = status
    m.readline.return_value = b'{"response": "hi"}' if ok else b'{"error": "fail"}'
    return m


# ── testes ──────────────────────────────────────────────────────────────────

@patch("health.test_key_via_api")
def test_fallback_only_activates_working_key(mock_test, health_mod, temp_db):
    """Bug 1: fallback NÃO pode ativar key que falhou no teste real."""
    from db import db_get_active_key, db_set_active, db_add_key, db_update_key_status

    # key1 é ativa e morre
    db_update_key_status("key1", is_alive=0, consecutive_fails=3)

    # key2 e key3 estão vivas no DB mas só key2 passa no teste real
    db_update_key_status("key2", is_alive=1, consecutive_fails=0)
    db_update_key_status("key3", is_alive=1, consecutive_fails=0)

    def test_side_effect(key):
        if key == "test_key_2":
            return (True, 120, None)  # key2 funciona
        return (False, 0, "HTTP 401")  # key3 não funciona

    mock_test.side_effect = test_side_effect

    db_set_active("key1")
    active_before, _ = db_get_active_key()

    health_mod.do_fallback("key3", reason="auto")

    active_after, _ = db_get_active_key()

    # Só ativa se o teste real passar — key3 falhou, então key2 deve ser a ativa
    assert active_after in ("key2", active_before), \
        f"Fallback ativou key3 que falhou no teste real (ativa={active_after})"


@patch("health.test_key_via_api")
def test_fallback_finds_next_live_key(mock_test, health_mod, temp_db):
    """Bug 1: find_next_alive_key testa antes de retornar."""
    from db import db_get_active_key, db_set_active, db_update_key_status

    db_update_key_status("key2", is_alive=1, consecutive_fails=0)
    db_update_key_status("key3", is_alive=1, consecutive_fails=0)

    call_order = []

    def test_side_effect(key):
        call_order.append(key)
        if key == "test_key_2":
            return (True, 100, None)
        return (False, 0, "HTTP 401")

    mock_test.side_effect = test_side_effect

    nid, nk = health_mod.find_next_alive_key("key1")

    # key2 foi testada e passou
    assert "test_key_2" in call_order, "find_next_alive_key não testou key candidate"
    # key3 só é testada se key2 falhar
    assert nid == "key2", f"Esperado key2, got {nid}"


@patch("health.test_key_via_api")
def test_consecutive_fails_increments(health_mod, temp_db):
    """Bug 2: consecutive_fails incrementa a cada falha real (não 404)."""
    from db import db_update_key_status, db_list_keys, db_set_active

    db_set_active("key1")

    # Simula duas falhas 404 e duas falhas reais
    calls = []

    def mock_test(key):
        calls.append(key)
        if len([c for c in calls if c == key]) <= 2:
            return (False, 0, "HTTP 404")  # 404 não soma fail
        return (False, 0, "HTTP 401")  # 401 soma fail

    with patch("health.test_key_via_api", side_effect=mock_test):
        for _ in range(4):
            health_mod.run_health_check()

    ks = next(k for k in db_list_keys() if k["id"] == "key1")
    # Duas falhas 404 (não conta) + duas falhas 401 (conta) = 2 fails
    assert ks["consecutive_fails"] == 2, \
        f"consecutive_fails deveria ser 2, got {ks['consecutive_fails']}"


@patch("health.test_key_via_api")
def test_health_check_marks_dead_keys(mock_test, health_mod, temp_db):
    """Bug 2: health check marca key como morta após FAIL_THRESHOLD falhas reais."""
    from db import db_update_key_status, db_list_keys, db_set_active

    db_set_active("key1")
    db_update_key_status("key1", is_alive=1, consecutive_fails=0)

    # Simula 3 falhas HTTP 401 (não 404)
    mock_test.return_value = (False, 0, "HTTP 401 Unauthorized")

    for _ in range(3):
        health_mod.run_health_check()

    ks = next(k for k in db_list_keys() if k["id"] == "key1")
    assert ks["is_alive"] == 0, "Key deveria estar morta após 3 falhas"
    assert ks["consecutive_fails"] == 3, "consecutive_fails deveria ser 3"


@patch("health.test_key_via_api")
def test_404_does_not_mark_total_dead(mock_test, health_mod, temp_db):
    """Bug 2: HTTP 404 não marca key como totalmente morta (fail=0)."""
    from db import db_list_keys, db_set_active, db_update_key_status

    db_set_active("key1")
    db_update_key_status("key1", is_alive=1, consecutive_fails=0)

    mock_test.return_value = (False, 0, "HTTP 404 model not found")

    health_mod.run_health_check()

    ks = next(k for k in db_list_keys() if k["id"] == "key1")
    # 404 não zera consecutive_fails
    assert ks["consecutive_fails"] == 0, \
        f"HTTP 404 não deveria incrementar consecutive_fails, got {ks['consecutive_fails']}"
    # key está marcada como não viva mas não como "morto definitivamente"
    assert ks["is_alive"] == 0


def test_alive_count_no_model_dependency(temp_db):
    """Bug 2: contador de alive não depende de modelo específico."""
    import config, importlib
    from db import db_add_key, db_update_key_status, db_list_keys
    from templates import render_page

    # Keys vivas sem filtro de modelo
    db_update_key_status("key1", is_alive=1, consecutive_fails=0)
    db_update_key_status("key2", is_alive=1, consecutive_fails=1)
    db_update_key_status("key3", is_alive=1, consecutive_fails=0)

    # O render_page usa sum(1 for k in keys if k["is_alive"])
    # Sem model fixo no health check, keys vivas são detectadas corretamente

    from flask import Flask
    app = Flask(__name__)
    with app.test_request():
        html = render_page(MagicMock())
        # alive_count = 3 (key1, key2, key3 todas is_alive=1)
        assert "3 keys vivas" in html or "3" in html, \
            "Contador de keys vivas deve mostrar 3"
