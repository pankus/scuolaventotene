from flask_wtf import FlaskForm
from flask_wtf.file import FileAllowed, FileField
from wtforms import (BooleanField, DateField, EmailField, HiddenField, IntegerField,
                     PasswordField, SelectField, StringField, TextAreaField)
from wtforms.validators import (URL, DataRequired, Email, EqualTo, Length, NumberRange,
                                Optional)

from .models import (RUOLI_EDIZIONE, STATI_CANDIDATURA, STATI_EDIZIONE, TIPI_CANDIDATURA, TIPI_MATERIALE,
                     TIPI_PROGRAMMA, VISIBILITA)

GRADI = [("", "—"), ("I", "Secondaria di I grado"), ("II", "Secondaria di II grado")]
CONTRATTI = [("", "—"), ("ruolo", "Di ruolo"), ("precario", "Precario")]
PROPOSTE = ["pdf", "doc", "docx", "odt"]
MATERIALI = ["pdf", "ppt", "pptx", "odp", "doc", "docx", "odt"]


def _scelte(d):
    return list(d.items())


class RegistrazioneForm(FlaskForm):
    nome = StringField("Nome", validators=[DataRequired(), Length(max=100)])
    cognome = StringField("Cognome", validators=[DataRequired(), Length(max=100)])
    email = EmailField("Email", validators=[DataRequired(), Email()])
    password = PasswordField("Password", validators=[DataRequired(), Length(min=10)])
    conferma = PasswordField("Conferma password", validators=[EqualTo("password", "Le password non coincidono")])
    consenso_privacy = BooleanField("Ho letto l'informativa privacy e acconsento al trattamento dei dati",
                                    validators=[DataRequired()])


class LoginForm(FlaskForm):
    email = EmailField("Email", validators=[DataRequired(), Email()])
    password = PasswordField("Password", validators=[DataRequired()])
    ricordami = BooleanField("Ricordami")


class PasswordDimenticataForm(FlaskForm):
    email = EmailField("Email", validators=[DataRequired(), Email()])


class ReimpostaPasswordForm(FlaskForm):
    password = PasswordField("Nuova password", validators=[DataRequired(), Length(min=10)])
    conferma = PasswordField("Conferma password", validators=[EqualTo("password", "Le password non coincidono")])


class ProfiloForm(FlaskForm):
    nome = StringField("Nome", validators=[DataRequired()])
    cognome = StringField("Cognome", validators=[DataRequired()])
    data_nascita = DateField("Data di nascita", validators=[Optional()])
    telefono = StringField("Telefono", validators=[Optional(), Length(max=40)])
    residenza = StringField("Residenza", validators=[Optional(), Length(max=255)])
    scuola = StringField("Scuola di servizio", validators=[Optional()])
    grado = SelectField("Grado", choices=GRADI)
    tipo_contratto = SelectField("Contratto", choices=CONTRATTI)
    paese = StringField("Paese (Italia o estero)", validators=[Optional()])
    materie = StringField("Materie insegnate", validators=[Optional()])


class CandidaturaForm(FlaskForm):
    tipo = SelectField("Partecipo come", choices=_scelte(TIPI_CANDIDATURA))
    titolo_ud = StringField("Titolo dell'unità didattica", validators=[Optional(), Length(max=255)])
    discipline = StringField("Discipline coinvolte", validators=[Optional(), Length(max=255)])
    abstract = TextAreaField("Breve abstract (facoltativo, max 1500 caratteri)",
                             validators=[Optional(), Length(max=1500)])
    file = FileField("Documento della proposta (6000–8000 caratteri spazi inclusi; .docx consigliato)",
                     validators=[FileAllowed(PROPOSTE, "Formati ammessi: pdf, doc, docx, odt")])


class CoautoreForm(FlaskForm):
    """Collega con cui si scrive la UD: deve avere già un account sul sito."""
    email = EmailField("Email del collega co-autore (deve essere registrato sul sito)",
                       validators=[DataRequired(), Email(), Length(max=255)])


