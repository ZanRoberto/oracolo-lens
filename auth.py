"""
Capsules — configurazione capsule attive per utente / azienda
"""

from flask import Blueprint, request, jsonify, session
from models import db, CapsuleConfig
from routes.auth import require_login

capsules_bp = Blueprint('capsules', __name__)


# ── GET /api/capsules/config?client_id=X ────────────────────────────────────
@capsules_bp.route('/config', methods=['GET'])
def get_config():
    user, err, code = require_login()
    if err: return err, code

    client_id = request.args.get('client_id', type=int)

    cfg = CapsuleConfig.query.filter_by(
        user_id   = user.id,
        client_id = client_id
    ).first()

    if not cfg:
        # Restituisce default basato sul piano utente
        return jsonify({
            'tier':           user.piano,
            'capsule_attive': {},
            'saved_at':       None
        }), 200

    return jsonify(cfg.to_dict()), 200


# ── POST /api/capsules/config ─────────────────────────────────────────────────
@capsules_bp.route('/config', methods=['POST'])
def save_config():
    user, err, code = require_login()
    if err: return err, code

    data      = request.get_json() or {}
    client_id = data.get('client_id')          # None = config globale
    tier      = data.get('tier', user.piano)
    capsule   = data.get('capsule_attive', {})

    # Verifica che il tier richiesto sia compatibile col piano acquistato
    tier_rank = {'base': 0, 'pro': 1, 'intel': 2}
    piano_map = {'base': 'base', 'professional': 'pro', 'intelligence': 'intel'}
    piano_tier = piano_map.get(user.piano, 'base')

    if tier_rank.get(tier, 0) > tier_rank.get(piano_tier, 0):
        return jsonify({'error': f'Tier {tier} non incluso nel piano {user.piano}'}), 403

    cfg = CapsuleConfig.query.filter_by(
        user_id   = user.id,
        client_id = client_id
    ).first()

    if not cfg:
        cfg = CapsuleConfig(user_id=user.id, client_id=client_id)
        db.session.add(cfg)

    cfg.tier = tier
    cfg.set_capsule(capsule)
    db.session.commit()

    return jsonify({'ok': True, 'config': cfg.to_dict()}), 200
