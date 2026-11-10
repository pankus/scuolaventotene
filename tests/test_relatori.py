"""Ruolo relatore (R2): account collegato alla lezione, materiali della lezione."""
import io

import pytest

from app import zotero_sync
from app.extensions import db
from app.models import Candidatura, EdizionePersona, Materiale, Persona, PropostaLettura, ZoteroItem
from app.zotero_sync import sincronizza

from conftest import crea_edizione, crea_intervento, crea_utente
from test_rotte import client_di


def crea_lezione(ed=None, utente=None, titolo="Esilio e migrazione", ordine=1):
    return crea_intervento(ed or crea_edizione(stato="chiusa"), titolo=titolo, ordine=ordine, utente=utente)


def pdf(nome="slide.pdf"):
    return (io.BytesIO(b"%PDF-1.4 prova"), nome)


# ------------------------------------------------------------------ admin
def test_admin_collega_account(app):
    iv = crea_lezione()
    (ep,) = iv.autori
    rel = crea_utente(ruolo="relatore")
    c = client_di(app, crea_utente(ruolo="admin"))
    html = c.get(f"/admin/edizioni/{iv.edizione_id}").get_data(as_text=True)
    assert rel.email in html  # tra gli account proponibili
    assert c.post(f"/admin/edizioni-persone/{ep.id}/account",
                  data={f"acc{ep.id}-utente_id": str(rel.id)}).status_code == 302
    assert c.post(f"/admin/interventi/{iv.id}",
                  data={f"iv{iv.id}-titolo": "Titolo nuovo", f"iv{iv.id}-ordine": "3"}).status_code == 302
    db.session.expire_all()
    assert (iv.titolo, iv.ordine, ep.persona.utente_id) == ("Titolo nuovo", 3, rel.id)
    assert rel.lezioni() == [iv]


def test_account_su_una_sola_persona(app):
    rel = crea_utente(ruolo="relatore")
    crea_lezione(utente=rel)
    (altra,) = crea_lezione().autori
    c = client_di(app, crea_utente(ruolo="admin"))
    c.post(f"/admin/edizioni-persone/{altra.id}/account", data={f"acc{altra.id}-utente_id": str(rel.id)})
    db.session.refresh(altra)
    assert altra.persona.utente_id is None


@pytest.mark.parametrize("ruolo", ["comitato", "relatore", "docente"])
def test_solo_admin_collega(app, ruolo):
    iv = crea_lezione()
    c = client_di(app, crea_utente(ruolo=ruolo))
    assert c.post(f"/admin/edizioni-persone/{iv.autori[0].id}/account", data={}).status_code == 403
    assert c.post(f"/admin/interventi/{iv.id}", data={}).status_code == 403
    assert c.post(f"/admin/interventi/{iv.id}/autori", data={}).status_code == 403
    assert c.post(f"/admin/interventi/{iv.id}/elimina").status_code == 403


def test_relatore_non_entra_nel_back_office(app):
    assert client_di(app, crea_utente(ruolo="relatore")).get("/admin/").status_code == 403


# ------------------------------------------------------------------ area del relatore
def test_dashboard_e_materiale_della_lezione(app):
    rel = crea_utente(ruolo="relatore")
    ep = crea_lezione(utente=rel)
    c = client_di(app, rel)
    html = c.get("/area/").get_data(as_text=True)
    assert "Le mie lezioni" in html and "Esilio e migrazione" in html
    r = c.post(f"/area/materiali/nuovo?lezione={ep.id}",
               data={"edizione_id": ep.edizione_id, "titolo": "Slide della lezione", "tipo": "slide",
                     "file": pdf()}, content_type="multipart/form-data")
    assert r.status_code == 302
    m = Materiale.query.one()
    assert (m.intervento_id, m.edizione_id, m.stato) == (ep.id, ep.edizione_id, "in_revisione")


def test_lezione_altrui(app):
    ep = crea_lezione(utente=crea_utente(ruolo="relatore"))
    altro = client_di(app, crea_utente(ruolo="relatore"))
    assert altro.get(f"/area/materiali/nuovo?lezione={ep.id}").status_code == 404
    docente = client_di(app, crea_utente())
    assert docente.get(f"/area/materiali/nuovo?lezione={ep.id}").status_code == 404
    assert "Le mie lezioni" not in docente.get("/area/").get_data(as_text=True)


