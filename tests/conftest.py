from datetime import date, timedelta
from itertools import count

import pytest
from flask import g

from app import create_app
from app.extensions import db
from app.models import RUOLO_AUTORE, Edizione, EdizionePersona, Intervento, Persona, Utente
from config import TestConfig

PASSWORD = "password-di-test"
_seq = count(1)
_comitato_ovunque = []  # utenti «comitato» senza edizioni indicate: entrano in tutte quelle del test


@pytest.fixture
def app(tmp_path):
    app = create_app(TestConfig)
    app.config["UPLOAD_FOLDER"] = str(tmp_path)

    # L'app context resta aperto per tutto il test e Flask lo riusa nelle richieste:
    # senza questo, l'utente che Flask-Login mette in g passerebbe da un client all'altro.
    @app.before_request
    def _azzera_utente():
        g.pop("_login_user", None)

    _comitato_ovunque.clear()
    with app.app_context():
        db.create_all()
        yield app
        db.session.remove()
        db.drop_all()


@pytest.fixture
def client(app):
    return app.test_client()


def _nel_comitato(u, ed):
    if not u.persona:
        db.session.add(Persona(nome=u.nome, cognome=u.cognome, utente=u))
        db.session.flush()
    db.session.add(EdizionePersona(edizione=ed, persona=u.persona, ruolo="comitato"))


def crea_utente(ruolo="docente", completo=True, verificata=True, edizioni=None):
    """ruolo "admin" = amministratore; "comitato" = nel comitato delle `edizioni` indicate, o di
    tutte quelle del test (anche create dopo) se non se ne indicano. Relatore e docente non
    cambiano nulla: valgono le lezioni e le candidature."""
    n = next(_seq)
    u = Utente(email=f"utente{n}@esempio.it", nome="Nome", cognome=f"Cognome{n}", admin=ruolo == "admin",
               email_verificata=verificata)
    u.set_password(PASSWORD)
    if completo:
        u.data_nascita, u.telefono, u.residenza = date(1980, 1, 1), "000 0000000", "Città di prova"
    db.session.add(u)
    if ruolo == "comitato":
        if edizioni is None:
            _comitato_ovunque.append(u)
            edizioni = Edizione.query.all()
        for ed in edizioni:
            _nel_comitato(u, ed)
    db.session.commit()
    return u


def crea_edizione(stato="aperta", scadenza=date.today() + timedelta(days=10)):
    n = next(_seq)
    ed = Edizione(numero=n, anno=2000 + n, slug=f"edizione-{n}", titolo=f"Edizione {n}",
                  stato=stato, scadenza_candidature=scadenza)
    db.session.add(ed)
    for u in _comitato_ovunque:
        _nel_comitato(u, ed)
    db.session.commit()
    return ed


def crea_intervento(ed, tipo="relazione", titolo="Esilio e migrazione", ordine=1, utente=None,
                    nome="Stefano", cognome="Gallo"):
    """Lezione (o UD) con un autore: la persona (legata a `utente`, se c'è) con il ruolo giusto."""
    p = (utente.persona if utente else None) or Persona(nome=nome, cognome=cognome, utente=utente)
    ep = EdizionePersona.query.filter_by(edizione_id=ed.id, persona_id=p.id, ruolo=RUOLO_AUTORE[tipo]).first() \
        if p.id else None
    ep = ep or EdizionePersona(edizione=ed, persona=p, ruolo=RUOLO_AUTORE[tipo])
    iv = Intervento(edizione=ed, tipo=tipo, titolo=titolo, ordine=ordine)
    db.session.add_all([ep, iv])
    iv.aggiungi_autore(ep)
    db.session.commit()
    return iv


def login(client, utente):
    r = client.post("/accedi", data={"email": utente.email, "password": PASSWORD})
    assert r.status_code == 302, "login non riuscito"


