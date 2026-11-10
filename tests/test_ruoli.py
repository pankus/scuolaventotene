"""Ruoli per edizione: l'unico ruolo globale è amministratore; comitato, relatore e docente
valgono nell'edizione in cui la persona compare (EdizionePersona)."""
from app.extensions import db
from app.models import Candidatura, EdizionePersona, Materiale, Persona

from conftest import crea_edizione, crea_utente
from test_rotte import client_di


def _ep(u, ed, ruolo, **kw):
    p = u.persona or Persona(nome=u.nome, cognome=u.cognome, utente=u)
    ep = EdizionePersona(edizione=ed, persona=p, ruolo=ruolo, **kw)
    db.session.add(ep)
    db.session.commit()
    return ep


def test_relatore_un_anno_docente_un_altro(app):
    ed24, ed26 = crea_edizione(stato="conclusa"), crea_edizione()
    u = crea_utente()
    lez = _ep(u, ed24, "relatore", titolo_lezione="Il confino")
    assert u.is_relatore and not u.is_comitato and u.ruoli() == [f"Relatore {ed24.anno}"]
    c = client_di(app, u)
    assert "Il confino" in c.get("/area/").get_data(as_text=True)
    assert c.get(f"/area/lezioni/{lez.id}/letture").status_code == 200
    r = c.post(f"/area/candidatura/edizione/{ed26.slug}", data={"tipo": "uditore"})
    assert r.status_code == 302 and Candidatura.query.filter_by(utente_id=u.id, edizione_id=ed26.id).one()


def test_relatore_e_comitato_nella_stessa_edizione(app):
    ed = crea_edizione()
    u = crea_utente()
    _ep(u, ed, "relatore", titolo_lezione="Il confino")
    _ep(u, ed, "comitato")
    assert u.is_relatore and u.comitato_di(ed)
    assert client_di(app, u).get(f"/admin/edizioni/{ed.id}/candidature").status_code == 200


def test_comitato_solo_delle_sue_edizioni(app):
    ed25, ed26 = crea_edizione(stato="chiusa"), crea_edizione()
    membro = crea_utente(ruolo="comitato", edizioni=[ed25])
    admin = crea_utente(ruolo="admin")
    c25 = Candidatura(utente=crea_utente(), edizione=ed25, stato="inviata", titolo_ud="UD 2025")
    c26 = Candidatura(utente=crea_utente(), edizione=ed26, stato="inviata", titolo_ud="UD 2026")
    db.session.add_all([c25, c26])
    db.session.commit()

    c = client_di(app, membro)
    assert c.get(f"/admin/edizioni/{ed25.id}/candidature").status_code == 200
    assert c.get(f"/admin/candidature/{c25.id}").status_code == 200
    for url in (f"/admin/edizioni/{ed26.id}/candidature", f"/admin/edizioni/{ed26.id}/candidature.csv",
                f"/admin/candidature/{c26.id}", f"/area/candidatura/{c26.id}/file"):
        assert c.get(url).status_code == 404, url
    html = c.get("/admin/").get_data(as_text=True)
    assert ed25.titolo in html and ed26.titolo not in html

    a = client_di(app, admin)
    assert a.get(f"/admin/candidature/{c26.id}").status_code == 200
    assert ed26.titolo in a.get("/admin/").get_data(as_text=True)


def test_materiale_riservato_al_comitato_della_sua_edizione(app):
    ed25, ed26 = crea_edizione(stato="conclusa"), crea_edizione()
    membro = crea_utente(ruolo="comitato", edizioni=[ed25])
    m25 = Materiale(edizione=ed25, titolo="A", stato="pubblicato", visibilita="privato")
    m26 = Materiale(edizione=ed26, titolo="B", stato="pubblicato", visibilita="privato")
    db.session.add_all([m25, m26])
    db.session.commit()
    assert m25.visibile_a(membro) and not m26.visibile_a(membro)
    assert m26.visibile_a(crea_utente(ruolo="admin"))