def test_edizione_fissata_dalla_lezione(app):
    rel = crea_utente(ruolo="relatore")
    ep = crea_lezione(utente=rel)
    altra = crea_edizione(stato="chiusa")
    c = client_di(app, rel)
    c.post(f"/area/materiali/nuovo?lezione={ep.id}",
           data={"edizione_id": altra.id, "titolo": "X", "tipo": "slide", "file": pdf()},
           content_type="multipart/form-data")
    assert Materiale.query.count() == 0  # edizione non tra le scelte: form non valido


# ------------------------------------------------------------------ archivio
def test_archivio_separa_lezioni(app):
    ed = crea_edizione(stato="conclusa")
    ep2 = crea_lezione(ed, titolo="Seconda", ordine=2)
    ep1 = crea_lezione(ed, titolo="Prima", ordine=None)  # ordine mancante (righe vecchie)
    for titolo, lez in (("Materiale B", ep2), ("Materiale A", ep1), ("Bando", None)):
        db.session.add(Materiale(edizione=ed, titolo=titolo, intervento=lez, url="https://x.it",
                                 stato="pubblicato", visibilita="pubblico"))
    db.session.commit()
    html = client_di(app).get(f"/archivio/{ed.slug}").get_data(as_text=True)
    ordine = [html.index(t) for t in ("<h2>Lezioni</h2>", f"/interventi/{ep1.id}", f"/interventi/{ep2.id}",
                                      "<h2>Altri materiali</h2>", "Bando")]
    assert ordine == sorted(ordine)
    assert html.count("1 materiale") == 2 and "Materiale A" not in html  # sta nella pagina della lezione


# ------------------------------------------------------------------ R3: bibliografia della lezione


@pytest.fixture
def zot(app, fake_zot, monkeypatch):
    monkeypatch.setattr(zotero_sync, "client", lambda: fake_zot)
    fake_zot.metti_collezione("COL26", "Edizione 2026")
    sincronizza(zot=fake_zot)
    return fake_zot


@pytest.fixture
def relatore(app, zot):
    rel = crea_utente(ruolo="relatore")
    ep = crea_lezione(utente=rel)
    ep.edizione.zotero_collection_key = "COL26"
    db.session.commit()
    return ep, client_di(app, rel)


LIBRO = {"title": "Esuli e confinati", "autori": "Rossi, Anna", "date": "2015", "ISBN": "0306406152"}


def test_lettura_della_lezione_diretta_in_zotero(app, zot, relatore):
    ep, c = relatore
    r = c.post(f"/area/lezioni/{ep.id}/letture", data=LIBRO)
    assert r.status_code == 302
    (p,) = ep.letture
    assert (p.stato, p.candidatura_id, p.deciso_da_id is not None) == ("approvata", None, True)
    inviato = zot.creati[0]
    assert inviato["tags"] == []  # niente tag delle proposte dei docenti
    relatori = ep.edizione.zotero_relatori_key
    assert zot.collezioni[relatori]["name"] == "Relatori" and inviato["collections"] == [relatori]
    assert PropostaLettura.query.join(Candidatura).count() == 0  # non nella coda del comitato


def test_doppione_chiede_conferma(app, zot, relatore):
    ep, c = relatore
    zot.metti_item("ESIST", "Esuli e confinati", ISBN="978-0-306-40615-7")
    sincronizza(zot=zot)
    html = c.post(f"/area/lezioni/{ep.id}/letture", data=LIBRO).get_data(as_text=True)
    assert "È già nella bibliografia?" in html and 'value="ESIST"' in html
    assert not ep.letture and not zot.creati  # niente salvato finché non si sceglie

    c.post(f"/area/lezioni/{ep.id}/letture", data={**LIBRO, "visti": "ESIST", "scelta": "ESIST"})
    (p,) = ep.letture
    assert p.zotero_key == "ESIST" and not zot.creati
    data = zot.record["ESIST"]["data"]
    assert ep.edizione.zotero_relatori_key in data["collections"] and data["tags"] == []


