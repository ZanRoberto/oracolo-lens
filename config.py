import os

class Config:
    SECRET_KEY = os.environ.get('SECRET_KEY', 'dev-secret-change-in-production')

    DATABASE_URL = os.environ.get('DATABASE_URL', '')
    if DATABASE_URL.startswith('postgres://'):
        DATABASE_URL = DATABASE_URL.replace('postgres://', 'postgresql://', 1)

    SQLALCHEMY_DATABASE_URI = DATABASE_URL or 'sqlite:///oracolo_lens_dev.db'
    SQLALCHEMY_TRACK_MODIFICATIONS = False

    ANTHROPIC_API_KEY = os.environ.get('ANTHROPIC_API_KEY', '')

    APP_NAME    = 'Oracolo Lens'
    APP_VERSION = '1.0.0'
    DEBUG       = os.environ.get('FLASK_DEBUG', 'false').lower() == 'true'

    PIANI = {
        'base':         {'nome': 'Base',         'prezzo_mese': 89,  'capsule_tier': ['base']},
        'professional': {'nome': 'Professional', 'prezzo_mese': 290, 'capsule_tier': ['base', 'pro']},
        'intelligence': {'nome': 'Intelligence', 'prezzo_mese': 690, 'capsule_tier': ['base', 'pro', 'intel']},
    }
