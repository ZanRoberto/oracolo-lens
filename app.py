"""
Oracolo Lens — Piattaforma Intelligence Finanziaria per PMI Italiane
© 2025 Albaconsulting S.r.l. — All rights reserved.
Software proprietario. Uso consentito solo su licenza contrattuale.
"""

from flask import Flask, send_from_directory, jsonify, request, session
from flask_cors import CORS
from config import Config
from models import db, User, Client, CapsuleConfig, AISession
import os, hashlib

app = Flask(__name__)
app.config.from_object(Config)
CORS(app, resources={r"/api/*": {"origins": "*"}})
db.init_app(app)

# ════════════════════════════════════════════════════════════════════════════
# HELPER
# ════════════════════════════════════════════════════════════════════════════
def get_user():
    uid = session.get('user_id')
    if not uid:
        return None
    return User.query.get(uid)

def need_login():
    u = get_user()
    if not u:
        return None, jsonify({'error': 'Non autenticato'}), 401
    return u, None, None

# ════════════════════════════════════════════════════════════════════════════
# AUTH
# ════════════════════════════════════════════════════════════════════════════
@app.route('/api/auth/login', methods=['POST'])
def login():
    d = request.get_json() or {}
    user = User.query.filter_by(email=d.get('email','').lower()).first()
    if not user or not user.check_password(d.get('password','')):
        return jsonify({'error': 'Credenziali non valide'}), 401
    if not user.piano_attivo:
        return jsonify({'error': 'Abbonamento scaduto'}), 403
    session['user_id'] = user.id
    session.permanent = True
    return jsonify({'ok': True, 'user': user.to_dict()})

@app.route('/api/auth/logout', methods=['POST'])
def logout():
    session.clear()
    return jsonify({'ok': True})

@app.route('/api/auth/me')
def me():
    u, err, code = need_login()
    if err: return err, code
    return jsonify({'user': u.to_dict()})

@app.route('/api/auth/register', methods=['POST'])
def register():
    caller, err, code = need_login()
    if err: return err, code
    if not caller.is_admin:
        return jsonify({'error': 'Accesso negato'}), 403
    d = request.get_json() or {}
    if User.query.filter_by(email=d.get('email','')).first():
        return jsonify({'error': 'Email già registrata'}), 409
    u = User(email=d['email'].lower(), nome=d.get('nome',''),
             societa=d.get('societa',''), piano=d.get('piano','base'))
    u.set_password(d.get('password',''))
    db.session.add(u)
    db.session.commit()
    return jsonify({'ok': True, 'user': u.to_dict()}), 201

# ════════════════════════════════════════════════════════════════════════════
# CLIENTS
# ════════════════════════════════════════════════════════════════════════════
@app.route('/api/clients/', methods=['GET'])
def get_clients():
    u, err, code = need_login()
    if err: return err, code
    return jsonify({'clients': [c.to_dict() for c in Client.query.filter_by(user_id=u.id, attivo=True).all()]})

@app.route('/api/clients/<int:cid>', methods=['GET'])
def get_client(cid):
    u, err, code = need_login()
    if err: return err, code
    c = Client.query.filter_by(id=cid, user_id=u.id).first()
    if not c: return jsonify({'error': 'Non trovato'}), 404
    return jsonify({'client': c.to_dict()})

@app.route('/api/clients/', methods=['POST'])
def create_client():
    u, err, code = need_login()
    if err: return err, code
    d = request.get_json() or {}
    c = Client(user_id=u.id, nome=d.get('nome',''), piva=d.get('piva'),
               ateco=d.get('ateco'), settore=d.get('settore'),
               rating=d.get('rating'), rating_score=d.get('rating_score'))
    if d.get('dati_finanziari'): c.set_dati(d['dati_finanziari'])
    db.session.add(c)
    db.session.commit()
    return jsonify({'ok': True, 'client': c.to_dict()}), 201

@app.route('/api/clients/<int:cid>', methods=['PUT'])
def update_client(cid):
    u, err, code = need_login()
    if err: return err, code
    c = Client.query.filter_by(id=cid, user_id=u.id).first()
    if not c: return jsonify({'error': 'Non trovato'}), 404
    d = request.get_json() or {}
    for f in ['nome','piva','ateco','settore','rating','rating_score']:
        if f in d: setattr(c, f, d[f])
    if 'dati_finanziari' in d: c.set_dati(d['dati_finanziari'])
    db.session.commit()
    return jsonify({'ok': True, 'client': c.to_dict()})

