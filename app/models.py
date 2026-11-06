"""Modello dati della Scuola di formazione di Ventotene.

Entità principali
- Utente            docenti registrati, membri del comitato, amministratori
- Edizione          un'edizione annuale della scuola (bando, date, stato)
- ProgrammaVoce     voci del programma (lezioni, sessioni UD, visite)
- Persona / EdizionePersona   comitato scientifico e relatori per edizione; per un relatore
                    l'EdizionePersona è la sua lezione, e Persona.utente lega l'account
- Candidatura       domanda di partecipazione (borsista / uditore) + proposta UD
- Valutazione       punteggi del comitato (originalità, potenzialità, fonti)
- Materiale         PDF/PowerPoint dell'archivio, caricati da admin o docenti
- PropostaLettura   libro o sito consigliato dal docente, rivisto dal comitato e scritto in Zotero
- ZoteroCollezione / ZoteroItem / SyncStato   cache locale del gruppo Zotero
"""
from datetime import date, datetime, timezone

from flask_login import UserMixin
from werkzeug.security import check_password_hash, generate_password_hash

from .extensions import db, login_manager


def adesso():
    return datetime.now(timezone.utc).replace(tzinfo=None)


# --------------------------------------------------------------------------- utenti
RUOLI = {"docente": "Docente", "relatore": "Relatore", "comitato": "Comitato scientifico",
         "admin": "Amministratore"}


class Utente(UserMixin, db.Model):
    __tablename__ = "utenti"

    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(255), unique=True, nullable=False, index=True)
    password_hash = db.Column(db.String(255), nullable=False)
    ruolo = db.Column(db.String(20), nullable=False, default="docente")
    attivo = db.Column(db.Boolean, nullable=False, default=True)
    email_verificata = db.Column(db.Boolean, nullable=False, default=False)

    nome = db.Column(db.String(100), nullable=False)
    cognome = db.Column(db.String(100), nullable=False)
    # dati richiesti dal bando
    data_nascita = db.Column(db.Date)
    telefono = db.Column(db.String(40))
    residenza = db.Column(db.String(255))
    # profilo professionale
    scuola = db.Column(db.String(255))
    grado = db.Column(db.String(4))  # I | II
    tipo_contratto = db.Column(db.String(20))  # ruolo | precario
    paese = db.Column(db.String(100), default="Italia")
    materie = db.Column(db.String(255))

    consenso_privacy_il = db.Column(db.DateTime)
    creato_il = db.Column(db.DateTime, default=adesso)

    candidature = db.relationship("Candidatura", back_populates="utente",
                                  cascade="all, delete-orphan")

    def set_password(self, pwd):
        self.password_hash = generate_password_hash(pwd)

    def check_password(self, pwd):
        return check_password_hash(self.password_hash, pwd)

    @property
    def is_active(self):
        return self.attivo

    @property
    def is_admin(self):
        return self.ruolo == "admin"

    @property
    def is_comitato(self):
        return self.ruolo in ("comitato", "admin")

    @property
    def is_relatore(self):
        return self.ruolo == "relatore"

    def lezioni(self):
        """Le lezioni (EdizionePersona con ruolo relatore) della persona legata all'account."""
        if not self.persona:
            return []
        return sorted((ep for ep in self.persona.edizioni if ep.ruolo == "relatore"),
                      key=lambda ep: (-ep.edizione.anno, ep.posizione))

    @property
    def nome_completo(self):
        return f"{self.nome} {self.cognome}"


@login_manager.user_loader
def _carica_utente(uid):
    return db.session.get(Utente, int(uid))


# --------------------------------------------------------------------------- edizioni
STATI_EDIZIONE = {
    "bozza": "Bozza (non visibile)",
    "aperta": "Candidature aperte",
    "chiusa": "Candidature chiuse",
    "conclusa": "Conclusa (archivio)",
}


