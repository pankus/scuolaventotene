"""Invito alla lettura pubblico (F7): sezioni con sottosezioni, copertine, schede, comitato."""
import os

from app.extensions import db
from app.models import Candidatura, PropostaLettura, ZoteroCollezione, ZoteroItem

from conftest import crea_edizione, crea_utente
from test_rotte import client_di


def libreria(app):
    """Edizione → Relatori, Docenti; un item per collezione, uno con copertina locale."""
    ed_col = ZoteroCollezione(key="ED", nome="Edizione 2026")
    rel = ZoteroCollezione(key="REL", nome="Relatori", parent_key="ED")
    doc = ZoteroCollezione(key="DOC", nome="Docenti", parent_key="ED")
    altra = ZoteroCollezione(key="ALT", nome="Altro")
    os.makedirs(os.path.join(app.config["UPLOAD_FOLDER"], "copertine"))
    with open(os.path.join(app.config["UPLOAD_FOLDER"], "copertine", "c.jpg"), "wb") as f:
        f.write(b"\xff\xd8\xff jpeg")
    items = [ZoteroItem(key="R1", titolo="Libro del relatore", tipo="book", collezioni=[rel]),
             ZoteroItem(key="D1", titolo="Libro del docente", tipo="book", isbn="9780306406157",
                        copertina_path="copertine/c.jpg", collezioni=[doc]),
             ZoteroItem(key="W1", titolo="Sito d'archivio", tipo="webpage",
                        url="https://archivio.example/", collezioni=[doc]),
             ZoteroItem(key="A1", titolo="Fuori edizione", tipo="book", collezioni=[altra]),
             ZoteroItem(key="X1", titolo="Nel cestino", tipo="book", eliminato=True,
                        copertina_path="copertine/c.jpg", collezioni=[doc])]
    db.session.add_all([ed_col, rel, doc, altra, *items])
    db.session.commit()


def test_sezione_include_le_sottosezioni(app, client):
    libreria(app)
    html = client.get("/bibliografia?collezione=ED").get_data(as_text=True)
    assert "Libro del relatore" in html and "Libro del docente" in html
    assert "Fuori edizione" not in html and "Nel cestino" not in html
    html = client.get("/bibliografia?collezione=DOC").get_data(as_text=True)
    assert "Libro del docente" in html and "Libro del relatore" not in html


def test_scheda_con_copertina_isbn_e_link(app, client):
    libreria(app)
    html = client.get("/bibliografia").get_data(as_text=True)
    assert 'src="/bibliografia/copertine/D1"' in html and "ISBN 9780306406157" in html
    assert 'href="https://archivio.example/"' in html
    r = client.get("/bibliografia/copertine/D1")
    assert r.status_code == 200 and r.mimetype == "image/jpeg"
    for key in ("R1", "X1", "NESSUNO"):  # senza copertina, nel cestino, inesistente
        assert client.get(f"/bibliografia/copertine/{key}").status_code == 404


def test_nessun_dato_del_docente(app, client):
    libreria(app)
    docente = crea_utente()
    c = Candidatura(utente=docente, edizione=crea_edizione(stato="chiusa"), stato="ammessa")
    db.session.add(PropostaLettura(candidatura=c, campi={"title": "Libro del docente"},
                                   motivazione="La uso in terza", zotero_key="D1", stato="approvata"))
    db.session.commit()
    html = client.get("/bibliografia").get_data(as_text=True)
    assert docente.cognome not in html and "La uso in terza" not in html


def test_letture_nella_scheda_del_comitato(app):
    c = Candidatura(utente=crea_utente(), edizione=crea_edizione(), stato="inviata")
    p = PropostaLettura(candidatura=c, campi={"title": "Proposta del docente"})
    db.session.add(p)
    db.session.commit()
    html = client_di(app, crea_utente(ruolo="comitato")).get(
        f"/admin/candidature/{c.id}").get_data(as_text=True)
    assert "Proposta del docente" in html and f'href="/admin/letture/{p.id}"' in html
