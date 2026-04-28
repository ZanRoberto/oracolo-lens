"""
Oracolo Lens — Dati Provvisori + Motore Capsule
Nuovo file da aggiungere al repo.
"""
import os, json
from flask import request, jsonify, session
from models import db, Client, DatiProvvisori, CapsuleStato
from datetime import datetime, timezone


def now_utc():
    return datetime.now(timezone.utc)


def _get_user():
    from models import User
    uid = session.get('user_id')
    return User.query.get(uid) if uid else None


def register_routes_dati(app):

    # ════════════════════════════════════════════════════════════════════════
    # DATI PROVVISORI — CRUD
    # ════════════════════════════════════════════════════════════════════════

    @app.route('/api/dati/provvisori/<int:client_id>', methods=['GET'])
    def get_dati_provvisori(client_id):
        u = _get_user()
        if not u: return jsonify({'error': 'Non autenticato'}), 401
        c = Client.query.filter_by(id=client_id, user_id=u.id).first()
        if not c: return jsonify({'error': 'Cliente non trovato'}), 404
        records = DatiProvvisori.query.filter_by(client_id=client_id)\
                    .order_by(DatiProvvisori.anno.desc()).all()
        return jsonify({'dati': [r.to_dict() for r in records]})

    @app.route('/api/dati/provvisori/<int:client_id>', methods=['POST'])
    def salva_dato_provvisorio(client_id):
        """Salva dati provvisori inseriti manualmente o già parsati dal frontend."""
        u = _get_user()
        if not u: return jsonify({'error': 'Non autenticato'}), 401
        c = Client.query.filter_by(id=client_id, user_id=u.id).first()
        if not c: return jsonify({'error': 'Cliente non trovato'}), 404
        d = request.get_json() or {}
        anno = d.get('anno')
        if not anno: return jsonify({'error': 'Anno obbligatorio'}), 400
        r = DatiProvvisori.query.filter_by(client_id=client_id, anno=anno).first()
        if not r:
            r = DatiProvvisori(client_id=client_id, user_id=u.id, anno=anno)
            db.session.add(r)
        r.fonte    = d.get('fonte', 'manuale')
        r.note     = d.get('note', '')
        r.nome_file = d.get('nome_file', '')
        r.set_dati(d.get('dati', {}))
        db.session.commit()
        return jsonify({'ok': True, 'dato': r.to_dict()})

    @app.route('/api/dati/provvisori/<int:client_id>/<int:anno>', methods=['DELETE'])
    def elimina_dato_provvisorio(client_id, anno):
        u = _get_user()
        if not u: return jsonify({'error': 'Non autenticato'}), 401
        r = DatiProvvisori.query.filter_by(client_id=client_id, anno=anno).first()
        if not r: return jsonify({'error': 'Non trovato'}), 404
        db.session.delete(r)
        db.session.commit()
        return jsonify({'ok': True})

    # ════════════════════════════════════════════════════════════════════════
    # UPLOAD PDF — estrazione via pdfplumber + DeepSeek
    # ════════════════════════════════════════════════════════════════════════

    @app.route('/api/dati/upload/<int:client_id>', methods=['POST'])
    def upload_pdf_provvisorio(client_id):
        """
        Riceve un PDF digitale nativo.
        1. pdfplumber estrae il testo grezzo
        2. DeepSeek interpreta e struttura i campi
        3. Restituisce dati estratti + campi mancanti per form rettifiche
        NON salva ancora — il frontend mostra il form rettifiche, poi chiama /salva
        """
        u = _get_user()
        if not u: return jsonify({'error': 'Non autenticato'}), 401
        c = Client.query.filter_by(id=client_id, user_id=u.id).first()
        if not c: return jsonify({'error': 'Cliente non trovato'}), 404

        f = request.files.get('file')
        anno = request.form.get('anno', type=int)
        if not f or not anno:
            return jsonify({'error': 'File e anno obbligatori'}), 400

        ext = f.filename.rsplit('.', 1)[-1].lower() if '.' in f.filename else ''
        if ext != 'pdf':
            return jsonify({'error': 'Solo PDF digitali nativi supportati'}), 400

        # Step 1: estrai testo grezzo con pdfplumber
        try:
            import pdfplumber
        except ImportError:
            return jsonify({'error': 'pdfplumber non installato — aggiungi a requirements.txt'}), 500

        testo_grezzo = ''
        try:
            with pdfplumber.open(f) as pdf:
                for page in pdf.pages:
                    t = page.extract_text()
                    if t:
                        testo_grezzo += t + '\n'
        except Exception as e:
            return jsonify({'error': f'Errore lettura PDF: {str(e)}'}), 500

        if not testo_grezzo.strip():
            return jsonify({
                'error': 'PDF senza testo estraibile. Assicurati che sia un PDF digitale nativo, non una scansione.'
            }), 400

        # Step 2: DeepSeek interpreta il testo
        dati_estratti, campi_mancanti = _deepseek_estrai_bilancio(testo_grezzo, anno, c)

        return jsonify({
            'ok': True,
            'nome_file': f.filename,
            'anno': anno,
            'dati_estratti': dati_estratti,
            'campi_mancanti': campi_mancanti,
            'testo_pagine': len([p for p in testo_grezzo.split('\n') if p.strip()])
        })


    @app.route('/api/dati/upload/slug/<string:slug>', methods=['POST'])
    def upload_pdf_per_slug(slug):
        """Upload PDF per societa hardcoded (rcs/vip) senza client_id numerico."""
        anno = request.form.get('anno', type=int)
        f = request.files.get('file')
        if not f or not anno:
            return jsonify({'error': 'File e anno obbligatori'}), 400
        if not f.filename.lower().endswith('.pdf'):
            return jsonify({'error': 'Solo PDF digitali nativi supportati'}), 400
        try:
            import pdfplumber
        except ImportError:
            return jsonify({'error': 'pdfplumber non installato'}), 500
        testo_grezzo = ''
        try:
            with pdfplumber.open(f) as pdf:
                for page in pdf.pages:
                    t = page.extract_text()
                    if t: testo_grezzo += t + '\n'
        except Exception as e:
            return jsonify({'error': f'Errore lettura PDF: {str(e)}'}), 500
        if not testo_grezzo.strip():
            return jsonify({'error': 'PDF senza testo estraibile — usa un PDF digitale nativo'}), 400

        class MockClient:
            ateco = None
            def get_dati(self): return []

        dati_estratti, campi_mancanti = _deepseek_estrai_bilancio(testo_grezzo, anno, MockClient())
        return jsonify({
            'ok': True,
            'nome_file': f.filename,
            'anno': anno,
            'dati_estratti': dati_estratti,
            'campi_mancanti': campi_mancanti,
            'testo_pagine': len([p for p in testo_grezzo.split('\n') if p.strip()])
        })

    # ════════════════════════════════════════════════════════════════════════
    # CAPSULE — calcolo + recupero
    # ════════════════════════════════════════════════════════════════════════

    @app.route('/api/capsule/calcola/<int:client_id>/<int:anno>', methods=['POST'])
    def calcola_capsule(client_id, anno):
        u = _get_user()
        if not u: return jsonify({'error': 'Non autenticato'}), 401
        c = Client.query.filter_by(id=client_id, user_id=u.id).first()
        if not c: return jsonify({'error': 'Cliente non trovato'}), 404

        # Dati anno corrente: provvisori > ufficiali
        prov = DatiProvvisori.query.filter_by(client_id=client_id, anno=anno).first()
        dati_anno = prov.get_dati() if prov else next(
            (d for d in c.get_dati() if d.get('anno') == anno), None)
        if not dati_anno:
            return jsonify({'error': f'Nessun dato per anno {anno}'}), 404

        # Dati anno precedente per trend
        prov_prec = DatiProvvisori.query.filter_by(client_id=client_id, anno=anno-1).first()
        dati_prec = prov_prec.get_dati() if prov_prec else next(
            (d for d in c.get_dati() if d.get('anno') == anno-1), None)

        risultato = _motore_capsule(dati_anno, dati_prec, c.ateco)

        cs = CapsuleStato.query.filter_by(client_id=client_id, anno=anno).first()
        if not cs:
            cs = CapsuleStato(client_id=client_id, user_id=u.id, anno=anno)
            db.session.add(cs)

        for cap in ['liquidita', 'redditivita', 'struttura', 'crescita']:
            r = risultato[cap]
            setattr(cs, f'{cap}_stato',     r['stato'])
            setattr(cs, f'{cap}_score',     r['score'])
            setattr(cs, f'{cap}_narrativa', r['narrativa'])

        cs.score_globale = risultato['score_globale']
        cs.stato_globale = risultato['stato_globale']
        db.session.commit()
        return jsonify({'ok': True, 'capsule': cs.to_dict()})

    @app.route('/api/capsule/stato/<int:client_id>/<int:anno>', methods=['GET'])
    def get_capsule_stato(client_id, anno):
        u = _get_user()
        if not u: return jsonify({'error': 'Non autenticato'}), 401
        cs = CapsuleStato.query.filter_by(client_id=client_id, anno=anno).first()
        return jsonify({'capsule': cs.to_dict() if cs else None})

    @app.route('/api/capsule/storia/<int:client_id>', methods=['GET'])
    def get_capsule_storia(client_id):
        u = _get_user()
        if not u: return jsonify({'error': 'Non autenticato'}), 401
        stati = CapsuleStato.query.filter_by(client_id=client_id)\
                    .order_by(CapsuleStato.anno.asc()).all()
        return jsonify({'storia': [s.to_dict() for s in stati]})