class Edizione(db.Model):
    __tablename__ = "edizioni"

    id = db.Column(db.Integer, primary_key=True)
    numero = db.Column(db.Integer, unique=True, nullable=False)
    anno = db.Column(db.Integer, nullable=False)
    slug = db.Column(db.String(50), unique=True, nullable=False)
    titolo = db.Column(db.String(255), nullable=False)
    sottotitolo = db.Column(db.String(255))
    luogo = db.Column(db.String(100), default="Ventotene")
    sede = db.Column(db.String(255))
    data_inizio = db.Column(db.Date)
    data_fine = db.Column(db.Date)
    scadenza_candidature = db.Column(db.Date)
    data_esiti = db.Column(db.Date)
    posti_borsisti = db.Column(db.Integer, default=8)
    ammessi_uditori = db.Column(db.Boolean, default=True)
    caratteri_min = db.Column(db.Integer, default=6000)
    caratteri_max = db.Column(db.Integer, default=8000)
    descrizione = db.Column(db.Text)  # markdown
    stato = db.Column(db.String(20), nullable=False, default="bozza")
    bando_path = db.Column(db.String(255))
    # Zotero: collezione dell'edizione, con dentro "Relatori" e "Docenti"; "Docenti" la crea
    # il sito alla prima lettura approvata. Lezione e UD di ogni lettura stanno solo nel sito.
    zotero_collection_key = db.Column(db.String(20))
    zotero_docenti_key = db.Column(db.String(20))
    zotero_relatori_key = db.Column(db.String(20))

    programma = db.relationship("ProgrammaVoce", back_populates="edizione",
                                cascade="all, delete-orphan",
                                order_by="(ProgrammaVoce.giorno, ProgrammaVoce.ordine)")
    persone = db.relationship("EdizionePersona", back_populates="edizione",
                              cascade="all, delete-orphan")
    candidature = db.relationship("Candidatura", back_populates="edizione")
    materiali = db.relationship("Materiale", back_populates="edizione")

    @property
    def candidature_aperte(self):
        if self.stato != "aperta":
            return False
        return self.scadenza_candidature is None or date.today() <= self.scadenza_candidature

    def persone_con_ruolo(self, ruolo):
        return [ep.persona for ep in self.persone if ep.ruolo == ruolo]

    def programma_per_giorno(self):
        giorni = {}
        for v in self.programma:
            giorni.setdefault(v.giorno, []).append(v)
        return sorted(giorni.items(), key=lambda kv: (kv[0] is None, kv[0]))


TIPI_PROGRAMMA = {
    "accoglienza": "Accoglienza",
    "lezione": "Lezione",
    "unita_didattiche": "Presentazione unità didattiche",
    "visita": "Visita",
    "chiusura": "Chiusura",
}


class ProgrammaVoce(db.Model):
    __tablename__ = "programma_voci"

    id = db.Column(db.Integer, primary_key=True)
    edizione_id = db.Column(db.Integer, db.ForeignKey("edizioni.id", ondelete="CASCADE"), nullable=False)
    giorno = db.Column(db.Date)
    ora = db.Column(db.String(20))
    tipo = db.Column(db.String(30), default="lezione")
    titolo = db.Column(db.String(255), nullable=False)
    relatori = db.Column(db.String(255))
    ordine = db.Column(db.Integer, default=0)

    edizione = db.relationship("Edizione", back_populates="programma")


class Persona(db.Model):
    __tablename__ = "persone"

    id = db.Column(db.Integer, primary_key=True)
    nome = db.Column(db.String(100), nullable=False)
    cognome = db.Column(db.String(100), nullable=False)
    affiliazione = db.Column(db.String(255))
    bio = db.Column(db.Text)
    url = db.Column(db.String(255))
    # account del relatore (uno per persona); l'admin lo collega nella scheda dell'edizione
    utente_id = db.Column(db.Integer, db.ForeignKey("utenti.id", ondelete="SET NULL"), unique=True)

    utente = db.relationship("Utente", backref=db.backref("persona", uselist=False))
    edizioni = db.relationship("EdizionePersona", back_populates="persona")

    @property
    def nome_completo(self):
        return f"{self.nome} {self.cognome}"


