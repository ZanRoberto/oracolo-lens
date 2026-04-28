"""
Oracolo Lens — Route per dati provvisori + motore capsule
Da includere in app.py con:  from routes_dati import register_routes_dati
                              register_routes_dati(app)
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
    # DATI PROVVISORI
    # ════════════════════════════════════════════════════════════════════════

    @app.route('/api/dati/provvisori/<int:client_id>', methods=['GET'])
    def get_dati_provvisori(client_id):
        u = _get_user()
        if not u:
            return jsonify({'error': 'Non autenticato'}), 401
        c = Client.query.filter_by(id=client_id, user_id=u.id).first()
        if not c:
            return jsonify({'error': 'Cliente non trovato'}), 404
        records = DatiProvvisori.query.filter_by(client_id=client_id)\
                    .order_by(DatiProvvisori.anno.desc()).all()
        return jsonify({'dati': [r.to_dict() for r in records]})

    @app.route('/api/dati/provvisori/<int:client_id>/<int:anno>', methods=['GET'])
    def get_dato_provvisorio_anno(client_id, anno):
        u = _get_user()
        if not u:
            return jsonify({'error': 'Non autenticato'}), 401
        r = DatiProvvisori.query.filter_by(client_id=client_id, anno=anno).first()
        if not r:
            return jsonify({'error': 'Non trovato'}), 404
        return jsonify({'dato': r.to_dict()})

    @app.route('/api/dati/provvisori/<int:client_id>', methods=['POST'])
    def salva_dato_provvisorio(client_id):
        """
        Salva dati provvisori da JSON manuale.
        Body: { anno, dati: {...}, note, fonte }
        """
        u = _get_user()
        if not u:
            return jsonify({'error': 'Non autenticato'}), 401
        c = Client.query.filter_by(id=client_id, user_id=u.id).first()
        if not c:
            return jsonify({'error': 'Cliente non trovato'}), 404
        d = request.get_json() or {}
        anno = d.get('anno')
        if not anno:
            return jsonify({'error': 'Anno obbligatorio'}), 400
        r = DatiProvvisori.query.filter_by(client_id=client_id, anno=anno).first()
        if not r:
            r = DatiProvvisori(client_id=client_id, user_id=u.id, anno=anno)
            db.session.add(r)
        r.fonte    = d.get('fonte', 'manuale')
        r.note     = d.get('note', '')
        r.set_dati(d.get('dati', {}))
        db.session.commit()
        return jsonify({'ok': True, 'dato': r.to_dict()})

    @app.route('/api/dati/upload/<int:client_id>', methods=['POST'])
    def upload_dato_provvisorio(client_id):
        """
        Upload PDF o Excel — estrae i dati e li salva in SQLite.
        Form-data: file=<file>, anno=<int>
        """
        u = _get_user()
        if not u:
            return jsonify({'error': 'Non autenticato'}), 401
        c = Client.query.filter_by(id=client_id, user_id=u.id).first()
        if not c:
            return jsonify({'error': 'Cliente non trovato'}), 404

        f = request.files.get('file')
        anno = request.form.get('anno', type=int)
        if not f or not anno:
            return jsonify({'error': 'File e anno obbligatori'}), 400

        nome_file = f.filename
        ext = nome_file.rsplit('.', 1)[-1].lower() if '.' in nome_file else ''

        try:
            if ext == 'pdf':
                dati, fonte = _parse_pdf(f), 'pdf'
            elif ext in ('xlsx', 'xls'):
                dati, fonte = _parse_excel(f), 'excel'
            else:
                return jsonify({'error': 'Formato non supportato. Usa PDF o Excel.'}), 400
        except Exception as e:
            return jsonify({'error': f'Errore parsing: {str(e)}'}), 500

        r = DatiProvvisori.query.filter_by(client_id=client_id, anno=anno).first()
        if not r:
            r = DatiProvvisori(client_id=client_id, user_id=u.id, anno=anno)
            db.session.add(r)
        r.fonte     = fonte
        r.nome_file = nome_file
        r.set_dati(dati)
        db.session.commit()
        return jsonify({'ok': True, 'dato': r.to_dict(), 'campi_estratti': list(dati.keys())})

    @app.route('/api/dati/provvisori/<int:client_id>/<int:anno>', methods=['DELETE'])
    def elimina_dato_provvisorio(client_id, anno):
        u = _get_user()
        if not u:
            return jsonify({'error': 'Non autenticato'}), 401
        r = DatiProvvisori.query.filter_by(client_id=client_id, anno=anno).first()
        if not r:
            return jsonify({'error': 'Non trovato'}), 404
        db.session.delete(r)
        db.session.commit()
        return jsonify({'ok': True})

    # ════════════════════════════════════════════════════════════════════════
    # MOTORE CAPSULE
    # ════════════════════════════════════════════════════════════════════════

    @app.route('/api/capsule/calcola/<int:client_id>/<int:anno>', methods=['POST'])
    def calcola_capsule(client_id, anno):
        """
        Calcola le 4 capsule per client+anno.
        Usa dati provvisori se esistono, altrimenti dati_finanziari ufficiali.
        """
        u = _get_user()
        if not u:
            return jsonify({'error': 'Non autenticato'}), 401
        c = Client.query.filter_by(id=client_id, user_id=u.id).first()
        if not c:
            return jsonify({'error': 'Cliente non trovato'}), 404

        # Recupera dati anno corrente
        prov = DatiProvvisori.query.filter_by(client_id=client_id, anno=anno).first()
        if prov:
            dati_anno = prov.get_dati()
        else:
            storico = c.get_dati()
            dati_anno = next((d for d in storico if d.get('anno') == anno), None)
            if not dati_anno:
                return jsonify({'error': f'Nessun dato per anno {anno}'}), 404

        # Recupera anno precedente per trend
        prov_prec = DatiProvvisori.query.filter_by(client_id=client_id, anno=anno-1).first()
        if prov_prec:
            dati_prec = prov_prec.get_dati()
        else:
            storico = c.get_dati()
            dati_prec = next((d for d in storico if d.get('anno') == anno-1), None)

        # Calcola capsule
        risultato = _motore_capsule(dati_anno, dati_prec, c.ateco)

        # Salva in SQLite
        cs = CapsuleStato.query.filter_by(client_id=client_id, anno=anno).first()
        if not cs:
            cs = CapsuleStato(client_id=client_id, user_id=u.id, anno=anno)
            db.session.add(cs)

        liq = risultato['liquidita']
        red = risultato['redditivita']
        str_ = risultato['struttura']
        cre = risultato['crescita']

        cs.liquidita_stato     = liq['stato']
        cs.liquidita_score     = liq['score']
        cs.liquidita_narrativa = liq['narrativa']
        cs.redditivita_stato     = red['stato']
        cs.redditivita_score     = red['score']
        cs.redditivita_narrativa = red['narrativa']
        cs.struttura_stato     = str_['stato']
        cs.struttura_score     = str_['score']
        cs.struttura_narrativa = str_['narrativa']
        cs.crescita_stato     = cre['stato']
        cs.crescita_score     = cre['score']
        cs.crescita_narrativa = cre['narrativa']
        cs.score_globale  = risultato['score_globale']
        cs.stato_globale  = risultato['stato_globale']
        db.session.commit()

        return jsonify({'ok': True, 'capsule': cs.to_dict()})

    @app.route('/api/capsule/stato/<int:client_id>/<int:anno>', methods=['GET'])
    def get_capsule_stato(client_id, anno):
        u = _get_user()
        if not u:
            return jsonify({'error': 'Non autenticato'}), 401
        cs = CapsuleStato.query.filter_by(client_id=client_id, anno=anno).first()
        if not cs:
            return jsonify({'capsule': None})
        return jsonify({'capsule': cs.to_dict()})

    @app.route('/api/capsule/storia/<int:client_id>', methods=['GET'])
    def get_capsule_storia(client_id):
        """Tutti gli anni calcolati — per mostrare trend capsule nel tempo."""
        u = _get_user()
        if not u:
            return jsonify({'error': 'Non autenticato'}), 401
        stati = CapsuleStato.query.filter_by(client_id=client_id)\
                    .order_by(CapsuleStato.anno.asc()).all()
        return jsonify({'storia': [s.to_dict() for s in stati]})


# ════════════════════════════════════════════════════════════════════════════
# PARSER PDF
# ════════════════════════════════════════════════════════════════════════════
def _parse_pdf(file_obj):
    """
    Estrae dati finanziari da PDF bilancio italiano.
    Cerca pattern numerici vicino a keyword contabili.
    """
    try:
        import pdfplumber
    except ImportError:
        raise Exception("pdfplumber non installato. Aggiungi pdfplumber a requirements.txt")

    testo = ''
    with pdfplumber.open(file_obj) as pdf:
        for page in pdf.pages:
            t = page.extract_text()
            if t:
                testo += t + '\n'

    return _estrai_dati_da_testo(testo)


# ════════════════════════════════════════════════════════════════════════════
# PARSER EXCEL
# ════════════════════════════════════════════════════════════════════════════
def _parse_excel(file_obj):
    """
    Estrae dati finanziari da Excel.
    Supporta fogli nominati CE (conto economico) e SP (stato patrimoniale).
    """
    try:
        import openpyxl
    except ImportError:
        raise Exception("openpyxl non installato. Aggiungi openpyxl a requirements.txt")

    wb = openpyxl.load_workbook(file_obj, data_only=True)
    testo = ''
    for sheet in wb.worksheets:
        for row in sheet.iter_rows(values_only=True):
            row_text = ' '.join(str(c) for c in row if c is not None)
            if row_text.strip():
                testo += row_text + '\n'

    return _estrai_dati_da_testo(testo)


# ════════════════════════════════════════════════════════════════════════════
# ESTRAZIONE DATI DA TESTO — keyword matching bilancio italiano
# ════════════════════════════════════════════════════════════════════════════
def _estrai_dati_da_testo(testo):
    """
    Cerca i valori chiave del bilancio italiano nel testo estratto.
    Restituisce un dict nel formato compatibile con i preset hardcoded.
    """
    import re

    def cerca_valore(keywords, testo, moltiplicatore=1):
        """Trova il primo numero vicino a una delle keyword."""
        for kw in keywords:
            pattern = rf'{re.escape(kw)}[^\d\-]*?([\-]?\d[\d\.\,]*)'
            m = re.search(pattern, testo, re.IGNORECASE)
            if m:
                val_str = m.group(1).replace('.', '').replace(',', '.')
                try:
                    return round(float(val_str) * moltiplicatore, 0)
                except ValueError:
                    continue
        return None

    dati = {}

    # Ricavi / Fatturato
    v = cerca_valore(['ricavi delle vendite', 'ricavi netti', 'fatturato', 'valore della produzione', 'ricavi totali'], testo)
    if v: dati['fatturato'] = v

    # EBITDA / MOL
    v = cerca_valore(['ebitda', 'mol', 'margine operativo lordo', 'risultato prima di'], testo)
    if v: dati['ebitda'] = v

    # EBIT
    v = cerca_valore(['ebit', 'risultato operativo', 'reddito operativo'], testo)
    if v: dati['ebit'] = v

    # Utile netto
    v = cerca_valore(['utile netto', 'risultato netto', 'utile d\'esercizio', 'perdita d\'esercizio'], testo)
    if v: dati['utile_netto'] = v

    # Totale attivo
    v = cerca_valore(['totale attivo', 'totale dell\'attivo', 'totale attività'], testo)
    if v: dati['totale_attivo'] = v

    # Patrimonio netto
    v = cerca_valore(['patrimonio netto', 'totale patrimonio netto', 'capitale e riserve'], testo)
    if v: dati['patrimonio_netto'] = v

    # Debiti finanziari
    v = cerca_valore(['debiti verso banche', 'debiti finanziari', 'posizione finanziaria netta', 'indebitamento finanziario'], testo)
    if v: dati['debiti_finanziari'] = v

    # Crediti clienti
    v = cerca_valore(['crediti verso clienti', 'crediti commerciali', 'crediti v/clienti'], testo)
    if v: dati['crediti_clienti'] = v

    # Debiti fornitori
    v = cerca_valore(['debiti verso fornitori', 'debiti commerciali', 'debiti v/fornitori'], testo)
    if v: dati['debiti_fornitori'] = v

    # Disponibilità liquide
    v = cerca_valore(['disponibilità liquide', 'cassa e banche', 'liquidità'], testo)
    if v: dati['cassa'] = v

    # Dipendenti
    v = cerca_valore(['numero dipendenti', 'dipendenti', 'organico'], testo)
    if v: dati['dipendenti'] = int(v)

    return dati


# ════════════════════════════════════════════════════════════════════════════
# MOTORE CAPSULE — calcolo deterministico delle 4 capsule
# ════════════════════════════════════════════════════════════════════════════
def _motore_capsule(d, d_prec, ateco=None):
    """
    Calcola le 4 capsule da dati finanziari.
    d      = dati anno corrente
    d_prec = dati anno precedente (può essere None)
    """

    def safe(val, default=0):
        return val if val is not None else default

    def pct_var(curr, prev):
        if not prev or prev == 0: return None
        return round((curr - prev) / abs(prev) * 100, 1)

    fat   = safe(d.get('fatturato'))
    ebitda = safe(d.get('ebitda'))
    ebit  = safe(d.get('ebit'))
    un    = safe(d.get('utile_netto'))
    ta    = safe(d.get('totale_attivo'))
    pn    = safe(d.get('patrimonio_netto'))
    df    = safe(d.get('debiti_finanziari'))
    cc    = safe(d.get('crediti_clienti'))
    dfor  = safe(d.get('debiti_fornitori'))
    cassa = safe(d.get('cassa'))

    fat_prec  = safe(d_prec.get('fatturato'))  if d_prec else 0
    ebit_prec = safe(d_prec.get('ebit'))       if d_prec else 0
    pn_prec   = safe(d_prec.get('patrimonio_netto')) if d_prec else 0

    risultato = {}

    # ── CAPSULA LIQUIDITÀ ────────────────────────────────────────────────
    dso = round(cc / fat * 365, 1) if fat > 0 else None       # giorni incasso
    dpo = round(dfor / fat * 365, 1) if fat > 0 else None     # giorni pagamento
    ciclo_cassa = round(dso - dpo, 1) if dso and dpo else None
    current_ratio = round((cc + cassa) / df, 2) if df > 0 else None

    liq_score = 50.0
    liq_flags = []
    if dso:
        if dso < 60:   liq_score += 15; liq_flags.append(f'DSO ottimo {dso}gg')
        elif dso < 90: liq_score += 5;  liq_flags.append(f'DSO nella norma {dso}gg')
        elif dso < 120: liq_score -= 10; liq_flags.append(f'DSO elevato {dso}gg')
        else:          liq_score -= 25; liq_flags.append(f'DSO critico {dso}gg')
    if ciclo_cassa is not None:
        if ciclo_cassa < 30:  liq_score += 10; liq_flags.append('ciclo cassa positivo')
        elif ciclo_cassa > 90: liq_score -= 15; liq_flags.append('ciclo cassa teso')
    if current_ratio:
        if current_ratio > 1.5: liq_score += 10
        elif current_ratio < 0.8: liq_score -= 20; liq_flags.append('copertura debiti insufficiente')

    liq_score = max(0, min(100, liq_score))
    if liq_score >= 70:   liq_stato = 'OFFENSIVO'
    elif liq_score >= 50: liq_stato = 'NEUTRO'
    elif liq_score >= 35: liq_stato = 'DIFENSIVO'
    else:                 liq_stato = 'ALLERTA'

    liq_narrativa = f"DSO {dso}gg — DPO {dpo}gg — ciclo cassa {ciclo_cassa}gg. " if dso else ""
    liq_narrativa += " | ".join(liq_flags) if liq_flags else "Dati insufficienti per analisi completa."

    risultato['liquidita'] = {'stato': liq_stato, 'score': round(liq_score,1), 'narrativa': liq_narrativa,
                               'kpi': {'dso': dso, 'dpo': dpo, 'ciclo_cassa': ciclo_cassa, 'current_ratio': current_ratio}}

    # ── CAPSULA REDDITIVITÀ ──────────────────────────────────────────────
    ebitda_margin = round(ebitda / fat * 100, 1) if fat > 0 else None
    ebit_margin   = round(ebit / fat * 100, 1)   if fat > 0 else None
    roe           = round(un / pn * 100, 1)       if pn > 0 else None
    roa           = round(ebit / ta * 100, 1)     if ta > 0 else None

    red_score = 50.0
    red_flags = []
    if ebitda_margin is not None:
        if ebitda_margin > 15:   red_score += 20; red_flags.append(f'EBITDA margin eccellente {ebitda_margin}%')
        elif ebitda_margin > 8:  red_score += 10; red_flags.append(f'EBITDA margin buono {ebitda_margin}%')
        elif ebitda_margin > 3:  red_score += 0;  red_flags.append(f'EBITDA margin basso {ebitda_margin}%')
        else:                    red_score -= 20; red_flags.append(f'EBITDA margin critico {ebitda_margin}%')
    if roe is not None:
        if roe > 15:   red_score += 15
        elif roe > 5:  red_score += 5
        elif roe < 0:  red_score -= 20; red_flags.append('ROE negativo')
    if roa is not None:
        if roa > 8:    red_score += 10
        elif roa < 2:  red_score -= 10

    red_score = max(0, min(100, red_score))
    if red_score >= 70:   red_stato = 'OFFENSIVO'
    elif red_score >= 50: red_stato = 'NEUTRO'
    elif red_score >= 35: red_stato = 'DIFENSIVO'
    else:                 red_stato = 'ALLERTA'

    red_narrativa = f"EBITDA {ebitda_margin}% — ROE {roe}% — ROA {roa}%. " if ebitda_margin else ""
    red_narrativa += " | ".join(red_flags) if red_flags else "Dati insufficienti."

    risultato['redditivita'] = {'stato': red_stato, 'score': round(red_score,1), 'narrativa': red_narrativa,
                                 'kpi': {'ebitda_margin': ebitda_margin, 'ebit_margin': ebit_margin, 'roe': roe, 'roa': roa}}

    # ── CAPSULA STRUTTURA ────────────────────────────────────────────────
    lev  = round(df / pn, 2)        if pn > 0 else None   # leverage
    debt_ebitda = round(df / ebitda, 1) if ebitda > 0 else None
    equity_ratio = round(pn / ta * 100, 1) if ta > 0 else None

    str_score = 50.0
    str_flags = []
    if lev is not None:
        if lev < 1:    str_score += 20; str_flags.append(f'leverage ottimo {lev}x')
        elif lev < 2:  str_score += 10; str_flags.append(f'leverage accettabile {lev}x')
        elif lev < 4:  str_score -= 10; str_flags.append(f'leverage elevato {lev}x')
        else:          str_score -= 25; str_flags.append(f'leverage critico {lev}x')
    if debt_ebitda is not None:
        if debt_ebitda < 2:   str_score += 10
        elif debt_ebitda > 5: str_score -= 15; str_flags.append(f'Debt/EBITDA alto {debt_ebitda}x')
    if equity_ratio is not None:
        if equity_ratio > 40: str_score += 10; str_flags.append(f'solidità patrimoniale {equity_ratio}%')
        elif equity_ratio < 15: str_score -= 15; str_flags.append('sottocapitalizzazione')

    str_score = max(0, min(100, str_score))
    if str_score >= 70:   str_stato = 'OFFENSIVO'
    elif str_score >= 50: str_stato = 'NEUTRO'
    elif str_score >= 35: str_stato = 'DIFENSIVO'
    else:                 str_stato = 'ALLERTA'

    str_narrativa = f"Leverage {lev}x — Debt/EBITDA {debt_ebitda}x — equity ratio {equity_ratio}%. " if lev else ""
    str_narrativa += " | ".join(str_flags) if str_flags else "Dati insufficienti."

    risultato['struttura'] = {'stato': str_stato, 'score': round(str_score,1), 'narrativa': str_narrativa,
                               'kpi': {'leverage': lev, 'debt_ebitda': debt_ebitda, 'equity_ratio': equity_ratio}}

    # ── CAPSULA CRESCITA ─────────────────────────────────────────────────
    cagr_fat  = pct_var(fat, fat_prec)
    cagr_ebit = pct_var(ebit, ebit_prec)
    cagr_pn   = pct_var(pn, pn_prec)
    qualita   = None
    if cagr_fat and cagr_ebit:
        qualita = round(cagr_ebit - cagr_fat, 1)  # positivo = crescita profittevole

    cre_score = 50.0
    cre_flags = []
    if cagr_fat is not None:
        if cagr_fat > 15:   cre_score += 20; cre_flags.append(f'crescita forte +{cagr_fat}%')
        elif cagr_fat > 5:  cre_score += 10; cre_flags.append(f'crescita buona +{cagr_fat}%')
        elif cagr_fat > 0:  cre_score += 2
        elif cagr_fat < -10: cre_score -= 25; cre_flags.append(f'contrazione ricavi {cagr_fat}%')
        else:               cre_score -= 10; cre_flags.append(f'ricavi in calo {cagr_fat}%')
    if qualita is not None:
        if qualita > 5:    cre_score += 15; cre_flags.append('crescita profittevole')
        elif qualita < -5: cre_score -= 15; cre_flags.append('crescita non profittevole')
    if d_prec is None:
        cre_flags.append('anno precedente non disponibile — trend non calcolabile')

    cre_score = max(0, min(100, cre_score))
    if cre_score >= 70:   cre_stato = 'OFFENSIVO'
    elif cre_score >= 50: cre_stato = 'NEUTRO'
    elif cre_score >= 35: cre_stato = 'DIFENSIVO'
    else:                 cre_stato = 'ALLERTA'

    cre_narrativa = f"Var. fatturato {cagr_fat}% — var. EBIT {cagr_ebit}% — qualità crescita {qualita}pp. " if cagr_fat else ""
    cre_narrativa += " | ".join(cre_flags) if cre_flags else "Dati storici insufficienti."

    risultato['crescita'] = {'stato': cre_stato, 'score': round(cre_score,1), 'narrativa': cre_narrativa,
                              'kpi': {'var_fatturato': cagr_fat, 'var_ebit': cagr_ebit, 'qualita_crescita': qualita}}

    # ── SCORE GLOBALE ────────────────────────────────────────────────────
    score_globale = round(
        liq_score * 0.30 +
        red_score * 0.30 +
        str_score * 0.25 +
        cre_score * 0.15, 1
    )
    if score_globale >= 70:   stato_globale = 'OFFENSIVO'
    elif score_globale >= 50: stato_globale = 'NEUTRO'
    elif score_globale >= 35: stato_globale = 'DIFENSIVO'
    else:                     stato_globale = 'ALLERTA'

    risultato['score_globale'] = score_globale
    risultato['stato_globale'] = stato_globale
    return risultato
