from flask_sqlalchemy import SQLAlchemy
from datetime import datetime, timezone
import json, os, hashlib

db = SQLAlchemy()

def now_utc():
    return datetime.now(timezone.utc)

class User(db.Model):
    __tablename__ = 'users'
    id             = db.Column(db.Integer, primary_key=True)
    email          = db.Column(db.String(255), unique=True, nullable=False)
    password_hash  = db.Column(db.String(255), nullable=False)
    nome           = db.Column(db.String(255))
    societa        = db.Column(db.String(255))
    piano          = db.Column(db.String(50), default='base')
    piano_attivo   = db.Column(db.Boolean, default=True)
    piano_scadenza = db.Column(db.DateTime)
    is_admin       = db.Column(db.Boolean, default=False)
    created_at     = db.Column(db.DateTime, default=now_utc)
    updated_at     = db.Column(db.DateTime, default=now_utc, onupdate=now_utc)
    clients         = db.relationship('Client', backref='owner', lazy=True, cascade='all, delete-orphan')
    capsule_configs = db.relationship('CapsuleConfig', backref='owner', lazy=True, cascade='all, delete-orphan')
    ai_sessions     = db.relationship('AISession', backref='owner', lazy=True, cascade='all, delete-orphan')

    def set_password(self, password):
        salt = os.urandom(32).hex()
        h = hashlib.sha256((salt + password).encode()).hexdigest()
        self.password_hash = f"{salt}${h}"

    def check_password(self, password):
        try:
            salt, h = self.password_hash.split('$', 1)
            return hashlib.sha256((salt + password).encode()).hexdigest() == h
        except Exception:
            return False

    def to_dict(self):
        return {
            'id': self.id,
            'email': self.email,
            'nome': self.nome,
            'societa': self.societa,
            'piano': self.piano,
            'piano_attivo': self.piano_attivo,
            'is_admin': self.is_admin
        }


class Client(db.Model):
    __tablename__ = 'clients'
    id              = db.Column(db.Integer, primary_key=True)
    user_id         = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    nome            = db.Column(db.String(255), nullable=False)
    piva            = db.Column(db.String(20))
    ateco           = db.Column(db.String(20))
    settore         = db.Column(db.String(100))
    citta           = db.Column(db.String(100))
    rating          = db.Column(db.String(10))
    rating_score    = db.Column(db.Integer)
    dati_finanziari = db.Column(db.Text)
    attivo          = db.Column(db.Boolean, default=True)
    created_at      = db.Column(db.DateTime, default=now_utc)
    updated_at      = db.Column(db.DateTime, default=now_utc, onupdate=now_utc)
    capsule_config  = db.relationship('CapsuleConfig', backref='client', lazy=True, uselist=False)
    ai_sessions     = db.relationship('AISession', backref='client', lazy=True)

    def get_dati(self):
        try:
            return json.loads(self.dati_finanziari) if self.dati_finanziari else []
        except Exception:
            return []

    def set_dati(self, data):
        self.dati_finanziari = json.dumps(data, ensure_ascii=False)

    def to_dict(self):
        return {
            'id': self.id,
            'nome': self.nome,
            'piva': self.piva,
            'ateco': self.ateco,
            'settore': self.settore,
            'citta': self.citta,
            'rating': self.rating,
            'rating_score': self.rating_score,
            'attivo': self.attivo,
            'dati_finanziari': self.get_dati()
        }


class CapsuleConfig(db.Model):
    __tablename__ = 'capsule_configs'
    id             = db.Column(db.Integer, primary_key=True)
    user_id        = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    client_id      = db.Column(db.Integer, db.ForeignKey('clients.id'), nullable=True)
    tier           = db.Column(db.String(20), default='pro')
    capsule_attive = db.Column(db.Text)
    saved_at       = db.Column(db.DateTime, default=now_utc, onupdate=now_utc)

    def get_capsule(self):
        try:
            return json.loads(self.capsule_attive) if self.capsule_attive else {}
        except Exception:
            return {}

    def set_capsule(self, data):
        self.capsule_attive = json.dumps(data, ensure_ascii=False)

    def to_dict(self):
        return {
            'id': self.id,
            'user_id': self.user_id,
            'client_id': self.client_id,
            'tier': self.tier,
            'capsule_attive': self.get_capsule(),
            'saved_at': self.saved_at.isoformat() if self.saved_at else None
        }


class AISession(db.Model):
    __tablename__ = 'ai_sessions'
    id         = db.Column(db.Integer, primary_key=True)
    user_id    = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    client_id  = db.Column(db.Integer, db.ForeignKey('clients.id'), nullable=True)
    modulo     = db.Column(db.String(50))
    contesto   = db.Column(db.Text)
    messaggi   = db.Column(db.Text)
    sommario   = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=now_utc)
    updated_at = db.Column(db.DateTime, default=now_utc, onupdate=now_utc)

    def get_messaggi(self):
        try:
            return json.loads(self.messaggi) if self.messaggi else []
        except Exception:
            return []

    def add_messaggio(self, role, content):
        msgs = self.get_messaggi()
        msgs.append({'role': role, 'content': content, 'ts': now_utc().isoformat()})
        self.messaggi = json.dumps(msgs, ensure_ascii=False)

    def get_contesto(self):
        try:
            return json.loads(self.contesto) if self.contesto else {}
        except Exception:
            return {}

    def to_dict(self):
        return {
            'id': self.id,
            'user_id': self.user_id,
            'client_id': self.client_id,
            'modulo': self.modulo,
            'messaggi': self.get_messaggi(),
            'updated_at': self.updated_at.isoformat() if self.updated_at else None
        }
