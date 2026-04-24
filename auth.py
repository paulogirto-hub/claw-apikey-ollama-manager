import secrets, hashlib, time
from config import SESSION_COOKIE, SESSION_TTL, PANEL_PASSWORD

SESSIONS = {}  # token -> {username, created_at}

def generate_session_token():
    return secrets.token_hex(32)

def validate_session(req):
    token = req.cookies.get(SESSION_COOKIE)
    if not token or token not in SESSIONS:
        return False
    sess = SESSIONS[token]
    if time.time() - sess["created_at"] > SESSION_TTL:
        del SESSIONS[token]
        return False
    return True

def login_required(f):
    from functools import wraps
    @wraps(f)
    def decorated(*args, **kwargs):
        if not validate_session(request):
            return render_login_page(), 401
        return f(*args, **kwargs)
    return decorated

def render_login_page():
    from flask import make_response
    html = """<!doctype html>
<html lang=en>
<head>
<meta charset=utf-8>
<meta name=viewport content="width=device-width, initial-scale=1">
<title>🦜 Login · Claw Key Manager</title>
<style>
  * { box-sizing: border-box; margin: 0; padding: 0; }
  body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Arial, sans-serif;
         background: #0a0e14; color: #c9d1d9; min-height: 100vh;
         display: flex; align-items: center; justify-content: center; }
  .login-card { background: #161b22; border: 1px solid #30363d; border-radius: 16px;
                padding: 40px 36px; width: 100%; max-width: 360px; text-align: center; }
  .login-logo { font-size: 48px; margin-bottom: 8px; }
  .login-title { font-size: 20px; color: #58a6ff; font-weight: 700; margin-bottom: 4px; }
  .login-sub { font-size: 13px; color: #484f58; margin-bottom: 32px; }
  .input-group { position: relative; margin-bottom: 16px; text-align: left; }
  .input-group label { display: block; font-size: 12px; color: #6e7681; margin-bottom: 6px;
                       text-transform: uppercase; letter-spacing: 1px; }
  .input-icon { position: relative; }
  .input-icon input { width: 100%; background: #0d1117; color: #c9d1d9; border: 1px solid #30363d;
                     padding: 10px 12px 10px 38px; border-radius: 8px; font-size: 14px;
                     outline: none; transition: border-color 0.15s; }
  .input-icon input:focus { border-color: #58a6ff; }
  .input-icon .icon { position: absolute; left: 12px; top: 50%; transform: translateY(-50%);
                      font-size: 14px; color: #484f58; }
  .login-btn { width: 100%; background: #238636; color: #fff; border: none; padding: 12px;
               border-radius: 8px; font-size: 15px; font-weight: 600; cursor: pointer;
               transition: background 0.15s; margin-top: 8px; }
  .login-btn:hover { background: #2ea043; }
  .login-error { background: #f8514920; border: 1px solid #f85149; color: #f85149;
                 border-radius: 8px; padding: 10px 14px; font-size: 13px; margin-bottom: 16px;
                 display: none; }
  .login-error.show { display: block; }
  .footer { margin-top: 24px; font-size: 11px; color: #30363d; }
</style>
</head>
<body>
<div class="login-card">
  <div class="login-logo">🦜</div>
  <div class="login-title">Claw Key Manager</div>
  <div class="login-sub">Painel de controle</div>
  <div id="loginError" class="login-error"></div>
  <form id="loginForm" onsubmit="return doLogin()">
    <div class="input-group">
      <label>Usuário</label>
      <div class="input-icon">
        <span class="icon">👤</span>
        <input type="text" id="username" placeholder="admin" autocomplete="username" />
      </div>
    </div>
    <div class="input-group">
      <label>Senha</label>
      <div class="input-icon">
        <span class="icon">🔒</span>
        <input type="password" id="password" placeholder="••••••••" autocomplete="current-password" />
      </div>
    </div>
    <button type="submit" class="login-btn" id="loginBtn">Entrar</button>
  </form>
  <div class="footer">claw.key.manager</div>
</div>
<script>
function doLogin() {
  var btn = document.getElementById('loginBtn');
  var err = document.getElementById('loginError');
  var user = document.getElementById('username').value.trim();
  var pass = document.getElementById('password').value;
  err.classList.remove('show');
  btn.disabled = true;
  btn.textContent = '⏳...';
  fetch('/api/login', {method:'POST', body: new URLSearchParams({username: user, password: pass}),
        headers:{'Content-Type':'application/x-www-form-urlencoded'}})
  .then(function(r){return r.json();})
  .then(function(d){
    btn.disabled = false;
    btn.textContent = 'Entrar';
    if (d.ok) { location.reload(); }
    else { err.textContent = d.error || 'Credenciais inválidas'; err.classList.add('show'); }
  })
  .catch(function(){
    btn.disabled = false;
    btn.textContent = 'Entrar';
    err.textContent = 'Erro de conexão';
    err.classList.add('show');
  });
  return false;
}
</script>
</body>
</html>"""
    resp = make_response(html)
    return resp

def do_login(username, password):
    from flask import make_response
    if username == "admin" and password == PANEL_PASSWORD:
        token = generate_session_token()
        SESSIONS[token] = {"username": username, "created_at": time.time()}
        resp = make_response(json.dumps({"ok": True}))
        resp.set_cookie(SESSION_COOKIE, token, max_age=SESSION_TTL, httponly=True, samesite='Lax')
        return resp
    from flask import jsonify
    return jsonify({"ok": False, "error": "Credenciais inválidas"}), 401