# ════════════════════════════════════════════════════════════════════════════
# DEEPSEEK — estrazione bilancio da testo grezzo
# ════════════════════════════════════════════════════════════════════════════

def _deepseek_estrai_bilancio(testo_grezzo, anno, client):
    """
    Passa il testo estratto dal PDF a DeepSeek.
    DeepSeek identifica i campi indipendentemente dal formato (ERP, gestionale, manuale).
    Restituisce dati_estratti + campi_mancanti per il form rettifiche.
    """
    import requests as req

    api_key = os.environ.get('DEEPSEEK_API_KEY', '')
    if not api_key:
        return {}, _campi_mancanti_default()

    # Storico per stima campi mancanti
    storico = client.get_dati() if client else []
    anno_prec = next((d for d in storico if d.get('anno') == anno - 1), None)

    prompt_sistema = """Sei un esperto contabile italiano. Analizzi testi di bilanci aziendali 
in qualsiasi formato (ERP, gestionale, bilancio civilistico, report interno).
Rispondi ESCLUSIVAMENTE con un oggetto JSON valido, senza testo prima o dopo, senza markdown."""

    prompt_utente = f"""Analizza questo testo estratto da un bilancio aziendale provvisorio italiano per l'anno {anno}.

TESTO BILANCIO:
{testo_grezzo[:6000]}

Estrai i seguenti campi se presenti. Per ogni campo non trovato usa null.
I valori devono essere numeri interi in euro (rimuovi separatori migliaia).

Rispondi SOLO con questo JSON:
{{
  "fatturato": null,
  "altri_ricavi": null,
  "costi_materie_prime": null,
  "costi_servizi": null,
  "costi_personale": null,
  "ammortamenti": null,
  "altri_costi_operativi": null,
  "oneri_finanziari": null,
  "proventi_finanziari": null,
  "imposte": null,
  "utile_netto": null,
  "totale_attivo": null,
  "immobilizzazioni": null,
  "crediti_clienti": null,
  "rimanenze": null,
  "cassa": null,
  "patrimonio_netto": null,
  "debiti_finanziari_lungo": null,
  "debiti_finanziari_breve": null,
  "debiti_fornitori": null,
  "tfr": null,
  "dipendenti": null,
  "note_estratte": "breve nota su formato riconosciuto e qualità dati"
}}"""

    try:
        r = req.post(
            'https://api.deepseek.com/v1/chat/completions',
            headers={'Authorization': f'Bearer {api_key}', 'Content-Type': 'application/json'},
            json={
                'model': 'deepseek-chat',
                'messages': [
                    {'role': 'system', 'content': prompt_sistema},
                    {'role': 'user',   'content': prompt_utente}
                ],
                'max_tokens': 1500,
                'temperature': 0.1   # bassa temperatura = più deterministico
            },
            timeout=45
        )
        testo_risposta = r.json()['choices'][0]['message']['content']

        # Pulizia risposta (rimuovi eventuale markdown)
        testo_risposta = testo_risposta.strip()
        if testo_risposta.startswith('```'):
            testo_risposta = testo_risposta.split('```')[1]
            if testo_risposta.startswith('json'):
                testo_risposta = testo_risposta[4:]
        testo_risposta = testo_risposta.strip()

        dati_estratti = json.loads(testo_risposta)

        # Calcola campi mancanti con stima da storico
        campi_mancanti = _calcola_campi_mancanti(dati_estratti, anno_prec, client)

        return dati_estratti, campi_mancanti

    except Exception as e:
        return {'errore_parsing': str(e)}, _campi_mancanti_default()