class FakeZot:
    """Il minimo di pyzotero usato dal sito, in memoria (come FakeZot di Itinera)."""

    def __init__(self):
        self.versione = 1
        self.collezioni = {}   # key -> data
        self.record = {}        # key -> {"data":..., "meta":..., "bib":...}
        self.cestino = set()
        self.creati = []       # payload ricevuti da create_items
        self.eliminati = {}    # key -> versione dell'eliminazione
        self.accesso = {"groups": {"12345": {"library": True, "write": True}}}

    # --- per preparare i casi di test
    def _bump(self):
        self.versione += 1
        return self.versione

    def metti_collezione(self, key, nome, parent=None, deleted=False):
        self.collezioni[key] = {"key": key, "name": nome, "parentCollection": parent or False,
                                "version": self._bump(), "deleted": deleted}

    def metti_item(self, key, titolo, tipo="book", collezioni=(), **campi):
        data = {"key": key, "itemType": tipo, "title": titolo, "collections": list(collezioni),
                "creators": [{"creatorType": "author", "lastName": "Rossi", "firstName": "Anna"}],
                "tags": [], "version": self._bump(), **campi}
        self.record[key] = {"data": data, "meta": {"parsedDate": campi.get("date", "")},
                           "bib": f"<div>{titolo}</div>"}

    def cestina(self, key):
        self.cestino.add(key)
        self.record[key]["data"]["version"] = self._bump()

    def elimina(self, key):
        del self.record[key]
        self.cestino.discard(key)
        self.eliminati[key] = self._bump()

    # --- API pyzotero
    def last_modified_version(self):
        return self.versione

    def everything(self, risultato):
        return risultato

    def collections(self, **_kw):
        return [{"data": dict(d)} for d in self.collezioni.values()]

    def _items(self, nel_cestino, since):
        return [dict(it) for k, it in self.record.items()
                if (k in self.cestino) == nel_cestino and it["data"]["version"] > since]

    def top(self, since=0, **_kw):
        return self._items(False, since)

    def trash(self, since=0, **_kw):
        return self._items(True, since)

    def deleted(self, since=0):
        return {"items": [k for k, v in self.eliminati.items() if v > since], "collections": []}

    def key_info(self):
        return {"access": self.accesso}

    def num_items(self):
        return len(self.record) - len(self.cestino)

    # --- scrittura
    TEMPLATE = {
        "book": ["title", "creators", "abstractNote", "series", "place", "publisher", "date",
                 "ISBN", "url", "tags", "collections", "relations"],
        "bookSection": ["title", "creators", "abstractNote", "bookTitle", "series", "place", "publisher",
                        "date", "pages", "ISBN", "url", "tags", "collections", "relations"],
        "journalArticle": ["title", "creators", "abstractNote", "publicationTitle", "volume", "issue",
                           "pages", "date", "DOI", "ISSN", "url", "tags", "collections", "relations"],
        "webpage": ["title", "creators", "abstractNote", "websiteTitle", "date", "url",
                    "accessDate", "tags", "collections", "relations"],
    }

    def item_template(self, tipo):
        d = {k: "" for k in self.TEMPLATE[tipo]}
        d.update(itemType=tipo, creators=[], tags=[], collections=[], relations={})
        return d

    def create_items(self, lista):
        res = {"successful": {}, "success": {}, "unchanged": {}, "failed": {}}
        for i, d in enumerate(lista):
            key = f"NEW{len(self.record) + 1:05d}"
            self.creati.append(dict(d))
            data = {**d, "key": key, "version": self._bump()}
            self.record[key] = {"data": data, "meta": {"parsedDate": d.get("date", "")},
                               "bib": f"<div>{d.get('title')}</div>"}
            res["successful"][str(i)] = {"key": key, "data": data}
            res["success"][str(i)] = key
        return res

    def create_collections(self, lista):
        res = {"successful": {}, "success": {}, "unchanged": {}, "failed": {}}
        for i, d in enumerate(lista):
            key = f"COLN{len(self.collezioni) + 1:04d}"
            self.metti_collezione(key, d["name"], d.get("parentCollection") or None)
            res["successful"][str(i)] = {"key": key, "data": dict(self.collezioni[key])}
            res["success"][str(i)] = key
        return res

    def item(self, key, **_kw):
        it = self.record[key]
        return {**it, "key": key, "version": it["data"]["version"], "data": dict(it["data"])}

    def update_item(self, data, last_modified=None):
        from pyzotero import errors as ze
        attuale = self.record[data["key"]]["data"]
        if last_modified is not None and last_modified != attuale["version"]:
            raise ze.PreConditionFailedError("412")
        self.record[data["key"]]["data"] = {**data, "version": self._bump()}
        return True

    def items(self, q="", limit=25, **_kw):
        q = q.lower()
        return [dict(it) for k, it in self.record.items()
                if k not in self.cestino and q in it["data"]["title"].lower()][:limit]


@pytest.fixture
def fake_zot():
    return FakeZot()
