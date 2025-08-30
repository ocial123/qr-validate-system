
import os
import io
import csv
import sqlite3
import secrets
import hashlib
from datetime import datetime
from urllib.parse import urljoin

from flask import (
    Flask, request, render_template, redirect, url_for,
    make_response, send_file, abort, session, flash
)
import qrcode

# ------------------ Config ------------------
def get_env(name, default=None, required=False):
    val = os.environ.get(name, default)
    if required and not val:
        raise RuntimeError(f"Missing required env var: {name}")
    return val

ADMIN_PASSWORD = get_env("ADMIN_PASSWORD", "changeme")
VALIDATOR_KEY  = get_env("VALIDATOR_KEY", "set-a-long-random-validator-key")
BASE_URL       = get_env("BASE_URL", "")  # If deploying behind a custom domain, set this (including https://...)

DB_PATH        = os.environ.get("DB_PATH", "tokens.db")
SECRET_KEY     = os.environ.get("FLASK_SECRET_KEY", os.urandom(24))

app = Flask(__name__)
app.secret_key = SECRET_KEY

# ------------------ DB helpers ------------------
def db_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    with db_conn() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS tokens (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                token TEXT UNIQUE NOT NULL,
                label TEXT,
                created_at TEXT NOT NULL,
                used_at TEXT
            )
        """)
        conn.commit()

init_db()

def token_url(token: str) -> str:
    if BASE_URL:
        # ensure ends with slash
        base = BASE_URL if BASE_URL.endswith("/") else BASE_URL + "/"
        return urljoin(base, f"t/{token}")
    return url_for("view_token", token=token, _external=True)

def is_validator(request) -> bool:
    cookie = request.cookies.get("validator_key")
    return cookie is not None and secrets.compare_digest(cookie, VALIDATOR_KEY)

# ------------------ Routes ------------------
@app.get("/")
def index():
    return render_template("index.html")

@app.get("/health")
def health():
    return {"ok": True}

# One-time set on your device only
@app.get("/set-validator")
def set_validator():
    key = request.args.get("key", "")
    if not key:
        abort(400, "key required as query param")
    if not secrets.compare_digest(key, VALIDATOR_KEY):
        abort(403, "invalid key")
    resp = make_response(redirect(url_for("index")))
    # HttpOnly prevents JS access; Secure recommended when running over HTTPS
    resp.set_cookie("validator_key", VALIDATOR_KEY, httponly=True, samesite="Lax", max_age=60*60*24*365*5)
    return resp

@app.get("/logout-validator")
def logout_validator():
    resp = make_response(redirect(url_for("index")))
    resp.delete_cookie("validator_key")
    return resp

@app.route("/t/<token>")
def view_token(token):
    # Lookup token
    with db_conn() as conn:
        row = conn.execute("SELECT * FROM tokens WHERE token = ?", (token,)).fetchone()

    if row is None:
        # Don't reveal existence to non-validator; to validator, show explicitly invalid
        if is_validator(request):
            return render_template("token_validator.html", status="not_found", token=token)
        else:
            # Silent for public
            return render_template("token_public.html")
    
    # If validator device: consume token on first valid scan
    if is_validator(request):
        if row["used_at"]:
            return render_template("token_validator.html", status="already_used", token=token, used_at=row["used_at"], label=row["label"])
        # mark used
        used_at = datetime.utcnow().isoformat() + "Z"
        with db_conn() as conn:
            conn.execute("UPDATE tokens SET used_at = ? WHERE token = ?", (used_at, token))
            conn.commit()
        return render_template("token_validator.html", status="validated", token=token, used_at=used_at, label=row["label"])
    
    # For non-validator devices: show a neutral page and DO NOT change state
    return render_template("token_public.html")

# ------------------ Admin (simple) ------------------
def require_admin():
    if session.get("admin_ok"):
        return
    pw = request.args.get("password") or request.form.get("password")
    if pw and secrets.compare_digest(pw, ADMIN_PASSWORD):
        session["admin_ok"] = True
        return
    # Render login form
    return render_template("admin.html", login=True)

@app.route("/admin", methods=["GET", "POST"])
def admin():
    gate = require_admin()
    if gate:
        return gate

    # Stats
    with db_conn() as conn:
        total = conn.execute("SELECT COUNT(*) FROM tokens").fetchone()[0]
        used  = conn.execute("SELECT COUNT(*) FROM tokens WHERE used_at IS NOT NULL").fetchone()[0]
    return render_template("admin.html", login=False, total=total, used=used)

@app.post("/admin/generate")
def admin_generate():
    gate = require_admin()
    if gate:
        return gate

    try:
        count = int(request.form.get("count", "1"))
        prefix = (request.form.get("prefix") or "").strip()
        label  = (request.form.get("label") or "").strip()
        count = max(1, min(count, 1000))  # safety cap
    except Exception:
        count = 1
        prefix = ""
        label = ""

    new_rows = []
    now = datetime.utcnow().isoformat() + "Z"

    with db_conn() as conn:
        for _ in range(count):
            # generate 12-char secure token (URL-safe)
            token = prefix + secrets.token_urlsafe(9)
            try:
                conn.execute(
                    "INSERT INTO tokens (token, label, created_at) VALUES (?, ?, ?)",
                    (token, label, now)
                )
                new_rows.append(token)
            except sqlite3.IntegrityError:
                # rare collision; retry
                token = prefix + secrets.token_urlsafe(9)
                conn.execute(
                    "INSERT INTO tokens (token, label, created_at) VALUES (?, ?, ?)",
                    (token, label, now)
                )
                new_rows.append(token)
        conn.commit()

    # Show results + links
    token_links = [(t, token_url(t)) for t in new_rows]
    return render_template("admin.html", login=False, just_created=token_links)

@app.get("/admin/export")
def admin_export():
    gate = require_admin()
    if gate:
        return gate

    # Export CSV of tokens
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["token", "url", "label", "created_at", "used_at"])
    with db_conn() as conn:
        rows = conn.execute("SELECT token, label, created_at, used_at FROM tokens ORDER BY id DESC").fetchall()
        for r in rows:
            writer.writerow([r["token"], token_url(r["token"]), r["label"] or "", r["created_at"], r["used_at"] or ""])
    mem = io.BytesIO(output.getvalue().encode("utf-8"))
    return send_file(mem, mimetype="text/csv", as_attachment=True, download_name="tokens.csv")

@app.get("/admin/qrs")
def admin_qrs():
    gate = require_admin()
    if gate:
        return gate

    # Render a simple printable grid of QR codes
    with db_conn() as conn:
        rows = conn.execute("SELECT token FROM tokens ORDER BY id DESC LIMIT 200").fetchall()

    # produce dict of token->data_url
    qr_data = []
    for r in rows:
        url = token_url(r["token"])
        img = qrcode.make(url)
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        b64 = buf.getvalue()
        import base64
        data_url = "data:image/png;base64," + base64.b64encode(b64).decode("ascii")
        qr_data.append({"token": r["token"], "url": url, "data_url": data_url})

    return render_template("admin.html", login=False, qr_grid=qr_data)

# --------------- Error handlers (minimal) ---------------
@app.errorhandler(400)
@app.errorhandler(403)
@app.errorhandler(404)
def err(e):
    return render_template("index.html", error=str(e)), getattr(e, "code", 500)

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", "5000")), debug=True)
