import os
import uuid
from flask import Flask, render_template, request, redirect, url_for, flash
from werkzeug.middleware.proxy_fix import ProxyFix

app = Flask(__name__)
app.secret_key = os.getenv("FLASK_SECRET_KEY", "default_secret")
app.wsgi_app = ProxyFix(app.wsgi_app)

# ENV variables
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "admin123")
VALIDATOR_KEY = os.getenv("VALIDATOR_KEY", "secret123")
BASE_URL = os.getenv("BASE_URL", "http://localhost:5000")

# Store QR codes (temporary memory)
qr_store = {}

@app.route("/")
def landing():
    return render_template("landing.html")

@app.route("/admin", methods=["GET", "POST"])
def admin():
    if request.method == "POST":
        password = request.form.get("password")
        if password == ADMIN_PASSWORD:
            return redirect(url_for("dashboard"))
        else:
            flash("Invalid admin password!", "danger")
    return render_template("enter_passcode.html")

@app.route("/dashboard")
def dashboard():
    return render_template("dashboard.html", qr_codes=qr_store)

@app.route("/generate_qr")
def generate_qr():
    qr_id = str(uuid.uuid4())
    qr_store[qr_id] = {"valid": True}
    qr_url = f"{BASE_URL}/scan/{qr_id}"
    return render_template("public_token.html", qr_url=qr_url)

@app.route("/scan/<qr_id>", methods=["GET", "POST"])
def scan(qr_id):
    qr = qr_store.get(qr_id)

    if not qr or not qr["valid"]:
        return render_template("scan.html", message="❌ QR Code Invalid or Already Used")

    if request.method == "POST":
        validator_input = request.form.get("validator")
        if validator_input == VALIDATOR_KEY:
            qr["valid"] = False  # expire after one use
            return render_template("scan.html", message="✅ QR Code Validated! Allow entry.")
        else:
            return render_template("scan.html", message="❌ Invalid Validator Key")

    return render_template("scan.html", message="⚠️ Please enter validator code to confirm")

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
