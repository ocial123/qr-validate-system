
# QR Validate System (single-use, validator-device only)

A tiny Flask app for generating QR codes that **only your device** can validate.  
If someone else scans a QR, they see a neutral page and the token is **not** consumed.  
When *your* device scans, the token is marked used and becomes invalid for future entries.

## Features
- Single-use tokens stored in SQLite
- Only "validator" device can consume tokens (via a secure cookie set using a secret `VALIDATOR_KEY`)
- Admin page to generate tokens, export CSV, and print QR grid
- Works over the internet; deploy free on Render/Railway
- Minimal dependencies; production-ready with Gunicorn

## Quick Start (Local)
```bash
python -m venv .venv && . .venv/bin/activate  # Windows: .venv\Scripts\activate
pip install -r requirements.txt
export ADMIN_PASSWORD=supersecret-admin
export VALIDATOR_KEY=$(python - <<'PY'\nimport secrets; print(secrets.token_urlsafe(32))\nPY)
flask --app app run  # or: python app.py
```

Open `http://localhost:5000`

## Mark your phone as the validator device
On **your** phone **once**, visit:
```
/set-validator?key=YOUR_VALIDATOR_KEY
```
This sets a secure cookie. From then on, when your phone hits a token URL, the server consumes it.  
Anyone else scanning only sees a neutral screen and nothing changes.

To remove validator on a device: visit `/logout-validator`.

## Generate codes
Go to `/admin` and login with `ADMIN_PASSWORD`. Create tokens:
- Download a CSV of URLs
- View a printable grid of QR codes
- Each QR links to `/t/<token>`

## Deploy free (Render example)
1. Push this folder to GitHub.
2. Create a new **Web Service** on Render.
3. Environment:
   - `ADMIN_PASSWORD` = choose one
   - `VALIDATOR_KEY`  = long random (keep secret)
   - `FLASK_SECRET_KEY` = random
   - (Optional) `BASE_URL` = your Render URL (e.g. `https://yourapp.onrender.com`)
4. Build command: *(none)* (Render auto-installs from `requirements.txt`)
5. Start command: `gunicorn app:app` (already in `Procfile`)

## Security notes
- Keep `VALIDATOR_KEY` secret. Only set it on your gatekeeper device via `/set-validator`.
- Token URLs do not reveal validation status to the public; only validator device sees it and consumes it.
- SQLite file `tokens.db` persists used/unused state across restarts.

## File layout
```
qr-validate-system/
│── app.py
│── requirements.txt
│── Procfile
│── README.md
│── .env.example
│
├── templates/
│   │── base.html
│   │── index.html
│   │── admin.html
│   │── token_public.html
│   └── token_validator.html
└── static/
    └── style.css
```