def test_doppione_ma_opera_diversa(app, zot, relatore):
    ep, c = relatore
    zot.metti_item("ESIST", "Esuli e confinati", ISBN="978-0-306-40615-7")
    sincronizza(zot=zot)
    c.post(f"/area/lezioni/{ep.id}/letture", data={**LIBRO, "visti": "ESIST", "scelta": ""})
    assert len(zot.creati) == 1 and ep.letture[0].zotero_key != "ESIST"


def test_doppione_comparso_dopo_la_scelta(app, zot, relatore):
    """Il relatore ha visto un doppione e sceglie «crea nuovo», ma intanto un altro relatore
    ha inserito lo stesso libro: si ripropone la scelta invece di creare un doppione."""
    ep, c = relatore
    zot.metti_item("ESIST", "Esuli e confinati", ISBN="978-0-306-40615-7")
    zot.metti_item("NUOVO", "Esuli e confinati", date="2015")
    sincronizza(zot=zot)
    html = c.post(f"/area/lezioni/{ep.id}/letture",
                  data={**LIBRO, "visti": "ESIST", "scelta": ""}).get_data(as_text=True)
    assert not zot.creati and not ep.letture
    assert 'value="NUOVO"' in html and 'name="visti" value="ESIST,NUOVO"' in html


def test_senza_collezione_dell_edizione(app, zot, relatore):
    ep, c = relatore
    ep.edizione.zotero_collection_key = None
    db.session.commit()
    c.post(f"/area/lezioni/{ep.id}/letture", data=LIBRO)
    assert not ep.letture and not zot.creati


def test_bibliografia_lezione_altrui(app, zot, relatore):
    ep, _ = relatore
    altro = client_di(app, crea_utente(ruolo="relatore"))
    assert altro.get(f"/area/lezioni/{ep.id}/letture").status_code == 404
    assert altro.post(f"/area/lezioni/{ep.id}/letture", data=LIBRO).status_code == 404
    assert client_di(app, crea_utente()).get(f"/area/lezioni/{ep.id}/unita-didattiche").status_code == 404


def test_togli_lettura_resta_in_zotero(app, zot, relatore):
    ep, c = relatore
    c.post(f"/area/lezioni/{ep.id}/letture", data=LIBRO)
    (p,) = ep.letture
    key, relatori = p.zotero_key, ep.edizione.zotero_relatori_key
    c.post(f"/area/lezioni/{ep.id}/letture/{p.id}/elimina")
    assert PropostaLettura.query.count() == 0 and key in zot.record  # resta nella libreria
    assert relatori not in zot.record[key]["data"]["collections"]    # ma non in «Relatori»
    assert relatori not in [col.key for col in db.session.get(ZoteroItem, key).collezioni]


def test_togli_lettura_usata_da_altra_lezione(app, zot, relatore):
    ep, c = relatore
    c.post(f"/area/lezioni/{ep.id}/letture", data=LIBRO)
    (p,) = ep.letture
    altra = crea_lezione(ed=ep.edizione, titolo="Altra lezione", ordine=2)
    db.session.add(PropostaLettura(intervento_id=altra.id, campi={"title": "x"}, zotero_key=p.zotero_key,
                                   stato="approvata"))
    db.session.commit()
    c.post(f"/area/lezioni/{ep.id}/letture/{p.id}/elimina")
    assert ep.edizione.zotero_relatori_key in zot.record[p.zotero_key]["data"]["collections"]


def test_scollega_dalla_pagina_della_lezione(app, zot, relatore):
    ep, c = relatore
    c.post(f"/area/lezioni/{ep.id}/letture", data=LIBRO)
    (p,) = ep.letture
    sincronizza(zot=zot)
    pagina = f"/edizioni/{ep.edizione.slug}/interventi/{ep.id}"
    azione = f"/area/lezioni/{ep.id}/letture/{p.id}/elimina"
    assert azione in c.get(pagina).get_data(as_text=True)                    # autore
    assert azione in client_di(app, crea_utente(ruolo="admin")).get(pagina).get_data(as_text=True)
    assert azione not in client_di(app).get(pagina).get_data(as_text=True)   # anonimo
    assert azione not in client_di(app, crea_utente(ruolo="relatore")).get(pagina).get_data(as_text=True)
    r = c.post(azione, data={"torna": "pagina"})
    assert r.headers["Location"].endswith(pagina + "#letture")
    assert PropostaLettura.query.count() == 0 and p.zotero_key in zot.record


