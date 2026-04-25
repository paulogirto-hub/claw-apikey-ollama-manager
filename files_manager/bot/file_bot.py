#!/usr/bin/env python3
"""
Haasgrow Files Bot - Armazenamento no Telegram
Files are stored on Telegram servers, bot only keeps metadata and streams on demand
"""

import os, json, uuid, sqlite3, logging, io
from datetime import datetime
from flask import Flask, request, jsonify, send_file, abort, Response

# ============== CONFIG ==============
BOT_TOKEN = os.environ.get("BOT_TOKEN", "SEU_BOT_TOKEN_AQUI")
BASE_URL = os.environ.get("BASE_URL", "https://seu-dominio.com")
DB_FILE = os.environ.get("DB_FILE", "/root/files.db")
STORAGE_DIR = "/root/telegram_files"  # Temporary cache only
ALLOWED_USER = os.environ.get("ALLOWED_USER", "SEU_TELEGRAM_USER_ID")  # Paulo only
# ====================================

app = Flask(__name__)
os.makedirs(STORAGE_DIR, exist_ok=True)

# ============== DATABASE ==============
def init_db():
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("""
        CREATE TABLE IF NOT EXISTS files (
            id TEXT PRIMARY KEY,
            filename TEXT NOT NULL,
            folder TEXT DEFAULT '/',
            parent_folder TEXT,
            size INTEGER,
            mime_type TEXT,
            uploaded_at TEXT,
            file_id TEXT,
            token TEXT UNIQUE,
            user_id TEXT
        )
    """)
    c.execute("""
        CREATE TABLE IF NOT EXISTS folders (
            id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            parent_id TEXT,
            created_at TEXT,
            user_id TEXT
        )
    """)
    # Add parent_folder column if not exists
    try:
        c.execute("ALTER TABLE files ADD COLUMN parent_folder TEXT")
    except:
        pass
    conn.commit()
    conn.close()

# Folder helpers
def db_create_folder(name, parent_id=None):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    folder_id = str(uuid.uuid4())
    c.execute("INSERT INTO folders (id, name, parent_id, created_at, user_id) VALUES (?, ?, ?, ?, ?)",
              (folder_id, name, parent_id, datetime.now().isoformat(), ALLOWED_USER))
    conn.commit()
    conn.close()
    return folder_id

def db_list_folders(parent_id=None):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("SELECT id, name, parent_id, created_at, user_id FROM folders WHERE parent_id IS ? ORDER BY name", (parent_id,))
    rows = c.fetchall()
    conn.close()
    return rows

def db_get_folder(folder_id):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("SELECT id, name, parent_id, created_at, user_id FROM folders WHERE id=?", (folder_id,))
    row = c.fetchone()
    conn.close()
    return row

def db_delete_folder(folder_id):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("DELETE FROM folders WHERE id=?", (folder_id,))
    conn.commit()
    conn.close()

