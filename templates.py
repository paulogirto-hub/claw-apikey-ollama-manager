from auth import validate_session
from db import db_list_keys, db_get_active_key, db_get_config, db_get_fallback_log, db_get_key_name, db_get_last_fallback
from config import FAIL_THRESHOLD

_MODAL_HTML = """
<div id="key-modal" class="modal-overlay" onclick="if(event.target===this)closeKeyModal()">
  <div class="modal-content">
    <h3 id="modal-title">Key Completa</h3>
    <pre id="modal-key"></pre>
    <button class="modal-close" onclick="closeKeyModal()">Fechar</button>
  </div>
</div>
"""


def render_page(req):
    """Renderiza a página principal do painel."""
    from flask import make_response
    from datetime import datetime, timezone
    from config import MODEL, PORT, SESSION_COOKIE

    active_key_id, active_key = db_get_active_key()
    fb_count = int(db_get_config("fallback_count") or "0")
    last_check = db_get_config("last_full_check") or "—"
    last_fb = db_get_last_fallback()
    last_fb_str = last_fb["triggered_at"][:19] if last_fb else "nunca"
    current_masked = active_key[:10] + "..." + active_key[-4:] if active_key else "nenhuma"

    keys = db_list_keys()

    def sort_key(ks):
        active = 1 if ks["is_active"] else 0
        is_alive = ks["is_alive"]
        fails = ks["consecutive_fails"]
        if is_alive and fails == 0:
            indicator_order = 0
        elif is_alive and fails > 0:
            indicator_order = 1
        elif not is_alive and fails >= FAIL_THRESHOLD:
            indicator_order = 3
        else:
            indicator_order = 2
        return (-active, indicator_order, ks["id"])

    sorted_keys = sorted(keys, key=sort_key)
    keys_html = ""

    for ks in sorted_keys:
        key_id = ks["id"]
        key = ks["key"]
        name = ks.get("name")
        fails = ks["consecutive_fails"]
        is_alive = ks["is_alive"]
        last_error = ks.get("last_error")
        last_tested = ks.get("last_tested")

        if is_alive and fails == 0:
            indicator, indicator_color = "🟢", "#3fb950"
        elif is_alive and fails > 0:
            indicator, indicator_color = "🟡", "#f0883e"
        elif not is_alive and fails >= FAIL_THRESHOLD:
            indicator, indicator_color = "🔴", "#f85149"
        else:
            indicator, indicator_color = "⚪", "#484f58"

        last_tested_str = last_tested or "—"
        if last_tested_str and last_tested_str != "—":
            try:
                dt = datetime.fromisoformat(last_tested_str.replace("Z", "+00:00"))
                last_tested_str = dt.strftime("%d/%m %H:%M")
            except:
                pass

        display_name = name if name else key_id
        fails_badge = f'<span class="fail-badge">{fails} fails</span>' if fails > 0 else ''
        latency_ms = ks.get("latency_ms", 0)
        slow_badge = '<span class="slow-badge" title="Latência alta">🐌 Lenta</span>' if latency_ms and latency_ms > 5000 else ''
        masked = key[:10] + "..." + key[-4:] if len(key) > 14 else "???"

        if ks["is_active"]:
            actions = f'<span class="key-active">✓ ATIVA {indicator}</span>'
        else:
            actions = f"""<button class="btn-activate" onclick="activate('{key_id}')">Ativar</button>
<button class="btn-copy" onclick="copyKey('{key}', '{key_id}')" title="Copiar">📋</button>
<button class="btn-test-single" onclick="testSingle('{key_id}')" title="Testar">🧪</button>
<button class="btn-rename" onclick="renameKey('{key_id}')" title="Renomear">✏️</button>
<button class="btn-del" onclick="delKey('{key_id}')">🗑</button>"""

        keys_html += f"""<div class="key-item" data-key-id="{key_id}">
  <div style="font-size:20px;color:{indicator_color};min-width:28px;text-align:center">{indicator}</div>
  <div class="key-info">
    <div class="key-name-row">
      <span class="key-name">{display_name}</span>
      {fails_badge}
      {slow_badge}
    </div>
    <div class="key-masked" onclick="showFullKey('{key_id}', '{key}', '{display_name}')" title="Clique pra ver completa">
      {masked}
    </div>
    <div class="key-meta">
      <span class="key-id">{key_id}</span> ·
      <span>testado: {last_tested_str}</span>
      {f'<span class="last-error"> · ❗ {last_error[:40]}</span>' if last_error else ''}
    </div>
  </div>
  <div class="key-actions">{actions}</div>
</div>"""

    if not keys:
        keys_html = '<div class="empty">Nenhuma key cadastrada ainda.</div>'

    fb_log = db_get_fallback_log(5)
    fb_log_html = ""
    if fb_log:
        for fb in fb_log:
            from_nm = db_get_key_name(fb["from_key_id"]) or fb["from_key_id"]
            to_nm = db_get_key_name(fb["to_key_id"]) or fb["to_key_id"]
            ts = fb["triggered_at"][:19].replace("T", " ")
            fb_log_html += f'<div class="fb-log-item"><span class="fb-time">{ts}</span><span>{from_nm}</span><span style="color:#6e7681">→</span><span>{to_nm}</span><span class="fb-reason">{fb["reason"]}</span></div>'
    else:
        fb_log_html = '<div class="empty" style="padding:12px">Nenhum fallback registrado.</div>'

    alive_count = sum(1 for k in keys if k["is_alive"])
    alive_class = "status-good" if alive_count >= 3 else "status-warn"

    html = f"""<!DOCTYPE html>
<html>
<head>
<title>🦜 Claw Key Manager</title>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<style>
  * {{ box-sizing: border-box; margin: 0; padding: 0; }}
  body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Arial, sans-serif;
         background: #0a0e14; color: #c9d1d9; min-height: 100vh; padding: 20px; }}
  .container {{ max-width: 760px; margin: 0 auto; }}
  h1 {{ color: #58a6ff; font-size: 22px; margin-bottom: 20px; display: flex;
        align-items: center; gap: 8px; }}
  .card {{ background: #161b22; border: 1px solid #30363d; border-radius: 12px;
           padding: 20px; margin-bottom: 16px; }}
  .card-title {{ color: #6e7681; font-size: 11px; text-transform: uppercase;
                 letter-spacing: 1.5px; margin-bottom: 14px; font-weight: 600; }}
  .gw-row {{ display: flex; align-items: center; justify-content: space-between; }}
  .gw-left {{ display: flex; align-items: center; gap: 8px; }}
  .dot {{ width: 9px; height: 9px; border-radius: 50%; flex-shrink: 0; }}
  .dot.online {{ background: #3fb950; box-shadow: 0 0 8px #3fb950; }}
  .dot.spinning {{ background: #f0883e; animation: pulse 1s infinite; }}
  @keyframes pulse {{ 0%{{opacity:1}} 50%{{opacity:0.3}} 100%{{opacity:1}} }}
  .input-row {{ display: flex; gap: 8px; align-items: center; }}
  input {{ flex: 1; background: #0d1117; color: #c9d1d9; border: 1px solid #30363d;
           padding: 10px 12px; border-radius: 8px; font-size: 14px; outline: none; }}
  input:focus {{ border-color: #58a6ff; }}
  input::placeholder {{ color: #484f58; }}
  button {{ background: #238636; color: #fff; border: none; padding: 10px 18px;
           border-radius: 8px; font-size: 13px; cursor: pointer; font-weight: 600;
           transition: all 0.15s; }}
  button:hover {{ background: #2ea043; }}
  button:active {{ transform: scale(0.97); }}
  button:disabled {{ opacity: 0.45; cursor: not-allowed; transform: none; }}
  .btn-gw {{ background: #21262d; color: #8b949e; }}
  .btn-gw:hover {{ background: #30363d; color: #c9d1d9; }}
  .btn-gw.spinning {{ color: #f0883e; }}
  .btn-del {{ background: transparent; color: #484f58; padding: 6px 10px;
              font-size: 12px; border: 1px solid #30363d; }}
  .btn-del:hover {{ background: #f8514920; color: #f85149; border-color: #f85149; }}
  .btn-test {{ background: #1f6feb; font-size: 12px; padding: 8px 14px; }}
  .btn-test:hover {{ background: #388bfd; }}
  .btn-test.testing {{ background: #484f58; }}
  .btn-test-single {{ background: transparent; color: #484f58; padding: 5px 8px;
               font-size: 12px; border: 1px solid #30363d; }}
  .btn-test-single:hover {{ color: #388bfd; border-color: #388bfd; }}
  .btn-rename {{ background: transparent; color: #484f58; padding: 5px 8px;
               font-size: 12px; border: 1px solid #30363d; }}
  .btn-rename:hover {{ color: #f0883e; border-color: #f0883e; }}
  .btn-health {{ background: #6e40c9; font-size: 12px; padding: 8px 14px; }}
  .btn-health:hover {{ background: #8b5cf6; }}
  .btn-fallback {{ background: #a85d00; font-size: 12px; padding: 8px 14px; }}
  .btn-fallback:hover {{ background: #d97706; }}
  .btn-log {{ background: #21262d; color: #8b949e; font-size: 12px; padding: 8px 14px; }}
  .btn-log:hover {{ background: #30363d; color: #c9d1d9; }}
  .btn-export {{ background: #21262d; color: #8b949e; font-size: 12px; padding: 8px 14px; }}
  .btn-export:hover {{ background: #30363d; color: #c9d1d9; }}
  .btn-import {{ background: #21262d; color: #8b949e; font-size: 12px; padding: 8px 14px; }}
  .btn-import:hover {{ background: #30363d; color: #c9d1d9; }}
  .key-item {{ display: flex; align-items: flex-start; padding: 14px 0;
               border-bottom: 1px solid #21262d; gap: 10px; }}
  .key-item:last-child {{ border-bottom: none; }}
  .key-info {{ flex: 1; min-width: 0; }}
  .key-name-row {{ display: flex; align-items: center; gap: 8px; margin-bottom: 4px; }}
  .key-name {{ font-size: 14px; font-weight: 600; color: #c9d1d9; }}
  .fail-badge {{ background: #f8514920; color: #f85149; border: 1px solid #f85149;
                 font-size: 10px; padding: 1px 7px; border-radius: 10px; font-weight: 600; }}
  .slow-badge {{ background: #6e40c920; color: #a371f7; border: 1px solid #a371f7;
                 font-size: 10px; padding: 1px 7px; border-radius: 10px; }}
  .last-error {{ color: #f0883e; font-size: 11px; }}
  .key-masked {{ font-family: monospace; font-size: 12px; color: #8b949e; cursor: pointer; }}
  .key-meta {{ font-size: 11px; color: #484f58; margin-top: 4px; }}
  .key-id {{ color: #6e7681; }}
  .key-active {{ font-size: 11px; color: #3fb950; font-weight: 700;
                 background: #0d1117; padding: 3px 10px; border-radius: 20px;
                 border: 1px solid #238636; white-space: nowrap; }}
  .key-actions {{ display: flex; gap: 6px; align-items: center; flex-wrap: wrap; justify-content: flex-end; }}
  .btn-activate {{ background: #1f6feb; font-size: 12px; padding: 7px 14px; }}
  .btn-activate:hover {{ background: #388bfd; }}
  .btn-copy {{ background: transparent; color: #484f58; padding: 5px 8px;
               font-size: 11px; border: 1px solid #30363d; }}
  .btn-copy:hover {{ color: #c9d1d9; border-color: #8b949e; }}
  .msg-box {{ padding: 10px 14px; border-radius: 8px; margin-top: 10px; font-size: 13px;
               display: none; border: 1px solid; }}
  .msg-box.show {{ display: block; }}
  .msg-box.ok {{ background: #0d1117; color: #3fb950; border-color: #238636; }}
  .msg-box.error {{ background: #0d1117; color: #f85149; border-color: #da3633; }}
  .msg-box.info {{ background: #0d1117; color: #f0883e; border-color: #f0883e; }}
  .stat-row {{ font-size: 13px; color: #6e7681; margin-bottom: 12px; }}
  .stat-row b {{ color: #c9d1d9; }}
  .empty {{ text-align: center; color: #484f58; padding: 30px; font-size: 14px; }}
  .footer {{ text-align: center; font-size: 11px; color: #30363d; margin-top: 20px; }}
  .health-info {{ font-size: 11px; color: #6e7681; margin-top: 8px; }}
  .health-info b {{ color: #c9d1d9; }}
  .btn-row {{ display: flex; gap: 8px; margin-top: 10px; flex-wrap: wrap; }}
  .log-section {{ margin-top: 12px; border-top: 1px solid #21262d; padding-top: 12px; }}
  .log-toggle {{ cursor: pointer; user-select: none; }}
  .log-toggle:hover {{ color: #c9d1d9; }}
  .log-content {{ display: none; margin-top: 10px; }}
  .log-content.open {{ display: block; }}
  .fb-log-item {{ display: flex; gap: 10px; align-items: center; font-size: 12px;
                  padding: 6px 0; border-bottom: 1px solid #21262d; flex-wrap: wrap; }}
  .fb-log-item:last-child {{ border-bottom: none; }}
  .fb-time {{ color: #484f58; font-size: 11px; min-width: 130px; }}
  .fb-reason {{ color: #484f58; font-size: 10px; text-transform: uppercase; margin-left: auto; }}
  .import-area {{ margin-top: 10px; }}
  .toast {{ position: fixed; bottom: 20px; right: 20px; background: #161b22; color: #c9d1d9;
            border: 1px solid #30363d; padding: 12px 18px; border-radius: 10px;
            font-size: 13px; z-index: 999; display: none; box-shadow: 0 4px 12px #0006; }}
  .toast.show {{ display: block; }}
  .toast.success {{ border-color: #238636; color: #3fb950; }}
  .toast.error {{ border-color: #f85149; color: #f85149; }}
  .principal-return-banner {{ background: #238636; color: #fff; border: 1px solid #3fb950;
                              border-radius: 10px; padding: 14px 18px; margin-bottom: 16px;
                              display: none; font-size: 13px; }}
  .principal-return-banner a {{ color: #fff; font-weight: 700; text-decoration: underline;
                                 cursor: pointer; }}
  .modal-overlay {{ display: none; position: fixed; inset: 0; background: #0a0e14cc;
                    align-items: center; justify-content: center; z-index: 1000; }}
  .modal-content {{ background: #161b22; border: 1px solid #30363d; border-radius: 14px;
                     padding: 24px 28px; max-width: 500px; width: 90%; text-align: center; }}
  .modal-content h3 {{ color: #c9d1d9; margin-bottom: 14px; font-size: 16px; }}
  .modal-content pre {{ background: #0d1117; color: #c9d1d9; padding: 14px; border-radius: 8px;
                        font-size: 11px; overflow-x: auto; text-align: left; margin: 10px 0 16px;
                        border: 1px solid #30363d; word-break: break-all; }}
  .modal-close {{ background: #21262d; color: #c9d1d9; padding: 8px 24px; font-size: 13px; }}
  .modal-close:hover {{ background: #30363d; }}
  .hc-selector {{ display: flex; gap: 6px; align-items: center; font-size: 11px; color: #6e7681; }}
  .hc-selector select {{ background: #0d1117; color: #c9d1d9; border: 1px solid #30363d;
                          padding: 4px 8px; border-radius: 6px; font-size: 11px; cursor: pointer; }}
  .status-warn {{ color: #f0883e; }}
  .status-good {{ color: #3fb950; }}
</style>
</head>
<body>
<div class="container">
  <h1>🦜 Claw Key Manager</h1>

  <div class="principal-return-banner" id="principal-return-banner">
    🔄 Principal disponível novamente!&nbsp;
    <a onclick="returnToPrincipal()">↩️ Voltar pra Principal</a>
  </div>

  <div class="card">
    <div class="gw-row">
      <div class="gw-left">
        <div class="dot online"></div>
        <span>Gateway: <b>Online</b></span>
      </div>
      <div class="hc-selector">
        Health Check:
        <select onchange="setHcInterval(this.value)">
          <option value="60">1 min</option>
          <option value="120">2 min</option>
          <option value="300" selected>5 min</option>
          <option value="600">10 min</option>
        </select>
      </div>
    </div>
    <div class="stat-row" style="margin-top:10px">
      <b>{alive_count}</b> keys vivas · Último check: <b>{last_check[:16].replace("T"," ")}</b> ·
      Fallbacks: <b>{fb_count}</b>
    </div>
  </div>

  <div class="card">
    <div class="card-title">🔑 Keys ({len(keys)} cadastradas)</div>
    <div id="keysList">{keys_html}</div>
  </div>

  <div class="card">
    <div class="card-title">📥 Importar Keys</div>
    <textarea id="importData" rows="4" placeholder="[{{"id":"ollama:xxx","key":"sua-key"}}]" style="width:100%;background:#0d1117;color:#c9d1d9;border:1px solid #30363d;padding:10px;border-radius:8px;font-size:12px;font-family:monospace;resize:vertical"></textarea>
    <div id="importMsg" class="msg-box"></div>
    <div class="btn-row" style="margin-top:10px">
      <button onclick="importKeys()">📥 Importar</button>
      <button onclick="exportKeys()">📤 Exportar</button>
    </div>
  </div>

  <div class="card">
    <div class="card-title">⚡ Ações</div>
    <div class="btn-row">
      <button onclick="testAll()" id="testAllBtn">🧪 Testar Todas</button>
      <button onclick="forceFallback()" class="btn-fallback">⚡ Forçar Fallback</button>
      <button onclick="toggleLog()" class="btn-log" id="logToggleBtn">📋 Histórico</button>
      <button onclick="restartGw()" class="btn-gw">🔄 Restart Gateway</button>
    </div>
    <div id="gwMsg" class="msg-box"></div>
    <div class="log-section">
      <div class="log-toggle" onclick="toggleLog()" id="logToggleLabel">📋 Histórico de Fallbacks</div>
      <div class="log-content" id="logContent">{fb_log_html}</div>
    </div>
  </div>

  <div class="footer">claw.key.manager · SQLite source of truth</div>
</div>

<div id="toast" class="toast"></div>

<script>
var _logOpen = false;

function showMsg(el, txt, type) {{
  el.textContent = txt; el.className = 'msg-box show ' + type;
  setTimeout(()=>{{ el.classList.remove('show'); }}, 4000);
}}
function showToast(txt, type) {{
  var t = document.getElementById('toast');
  t.textContent = txt; t.className = 'toast show ' + type;
  setTimeout(()=>{{ t.classList.remove('show'); }}, 2500);
}}

function activate(keyId) {{
  fetch('/api/keys', {{method:'POST',headers:{{'Content-Type':'application/json'}},
    body: JSON.stringify({{action:'activate',key_id:keyId}})}}).then(r=>r.json()).then(d=>{{
      if(d.ok) {{ showToast('✅ Key ativada!', 'success'); setTimeout(()=>location.reload(), 1500); }}
      else {{ showToast('❌ '+d.error, 'error'); }}
  }});
}}

function testAll() {{
  var btn = document.getElementById('testAllBtn');
  btn.disabled = true; btn.classList.add('spinning'); btn.textContent = '⏳ testando...';
  fetch('/api/health_check', {{method:'POST',headers:{{'Content-Type':'application/json'}}}}).then(r=>r.json()).then(d=>{{
    btn.disabled = false; btn.classList.remove('spinning'); btn.textContent = '🧪 Testar Todas';
    var el = document.getElementById('gwMsg');
    if(d.ok) {{
      showMsg(el, d.fallback_triggered ? '⚡ Fallback acionado!' : '✅ Health check OK', 'ok');
      setTimeout(()=>location.reload(), 2000);
    }} else {{
      showMsg(el, '❌ Erro no health check', 'error');
    }}
  }});
}}

function restartGw() {{
  if(!confirm('Reiniciar gateway?')) return;
  fetch('/api/restart', {{method:'POST'}}).then(r=>r.json()).then(d=>{{
    showToast(d.ok ? '♻️ Gateway reiniciando...' : '❌ Erro', d.ok ? 'success' : 'error');
  }});
}}

function forceFallback() {{
  if(!confirm('Forçar fallback para próxima key viva?')) return;
  fetch('/api/fallback', {{method:'POST'}}).then(r=>r.json()).then(d=>{{
    var el = document.getElementById('gwMsg');
    if(d.ok) {{
      showMsg(el, '✅ Fallback para: ' + d.new_key_id, 'ok');
      setTimeout(()=>location.reload(), 2000);
    }} else {{
      showMsg(el, '❌ ' + (d.error||'Nenhuma key viva disponível'), 'error');
    }}
  }});
}}

function toggleLog() {{
  _logOpen = !_logOpen;
  document.getElementById('logContent').classList.toggle('open', _logOpen);
  document.getElementById('logToggleLabel').textContent = _logOpen
    ? '▲ Ocultar Histórico de Fallbacks'
    : '📋 Histórico de Fallbacks';
}}

function exportKeys() {{
  fetch('/api/export').then(r=>r.json()).then(d=>{{
    if(d.keys) {{
      var blob = new Blob([JSON.stringify(d.keys, null, 2)], {{type:'application/json'}});
      var a = document.createElement('a'); a.href = URL.createObjectURL(blob);
      a.download = 'claw_keys_backup.json'; a.click(); URL.revokeObjectURL(url);
    }}
  }}).catch(()=>showToast('❌ Erro ao exportar', 'error'));
}}

function importKeys() {{
  var data = document.getElementById('importData').value.trim();
  if(!data) return;
  var parsed;
  try {{ parsed = JSON.parse(data); }} catch(e) {{
    showMsg(document.getElementById('importMsg'), '❌ JSON inválido', 'error'); return;
  }}
  if(!Array.isArray(parsed)) {{
    showMsg(document.getElementById('importMsg'), '❌ JSON deve ser um array', 'error'); return;
  }}
  fetch('/api/keys', {{method:'POST',headers:{{'Content-Type':'application/json'}},
    body: JSON.stringify({{action:'import',keys:parsed}})}}).then(r=>r.json()).then(d=>{{
    var el = document.getElementById('importMsg');
    if(d.ok) {{ showMsg(el, '✅ ' + d.imported + ' keys importadas', 'ok'); setTimeout(()=>location.reload(), 1200); }}
    else {{ showMsg(el, '❌ ' + (d.error||'Erro'), 'error'); }}
  }});
}}

function setHcInterval(val) {{
  fetch('/api/config', {{method:'POST',headers:{{'Content-Type':'application/json'}},
    body: JSON.stringify({{health_check_interval: parseInt(val)}})}}).then(r=>r.json()).then(d=>{{
      if(d.ok) showToast('✅ Intervalo atualizado!', 'success');
  }});
}}

function checkPrincipalReturn() {{
  fetch('/api/check_principal_return').then(r=>r.json()).then(d=>{{
    if(d.should_suggest_return) {{
      var b = document.getElementById('principal-return-banner');
      if(b) b.style.display = 'block';
    }}
  }});
}}

function returnToPrincipal() {{
  fetch('/api/return_to_principal', {{method:'POST'}}).then(r=>r.json()).then(d=>{{
    if(d.ok) location.reload();
  }});
}}

function showFullKey(keyId, key, name) {{
  document.getElementById('modal-title').textContent = name || keyId;
  document.getElementById('modal-key').textContent = key;
  document.getElementById('key-modal').style.display = 'flex';
}}

function closeKeyModal() {{
  document.getElementById('key-modal').style.display = 'none';
}}

function copyKey(key, keyId) {{
  if(navigator.clipboard) {{
    navigator.clipboard.writeText(key).then(()=>showToast('✅ Key copiada!', 'success'))
      .catch(()=>showToast('❌ Erro ao copiar', 'error'));
  }}
}}

function testSingle(keyId) {{
  fetch('/api/test_key_single/' + keyId).then(r=>r.json()).then(d=>{{
    if(d.ok) showToast('✅ Key viva! (' + d.latency_ms + 'ms)', 'success');
    else showToast('❌ ' + (d.error||'Erro'), 'error');
  }});
}}

function renameKey(keyId) {{
  var newName = prompt('Novo nome para a key:');
  if(!newName) return;
  fetch('/api/keys', {{method:'POST',headers:{{'Content-Type':'application/json'}},
    body: JSON.stringify({{action:'rename',key_id:keyId,name:newName}})}}).then(r=>r.json()).then(d=>{{
    if(d.ok) location.reload(); else showToast('❌ '+d.error, 'error');
  }});
}}

function delKey(keyId) {{
  if(!confirm('Deletar key ' + keyId + '?')) return;
  fetch('/api/keys', {{method:'POST',headers:{{'Content-Type':'application/json'}},
    body: JSON.stringify({{action:'delete',key_id:keyId}})}}).then(r=>r.json()).then(d=>{{
    if(d.ok) location.reload(); else showToast('❌ '+d.error, 'error');
  }});
}}

checkPrincipalReturn();
setTimeout(() => location.reload(), 60000);
</script>
</body>
</html>""" + _MODAL_HTML

    resp = make_response(html)
    return resp
