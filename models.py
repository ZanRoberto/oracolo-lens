"""
Oracolo Lens — Piattaforma Intelligence Finanziaria per PMI Italiane
© 2025 Albaconsulting S.r.l. — All rights reserved.
Software proprietario. Uso consentito solo su licenza contrattuale.
"""

from flask import Flask, send_from_directory, jsonify
from flask_cors import CORS
from config import Config
from models import db
import os

app = Flask(__name__, static_folder='static', template_folder='templates')
app.config.from_object(Config)

CORS(app, resources={r"/api/*": {"origins": "*"}})
db.init_app(app)

# ── Routes ──────────────────────────────────────────────────────────────────
from routes.auth     import auth_bp
from routes.clients  import clients_bp
from routes.capsules import capsules_bp
from routes.sessions import sessions_bp

app.register_blueprint(auth_bp,     url_prefix='/api/auth')
app.register_blueprint(clients_bp,  url_prefix='/api/clients')
app.register_blueprint(capsules_bp, url_prefix='/api/capsules')
app.register_blueprint(sessions_bp, url_prefix='/api/sessions')

# ── Serve frontend ───────────────────────────────────────────────────────────
@app.route('/')
def index():
    return send_from_directory('static', 'hub.html')

@app.route('/<path:filename>')
def static_files(filename):
    return send_from_directory('static', filename)

# ── Health check (Render lo usa) ─────────────────────────────────────────────
@app.route('/health')
def health():
    return jsonify({'status': 'ok', 'app': 'oracolo-lens'}), 200

# ── Init DB ──────────────────────────────────────────────────────────────────
with app.app_context():
    db.create_all()

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)
