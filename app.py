import os
import uuid
from flask import Flask, render_template, request, redirect, url_for

app = Flask(__name__)

# In-memory DB (you can switch to SQLite later if needed)
tokens = {}

ADMIN_PASSCODE = os.getenv("VALIDATOR_CODE", "1234")  # secret code from env

@app.route("/")
def index():
    return render_template("index.html", tokens=tokens)

@app.route("/generate", methods=["POST"])
def generate():
    token = str(uuid.uuid4())
    tokens[token] = {"used": False}
    return render_template("token_public.html", token=token)

# Guest scan → always useless
@app.route("/t/<token>")
def guest_view(token):
    if token not in tokens:
        return "❌ Invalid QR", 404
    if tokens[token]["used"]:
        return "❌ QR already used", 400
    return "⚠️ Please wait for staff to validate"

# Admin scan & validate
@app.route("/validate/<token>", methods=["GET", "POST"])
def validate(token):
    if token not in tokens:
        return "❌ Invalid QR", 404

    if request.method == "POST":
        code = request.form.get("code")
        if code != ADMIN_PASSCODE:
            return "❌ Wrong passcode", 403
        if tokens[token]["used"]:
            return "❌ QR already used", 400

        # mark as used
        tokens[token]["used"] = True
        return "✅ QR validated & expired!"

    return '''
        <form method="POST">
            <input type="password" name="code" placeholder="Enter passcode"/>
            <button type="submit">Validate</button>
        </form>
    '''
