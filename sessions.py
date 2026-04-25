"""
seed_admin.py — crea il superadmin iniziale
Eseguire UNA VOLTA dopo il primo deploy:
    python seed_admin.py
"""

from app import app
from models import db, User

ADMIN_EMAIL    = 'admin@albaconsulting.it'   # cambiare
ADMIN_PASSWORD = 'OracoloLens2025!'          # cambiare — password forte
ADMIN_NOME     = 'Albaconsulting Admin'

with app.app_context():
    if User.query.filter_by(email=ADMIN_EMAIL).first():
        print(f'Admin {ADMIN_EMAIL} già esistente.')
    else:
        admin = User(
            email    = ADMIN_EMAIL,
            nome     = ADMIN_NOME,
            societa  = 'Albaconsulting S.r.l.',
            piano    = 'intelligence',
            is_admin = True,
            piano_attivo = True,
        )
        admin.set_password(ADMIN_PASSWORD)
        db.session.add(admin)
        db.session.commit()
        print(f'✓ Superadmin creato: {ADMIN_EMAIL}')