class MaterialeForm(FlaskForm):
    edizione_id = SelectField("Edizione", coerce=int)
    titolo = StringField("Titolo", validators=[DataRequired(), Length(max=255)])
    autori = StringField("Autori", validators=[Optional(), Length(max=255)])
    tipo = SelectField("Tipo", choices=_scelte(TIPI_MATERIALE))
    descrizione = TextAreaField("Descrizione", validators=[Optional()])
    file = FileField("File (PDF o PowerPoint)",
                     validators=[FileAllowed(MATERIALI, "Formati ammessi: pdf, ppt, pptx, odp, doc, docx, odt")])
    url = StringField("oppure link esterno", validators=[Optional(), URL()])


class EmailPartecipantiForm(FlaskForm):
    """Messaggio dell'admin a relatori, docenti e comitato (scelte dell'edizione nella vista)."""
    edizione_id = SelectField("Edizione", coerce=int)
    relatori = BooleanField("Relatori")
    docenti = BooleanField("Docenti (UD delle edizioni passate e candidature ammesse)")
    comitato = BooleanField("Comitato scientifico")
    oggetto = StringField("Oggetto", validators=[DataRequired(), Length(max=200)])
    testo = TextAreaField("Testo", validators=[DataRequired()], render_kw={"rows": 12})


class MaterialeAdminForm(MaterialeForm):
    visibilita = SelectField("Visibilità", choices=_scelte(VISIBILITA))


class MaterialeUDForm(MaterialeAdminForm):
    """Materiale caricato dall'admin dentro una lezione o UD: l'edizione è già quella."""
    edizione_id = None


class DescrizioneForm(FlaskForm):
    descrizione = TextAreaField("Abstract (markdown)", validators=[Optional()])


class ValutazioneForm(FlaskForm):
    originalita = IntegerField("Originalità (0–25)", validators=[NumberRange(0, 25)])
    potenzialita = IntegerField("Potenzialità didattiche (0–25)", validators=[NumberRange(0, 25)])
    fonti = IntegerField("Valorizzazione delle fonti (0–25)", validators=[NumberRange(0, 25)])
    note = TextAreaField("Note", validators=[Optional()])


class StatoCandidaturaForm(FlaskForm):
    stato = SelectField("Stato", choices=_scelte(STATI_CANDIDATURA))
    note_comitato = TextAreaField("Note interne del comitato", validators=[Optional()])


class EdizioneForm(FlaskForm):
    numero = IntegerField("Numero edizione", validators=[DataRequired()])
    anno = IntegerField("Anno", validators=[DataRequired()])
    slug = StringField("Slug URL (es. 2026)", validators=[DataRequired(), Length(max=50)])
    titolo = StringField("Titolo", validators=[DataRequired()])
    sottotitolo = StringField("Sottotitolo", validators=[Optional()])
    luogo = StringField("Luogo", validators=[Optional()])
    sede = StringField("Sede", validators=[Optional()])
    data_inizio = DateField("Inizio", validators=[Optional()])
    data_fine = DateField("Fine", validators=[Optional()])
    scadenza_candidature = DateField("Scadenza candidature", validators=[Optional()])
    data_esiti = DateField("Comunicazione esiti entro", validators=[Optional()])
    chiusura_contenuti = DateField("Chiusura dei contenuti (materiali e letture di lezioni e UD; vuota = sempre aperti)",
                                   validators=[Optional()])
    posti_borsisti = IntegerField("Posti borsisti", validators=[Optional()])
    ammessi_uditori = BooleanField("Ammessi uditori")
    caratteri_min = IntegerField("Caratteri minimi proposta", validators=[Optional()])
    caratteri_max = IntegerField("Caratteri massimi proposta", validators=[Optional()])
    stato = SelectField("Stato", choices=_scelte(STATI_EDIZIONE))
    descrizione = TextAreaField("Presentazione (Markdown)", validators=[Optional()],
                                render_kw={"rows": 12})
    # scelte: collezioni radice della cache Zotero (admin._form_edizione)
    zotero_collection_key = SelectField(
        "Collezione Zotero dell'edizione",
        description="Se manca: creala in Zotero (es. «2027») e sincronizza dal cruscotto.")
    bando = FileField("Bando (PDF)", validators=[FileAllowed(["pdf", "docx"])])