# ════════════════════════════════════════════════════════════════════════════
# CAMPI MANCANTI — form rettifiche con stime da storico
# ════════════════════════════════════════════════════════════════════════════

def _calcola_campi_mancanti(dati_estratti, anno_prec, client):
    """
    Identifica i campi tipicamente mancanti nei provvisori.
    Se disponibile lo storico, propone una stima come valore default nel form.
    """
    mancanti = []

    def stima_da_storico(campo, fallback=0):
        if anno_prec and anno_prec.get(campo):
            return {'valore': anno_prec[campo], 'fonte': f'storico {anno_prec.get("anno","")}'}
        return {'valore': fallback, 'fonte': 'inserisci manualmente'}

    # Ammortamenti — quasi sempre mancanti nel provvisorio
    if not dati_estratti.get('ammortamenti'):
        s = stima_da_storico('ammortamenti')
        mancanti.append({
            'campo': 'ammortamenti',
            'label': 'Ammortamenti',
            'descrizione': 'Quote ammortamento immobilizzazioni — calcolate a fine anno dal commercialista',
            'stima': s['valore'],
            'fonte_stima': s['fonte'],
            'obbligatorio': True
        })

    # Fatture da ricevere (FdR)
    mancanti.append({
        'campo': 'fatture_da_ricevere',
        'label': 'Fatture da ricevere',
        'descrizione': 'Forniture ricevute ma non ancora fatturate dai fornitori',
        'stima': 0,
        'fonte_stima': 'inserisci manualmente',
        'obbligatorio': False
    })

    # Leasing e mutui attivati in corso d'anno
    mancanti.append({
        'campo': 'nuovi_leasing_mutui',
        'label': 'Nuovi leasing / mutui anno in corso',
        'descrizione': 'Finanziamenti attivati durante l\'anno non ancora completamente registrati',
        'stima': 0,
        'fonte_stima': 'inserisci manualmente',
        'obbligatorio': False
    })

    # TFR maturato
    if not dati_estratti.get('tfr'):
        s = stima_da_storico('tfr')
        mancanti.append({
            'campo': 'tfr_maturato',
            'label': 'TFR maturato nell\'anno',
            'descrizione': 'Trattamento di fine rapporto maturato — stima da costo del personale',
            'stima': s['valore'],
            'fonte_stima': s['fonte'],
            'obbligatorio': False
        })

    # Ratei e risconti
    mancanti.append({
        'campo': 'ratei_risconti',
        'label': 'Ratei e risconti passivi',
        'descrizione': 'Costi di competenza dell\'anno non ancora liquidati (assicurazioni, canoni, ecc.)',
        'stima': 0,
        'fonte_stima': 'inserisci manualmente',
        'obbligatorio': False
    })

    # Imposte stimate
    if not dati_estratti.get('imposte'):
        mancanti.append({
            'campo': 'imposte_stimate',
            'label': 'Imposte stimate (IRES + IRAP)',
            'descrizione': 'Stima imposte sul reddito — calcolate su utile ante imposte rettificato',
            'stima': 0,
            'fonte_stima': 'calcolato automaticamente dopo rettifiche',
            'obbligatorio': False
        })

    return mancanti


