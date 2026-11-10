"""Permessi delle rotte e download controllati, tramite il client di test."""
from datetime import date, timedelta

import pytest

from app.extensions import db
from app.models import Candidatura, Materiale

from conftest import PASSWORD, crea_edizione, crea_utente, login


def client_di(app, utente=None):
    """Un client separato per utente, così le sessioni non si mescolano."""
    c = app.test_client()
    if utente:
        login(c, utente)
    return c


# ------------------------------------------------------------------ back-office
@pytest.mark.parametrize("ruolo, atteso", [(None, 302), ("docente", 403), ("comitato", 200), ("admin", 200)])
def test_admin_dashboard_e_csv(app, ruolo, atteso):
    ed = crea_edizione()
    c = client_di(app, crea_utente(ruolo=ruolo) if ruolo else None)
    assert c.get("/admin/").status_code == atteso
    r = c.get(f"/admin/edizioni/{ed.id}/candidature.csv")
    assert r.status_code == atteso
    if atteso == 200:
        assert r.data.decode("utf-8").startswith("﻿Pos.;Cognome")


@pytest.mark.parametrize("url", ["/admin/utenti", "/admin/edizioni/nuova"])
@pytest.mark.parametrize("ruolo, atteso", [("comitato", 403), ("admin", 200)])
def test_rotte_solo_admin(app, url, ruolo, atteso):
    assert client_di(app, crea_utente(ruolo=ruolo)).get(url).status_code == atteso


# ------------------------------------------------------------------ area docente
def test_area_richiede_login(app):
    assert client_di(app).get("/area/").status_code == 302
    assert client_di(app, crea_utente()).get("/area/").status_code == 200


def _candidatura(app, autore, edizione=None):
    with open(f"{app.config['UPLOAD_FOLDER']}/ud.pdf", "wb") as f:
        f.write(b"%PDF")
    c = Candidatura(utente=autore, edizione=edizione or crea_edizione(), tipo="borsista",
                    titolo_ud="UD", file_path="ud.pdf", file_nome="ud.pdf")
    db.session.add(c)
    db.session.commit()
    return c


def test_candidatura_di_altri_non_visibile(app):
    autore, altro, comitato = crea_utente(), crea_utente(), crea_utente(ruolo="comitato")
    cand = _candidatura(app, autore)
    c_altro = client_di(app, altro)
    assert c_altro.get(f"/area/candidatura/{cand.id}").status_code == 404
    assert c_altro.get(f"/area/candidatura/{cand.id}/file").status_code == 404
    assert client_di(app, autore).get(f"/area/candidatura/{cand.id}/file").status_code == 200
    assert client_di(app, comitato).get(f"/area/candidatura/{cand.id}/file").status_code == 200


def test_invio_bloccato_se_ci_sono_problemi(app):
    autore = crea_utente(completo=False)
    cand = _candidatura(app, autore)
    client_di(app, autore).post(f"/area/candidatura/{cand.id}/invia")
    db.session.refresh(cand)
    assert cand.stato == "bozza"


def test_invio_riuscito(app):
    autore = crea_utente()
    cand = _candidatura(app, autore)
    client_di(app, autore).post(f"/area/candidatura/{cand.id}/invia")
    db.session.refresh(cand)
    assert cand.stato == "inviata" and cand.inviata_il is not None


def test_invio_dopo_scadenza(app):
    autore = crea_utente()
    ed = crea_edizione(scadenza=date.today() - timedelta(days=1))
    cand = _candidatura(app, autore, edizione=ed)
    assert client_di(app, autore).post(f"/area/candidatura/{cand.id}/invia").status_code == 400


# ------------------------------------------------------------------ download materiali
def test_scarica_materiale(app):
    autore, docente, comitato = crea_utente(), crea_utente(), crea_utente(ruolo="comitato")
    ed = crea_edizione(stato="conclusa")
    with open(f"{app.config['UPLOAD_FOLDER']}/m.pdf", "wb") as f:
        f.write(b"%PDF")

    def materiale(stato, visibilita):
        m = Materiale(edizione=ed, titolo="M", stato=stato, visibilita=visibilita, file_path="m.pdf",
                      file_nome="m.pdf", mime="application/pdf", caricato_da_id=autore.id)
        db.session.add(m)
        db.session.commit()
        return f"/materiali/{m.id}/scarica"

    anonimo, c_docente = client_di(app), client_di(app, docente)
    c_autore, c_comitato = client_di(app, autore), client_di(app, comitato)

    url = materiale("pubblicato", "pubblico")
    assert anonimo.get(url).status_code == 200

    url = materiale("pubblicato", "registrati")
    assert anonimo.get(url).status_code == 404
    assert c_docente.get(url).status_code == 200

    url = materiale("in_revisione", "pubblico")
    assert c_docente.get(url).status_code == 404
    assert c_autore.get(url).status_code == 200
    assert c_comitato.get(url).status_code == 200