class EdizionePersona(db.Model):
    __tablename__ = "edizioni_persone"
    __table_args__ = (db.UniqueConstraint("edizione_id", "persona_id", "ruolo"),)

    id = db.Column(db.Integer, primary_key=True)
    edizione_id = db.Column(db.Integer, db.ForeignKey("edizioni.id", ondelete="CASCADE"), nullable=False)
    persona_id = db.Column(db.Integer, db.ForeignKey("persone.id", ondelete="CASCADE"), nullable=False)
    ruolo = db.Column(db.String(20), nullable=False, default="comitato")  # comitato | relatore
    # solo per i relatori: la lezione
    titolo_lezione = db.Column(db.String(255))
    ordine = db.Column(db.Integer, default=0)

    edizione = db.relationship("Edizione", back_populates="persone")
    persona = db.relationship("Persona", back_populates="edizioni")
    materiali = db.relationship("Materiale", back_populates="lezione")
    letture = db.relationship("PropostaLettura", back_populates="lezione",
                              cascade="all, delete-orphan", order_by="PropostaLettura.id")

    @property
    def posizione(self):
        """Chiave d'ordinamento delle lezioni (ordine può mancare nelle righe vecchie)."""
        return (self.ordine or 0, self.id)

    @property
    def nome_lezione(self):
        return f"{self.persona.nome_completo} – {self.titolo_lezione or 'lezione'}"


# --------------------------------------------------------------------------- candidature
STATI_CANDIDATURA = {
    "bozza": "Bozza",
    "inviata": "Inviata",
    "in_valutazione": "In valutazione",
    "ammessa": "Ammessa",
    "riserva": "In graduatoria (riserva)",
    "non_ammessa": "Non ammessa",
    "ritirata": "Ritirata",
}
ESITI_CANDIDATURA = ("ammessa", "riserva", "non_ammessa")  # comunicati al docente via email
TIPI_CANDIDATURA = {"borsista": "Borsista (con proposta di UD)", "uditore": "Uditore"}


class Candidatura(db.Model):
    __tablename__ = "candidature"
    __table_args__ = (db.UniqueConstraint("utente_id", "edizione_id"),)

    id = db.Column(db.Integer, primary_key=True)
    utente_id = db.Column(db.Integer, db.ForeignKey("utenti.id", ondelete="CASCADE"), nullable=False)
    edizione_id = db.Column(db.Integer, db.ForeignKey("edizioni.id"), nullable=False)
    tipo = db.Column(db.String(20), nullable=False, default="borsista")
    stato = db.Column(db.String(20), nullable=False, default="bozza")

    titolo_ud = db.Column(db.String(255))
    discipline = db.Column(db.String(255))
    abstract = db.Column(db.Text)
    file_path = db.Column(db.String(255))
    file_nome = db.Column(db.String(255))
    n_caratteri = db.Column(db.Integer)  # calcolato per .docx

    note_comitato = db.Column(db.Text)
    inviata_il = db.Column(db.DateTime)
    creato_il = db.Column(db.DateTime, default=adesso)
    aggiornato_il = db.Column(db.DateTime, default=adesso, onupdate=adesso)

    utente = db.relationship("Utente", back_populates="candidature")
    edizione = db.relationship("Edizione", back_populates="candidature")
    valutazioni = db.relationship("Valutazione", back_populates="candidatura",
                                  cascade="all, delete-orphan")
    letture = db.relationship("PropostaLettura", back_populates="candidatura",
                              cascade="all, delete-orphan", order_by="PropostaLettura.id")

    @property
    def punteggio_medio(self):
        if not self.valutazioni:
            return None
        return round(sum(v.totale for v in self.valutazioni) / len(self.valutazioni), 1)

    def problemi_invio(self):
        """Controlli richiesti dal bando prima dell'invio."""
        p = []
        u = self.utente
        if not u.email_verificata:
            p.append("Conferma il tuo indirizzo email con il link che ti abbiamo inviato.")
        for campo, label in (("data_nascita", "data di nascita"),
                             ("telefono", "telefono"), ("residenza", "residenza")):
            if not getattr(u, campo):
                p.append(f"Completa il profilo: manca {label}.")
        if self.tipo == "borsista":
            if not self.titolo_ud:
                p.append("Indica il titolo dell'unità didattica.")
            if not self.file_path:
                p.append("Carica il documento con la proposta di unità didattica.")
            elif self.n_caratteri is not None:
                ed = self.edizione
                if not (ed.caratteri_min <= self.n_caratteri <= ed.caratteri_max):
                    p.append(f"La proposta conta {self.n_caratteri} caratteri: il bando ne "
                             f"richiede tra {ed.caratteri_min} e {ed.caratteri_max} (spazi inclusi).")
        return p