def test_pagina_edizione_per_lezione(app, zot, relatore):
    ep, c = relatore
    c.post(f"/area/lezioni/{ep.id}/letture", data=LIBRO)
    zot.metti_item("MANO", "Aggiunto a mano", collezioni=[ep.edizione.zotero_relatori_key])
    sincronizza(zot=zot)
    html = client_di(app).get(f"/edizioni/{ep.edizione.slug}").get_data(as_text=True)
    ordine = [html.index(t) for t in ("<h3>Relatori</h3>", "Aggiunto a mano",
                                      "<h3>Relatori · Stefano Gallo – Esilio e migrazione</h3>",
                                      "Esuli e confinati")]
    assert ordine == sorted(ordine)


# ------------------------------------------------------------------ R3: UD dei docenti ammessi
def test_ud_dei_docenti_ammessi(app, zot, relatore, tmp_path):
    ep, c = relatore
    ammesso, escluso = crea_utente(), crea_utente()
    ammesso.telefono, ammesso.residenza = "333 1234567", "Via Segreta 1"
    for u, stato, titolo in ((ammesso, "ammessa", "UD ammessa"), (escluso, "non_ammessa", "UD esclusa")):
        db.session.add(Candidatura(utente=u, edizione=ep.edizione, stato=stato, titolo_ud=titolo,
                                   file_path="candidature/x.pdf", file_nome="proposta.pdf"))
    db.session.commit()
    (tmp_path / "candidature").mkdir()
    (tmp_path / "candidature" / "x.pdf").write_bytes(b"%PDF")

    html = c.get(f"/area/lezioni/{ep.id}/unita-didattiche").get_data(as_text=True)
    assert "UD ammessa" in html and ammesso.nome_completo in html
    assert "UD esclusa" not in html
    for privato in (ammesso.email, "333 1234567", "Via Segreta", "1980"):
        assert privato not in html

    amm = Candidatura.query.filter_by(stato="ammessa").one()
    esc = Candidatura.query.filter_by(stato="non_ammessa").one()
    assert c.get(f"/area/candidatura/{amm.id}/file").status_code == 200
    assert c.get(f"/area/candidatura/{esc.id}/file").status_code == 404
    # relatore di un'altra edizione: niente
    altro_rel = crea_utente(ruolo="relatore")
    crea_lezione(utente=altro_rel)
    assert client_di(app, altro_rel).get(f"/area/candidatura/{amm.id}/file").status_code == 404


def test_vincolo_una_origine(app):
    from sqlalchemy.exc import IntegrityError
    db.session.add(PropostaLettura(tipo="book", campi={"title": "Orfana"}))
    with pytest.raises(IntegrityError):
        db.session.commit()
    db.session.rollback()


# ------------------------------------------------------------------ lezioni dal programma
def _voce(c, ed, **campi):
    dati = {"voce-tipo": "lezione", "voce-titolo": "Esuli", "voce-relatori": "Anna Neri, Luca Blu"}
    dati.update({f"voce-{k}": v for k, v in campi.items()})
    return c.post(f"/admin/edizioni/{ed.id}/programma", data=dati)


def _lezioni(ed):
    db.session.expire_all()
    return sorted((a.persona.cognome, iv.titolo) for iv in ed.interventi if not iv.ud for a in iv.autori)


def test_voce_lezione_crea_le_lezioni(app):
    ed = crea_edizione(stato="chiusa")
    c = client_di(app, crea_utente(ruolo="admin"))
    assert _voce(c, ed).status_code == 302
    assert _lezioni(ed) == [("Blu", "Esuli"), ("Neri", "Esuli")]
    _voce(c, ed, tipo="pausa", titolo="Pranzo", relatori="")
    assert len(_lezioni(ed)) == 2