@pytest.mark.parametrize("nxt,atteso", [("/area/profilo", "/area/profilo"), ("//evil.com", "/area/"),
                                        ("/\\evil.com", "/area/"), ("https://evil.com", "/area/")])
def test_login_next_solo_interno(app, nxt, atteso):
    u = crea_utente()
    r = app.test_client().post("/accedi", query_string={"next": nxt},
                               data={"email": u.email, "password": PASSWORD})
    assert r.headers["Location"] == atteso


def test_secret_key_obbligatoria_fuori_dai_test():
    from app import create_app
    from config import Config

    class Prod(Config):
        SECRET_KEY = "cambiami-in-produzione"
        SQLALCHEMY_DATABASE_URI = "sqlite:///:memory:"

    with pytest.raises(RuntimeError):
        create_app(Prod)


def test_elimina_utente(app):
    from app.models import Utente, Valutazione
    admin, comitato = crea_utente(ruolo="admin"), crea_utente(ruolo="comitato")
    prova = crea_utente()
    cand = _candidatura(app, prova)
    db.session.add(Valutazione(candidatura=cand, valutatore=comitato))
    db.session.commit()
    c = client_di(app, admin)
    assert client_di(app, comitato).post(f"/admin/utenti/{prova.id}/elimina").status_code == 403
    c.post(f"/admin/utenti/{admin.id}/elimina")      # sé stesso: no
    c.post(f"/admin/utenti/{comitato.id}/elimina")   # ha valutato: no
    c.post(f"/admin/utenti/{prova.id}/elimina")
    db.session.expire_all()
    assert db.session.get(Utente, admin.id) and db.session.get(Utente, comitato.id)
    assert db.session.get(Utente, prova.id) is None
    assert Candidatura.query.count() == 0 and Valutazione.query.count() == 0
    import os
    assert not os.path.exists(f"{app.config['UPLOAD_FOLDER']}/ud.pdf")


def test_programma_modifica_e_ordine(app):
    from app.models import ProgrammaVoce
    admin, comitato = crea_utente(ruolo="admin"), crea_utente(ruolo="comitato")
    ed, altra = crea_edizione(), crea_edizione()
    c = client_di(app, admin)
    for t in ("A", "B", "C"):  # senza ordine: in fondo
        c.post(f"/admin/edizioni/{ed.id}/programma", data={"voce-titolo": t, "voce-tipo": "lezione"})
    a, b, cc = sorted(ed.programma, key=lambda v: v.ordine)
    assert [v.titolo for v in (a, b, cc)] == ["A", "B", "C"]
    estranea = ProgrammaVoce(edizione=altra, titolo="X", ordine=7)
    db.session.add(estranea)
    db.session.commit()

    assert client_di(app, comitato).post(f"/admin/edizioni/{ed.id}/programma/ordine",
                                         data={"id": [cc.id]}).status_code == 403
    r = c.post(f"/admin/edizioni/{ed.id}/programma/ordine", data={"id": [cc.id, estranea.id, b.id, a.id]})
    assert r.status_code == 204
    db.session.expire_all()
    assert [v.titolo for v in ed.programma] == ["C", "B", "A"] and estranea.ordine == 7

    assert client_di(app, comitato).post(f"/admin/programma/{a.id}").status_code == 403
    c.post(f"/admin/programma/{a.id}", data={f"v{a.id}-titolo": "A2", f"v{a.id}-tipo": "lezione",
                                            f"v{a.id}-giorno": "2026-09-01", f"v{a.id}-ordine": "3"})
    db.session.expire_all()
    assert a.titolo == "A2" and str(a.giorno) == "2026-09-01" and a.ordine == 3
    assert "A2" in c.get(f"/admin/edizioni/{ed.id}").data.decode()


def test_admin_modifica_nome_utente(app):
    admin, docente, comitato = crea_utente(ruolo="admin"), crea_utente(), crea_utente(ruolo="comitato")
    c = client_di(app, admin)
    assert client_di(app, comitato).post(f"/admin/utenti/{docente.id}",
                                         data={"nome": "X", "cognome": "Y"}).status_code == 403
    c.post(f"/admin/utenti/{docente.id}", data={"nome": " Maria Gloria ", "cognome": "Calì",
                                               "admin": "1", "attivo": "1"})
    c.post(f"/admin/utenti/{docente.id}", data={"nome": "", "cognome": "Vuoto"})  # rifiutato
    c.post(f"/admin/utenti/{admin.id}", data={"nome": "Io", "cognome": "Admin"})  # senza admin=1
    db.session.expire_all()
    assert (docente.nome, docente.cognome, docente.admin, docente.attivo) == ("Maria Gloria", "Calì", True, True)
    assert (admin.nome, admin.cognome, admin.admin) == ("Io", "Admin", True)  # il proprio ruolo non cambia


