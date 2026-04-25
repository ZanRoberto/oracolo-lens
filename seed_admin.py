# Oracolo Lens

**Piattaforma di Intelligence Finanziaria per PMI Italiane**

Scoring proprietario · Analisi predittiva · AI Narratore · Capsule modulari · Altman Z-Score · Modello Banca d'Italia

---

## Stack

- **Backend:** Python / Flask / SQLAlchemy
- **Database:** PostgreSQL (Render managed) · SQLite in sviluppo locale
- **AI:** Anthropic Claude (Narratore + Superrisponditore)
- **Deploy:** Render.com
- **Frontend:** HTML/CSS/JS vanilla (5 moduli)

## Moduli

| Modulo | Descrizione |
|--------|-------------|
| Hub | Navigazione centrale tra i moduli |
| Platform Intelligence | Portafoglio clienti · Predittivo 12m · Stress test · Alert · Lettera due diligence |
| Due Diligence | Analisi finanziaria · Punteggio proprietario · Altman Z-Score · Modello BdI |
| Budget | Budget economico e finanziario · Flussi di cassa · Grafici |
| Capsule Manager | Configurazione moduli per tier · Base / Professional / Intelligence |

## Piani

| Piano | Prezzo | Accesso |
|-------|--------|---------|
| Base | €89/mese | Capsule base |
| Professional | €290/mese | Capsule base + pro |
| Intelligence | €690/mese | Accesso completo |

## Setup locale

```bash
git clone https://github.com/ZanRoberto/oracolo-lens.git
cd oracolo-lens
pip install -r requirements.txt
cp .env.example .env
# editare .env con le proprie chiavi
python app.py
```

Aprire `http://localhost:5000`

## Deploy su Render

1. Collegare repo GitHub a Render (Web Service)
2. Build command: `pip install -r requirements.txt`
3. Start command: `gunicorn app:app`
4. Aggiungere PostgreSQL managed (Render Dashboard → New → PostgreSQL)
5. Impostare variabili d'ambiente: `SECRET_KEY`, `ANTHROPIC_API_KEY`
6. `DATABASE_URL` viene iniettato automaticamente da Render

---

© 2025 Albaconsulting S.r.l. — All rights reserved.
Software proprietario. Uso consentito solo su licenza contrattuale.