def test_voce_rinominata_ed_eliminata(app):
    ed = crea_edizione(stato="bozza")
    c = client_di(app, crea_utente(ruolo="admin"))
    _voce(c, ed, relatori="Anna Neri")
    v = ed.programma[0]
    c.post(f"/admin/programma/{v.id}", data={f"v{v.id}-tipo": "lezione", f"v{v.id}-titolo": "Confinati",
                                              f"v{v.id}-relatori": "Anna Neri", f"v{v.id}-ordine": "0"})
    assert _lezioni(ed) == [("Neri", "Confinati")]
    c.post(f"/admin/programma/{v.id}/elimina")
    assert _lezioni(ed) == [("Neri", "Confinati")]  # la lezione resta


def test_pulsante_lezioni_dal_programma(app):
    from app.models import ProgrammaVoce
    ed = crea_edizione(stato="chiusa")
    db.session.add(ProgrammaVoce(edizione=ed, tipo="lezione", titolo="Esuli", relatori="Anna Neri"))
    db.session.commit()
    c = client_di(app, crea_utente(ruolo="admin"))
    assert "Crea le lezioni dal programma" in c.get(f"/admin/edizioni/{ed.id}").get_data(as_text=True)
    assert c.post(f"/admin/edizioni/{ed.id}/lezioni-dal-programma").status_code == 302
    c.post(f"/admin/edizioni/{ed.id}/lezioni-dal-programma")  # di nuovo: niente doppioni
    assert _lezioni(ed) == [("Neri", "Esuli")]


@pytest.mark.parametrize("ruolo", ["comitato", "relatore", "docente"])
def test_pulsante_solo_admin(app, ruolo):
    ed = crea_edizione(stato="chiusa")
    c = client_di(app, crea_utente(ruolo=ruolo))
    assert c.post(f"/admin/edizioni/{ed.id}/lezioni-dal-programma").status_code == 403


# ------------------------------------------------------------------ chiusura dei contenuti
def test_contenuti_chiusi_dopo_la_data(app):
    from datetime import date, timedelta
    rel = crea_utente()
    ep = crea_lezione(utente=rel)
    ed = ep.edizione
    assert ed.contenuti_aperti and rel.puo_modificare(ed)
    ed.chiusura_contenuti = date.today()
    db.session.commit()
    assert ed.contenuti_aperti  # il giorno stesso si può ancora
    ed.chiusura_contenuti = date.today() - timedelta(days=1)
    db.session.commit()
    assert not ed.contenuti_aperti and not rel.puo_modificare(ed)

    c = client_di(app, rel)
    assert c.get(f"/area/lezioni/{ep.id}/letture").status_code == 200  # si consulta
    assert c.post(f"/area/lezioni/{ep.id}/letture", data={"title": "X"}).status_code == 403
    assert c.get(f"/area/materiali/nuovo?lezione={ep.id}").status_code == 403
    assert "contenuti chiusi" in c.get("/area/").get_data(as_text=True)

    admin = crea_utente(ruolo="admin")
    assert admin.puo_modificare(ed)
    r = client_di(app, admin).post(f"/area/materiali/nuovo?lezione={ep.id}",
                                   data={"edizione_id": ed.id, "titolo": "Slide", "tipo": "slide",
                                         "file": pdf()}, content_type="multipart/form-data")
    assert r.status_code == 302 and Materiale.query.one().intervento_id == ep.id


def test_docente_contenuti_chiusi(app):
    from datetime import date, timedelta
    ed = crea_edizione(stato="conclusa")
    c = Candidatura(utente=crea_utente(), edizione=ed, stato="ammessa")
    db.session.add(c)
    db.session.commit()
    assert c.dopo_la_scuola and c.letture_aperte
    ed.chiusura_contenuti = date.today() - timedelta(days=1)
    db.session.commit()
    assert not c.dopo_la_scuola and not c.letture_aperte
    assert client_di(app, c.utente).get(f"/area/materiali/nuovo?candidatura={c.id}").status_code == 404