def _campi_mancanti_default():
    """Form rettifiche vuoto quando DeepSeek non è disponibile."""
    campi = ['ammortamenti','fatture_da_ricevere','nuovi_leasing_mutui',
             'tfr_maturato','ratei_risconti','imposte_stimate']
    labels = ['Ammortamenti','Fatture da ricevere','Nuovi leasing / mutui',
              'TFR maturato','Ratei e risconti passivi','Imposte stimate']
    return [{'campo': c, 'label': l, 'stima': 0,
             'fonte_stima': 'inserisci manualmente', 'obbligatorio': False}
            for c, l in zip(campi, labels)]


# ════════════════════════════════════════════════════════════════════════════
# MOTORE CAPSULE — pesi dinamici per ATECO + segnali precursori
# ════════════════════════════════════════════════════════════════════════════

def _pesi_per_ateco(ateco):
    """
    Ridistribuisce i pesi delle 4 capsule in base al settore ATECO.
    Pesi base: Liquidità 30, Redditività 30, Struttura 25, Crescita 15
    """
    if not ateco:
        return {'liquidita': 0.30, 'redditivita': 0.30, 'struttura': 0.25, 'crescita': 0.15}

    codice = str(ateco).strip()[:2]

    # Manifatturiero (10-33) — struttura e immobilizzi pesano di più
    if codice in [str(i) for i in range(10, 34)]:
        return {'liquidita': 0.25, 'redditivita': 0.28, 'struttura': 0.32, 'crescita': 0.15}

    # Costruzioni (41-43) — liquidità critica, cicli lunghi
    if codice in ['41','42','43']:
        return {'liquidita': 0.40, 'redditivita': 0.20, 'struttura': 0.28, 'crescita': 0.12}

    # Commercio (45-47) — redditività e liquidità, struttura leggera
    if codice in ['45','46','47']:
        return {'liquidita': 0.35, 'redditivita': 0.32, 'struttura': 0.18, 'crescita': 0.15}

    # Trasporti e logistica (49-53)
    if codice in ['49','50','51','52','53']:
        return {'liquidita': 0.30, 'redditivita': 0.25, 'struttura': 0.30, 'crescita': 0.15}

    # Servizi professionali (69-75) — redditività e crescita dominano
    if codice in [str(i) for i in range(69, 76)]:
        return {'liquidita': 0.18, 'redditivita': 0.40, 'struttura': 0.12, 'crescita': 0.30}

    # ICT (58-63)
    if codice in [str(i) for i in range(58, 64)]:
        return {'liquidita': 0.20, 'redditivita': 0.35, 'struttura': 0.15, 'crescita': 0.30}

    # Default
    return {'liquidita': 0.30, 'redditivita': 0.30, 'struttura': 0.25, 'crescita': 0.15}


