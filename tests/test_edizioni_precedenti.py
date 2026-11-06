"""Edizioni 2023–2025 (flask seed-precedenti): dati, lezioni, allegati, nessun doppione."""
from app.extensions import db
from app.edizioni_precedenti import EDIZIONI, carica
from app.models import EdizionePersona, Edizione, Materiale, Persona, ZoteroCollezione


def pdf_finto(url):
    return b"%PDF-1.4 " + url.encode()


def test_carica_le_tre_edizioni(app, client):
    db.session.add(ZoteroCollezione(key="COL24", nome="2024"))
    db.session.commit()
    avvisi = []
    assert carica(scarica=pdf_finto, avviso=avvisi.append) == [2023, 2024, 2025]
    e23, e24, e25 = Edizione.query.order_by(Edizione.numero).all()
    assert (e23.slug, e23.stato, e23.data_inizio.isoformat()) == ("2023", "conclusa", "2023-10-29")
    assert e24.zotero_collection_key == "COL24" and e23.zotero_collection_key is None
    assert len(e24.programma) == len(EDIZIONI[1]["programma"])
    # lezioni: una per relatore, nell'ordine del programma; lezione a due voci = due relatori
    lezioni = sorted((ep for ep in e24.persone if ep.ruolo == "relatore"), key=lambda ep: ep.posizione)
    assert [ep.persona.cognome for ep in lezioni] == ["Gallo", "Deplano", "Onidi", "Colucci", "Inesi",
                                                      "Di Sanzo", "Ferrarese"]
    assert lezioni[5].titolo_lezione == lezioni[6].titolo_lezione
    # la stessa persona in più edizioni
    assert Persona.query.filter_by(cognome="Gallo").count() == 1
    assert Materiale.query.filter_by(stato="pubblicato", tipo="bando").count() == 3
    html = client.get("/edizioni/2023").get_data(as_text=True)
    assert "Esilio e migrazione dal Risorgimento alla Grande Guerra" in html
    assert client.get("/archivio/2025").status_code == 200 and not avvisi


def test_rilancio_e_allegato_non_scaricabile(app):
    def giu(url):
        raise OSError("rete giù")
    avvisi = []
    carica(scarica=giu, avviso=avvisi.append)
    assert Edizione.query.count() == 3 and Materiale.query.count() == 0
    assert len(avvisi) == 3  # un allegato per edizione non scaricato
    n = EdizionePersona.query.count()
    assert carica(scarica=pdf_finto, avviso=avvisi.append) == []  # già presenti: non toccate
    assert EdizionePersona.query.count() == n


def test_allegato_che_non_e_un_pdf(app):
    avvisi = []
    carica(scarica=lambda url: b"<html>errore</html>", avviso=avvisi.append)
    assert Materiale.query.count() == 0 and all("non è un PDF" in a for a in avvisi)