def test_utenti_edizioni_e_filtri(app):
    from app.models import EdizionePersona, Persona
    admin = crea_utente(ruolo="admin")
    ed24, ed23 = crea_edizione(stato="conclusa"), crea_edizione(stato="conclusa")
    docente, relatore, solo, candidato = crea_utente(), crea_utente(ruolo="relatore"), crea_utente(), crea_utente()
    for ed, u, ruolo in ((ed24, docente, "docente"), (ed23, relatore, "relatore")):
        db.session.add(EdizionePersona(edizione=ed, ruolo=ruolo,
                                       persona=Persona(nome=u.nome, cognome=u.cognome, utente_id=u.id)))
    db.session.add(Candidatura(utente=candidato, edizione=ed24, stato="inviata"))
    db.session.commit()
    c = client_di(app, admin)

    def mostra(qs=""):
        return c.get(f"/admin/utenti{qs}").data.decode()

    html = mostra()
    assert f"{ed24.anno}</strong> · Docente" in html and f"{ed23.anno}</strong> · Relatore" in html
    assert f"{ed24.anno} · candidatura inviata" in html and "nessuna edizione" in html
    assert 'aria-current="page">Utenti</a>' in html and 'aria-current="page">Cruscotto</a>' not in html

    html = mostra(f"?edizione={ed24.id}&gruppo=docenti")
    assert docente.email in html and relatore.email not in html and candidato.email not in html
    html = mostra(f"?edizione={ed24.id}")
    assert docente.email in html and candidato.email in html and relatore.email not in html
    html = mostra("?gruppo=relatori")
    assert relatore.email in html and docente.email not in html
    html = mostra("?gruppo=nessuno")
    assert solo.email in html and docente.email not in html and candidato.email not in html

    dati = {"nome": "N", "cognome": "C", "attivo": "1"}
    r = c.post(f"/admin/utenti/{solo.id}", data=dati | {"ritorno": "/admin/utenti?gruppo=nessuno"})
    assert r.headers["Location"].endswith("/admin/utenti?gruppo=nessuno")
    r = c.post(f"/admin/utenti/{solo.id}", data=dati | {"ritorno": "//evil.example/"})
    assert r.headers["Location"].endswith("/admin/utenti")


def test_utenti_sposta_e_aggiungi_edizione(app):
    from app.models import EdizionePersona, Persona
    admin, comitato = crea_utente(ruolo="admin"), crea_utente(ruolo="comitato")
    ed1, ed2 = crea_edizione(stato="conclusa"), crea_edizione(stato="conclusa")
    docente, nuovo, altro = crea_utente(), crea_utente(ruolo="relatore"), crea_utente()
    from app.models import Intervento
    ep = EdizionePersona(edizione=ed1, ruolo="docente",
                         persona=Persona(nome=docente.nome, cognome=docente.cognome, utente_id=docente.id))
    iv = Intervento(edizione=ed1, tipo="ud", titolo="UD")
    db.session.add_all([ep, iv])
    iv.aggiungi_autore(ep)
    db.session.add(Materiale(edizione=ed1, titolo="Slide", intervento=iv))
    omonimo = Persona(nome=nuovo.nome, cognome=nuovo.cognome)  # dal programma, senza account
    db.session.add(omonimo)
    db.session.commit()
    c = client_di(app, admin)
    url = f"/admin/utenti/{docente.id}/edizione"

    assert client_di(app, comitato).post(url, data={"epid": ep.id, "edizione": ed2.id}).status_code == 403
    assert c.post(f"/admin/utenti/{altro.id}/edizione", data={"epid": ep.id, "edizione": ed2.id}).status_code == 404
    c.post(url, data={"epid": ep.id, "edizione": ed2.id})
    db.session.expire_all()
    assert ep.edizione_id == iv.edizione_id == ed2.id and iv.titolo == "UD" and iv.materiali[0].edizione_id == ed2.id

    c.post(f"/admin/utenti/{nuovo.id}/edizione", data={"edizione": ed1.id})  # senza ruolo: rifiutato
    assert not EdizionePersona.query.filter_by(persona_id=omonimo.id).all()
    c.post(f"/admin/utenti/{nuovo.id}/edizione", data={"edizione": ed1.id, "ruolo": "relatore"})
    c.post(f"/admin/utenti/{nuovo.id}/edizione", data={"edizione": ed1.id, "ruolo": "relatore"})  # niente doppione
    db.session.expire_all()
    eps = EdizionePersona.query.filter_by(persona_id=omonimo.id).all()
    assert [(e.edizione_id, e.ruolo) for e in eps] == [(ed1.id, "relatore")] and omonimo.utente_id == nuovo.id
    html = c.get("/admin/utenti").data.decode()
    assert ">Sposta</button>" in html and ">Aggiungi</button>" in html
