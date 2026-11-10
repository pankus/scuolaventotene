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
    html = client.get("/bibliografia?tutto=1").get_data(as_text=True)
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
    html = client.get("/bibliografia?tutto=1").get_data(as_text=True)
    assert docente.cognome not in html and "La uso in terza" not in html


def test_letture_nella_scheda_del_comitato(app):
    c = Candidatura(utente=crea_utente(), edizione=crea_edizione(), stato="inviata")
    p = PropostaLettura(candidatura=c, campi={"title": "Proposta del docente"})
    db.session.add(p)
    db.session.commit()
    html = client_di(app, crea_utente(ruolo="comitato")).get(
        f"/admin/candidature/{c.id}").get_data(as_text=True)
    assert "Proposta del docente" in html and f'href="/admin/letture/{p.id}"' in html


def test_riferimenti_di_base_in_ogni_edizione(app, client):
    libreria(app)
    base = ZoteroCollezione(key="BASE", nome="Riferimenti di base")
    db.session.add(base)
    db.session.add(ZoteroItem(key="B1", titolo="Manuale di base", tipo="book", collezioni=[base]))
    r1 = db.session.get(ZoteroItem, "R1")
    r1.collezioni.append(base)  # già nell'edizione: una volta sola
    con = crea_edizione(stato="chiusa")
    con.zotero_collection_key = "ED"
    senza = crea_edizione(stato="chiusa")
    db.session.commit()

    assert "Riferimenti di base" not in client.get(f"/edizioni/{con.slug}").get_data(as_text=True)
    app.config["ZOTERO_COLLEZIONE_BASE"] = "BASE"
    html = client.get(f"/edizioni/{con.slug}").get_data(as_text=True)
    assert "Riferimenti di base" in html and "Manuale di base" in html
    assert html.count("<em>Libro del relatore</em>") == 1
    assert html.index("Libro del docente") < html.index("Manuale di base")  # in fondo
    html = client.get(f"/edizioni/{senza.slug}").get_data(as_text=True)
    assert "Manuale di base" in html and "Libro del relatore" in html  # R1 è anche nella base
    assert "Cerca nella bibliografia dell'edizione" not in html


def test_riferimenti_di_base_nella_ricerca(app):
    from app.ricerca_libri import cerca_zotero
    base = ZoteroCollezione(key="BASE", nome="Riferimenti di base")
    db.session.add(ZoteroItem(key="B1", titolo="Manuale di base", tipo="book", collezioni=[base]))
    db.session.commit()
    assert [z["key"] for z in cerca_zotero("manuale")] == ["B1"]


def test_pagina_a_sezioni_ultima_edizione_chiusa(app, client):
    """Di default: ultima edizione chiusa, riferimenti di base → relatori → docenti, a tessere."""
    libreria(app)
    base = ZoteroCollezione(key="BASE", nome="Riferimenti di base")
    db.session.add_all([base, ZoteroItem(key="B1", titolo="Manuale di base", tipo="book", collezioni=[base]),
                        ZoteroCollezione(key="NUOVA", nome="Edizione nuova")])
    vecchia, chiusa, aperta = (crea_edizione(stato=s) for s in ("conclusa", "chiusa", "aperta"))
    vecchia.anno, chiusa.anno, aperta.anno = 2024, 2025, 2026
    chiusa.zotero_collection_key, aperta.zotero_collection_key = "ED", "NUOVA"
    vecchia.zotero_collection_key = "ALT"
    app.config["ZOTERO_COLLEZIONE_BASE"] = "BASE"
    db.session.commit()

    html = client.get("/bibliografia").get_data(as_text=True)
    assert 'class="tessera' in html and "Fuori edizione" not in html
    assert html.index("Manuale di base") < html.index("Libro del relatore") < html.index("Libro del docente")
    assert "Edizione 2025 (ultima)" in html and f'value="e{aperta.id}"' not in html  # l'aperta no
    html = client.get(f"/bibliografia?mostra=e{vecchia.id}").get_data(as_text=True)
    assert "Fuori edizione" in html and "Libro del relatore" not in html
    assert client.get(f"/bibliografia?mostra=e{aperta.id}").status_code == 404
    html = client.get("/bibliografia?mostra=cDOC").get_data(as_text=True)
    assert "Libro del docente" in html and "Libro del relatore" not in html
    # ricerca dentro l'edizione scelta
    html = client.get(f"/bibliografia?mostra=e{chiusa.id}&q=libro").get_data(as_text=True)
    assert "Libro del docente" in html and "Fuori edizione" not in html


def test_pannello_interventi(app, client):
    """Tessera con le lezioni e le UD che consigliano l'item; niente nome del docente."""
    from conftest import crea_intervento
    libreria(app)
    ed = crea_edizione(stato="chiusa")
    iv = crea_intervento(ed, "relazione", "Esilio e migrazione", utente=crea_utente(ruolo="relatore"))
    docente, altro = crea_utente(), crea_utente()
    ammessa = Candidatura(utente=docente, edizione=ed, stato="ammessa", titolo_ud="Confini in classe")
    respinta = Candidatura(utente=altro, edizione=ed, stato="non_ammessa", titolo_ud="Respinta")
    db.session.add_all([ammessa, respinta])
    db.session.add_all([
        PropostaLettura(intervento_id=iv.id, campi={}, zotero_key="R1", stato="approvata"),
        PropostaLettura(candidatura=ammessa, campi={}, zotero_key="D1", stato="approvata"),
        PropostaLettura(candidatura=respinta, campi={}, zotero_key="W1", stato="approvata"),
        PropostaLettura(candidatura=ammessa, campi={}, zotero_key="A1", stato="proposta")])
    db.session.commit()
    html = client.get("/bibliografia?tutto=1").get_data(as_text=True)
    assert 'popovertarget="iv-R1"' in html and f"/edizioni/{ed.slug}/interventi/{iv.id}" in html
    assert "Esilio e migrazione" in html
    assert 'popovertarget="iv-D1"' in html and f"/edizioni/{ed.slug}/unita-didattiche/{ammessa.id}" in html
    assert docente.cognome not in html
    assert 'popovertarget="iv-W1"' not in html and 'popovertarget="iv-A1"' not in html


def test_homepage_riferimenti_di_base(app, client):
    assert "Invito alla lettura</h2>" not in client.get("/").get_data(as_text=True)  # base non configurata
    base = ZoteroCollezione(key="BASE", nome="Riferimenti di base")
    sotto = ZoteroCollezione(key="SUB", nome="Classici", parent_key="BASE")
    db.session.add_all([base, sotto,
                        ZoteroItem(key="CEST", titolo="Base nel cestino", tipo="book", eliminato=True, collezioni=[base]),
                        ZoteroItem(key="SUB1", titolo="Classico della sottosezione", tipo="book", collezioni=[sotto])])
    db.session.add_all(ZoteroItem(key=f"B{n}", titolo=f"Base {n}", tipo="book", primo_autore=f"Autore {n}",
                                  collezioni=[base]) for n in range(9))
    db.session.commit()
    app.config["ZOTERO_COLLEZIONE_BASE"] = "BASE"
    html = client.get("/").get_data(as_text=True)
    assert "Invito alla lettura</h2>" in html and html.count('class="tessera ') == 8
    assert "Base nel cestino" not in html
    assert "/bibliografia?mostra=cBASE" in html and "Tutti i riferimenti di base (10)" in html
