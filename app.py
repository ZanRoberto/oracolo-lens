# Oracolo Lens — Variabili d'ambiente
# Copiare questo file in .env per sviluppo locale
# Su Render: impostare queste variabili nel pannello Environment

# ── Sicurezza ─────────────────────────────────────────────────────────────────
SECRET_KEY=cambia-questa-stringa-con-qualcosa-di-casuale-e-lungo

# ── Database ──────────────────────────────────────────────────────────────────
# Render inietta DATABASE_URL automaticamente per PostgreSQL managed
# In locale lasciare vuoto → usa SQLite automaticamente
DATABASE_URL=

# ── Anthropic ─────────────────────────────────────────────────────────────────
ANTHROPIC_API_KEY=sk-ant-...

# ── Flask ─────────────────────────────────────────────────────────────────────
FLASK_DEBUG=false
PORT=5000