class ProgrammaVoceForm(FlaskForm):
    giorno = DateField("Giorno", validators=[Optional()])
    ora = StringField("Ora (es. 9-13)", validators=[Optional()])
    tipo = SelectField("Tipo", choices=_scelte(TIPI_PROGRAMMA))
    titolo = StringField("Titolo", validators=[DataRequired()])
    relatori = StringField("Relatori", validators=[Optional()])
    ordine = IntegerField("Ordine", default=0, validators=[Optional()])


class PersonaEdizioneForm(FlaskForm):
    nome = StringField("Nome", validators=[DataRequired()])
    cognome = StringField("Cognome", validators=[DataRequired()])
    affiliazione = StringField("Affiliazione", validators=[Optional()])
    ruolo = SelectField("Ruolo", choices=_scelte(RUOLI_EDIZIONE))
    titolo_lezione = StringField("Titolo della lezione o della UD (crea un nuovo intervento)",
                                 validators=[Optional(), Length(max=255)])


class InterventoForm(FlaskForm):
    """Lezione o UD dell'edizione: titolo e ordine (gli autori si aggiungono a parte)."""
    titolo = StringField("Titolo", validators=[Optional(), Length(max=255)])
    ordine = IntegerField("Ordine", default=0, validators=[Optional()])


class AccountPersonaForm(FlaskForm):
    """Account collegato alla persona (uno per persona, vale per tutte le edizioni)."""
    utente_id = SelectField("Account", coerce=int)


class LetturaForm(FlaskForm):
    """Scheda di un libro o sito (nomi dei campi = Zotero; quali si mostrano: CAMPI_MODULO)."""
    title = StringField("Titolo", validators=[DataRequired(), Length(max=500)])
    autori = TextAreaField("Autori (Cognome, Nome — uno per riga; un ente su una riga senza virgola)",
                           validators=[Optional()], render_kw={"rows": 3})
    curatori = TextAreaField("Curatori (uno per riga)", validators=[Optional()], render_kw={"rows": 2})
    date = StringField("Anno", validators=[Optional(), Length(max=50)])
    publisher = StringField("Editore", validators=[Optional(), Length(max=255)])
    place = StringField("Luogo di edizione", validators=[Optional(), Length(max=255)])
    ISBN = StringField("ISBN", validators=[Optional(), Length(max=100)])
    series = StringField("Collana", validators=[Optional(), Length(max=255)])
    websiteTitle = StringField("Sito / ente", validators=[Optional(), Length(max=255)])
    url = StringField("URL", validators=[Optional(), URL(), Length(max=1000)])
    accessDate = StringField("Data di consultazione (AAAA-MM-GG)", validators=[Optional(), Length(max=20)])


class ItemZoteroForm(LetturaForm):
    """L'admin corregge un item della bibliografia: si scrive in Zotero (versione = controllo 412)."""
    versione = HiddenField(validators=[DataRequired()])


class CopertinaForm(FlaskForm):
    url = StringField("Indirizzo dell'immagine (Open Library, Google Books, archive.org)",
                      validators=[Optional(), URL(), Length(max=1000)])
    file = FileField("oppure carica un'immagine (jpg, png, webp, gif; max 2 MB)",
                     validators=[FileAllowed(["jpg", "jpeg", "png", "webp", "gif"], "Solo immagini")])


class LetturaRevisioneForm(LetturaForm):
    """Il comitato corregge la scheda prima di scriverla in Zotero."""
    nota_comitato = TextAreaField("Nota del comitato (visibile al docente)", validators=[Optional()])


class LetturaDocenteForm(LetturaForm):
    """Il docente consiglia una lettura; copertina e key Zotero arrivano dalla ricerca (letture.js)."""
    motivazione = TextAreaField("Perché la consigli (facoltativo)", validators=[Optional(), Length(max=1500)],
                                render_kw={"rows": 3})
    copertina_url = HiddenField(validators=[Optional(), Length(max=1000)])
    zotero_key = HiddenField(validators=[Optional(), Length(max=20)])
