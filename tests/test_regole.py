"""Regole del bando e logica di modello, senza passare dalle rotte."""
from datetime import date, datetime, timedelta

import docx
import pytest
from flask_login import AnonymousUserMixin

from app.extensions import db
from app.models import Candidatura, Materiale, Valutazione
from app.utils import conta_caratteri
from app.views.admin import _graduatoria

from conftest import crea_edizione, crea_utente

OGGI = date.today()


# ------------------------------------------------------------------ candidature_aperte
@pytest.mark.parametrize("stato, scadenza, atteso", [
    ("aperta", OGGI + timedelta(days=1), True),
    ("aperta", OGGI, True),
    ("aperta", OGGI - timedelta(days=1), False),
    ("aperta", None, True),
    ("bozza", None, False),
    ("chiusa", None, False),
    ("conclusa", None, False),
])
def test_candidature_aperte(app, stato, scadenza, atteso):
    assert crea_edizione(stato=stato, scadenza=scadenza).candidature_aperte is atteso


# ------------------------------------------------------------------ problemi_invio
def _cand(utente=None, **kw):
    dati = dict(tipo="borsista", titolo_ud="UD di prova", file_path="x.docx", n_caratteri=7000)
    dati.update(kw)
    c = Candidatura(utente=utente or crea_utente(), edizione=crea_edizione(), **dati)
    db.session.add(c)
    db.session.commit()
    return c


def test_candidatura_completa_senza_problemi(app):
    assert _cand().problemi_invio() == []


@pytest.mark.parametrize("campo", ["data_nascita", "telefono", "residenza"])
def test_profilo_incompleto(app, campo):
    u = crea_utente()
    setattr(u, campo, None)
    problemi = _cand(utente=u).problemi_invio()
    assert len(problemi) == 1 and "Completa il profilo" in problemi[0]


def test_email_non_verificata(app):
    problemi = _cand(utente=crea_utente(verificata=False)).problemi_invio()
    assert len(problemi) == 1 and "email" in problemi[0]


def test_borsista_senza_titolo_e_senza_file(app):
    problemi = _cand(titolo_ud=None, file_path=None).problemi_invio()
    assert len(problemi) == 2


@pytest.mark.parametrize("n, ok", [(5999, False), (6000, True), (8000, True), (8001, False),
                                   (None, True)])  # None: PDF/ODT, non contato
def test_limiti_caratteri(app, n, ok):
    assert (_cand(n_caratteri=n).problemi_invio() == []) is ok


def test_uditore_non_serve_ud(app):
    assert _cand(tipo="uditore", titolo_ud=None, file_path=None).problemi_invio() == []


# ------------------------------------------------------------------ conta_caratteri
def test_conta_caratteri_docx(app, tmp_path):
    d = docx.Document()
    d.add_paragraph("Ciao mondo")       # 10 caratteri, spazio incluso
    d.add_table(rows=1, cols=1).cell(0, 0).text = "abc"
    d.save(tmp_path / "prova.docx")
    assert conta_caratteri("prova.docx") == 13
    assert conta_caratteri("prova.pdf") is None


# ------------------------------------------------------------------ visibilità materiali
def test_visibile_a(app):
    anonimo, docente, autore = AnonymousUserMixin(), crea_utente(), crea_utente()
    comitato = crea_utente(ruolo="comitato")
    ed = crea_edizione()

    def m(stato, visibilita):
        return Materiale(edizione_id=ed.id, titolo="M", stato=stato, visibilita=visibilita,
                         caricato_da_id=autore.id)

    casi = [  # (stato, visibilità) → (anonimo, docente, autore, comitato)
        ("pubblicato", "pubblico", (True, True, True, True)),
        ("pubblicato", "registrati", (False, True, True, True)),
        ("pubblicato", "privato", (False, False, True, True)),
        ("in_revisione", "pubblico", (False, False, True, True)),
        ("rifiutato", "pubblico", (False, False, True, True)),
    ]
    for stato, vis, attesi in casi:
        mat = m(stato, vis)
        ottenuti = tuple(mat.visibile_a(u) for u in (anonimo, docente, autore, comitato))
        assert ottenuti == attesi, (stato, vis)


# ------------------------------------------------------------------ graduatoria
def test_graduatoria(app):
    ed = crea_edizione()
    valutatori = [crea_utente(ruolo="comitato") for _ in range(2)]

    def cand(tipo, stato="inviata", punteggi=(), inviata=datetime(2026, 1, 1)):
        c = Candidatura(utente=crea_utente(), edizione=ed, tipo=tipo, stato=stato, inviata_il=inviata)
        db.session.add(c)
        for v, (o, p, f) in zip(valutatori, punteggi):
            c.valutazioni.append(Valutazione(valutatore_id=v.id, originalita=o, potenzialita=p, fonti=f))
        return c

    bozza = cand("borsista", stato="bozza", punteggi=[(25, 25, 25)])
    alta = cand("borsista", punteggi=[(20, 20, 20), (25, 25, 25)])        # media 67.5
    bassa_prima = cand("borsista", punteggi=[(10, 10, 10)], inviata=datetime(2026, 1, 1))
    bassa_dopo = cand("borsista", punteggi=[(10, 10, 10)], inviata=datetime(2026, 1, 2))
    senza_voti = cand("borsista")
    uditore = cand("uditore", punteggi=[(25, 25, 25)])
    db.session.commit()

    assert alta.punteggio_medio == 67.5
    assert senza_voti.punteggio_medio is None
    assert _graduatoria(ed) == [alta, bassa_prima, bassa_dopo, senza_voti, uditore]
    assert bozza not in _graduatoria(ed)