def _pesi_con_precursori(pesi_base, scores):
    """
    Se una capsula è in ALLERTA, il suo peso sale automaticamente
    perché un problema critico non può essere mascherato dagli altri.
    """
    pesi = dict(pesi_base)

    # Capsula in ALLERTA (score < 35) → peso minimo 40%
    allerte = [k for k, v in scores.items() if v < 35]

    if len(allerte) == 1:
        cap = allerte[0]
        delta = 0.40 - pesi[cap]
        if delta > 0:
            # Sottrai proporzionalmente dagli altri
            altri = [k for k in pesi if k != cap]
            totale_altri = sum(pesi[k] for k in altri)
            for k in altri:
                pesi[k] = round(pesi[k] - delta * (pesi[k] / totale_altri), 4)
            pesi[cap] = 0.40

    elif len(allerte) >= 2:
        # Due allerte → sistema in crisi, liquidità e struttura dominano
        pesi = {'liquidita': 0.40, 'redditivita': 0.20, 'struttura': 0.30, 'crescita': 0.10}

    return pesi


def _score_to_rating(score):
    """Converte score 0-100 in rating proprietario Oracolo Lens."""
    if score >= 90: return 'AAA'
    if score >= 80: return 'AA'
    if score >= 70: return 'A'
    if score >= 60: return 'BBB'
    if score >= 50: return 'BB'
    if score >= 40: return 'B'
    if score >= 30: return 'CCC'
    if score >= 20: return 'CC'
    if score >= 10: return 'C'
    return 'D'