class Valutazione(db.Model):
    __tablename__ = "valutazioni"
    __table_args__ = (db.UniqueConstraint("candidatura_id", "valutatore_id"),)

    id = db.Column(db.Integer, primary_key=True)
    candidatura_id = db.Column(db.Integer, db.ForeignKey("candidature.id", ondelete="CASCADE"), nullable=False)
    valutatore_id = db.Column(db.Integer, db.ForeignKey("utenti.id"), nullable=False)
    originalita = db.Column(db.Integer, nullable=False, default=0)   # 0-25
    potenzialita = db.Column(db.Integer, nullable=False, default=0)  # 0-25
    fonti = db.Column(db.Integer, nullable=False, default=0)         # 0-25
    note = db.Column(db.Text)
    creato_il = db.Column(db.DateTime, default=adesso, onupdate=adesso)

    candidatura = db.relationship("Candidatura", back_populates="valutazioni")
    valutatore = db.relationship("Utente")

    @property
    def totale(self):
        return self.originalita + self.potenzialita + self.fonti


# --------------------------------------------------------------------------- letture
TIPI_LETTURA = {"book": "Libro", "webpage": "Sito / pagina web"}  # tipi Zotero
STATI_PROPOSTA = {"proposta": "Da rivedere", "approvata": "Approvata", "rifiutata": "Rifiutata"}
MOMENTI_PROPOSTA = {"iscrizione": "Con la candidatura", "post_scuola": "Dopo la scuola"}


class PropostaLettura(db.Model):
    """Lettura consigliata da un docente (legata alla candidatura, rivista dal comitato) o dal
    relatore di una lezione (scritta subito in Zotero). Il legame persona↔libro resta solo qui."""
    __tablename__ = "proposte_lettura"
    __table_args__ = (db.CheckConstraint("(candidatura_id IS NULL) <> (lezione_id IS NULL)",
                                         name="una_origine"),)

    id = db.Column(db.Integer, primary_key=True)
    candidatura_id = db.Column(db.Integer, db.ForeignKey("candidature.id", ondelete="CASCADE"),
                               index=True)
    lezione_id = db.Column(db.Integer, db.ForeignKey("edizioni_persone.id", ondelete="CASCADE"),
                           index=True)
    tipo = db.Column(db.String(20), nullable=False, default="book")
    # campi Zotero (title, date, publisher, place, ISBN, series, url, websiteTitle, accessDate)
    # più "autori" e "curatori" come testo, una persona per riga ("Cognome, Nome")
    campi = db.Column(db.JSON, nullable=False, default=dict)
    copertina_url = db.Column(db.String(1000))  # dal lookup; scaricata in locale all'approvazione
    motivazione = db.Column(db.Text)            # perché il docente lo consiglia (resta nel sito)
    zotero_key = db.Column(db.String(20), index=True)  # già in Zotero, o creato all'approvazione
    stato = db.Column(db.String(20), nullable=False, default="proposta")
    momento = db.Column(db.String(20), nullable=False, default="iscrizione")
    nota_comitato = db.Column(db.Text)
    creato_il = db.Column(db.DateTime, default=adesso)
    deciso_il = db.Column(db.DateTime)
    deciso_da_id = db.Column(db.Integer, db.ForeignKey("utenti.id", ondelete="SET NULL"))

    candidatura = db.relationship("Candidatura", back_populates="letture")
    lezione = db.relationship("EdizionePersona", back_populates="letture")
    deciso_da = db.relationship("Utente")

    @property
    def titolo(self):
        return (self.campi or {}).get("title") or "(senza titolo)"


# --------------------------------------------------------------------------- materiali
TIPI_MATERIALE = {
    "slide": "Presentazione (slide)",
    "relazione": "Testo / relazione",
    "unita_didattica": "Unità didattica",
    "bando": "Bando / programma",
    "altro": "Altro",
}
VISIBILITA = {"pubblico": "Pubblico", "registrati": "Solo utenti registrati", "privato": "Solo comitato"}
STATI_MATERIALE = {"in_revisione": "In revisione", "pubblicato": "Pubblicato", "rifiutato": "Rifiutato"}