def db_add_file(file_id, filename, folder, parent_folder, size, mime_type, token, user_id):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("""
        INSERT OR REPLACE INTO files (id, filename, folder, parent_folder, size, mime_type, uploaded_at, file_id, token, user_id)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (str(uuid.uuid4()), filename, folder, parent_folder, size, mime_type, datetime.now().isoformat(), file_id, token, user_id))
    conn.commit()
    conn.close()

def db_list_files(folder=None, parent_folder=None, user_id=None):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    if parent_folder is not None:
        c.execute("SELECT * FROM files WHERE parent_folder IS ? ORDER BY uploaded_at DESC", (parent_folder,))
    elif folder:
        c.execute("SELECT * FROM files WHERE folder=? ORDER BY uploaded_at DESC", (folder,))
    else:
        c.execute("SELECT * FROM files ORDER BY uploaded_at DESC")
    rows = c.fetchall()
    conn.close()
    return rows

def db_delete_file(token):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("DELETE FROM files WHERE token=?", (token,))
    conn.commit()
    conn.close()

def db_get_file(token):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("SELECT * FROM files WHERE token=?", (token,))
    row = c.fetchone()
    conn.close()
    return row

# ============== HELPERS ==============
def generate_token():
    return uuid.uuid4().hex[:12]

def format_size(bytes_size):
    for unit in ['B', 'KB', 'MB', 'GB']:
        if bytes_size < 1024:
            return f"{bytes_size:.1f} {unit}"
        bytes_size /= 1024
    return f"{bytes_size:.1f} TB"

# ============== TELEGRAM API ==============
def send_telegram(method, data=None, files=None):
    import requests
    import json
    
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/{method}"
    
    try:
        payload = dict(data) if data else {}
        
        if files:
            # Multipart files
            file_data = {}
            for key, value in files.items():
                if isinstance(value, tuple) and len(value) == 3:
                    filename, content_data, content_type = value
                    file_data[key] = (filename, content_data, content_type)
                else:
                    filename, content_data = value if isinstance(value, tuple) else (str(value), b"")
                    file_data[key] = (filename, content_data)
            
            resp = requests.post(url, data=payload, files=file_data, timeout=60)
            return resp.json()
        else:
            resp = requests.post(url, data=payload, timeout=30)
            return resp.json()
    except Exception as e:
        logging.error("Telegram API error: " + str(e))
        return None

def get_file_from_telegram(file_id):
    """Download file from Telegram by file_id"""
    result = send_telegram("getFile", {"file_id": file_id})
    if not result or not result.get('ok'):
        return None
    
    file_path = result['result']['file_path']
    file_url = f"https://api.telegram.org/file/bot{BOT_TOKEN}/{file_path}"
    
    import urllib.request
    try:
        req = urllib.request.Request(file_url)
        with urllib.request.urlopen(req, timeout=60) as resp:
            return resp.read(), result['result'].get('file_size', len(resp.read()))
    except Exception as e:
        logging.error(f"Download from Telegram error: {e}")
        return None

# ============== MESSAGE HANDLER ==============
def handle_message(chat_id, user_id, text, file_data=None):
    # /start
    if text == '/start':
        send_telegram("sendMessage", {
            "chat_id": chat_id,
            "text": "📁 *Haasgrow Files*\n\nSeu gerenciador de arquivos pessoal.\n\n*Comandos:*\n`/list` - Ver arquivos\n`/upload` - Enviar arquivo\n`/delete [token]` - Deletar\n`/share [token]` - Link de download\n`/search [termo]` - Buscar",
            "parse_mode": "Markdown"
        })
        return
    
    # /list
    if text == '/list' or text == '/list@haasgrowfiles_bot':
        files = db_list_files()
        if not files:
            send_telegram("sendMessage", {"chat_id": chat_id, "text": "📂 Nenhum arquivo ainda."})
            return
        
        msg_text = "📂 *Seus arquivos:*\n\n"
        for f in files[:20]:
            size = format_size(f[3] or 0)
            msg_text += f"📎 `{f[7]}` - {f[1]} ({size})\n"
        
        if len(files) > 20:
            msg_text += f"\n_...e mais {len(files)-20} arquivos_"
        
        send_telegram("sendMessage", {"chat_id": chat_id, "text": msg_text, "parse_mode": "Markdown"})
        return
    
    # /delete
    if text.startswith('/delete '):
        token = text[8:].strip().split()[0]
        file_row = db_get_file(token)
        if not file_row:
            send_telegram("sendMessage", {"chat_id": chat_id, "text": "❌ Arquivo não encontrado."})
            return
        
        db_delete_file(token)
        send_telegram("sendMessage", {"chat_id": chat_id, "text": "🗑️ Arquivo deletado!"})
        return
    
    # /share
    if text.startswith('/share ') or text.startswith('/share@haasgrowfiles_bot '):
        token = text.split()[1] if ' ' in text else text[7:].strip().split()[0]
        if token.startswith('@'):
            token = text.split()[1] if ' ' in text else ''
        else:
            token = text[7:].strip().split()[0]
        
        file_row = db_get_file(token)
        if not file_row:
            send_telegram("Message", {"chat_id": chat_id, "text": "❌ Arquivo não encontrado."})
            return
        
        download_url = f"{BASE_URL}/f/{token}"
        send_telegram("sendMessage", {
            "chat_id": chat_id,
            "text": f"🔗 *Download:*\n{download_url}"
        })
        return
    
    # /search
    if text.startswith('/search ') or text.startswith('/search@haasgrowfiles_bot '):
        term = text.split(None, 1)[1] if ' ' in text else ''
        if not term:
            send_telegram("sendMessage", {"chat_id": chat_id, "text": "Uso: /search [termo]"})
            return
        
        files = db_list_files()
        matches = [f for f in files if term.lower() in f[1].lower()]
        
        if not matches:
            send_telegram("sendMessage", {"chat_id": chat_id, "text": "🔍 Nenhum resultado."})
            return
        
        msg_text = f"🔍 *Resultados ({len(matches)}):*\n\n"
        for f in matches[:10]:
            msg_text += f"📎 `{f[7]}` - {f[1]}\n"
        
        send_telegram("sendMessage", {"chat_id": chat_id, "text": msg_text, "parse_mode": "Markdown"})
        return
    
    # Handle document/video/photo - UPLOAD TO TELEGRAM
    if file_data:
        doc = file_data
        file_id = doc.get('file_id')
        filename = doc.get('filename', 'file')
        size = doc.get('size', 0)
        mime_type = doc.get('mime_type', 'application/octet-stream')
        
        if not file_id:
            send_telegram("sendMessage", {"chat_id": chat_id, "text": "❌ Erro ao processar arquivo."})
            return
        
        token = generate_token()
        folder = '/'
        
        # Save ONLY metadata, file stays on Telegram
        db_add_file(file_id, filename, folder, size, mime_type, token, user_id)
        
        download_url = f"{BASE_URL}/f/{token}"
        send_telegram("sendMessage", {
            "chat_id": chat_id,
            "text": f"✅ *Arquivo salvo no Telegram!*\n\n📎 {filename}\n💾 {format_size(size)}\n\n🔗 {download_url}",
            "parse_mode": "Markdown"
        })
        return
    
    # Unknown
    send_telegram("sendMessage", {
        "chat_id": chat_id,
        "text": "🤔 Não entendi. Use /start pra ver os comandos."
    })

# ============== TELEGRAM WEBHOOK ==============
@app.route("/webhook", methods=['POST'])
def telegram_webhook():
    update = request.get_json()
    
    if 'message' not in update:
        return "ok"
    
    msg = update['message']
    chat_id = str(msg['chat']['id'])
    user_id = str(msg['from']['id'])
    
    # Only allow Paulo
    if user_id != ALLOWED_USER:
        return "ok"
    
    text = msg.get('text', '')
    
    # Handle document
    if 'document' in msg:
        doc = msg['document']
        file_data = {
            'file_id': doc.get('file_id'),
            'filename': doc.get('file_name', 'document'),
            'size': doc.get('file_size', 0),
            'mime_type': doc.get('mime_type', 'application/octet-stream')
        }
        handle_message(chat_id, user_id, text, file_data)
        return "ok"
    
    # Handle photo
    if 'photo' in msg:
        photo = msg['photo'][-1]  # Largest photo
        ext = 'jpg'
        if photo.get('mime_type'):
            ext = photo['mime_type'].split('/')[-1]
        file_data = {
            'file_id': photo.get('file_id'),
            'filename': f"photo_{photo.get('file_id', 'unknown')[:8]}.{ext}",
            'size': photo.get('file_size', 0),
            'mime_type': photo.get('mime_type', 'image/jpeg')
        }
        handle_message(chat_id, user_id, text, file_data)
        return "ok"
    
    # Handle video
    if 'video' in msg:
        vid = msg['video']
        file_data = {
            'file_id': vid.get('file_id'),
            'filename': vid.get('file_name', 'video.mp4'),
            'size': vid.get('file_size', 0),
            'mime_type': vid.get('mime_type', 'video/mp4')
        }
        handle_message(chat_id, user_id, text, file_data)
        return "ok"
    
    # Text only
    handle_message(chat_id, user_id, text, None)
    return "ok"

# ============== FILE DOWNLOAD (STREAM FROM TELEGRAM) ==============
@app.route("/f/<token>")
def serve_file(token):
    """Download file by token - streams from Telegram"""
    file_row = db_get_file(token)
    if not file_row:
        abort(404)
    
    file_id = file_row[6]
    filename = file_row[1]
    mime_type = file_row[4] or 'application/octet-stream'
    
    if not file_id:
        abort(404)
    
    # Stream from Telegram
    result = get_file_from_telegram(file_id)
    if not result:
        abort(502)
    
    data, size = result
    
    response = Response(data, status=200)
    response.headers['Content-Type'] = mime_type
    response.headers['Content-Length'] = size or len(data)
    response.headers['Content-Disposition'] = f'attachment; filename="{filename}"'
    response.headers['Access-Control-Allow-Origin'] = '*'
    return response

# ============== FOLDER API ==============
@app.route("/files/api/folders", methods=["GET", "POST"])
def api_folders():
    if request.method == "POST":
        data = request.json or {}
        name = data.get("name", "").strip()
        parent = data.get("parent")  # folder id or None, "/" for root
        if parent == "/":
            parent = None
        if not name:
            return jsonify({"error": "Nome obrigatorio"}), 400
        
        # Validate parent exists if provided
        if parent:
            parent_row = db_get_folder(parent)
            if not parent_row:
                return jsonify({"error": "Pasta pai nao encontrada"}), 404
        
        folder_id = db_create_folder(name, parent)
        return jsonify({"success": True, "id": folder_id, "name": name})
    else:
        # GET - list folders (optionally by parent)
        parent = request.args.get("parent")  # None for root, "/" for root too
        if parent == "/" or parent == "":
            parent = None
        folders = db_list_folders(parent)
        return jsonify([{"id": f[0], "name": f[1], "parent_id": f[2]} for f in folders])

@app.route("/files/api/folders/<folder_id>", methods=["GET", "DELETE"])
def api_folder_detail(folder_id):
    if request.method == "DELETE":
        # Check if folder is empty
        files = db_list_files(parent_folder=folder_id)
        subfolders = db_list_folders(folder_id)
        if files or subfolders:
            return jsonify({"error": "Pasta nao vazia"}), 400
        db_delete_folder(folder_id)
        return jsonify({"success": True})
    else:
        folder = db_get_folder(folder_id)
        if not folder:
            return jsonify({"error": "Pasta nao encontrada"}), 404
        return jsonify({"id": folder[0], "name": folder[1], "parent_id": folder[2]})

@app.route("/files/api/files/<token>/move", methods=["POST"])
def api_move_file(token):
    data = request.json or {}
    new_folder = data.get("folder")  # folder id or None for root
    new_parent = data.get("parent_folder")  # None = root
    
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("UPDATE files SET folder=?, parent_folder=? WHERE token=?", (new_folder or '/', new_parent, token))
    conn.commit()
    affected = c.rowcount
    conn.close()
    
    if affected == 0:
        return jsonify({"error": "Arquivo nao encontrado"}), 404
    return jsonify({"success": True})

@app.route("/files/api/files/<token>/rename", methods=["POST"])
def api_rename_file(token):
    data = request.json or {}
    new_name = data.get("filename", "").strip()
    if not new_name:
        return jsonify({"error": "Nome obrigatorio"}), 400
    
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("UPDATE files SET filename=? WHERE token=?", (new_name, token))
    conn.commit()
    affected = c.rowcount
    conn.close()
    
    if affected == 0:
        return jsonify({"error": "Arquivo nao encontrado"}), 404
    return jsonify({"success": True})

# ============== WEB API ==============
@app.route("/files/api/list")
def api_list():
    files = db_list_files()
    return jsonify([{
        "token": f[7],
        "filename": f[1],
        "folder": f[2],
        "size": f[3],
        "size_formatted": format_size(f[3] or 0),
        "mime_type": f[4],
        "uploaded_at": f[5]
    } for f in files])

@app.route("/files/api/upload", methods=["POST"])
def api_upload():
    """Upload file via web interface - sends to Telegram"""
    if 'file' not in request.files:
        return jsonify({"error": "No file"}), 400
    
    file = request.files['file']
    if file.filename == '':
        return jsonify({"error": "No filename"}), 400
    
    file_content = file.read()
    filename = file.filename
    size = len(file_content)
    mime_type = file.content_type or 'application/octet-stream'
    
    # Send to Telegram
    files = {'document': (filename, file_content, mime_type)}
    result = send_telegram("sendDocument", {"chat_id": ALLOWED_USER}, files=files)
    
    if not result or not result.get('ok'):
        return jsonify({"error": "Failed to upload to Telegram"}), 500
    
    doc = result['result'].get('document', {})
    file_id = doc.get('file_id')
    
    if not file_id:
        return jsonify({"error": "No file_id from Telegram"}), 500
    
    token = generate_token()
    db_add_file(file_id, filename, '/', None, size, mime_type, token, 'web')
    
    # Notify via Telegram
    download_url = f"{BASE_URL}/f/{token}"
    send_telegram("sendMessage", {
        "chat_id": ALLOWED_USER,
        "text": f"📤 *Upload via Web!*\n\n📎 {filename}\n💾 {format_size(size)}\n\n🔗 {download_url}",
        "parse_mode": "Markdown"
    })
    
    return jsonify({
        "success": True,
        "token": token,
        "url": download_url
    })

@app.route("/files")
def files_page():
    with open("/root/files_ui.html", "r") as f:
        return f.read()

# ============== MAIN ==============
if __name__ == "__main__":
    init_db()
    print("✅ Haasgrow Files Bot started! (Telegram storage mode)")
    app.run(host="0.0.0.0", port=20131, debug=False)