@app.route('/api/clients/<int:cid>', methods=['DELETE'])
def delete_client(cid):
    u, err, code = need_login()
    if err: return err, code
    c = Client.query.filter_by(id=cid, user_id=u.id).first()
    if not c: return jsonify({'error': 'Non trovato'}), 404
    c.attivo = False
    db.session.commit()
    return jsonify({'ok': True})

# ════════════════════════════════════════════════════════════════════════════
# CAPSULES
# ════════════════════════════════════════════════════════════════════════════
@app.route('/api/capsules/config', methods=['GET'])
def get_capsule_config():
    u, err, code = need_login()
    if err: return err, code
    client_id = request.args.get('client_id', type=int)
    cfg = CapsuleConfig.query.filter_by(user_id=u.id, client_id=client_id).first()
    if not cfg:
        return jsonify({'tier': u.piano, 'capsule_attive': {}, 'saved_at': None})
    return jsonify(cfg.to_dict())

@app.route('/api/capsules/config', methods=['POST'])
def save_capsule_config():
    u, err, code = need_login()
    if err: return err, code
    d = request.get_json() or {}
    client_id = d.get('client_id')
    tier = d.get('tier', u.piano)
    cfg = CapsuleConfig.query.filter_by(user_id=u.id, client_id=client_id).first()
    if not cfg:
        cfg = CapsuleConfig(user_id=u.id, client_id=client_id)
        db.session.add(cfg)
    cfg.tier = tier
    cfg.set_capsule(d.get('capsule_attive', {}))
    db.session.commit()
    return jsonify({'ok': True, 'config': cfg.to_dict()})

# ════════════════════════════════════════════════════════════════════════════
# SESSIONS
# ════════════════════════════════════════════════════════════════════════════
@app.route('/api/sessions/', methods=['GET'])
def get_session():
    u, err, code = need_login()
    if err: return err, code
    client_id = request.args.get('client_id', type=int)
    modulo    = request.args.get('modulo', 'platform')
    sess = AISession.query.filter_by(user_id=u.id, client_id=client_id, modulo=modulo)\
                          .order_by(AISession.updated_at.desc()).first()
    return jsonify({'session': sess.to_dict() if sess else None})

@app.route('/api/sessions/', methods=['POST'])
def save_session():
    u, err, code = need_login()
    if err: return err, code
    d = request.get_json() or {}
    client_id = d.get('client_id')
    modulo    = d.get('modulo', 'platform')
    sess = AISession.query.filter_by(user_id=u.id, client_id=client_id, modulo=modulo)\
                          .order_by(AISession.updated_at.desc()).first()
    if not sess:
        sess = AISession(user_id=u.id, client_id=client_id, modulo=modulo)
        db.session.add(sess)
    if d.get('contesto'):
        import json
        sess.contesto = json.dumps(d['contesto'], ensure_ascii=False)
    sess.add_messaggio(d.get('role','user'), d.get('content',''))
    db.session.commit()
    return jsonify({'ok': True, 'session_id': sess.id})

@app.route('/api/sessions/', methods=['DELETE'])
def clear_session():
    u, err, code = need_login()
    if err: return err, code
    AISession.query.filter_by(user_id=u.id,
        client_id=request.args.get('client_id', type=int),
        modulo=request.args.get('modulo','platform')).delete()
    db.session.commit()
    return jsonify({'ok': True})

# ════════════════════════════════════════════════════════════════════════════
# FRONTEND — serve gli HTML direttamente dalla root
# ════════════════════════════════════════════════════════════════════════════
@app.route('/')
def index():
    return send_from_directory('.', 'due_diligence.html')

@app.route('/<path:filename>')
def static_files(filename):
    return send_from_directory('.', filename)

# ── Health check ─────────────────────────────────────────────────────────────
@app.route('/health')
def health():
    return jsonify({'status': 'ok', 'app': 'oracolo-lens'}), 200

# ── Init DB ──────────────────────────────────────────────────────────────────
with app.app_context():
    db.create_all()

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)
