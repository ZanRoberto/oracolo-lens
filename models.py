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
            'id': self.id, 'email': self.email, 'nome': self.nome,
            'societa': self.societa, 'piano': self.piano,
            'piano_attivo': self.piano_attivo, 'is_admin': self.is_admin
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
    dati_finanziari = db.Column(db.Text)   # storico anni ufficiali [{"anno":2022,...}]
    attivo          = db.Column(db.Boolean, default=True)
    created_at      = db.Column(db.DateTime, default=now_utc)
    updated_at      = db.Column(db.DateTime, default=now_utc, onupdate=now_utc)
    capsule_config  = db.relationship('CapsuleConfig', backref='client', lazy=True, uselist=False)
    ai_sessions     = db.relationship('AISession', backref='client', lazy=True)
    dati_provvisori = db.relationship('DatiProvvisori', backref='client', lazy=True, cascade='all, delete-orphan')
    capsule_stati   = db.relationship('CapsuleStato', backref='client', lazy=True, cascade='all, delete-orphan')

    def get_dati(self):
        try:
            return json.loads(self.dati_finanziari) if self.dati_finanziari else []
        except Exception:
            return []

    def set_dati(self, data):
        self.dati_finanziari = json.dumps(data, ensure_ascii=False)

    def to_dict(self):
        return {
            'id': self.id, 'nome': self.nome, 'piva': self.piva,
            'ateco': self.ateco, 'settore': self.settore, 'citta': self.citta,
            'rating': self.rating, 'rating_score': self.rating_score,
            'attivo': self.attivo, 'dati_finanziari': self.get_dati()
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
            'id': self.id, 'user_id': self.user_id, 'client_id': self.client_id,
            'tier': self.tier, 'capsule_attive': self.get_capsule(),
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
            'id': self.id, 'user_id': self.user_id, 'client_id': self.client_id,
            'modulo': self.modulo, 'messaggi': self.get_messaggi(),
            'updated_at': self.updated_at.isoformat() if self.updated_at else None
        }


# ════════════════════════════════════════════════════════════════════════════
# DATI PROVVISORI — PDF/Excel caricati dal consulente, persistiti per anno
# ════════════════════════════════════════════════════════════════════════════
class DatiProvvisori(db.Model):
    __tablename__ = 'dati_provvisori'
    id           = db.Column(db.Integer, primary_key=True)
    client_id    = db.Column(db.Integer, db.ForeignKey('clients.id'), nullable=False)
    user_id      = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    anno         = db.Column(db.Integer, nullable=False)
    fonte        = db.Column(db.String(20), default='manuale')  # pdf | excel | manuale
    nome_file    = db.Column(db.String(255))
    dati_json    = db.Column(db.Text, nullable=False)  # stesso formato preset hardcoded
    note         = db.Column(db.Text)
    creato_at    = db.Column(db.DateTime, default=now_utc)
    aggiornato_at = db.Column(db.DateTime, default=now_utc, onupdate=now_utc)

    __table_args__ = (
        db.UniqueConstraint('client_id', 'anno', name='uq_client_anno'),
    )

    def get_dati(self):
        try:
            return json.loads(self.dati_json) if self.dati_json else {}
        except Exception:
            return {}

    def set_dati(self, data):
        self.dati_json = json.dumps(data, ensure_ascii=False)

    def to_dict(self):
        return {
            'id': self.id,
            'client_id': self.client_id,
            'anno': self.anno,
            'fonte': self.fonte,
            'nome_file': self.nome_file,
            'dati': self.get_dati(),
            'note': self.note,
            'aggiornato_at': self.aggiornato_at.isoformat() if self.aggiornato_at else None
        }


# ════════════════════════════════════════════════════════════════════════════
# CAPSULE STATO — risultato del motore capsule per client + anno
# ════════════════════════════════════════════════════════════════════════════
class CapsuleStato(db.Model):
    __tablename__ = 'capsule_stati'
    id              = db.Column(db.Integer, primary_key=True)
    client_id       = db.Column(db.Integer, db.ForeignKey('clients.id'), nullable=False)
    user_id         = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    anno            = db.Column(db.Integer, nullable=False)

    # 4 capsule — stato + score + narrativa
    liquidita_stato    = db.Column(db.String(20))   # OFFENSIVO|DIFENSIVO|ALLERTA|NEUTRO
    liquidita_score    = db.Column(db.Float)
    liquidita_narrativa = db.Column(db.Text)

    redditivita_stato    = db.Column(db.String(20))
    redditivita_score    = db.Column(db.Float)
    redditivita_narrativa = db.Column(db.Text)

    struttura_stato    = db.Column(db.String(20))
    struttura_score    = db.Column(db.Float)
    struttura_narrativa = db.Column(db.Text)

    crescita_stato    = db.Column(db.String(20))
    crescita_score    = db.Column(db.Float)
    crescita_narrativa = db.Column(db.Text)

    # Score composito finale
    score_globale   = db.Column(db.Float)
    stato_globale   = db.Column(db.String(20))
    sintesi_ai      = db.Column(db.Text)  # narrativa DeepSeek finale

    calcolato_at    = db.Column(db.DateTime, default=now_utc, onupdate=now_utc)

    __table_args__ = (
        db.UniqueConstraint('client_id', 'anno', name='uq_caps_client_anno'),
    )

    def to_dict(self):
        return {
            'client_id': self.client_id,
            'anno': self.anno,
            'capsule': {
                'liquidita':   {'stato': self.liquidita_stato,   'score': self.liquidita_score,   'narrativa': self.liquidita_narrativa},
                'redditivita': {'stato': self.redditivita_stato, 'score': self.redditivita_score, 'narrativa': self.redditivita_narrativa},
                'struttura':   {'stato': self.struttura_stato,   'score': self.struttura_score,   'narrativa': self.struttura_narrativa},
                'crescita':    {'stato': self.crescita_stato,    'score': self.crescita_score,    'narrativa': self.crescita_narrativa},
            },
            'score_globale': self.score_globale,
            'stato_globale': self.stato_globale,
            'sintesi_ai': self.sintesi_ai,
            'calcolato_at': self.calcolato_at.isoformat() if self.calcolato_at else None
        }