def _motore_capsule(d, d_prec, ateco=None):
    def safe(val, default=0):
        return val if val is not None else default

    def pct_var(curr, prev):
        if not prev or prev == 0: return None
        return round((curr - prev) / abs(prev) * 100, 1)

    fat   = safe(d.get('fatturato'))
    ebitda = safe(d.get('ebitda')) or safe(d.get('ebitda_rettificato'))
    ebit  = safe(d.get('ebit'))
    un    = safe(d.get('utile_netto'))
    ta    = safe(d.get('totale_attivo'))
    pn    = safe(d.get('patrimonio_netto'))
    df    = safe(d.get('debiti_finanziari')) or (safe(d.get('debiti_finanziari_lungo')) + safe(d.get('debiti_finanziari_breve')))
    cc    = safe(d.get('crediti_clienti'))
    dfor  = safe(d.get('debiti_fornitori'))
    cassa = safe(d.get('cassa'))

    fat_prec  = safe(d_prec.get('fatturato'))        if d_prec else 0
    ebit_prec = safe(d_prec.get('ebit'))             if d_prec else 0
    pn_prec   = safe(d_prec.get('patrimonio_netto')) if d_prec else 0

    risultato = {}

    # ── CAPSULA LIQUIDITÀ ────────────────────────────────────────────────
    dso = round(cc / fat * 365, 1) if fat > 0 else None
    dpo = round(dfor / fat * 365, 1) if fat > 0 else None
    ciclo_cassa = round(dso - dpo, 1) if dso and dpo else None
    current_ratio = round((cc + cassa) / df, 2) if df > 0 else None

    liq_score = 50.0
    liq_flags = []
    if dso:
        if dso < 60:    liq_score += 15; liq_flags.append(f'DSO ottimo {dso}gg')
        elif dso < 90:  liq_score += 5;  liq_flags.append(f'DSO nella norma {dso}gg')
        elif dso < 120: liq_score -= 10; liq_flags.append(f'DSO elevato {dso}gg — rischio incasso')
        else:           liq_score -= 25; liq_flags.append(f'DSO critico {dso}gg — potere contrattuale eroso')
    if ciclo_cassa is not None:
        if ciclo_cassa < 30:  liq_score += 10; liq_flags.append('ciclo cassa positivo')
        elif ciclo_cassa > 90: liq_score -= 15; liq_flags.append('ciclo cassa teso — fabbisogno finanziario strutturale')
    if current_ratio:
        if current_ratio > 1.5: liq_score += 10
        elif current_ratio < 0.8: liq_score -= 20; liq_flags.append('copertura debiti a breve insufficiente')

    liq_score = max(0, min(100, liq_score))

    # ── CAPSULA REDDITIVITÀ ──────────────────────────────────────────────
    ebitda_margin = round(ebitda / fat * 100, 1) if fat > 0 and ebitda else None
    ebit_margin   = round(ebit / fat * 100, 1)   if fat > 0 and ebit else None
    roe           = round(un / pn * 100, 1)       if pn > 0 and un else None
    roa           = round(ebit / ta * 100, 1)     if ta > 0 and ebit else None

    red_score = 50.0
    red_flags = []
    if ebitda_margin is not None:
        if ebitda_margin > 15:   red_score += 20; red_flags.append(f'EBITDA margin eccellente {ebitda_margin}%')
        elif ebitda_margin > 8:  red_score += 10; red_flags.append(f'EBITDA margin buono {ebitda_margin}%')
        elif ebitda_margin > 3:  red_score += 0;  red_flags.append(f'EBITDA margin compresso {ebitda_margin}%')
        else:                    red_score -= 20; red_flags.append(f'EBITDA margin critico {ebitda_margin}% — struttura costi da rivedere')
    if roe is not None:
        if roe > 15:   red_score += 15
        elif roe > 5:  red_score += 5
        elif roe < 0:  red_score -= 20; red_flags.append('ROE negativo — distruzione di valore')
    if roa is not None:
        if roa > 8:    red_score += 10
        elif roa < 2:  red_score -= 10; red_flags.append('ROA basso — attivo non genera rendimento')

    red_score = max(0, min(100, red_score))

    # ── CAPSULA STRUTTURA ────────────────────────────────────────────────
    lev         = round(df / pn, 2)         if pn > 0 and df else None
    debt_ebitda = round(df / ebitda, 1)     if ebitda > 0 and df else None
    equity_ratio = round(pn / ta * 100, 1)  if ta > 0 and pn else None

    str_score = 50.0
    str_flags = []
    if lev is not None:
        if lev < 1:    str_score += 20; str_flags.append(f'leverage ottimo {lev}x')
        elif lev < 2:  str_score += 10; str_flags.append(f'leverage accettabile {lev}x')
        elif lev < 4:  str_score -= 10; str_flags.append(f'leverage elevato {lev}x')
        else:          str_score -= 25; str_flags.append(f'leverage critico {lev}x — dipendenza da debito')
    if debt_ebitda is not None:
        if debt_ebitda < 2:   str_score += 10
        elif debt_ebitda > 5: str_score -= 15; str_flags.append(f'Debt/EBITDA {debt_ebitda}x — rientro debito lento')
    if equity_ratio is not None:
        if equity_ratio > 40: str_score += 10; str_flags.append(f'solidità patrimoniale {equity_ratio}%')
        elif equity_ratio < 15: str_score -= 15; str_flags.append('sottocapitalizzazione — vulnerabilità strutturale')

    str_score = max(0, min(100, str_score))

    # ── CAPSULA CRESCITA ─────────────────────────────────────────────────
    cagr_fat  = pct_var(fat, fat_prec)
    cagr_ebit = pct_var(ebit, ebit_prec)
    qualita   = round(cagr_ebit - cagr_fat, 1) if cagr_fat and cagr_ebit else None

    cre_score = 50.0
    cre_flags = []
    if cagr_fat is not None:
        if cagr_fat > 15:    cre_score += 20; cre_flags.append(f'crescita forte +{cagr_fat}%')
        elif cagr_fat > 5:   cre_score += 10; cre_flags.append(f'crescita buona +{cagr_fat}%')
        elif cagr_fat > 0:   cre_score += 2
        elif cagr_fat < -10: cre_score -= 25; cre_flags.append(f'contrazione ricavi {cagr_fat}%')
        else:                cre_score -= 10; cre_flags.append(f'ricavi in calo {cagr_fat}%')
    if qualita is not None:
        if qualita > 5:    cre_score += 15; cre_flags.append('crescita profittevole — margini in espansione')
        elif qualita < -5: cre_score -= 15; cre_flags.append('crescita non profittevole — costi crescono più dei ricavi')
    if d_prec is None:
        cre_flags.append('anno precedente non disponibile — trend non calcolabile')

    cre_score = max(0, min(100, cre_score))

    # ── PESI DINAMICI ────────────────────────────────────────────────────
    pesi_base = _pesi_per_ateco(ateco)
    scores_map = {
        'liquidita': liq_score, 'redditivita': red_score,
        'struttura': str_score, 'crescita': cre_score
    }
    pesi_finali = _pesi_con_precursori(pesi_base, scores_map)

    # ── SCORE GLOBALE CON PESI DINAMICI ──────────────────────────────────
    score_globale = round(
        liq_score * pesi_finali['liquidita'] +
        red_score * pesi_finali['redditivita'] +
        str_score * pesi_finali['struttura'] +
        cre_score * pesi_finali['crescita'], 1
    )

    def _stato(s):
        if s >= 70: return 'OFFENSIVO'
        if s >= 50: return 'NEUTRO'
        if s >= 35: return 'DIFENSIVO'
        return 'ALLERTA'

    def _narrativa(flags, fallback):
        return ' | '.join(flags) if flags else fallback

    risultato['liquidita'] = {
        'stato': _stato(liq_score), 'score': round(liq_score, 1),
        'rating': _score_to_rating(liq_score),
        'narrativa': _narrativa(liq_flags, 'Dati insufficienti per analisi liquidità.'),
        'kpi': {'dso': dso, 'dpo': dpo, 'ciclo_cassa': ciclo_cassa, 'current_ratio': current_ratio},
        'peso_applicato': round(pesi_finali['liquidita'] * 100, 1)
    }
    risultato['redditivita'] = {
        'stato': _stato(red_score), 'score': round(red_score, 1),
        'rating': _score_to_rating(red_score),
        'narrativa': _narrativa(red_flags, 'Dati insufficienti per analisi redditività.'),
        'kpi': {'ebitda_margin': ebitda_margin, 'ebit_margin': ebit_margin, 'roe': roe, 'roa': roa},
        'peso_applicato': round(pesi_finali['redditivita'] * 100, 1)
    }
    risultato['struttura'] = {
        'stato': _stato(str_score), 'score': round(str_score, 1),
        'rating': _score_to_rating(str_score),
        'narrativa': _narrativa(str_flags, 'Dati insufficienti per analisi struttura.'),
        'kpi': {'leverage': lev, 'debt_ebitda': debt_ebitda, 'equity_ratio': equity_ratio},
        'peso_applicato': round(pesi_finali['struttura'] * 100, 1)
    }
    risultato['crescita'] = {
        'stato': _stato(cre_score), 'score': round(cre_score, 1),
        'rating': _score_to_rating(cre_score),
        'narrativa': _narrativa(cre_flags, 'Dati storici insufficienti per analisi crescita.'),
        'kpi': {'var_fatturato': cagr_fat, 'var_ebit': cagr_ebit, 'qualita_crescita': qualita},
        'peso_applicato': round(pesi_finali['crescita'] * 100, 1)
    }
    risultato['score_globale'] = score_globale
    risultato['rating_globale'] = _score_to_rating(score_globale)
    risultato['stato_globale'] = _stato(score_globale)
    risultato['pesi_applicati'] = {k: round(v*100,1) for k,v in pesi_finali.items()}
    risultato['pesi_fonte'] = f'ATECO {ateco}' if ateco else 'default'

    return risultato