class Materiale(db.Model):
    __tablename__ = "materiali"

    id = db.Column(db.Integer, primary_key=True)
    edizione_id = db.Column(db.Integer, db.ForeignKey("edizioni.id"), nullable=False)
    titolo = db.Column(db.String(255), nullable=False)
    autori = db.Column(db.String(255))
    descrizione = db.Column(db.Text)
    tipo = db.Column(db.String(30), default="slide")
    file_path = db.Column(db.String(255))
    file_nome = db.Column(db.String(255))
    mime = db.Column(db.String(100))
    dimensione = db.Column(db.Integer)
    url = db.Column(db.String(500))  # alternativa al file (video, link esterno)
    visibilita = db.Column(db.String(20), nullable=False, default="pubblico")
    stato = db.Column(db.String(20), nullable=False, default="in_revisione")
    caricato_da_id = db.Column(db.Integer, db.ForeignKey("utenti.id"))
    # materiale di una lezione (caricato dal relatore); vuoto per quelli dei docenti e dello staff
    lezione_id = db.Column(db.Integer, db.ForeignKey("edizioni_persone.id", ondelete="SET NULL"))
    creato_il = db.Column(db.DateTime, default=adesso)

    edizione = db.relationship("Edizione", back_populates="materiali")
    caricato_da = db.relationship("Utente")
    lezione = db.relationship("EdizionePersona", back_populates="materiali")

    def visibile_a(self, user):
        if user.is_authenticated and (user.is_comitato or user.id == self.caricato_da_id):
            return True
        if self.stato != "pubblicato":
            return False
        if self.visibilita == "pubblico":
            return True
        if self.visibilita == "registrati":
            return user.is_authenticated
        return False


# --------------------------------------------------------------------------- Zotero
zotero_item_collezioni = db.Table(
    "zotero_item_collezioni",
    db.Column("item_key", db.String(20), db.ForeignKey("zotero_items.key", ondelete="CASCADE"), primary_key=True),
    db.Column("collezione_key", db.String(20), db.ForeignKey("zotero_collezioni.key", ondelete="CASCADE"), primary_key=True),
)


class ZoteroCollezione(db.Model):
    __tablename__ = "zotero_collezioni"

    key = db.Column(db.String(20), primary_key=True)
    nome = db.Column(db.String(255), nullable=False)
    parent_key = db.Column(db.String(20))
    version = db.Column(db.Integer)


class ZoteroItem(db.Model):
    __tablename__ = "zotero_items"

    key = db.Column(db.String(20), primary_key=True)
    version = db.Column(db.Integer)
    tipo = db.Column(db.String(50))
    titolo = db.Column(db.Text)
    autori = db.Column(db.Text)
    primo_autore = db.Column(db.String(255), index=True)
    anno = db.Column(db.String(4), index=True)
    data = db.Column(db.String(100))
    pubblicazione = db.Column(db.String(500))
    url = db.Column(db.String(1000))
    doi = db.Column(db.String(255))
    isbn = db.Column(db.String(13), index=True)    # primo ISBN valido, sempre a 13 cifre
    firma = db.Column(db.String(500), index=True)  # titolo normalizzato|tipo, per i doppioni
    copertina_path = db.Column(db.String(255))     # copia locale in uploads/ (letture approvate)
    abstract = db.Column(db.Text)
    tags = db.Column(db.Text)  # JSON
    citazione_html = db.Column(db.Text)  # formattata dall'API Zotero (CSL)
    dati_json = db.Column(db.Text)
    eliminato = db.Column(db.Boolean, default=False)  # nel cestino Zotero
    sincronizzato_il = db.Column(db.DateTime)

    collezioni = db.relationship("ZoteroCollezione", secondary=zotero_item_collezioni,
                                 backref="items")


class SyncStato(db.Model):
    __tablename__ = "sync_stato"

    chiave = db.Column(db.String(50), primary_key=True)
    valore = db.Column(db.String(255))

    @classmethod
    def get(cls, chiave, default=None):
        r = db.session.get(cls, chiave)
        return r.valore if r else default

    @classmethod
    def set(cls, chiave, valore):
        r = db.session.get(cls, chiave) or cls(chiave=chiave)
        r.valore = str(valore)
        db.session.add(r)
