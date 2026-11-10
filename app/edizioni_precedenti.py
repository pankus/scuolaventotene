"""Edizioni I–III (2023–2025), dalle pagine e dai programmi pubblicati sul sito CNR-ISMed:
- 2023: ismed.cnr.it/evento/al-via-la-scuola-di-formazione-per-insegnanti-sul-tema-delle-migrazioni/
  e ismed.cnr.it/scuola-di-formazione-per-insegnanti/ (programma);
- 2024: ismed.cnr.it/evento/scuola-formazione-ii-ed/ (programma e locandina);
- 2025: ismed.cnr.it/evento/scuola-formazione-iii-ed-migrazioni-politiche-nellitalia-contemporanea/
  (locandina con il programma).
Caricate da ``flask seed-precedenti``: un'edizione già presente (stesso numero) non si tocca.
Docenti delle UD e titoli sono quelli già pubblici sul sito ISMed."""
import io
import urllib.request
from datetime import date as D

from werkzeug.datastructures import FileStorage

from .extensions import db
from .models import (RUOLO_AUTORE, Edizione, EdizionePersona, Intervento, Materiale, Persona, ProgrammaVoce, ZoteroCollezione,
                     ep_di)
from .utils import salva_upload

SEDE = ("Centro di ricerca e documentazione sul confino politico e la detenzione "
        "Isole di Ventotene e Santo Stefano")
ISMED = "CNR-ISMed"
UNICAL, ORIENTALE, PADOVA = "Università della Calabria", "Università L'Orientale di Napoli", "Università di Padova"
CAGLIARI, PALERMO = "Università di Cagliari", "Università di Palermo"

TITOLO = "Le migrazioni politiche nell'Italia contemporanea"
SOTTOTITOLO = "definizioni, confini, proposte didattiche"
OBIETTIVO = (
    "La migrazione politica rappresenta uno dei temi più dibattuti nel dibattito pubblico. I "
    "confini e le differenze tra motivazioni politiche ed economiche alla radice dei flussi "
    "migratori stanno alla base di discussioni, conflitti, interpretazioni che incidono in modo "
    "rilevante sulla lettura, la percezione e il governo della mobilità internazionale. "
    "Obiettivo della scuola di formazione è approfondire in chiave storica l'evoluzione delle "
    "migrazioni politiche nell'Italia contemporanea, dal Risorgimento ai giorni nostri, "
    "individuando sia chiavi di lettura efficaci per comprenderne le specificità sia percorsi "
    "didattici capaci di sostenerne la disseminazione in ambito scolastico.\n\n"
    "Nelle sessioni mattutine relazioni e interventi di studiosi, nelle sessioni pomeridiane "
    "presentazione e discussione delle unità didattiche dei docenti. Sono ammessi uditori "
    "esterni; ai partecipanti (borsisti e uditori) è stato rilasciato un attestato di frequenza."
)

# Programma: (giorno, ora, tipo, titolo, relatori). Le voci "lezione" con relatori diventano
# anche lezioni del sito (interventi con i relatori come autori), per collegarvi materiali e account.
EDIZIONI = [
    {
        "numero": 1, "anno": 2023, "inizio": D(2023, 10, 29), "fine": D(2023, 11, 1), "posti": 10,
        "fonte": "https://www.ismed.cnr.it/scuola-di-formazione-per-insegnanti/",
        "descrizione": OBIETTIVO + (
            "\n\nPrima edizione: dieci docenti delle scuole secondarie di primo e secondo grado, "
            "selezionati con una call, hanno presentato le loro unità didattiche.\n\n"
            "Organizzazione: CNR-ISMed, Osservatorio Placido Rizzotto, Centro di ricerca e "
            "documentazione sul confino politico e la detenzione Isole di Ventotene e Santo "
            "Stefano. Coordinamento tecnico: Francesco Di Filippo (CNR-ISMed).\n\n"
            "Iniziativa che ha beneficiato del contributo della Struttura di missione per la "
            "valorizzazione degli anniversari nazionali e per la dimensione partecipativa delle "
            "nuove generazioni – Presidenza del Consiglio dei Ministri – Progetto «Un partito in "
            "movimento: il Pci e le migrazioni dalla nascita allo scioglimento» – Codice Progetto "
            "«190 PCI» – CUP J61B22002250004."),
        "comitato": [("Simona", "Berhe", UNICAL), ("Michele", "Colucci", ISMED),
                     ("Donato", "Di Sanzo", ISMED), ("Giovanni", "Ferrarese", ISMED),
                     ("Stefano", "Gallo", ISMED), ("Alessandra", "Gissi", ORIENTALE),
                     ("Valeria", "Piro", PADOVA), ("Anthony", "Santilli", SEDE)],
        "programma": [
            (D(2023, 10, 29), "18", "accoglienza", "Accoglienza, saluti e presentazione della scuola", None),
            (D(2023, 10, 30), "9.30-12.30", "lezione", "Esilio e migrazione dal Risorgimento alla Grande Guerra", "Stefano Gallo"),
            (D(2023, 10, 30), "9.30-12.30", "lezione", "L'emigrazione delle donne", "Alessandra Gissi"),
            (D(2023, 10, 30), "9.30-12.30", "lezione", "Mobilità politica e migrazioni tra Otto e Novecento: differenze e contatti", "Anthony Santilli"),
            (D(2023, 10, 30), "14-18", "unita_didattiche", "Dalla febbre rivoluzionaria a quella dell'oro. Spirito politico, imprenditoriale e d'avventura nell'esilio risorgimentale in California", "Tommaso Caiazza"),
            (D(2023, 10, 30), "14-18", "unita_didattiche", "Sardegna terra di esuli: esperimenti giornalistici ed economici tra avanguardia e arretratezza", "Arianna Onidi"),
            (D(2023, 10, 30), "14-18", "unita_didattiche", "La guerra di Libia e i profughi italiani", "Daniela De Lorentiis"),
            (D(2023, 10, 30), "14-18", "unita_didattiche", "Gli albi illustrati dei fuoriusciti e dei migranti. Il racconto degli italiani all'estero durante il regime fascista", "Caterina Inesi"),
            (D(2023, 10, 30), "14-18", "unita_didattiche", "L'incontro con l'altro nei luoghi di confino politico durante il fascismo", "Margherita Marchetti"),
            (D(2023, 10, 30), "14-18", "unita_didattiche", "I “fuoriusciti” e l'antifascismo in Francia", "Giulio Massimo Girola Ceccacci"),
            (D(2023, 10, 31), "9.30-12.30", "lezione", "La mobilità degli studenti internazionali come migrazione politica", "Simona Berhe"),
            (D(2023, 10, 31), "9.30-12.30", "lezione", "L'asilo in Italia dal secondo dopoguerra all'uccisione di Jerry Masslo", "Donato Di Sanzo"),
            (D(2023, 10, 31), "9.30-12.30", "lezione", "La profughizzazione del lavoro migrante", "Valeria Piro"),
            (D(2023, 10, 31), "14-18", "unita_didattiche", "Crescere per accogliere", "Roberta Sale"),
            (D(2023, 10, 31), "14-18", "unita_didattiche", "Migrazioni politiche dell'Italia coloniale", "Cristina Di Cesare"),
            (D(2023, 10, 31), "14-18", "unita_didattiche", "Rifugiati: migranti politici o migranti economici? Il caso delle migrazioni jugoslave nel secondo dopoguerra", "Ada Alvaro"),
            (D(2023, 10, 31), "14-18", "unita_didattiche", "Attraversare i confini", "Francesca Gori"),
            (D(2023, 11, 1), "9.30", "visita", "Visita guidata ai luoghi della reclusione sull'isola di Ventotene", None),
            (D(2023, 11, 1), "12", "chiusura", "Chiusura della Scuola", None),
        ],
        "allegati": [("Call per la selezione dei docenti",
                      "https://www.ismed.cnr.it/wp-content/uploads/2023/10/CALL_Docenti_Scuola_di_Formazione-2.pdf")],
    },
    {
        "numero": 2, "anno": 2024, "inizio": D(2024, 10, 31), "fine": D(2024, 11, 3), "posti": 6,
        "fonte": "https://www.ismed.cnr.it/evento/scuola-formazione-ii-ed/",
        "zotero": "2024",  # nome della collezione radice
        "descrizione": OBIETTIVO + "\n\nCoordinamento tecnico: Francesco Di Filippo (CNR-ISMed).",
        "comitato": [("Michele", "Colucci", ISMED), ("Donato", "Di Sanzo", ISMED),
                     ("Giovanni", "Ferrarese", ISMED), ("Stefano", "Gallo", ISMED),
                     ("Valeria", "Deplano", CAGLIARI), ("Caterina", "Inesi", "Liceo artistico Ripetta, Roma"),
                     ("Arianna", "Onidi", "IC “Via Stoccolma”, Cagliari"), ("Anthony", "Santilli", SEDE)],
        "programma": [
            (D(2024, 10, 31), "19", "accoglienza", "Accoglienza, saluti e presentazione della scuola", None),
            (D(2024, 11, 1), "10-13", "lezione", "Esilio e migrazione nell'Italia liberale", "Stefano Gallo"),
            (D(2024, 11, 1), "10-13", "lezione", "Tra l'Africa e l'Italia. Mobilità (post) coloniali prima e dopo la seconda guerra mondiale", "Valeria Deplano"),
            (D(2024, 11, 1), "10-13", "lezione", "Investitori o colonizzatori? Convergenze e circolazione di idee democratiche nella nascita della questione sarda", "Arianna Onidi"),
            (D(2024, 11, 1), "15-18", "unita_didattiche", "Una graphic novel su Alberto Pallone", "Lorenzo Teodonio"),
            (D(2024, 11, 1), "15-18", "unita_didattiche", "Migrazioni politiche e strategie comunicative. L'Hymn of the Nations dell'Office of War Information", "Sara Follacchio"),
            (D(2024, 11, 1), "15-18", "unita_didattiche", "Un prima e un dopo. L'informazione visiva e il suo ruolo nella costruzione di una biografia sociale collettiva", "Claudia Tombini"),
            (D(2024, 11, 2), "10-13", "lezione", "L'emigrazione nella ricostruzione post-bellica: un movimento solo economico?", "Michele Colucci"),
            (D(2024, 11, 2), "10-13", "lezione", "Il colonialismo italiano e le migrazioni: letture, scritture, narrazioni. Percorsi di didattica della storia attraverso la letteratura, il laboratorio di scrittura e la lettura ad alta voce condivisa", "Caterina Inesi"),
            (D(2024, 11, 2), "10-13", "lezione", "Immigrazione straniera e agricoltura: una questione politica", "Donato Di Sanzo, Giovanni Ferrarese"),
            (D(2024, 11, 2), "15-18", "unita_didattiche", "Ventotene tra confino e partecipazione", "Simone Colafranceschi"),
            (D(2024, 11, 2), "15-18", "unita_didattiche", "Europa, un fatto prima che un'idea", "Olivia Pallenberg"),
            (D(2024, 11, 2), "15-18", "unita_didattiche", "Confini interni e confini esterni", "Olivia Russo"),
            (D(2024, 11, 3), "9.30", "visita", "Un esempio di percorso didattico-esperienziale. Le piccole isole come luoghi di mobilità politica ed economica attraverso il caso Ventotene, visita itinerante", "Anthony Santilli"),
            (D(2024, 11, 3), "12", "chiusura", "Chiusura della Scuola", None),
        ],
        "allegati": [("Locandina e programma",
                      "https://www.ismed.cnr.it/wp-content/uploads/2024/10/Le-migrazioni-politiche-nellItalia-contemporanea.pdf")],
    },
    {
        "numero": 3, "anno": 2025, "inizio": D(2025, 10, 30), "fine": D(2025, 11, 2), "posti": 8,
        "fonte": "https://www.ismed.cnr.it/evento/scuola-formazione-iii-ed-migrazioni-politiche-nellitalia-contemporanea/",
        "descrizione": OBIETTIVO,
        "comitato": [("Michele", "Colucci", ISMED), ("Francesco", "Di Filippo", ISMED),
                     ("Donato", "Di Sanzo", ISMED), ("Giovanni", "Ferrarese", ISMED),
                     ("Stefano", "Gallo", ISMED), ("Martina", "Lo Cascio", PALERMO),
                     ("Manoela", "Patti", PALERMO), ("Anthony", "Santilli", SEDE)],
        "programma": [
            (D(2025, 10, 30), "19", "accoglienza", "Accoglienza, saluti e presentazione della scuola", None),
            (D(2025, 10, 31), "9-13", "lezione", "Politiche migratorie, rapporti internazionali, diritto d'asilo: una storia complessa", "Stefano Gallo"),
            (D(2025, 10, 31), "9-13", "lezione", "Mobilità, confino politico e confino comune tra fascismo e Italia repubblicana", "Manoela Patti"),
            (D(2025, 10, 31), "9-13", "lezione", "Mobilità politica, circuiti punitivi e forme di resistenza tra epoca liberale e fascista", "Anthony Santilli"),
            (D(2025, 10, 31), "15-18", "unita_didattiche", "Da confinati a protagonisti: come un manifesto scritto in clandestinità abbia guidato le politiche europee del dopoguerra", "Andrea Matteini"),
            (D(2025, 10, 31), "15-18", "unita_didattiche", "Migrazione politica ed esilio: storie, cause e conseguenze. E se io, e quando io", "Giulia Del Vecchio"),
            (D(2025, 10, 31), "15-18", "unita_didattiche", "Parole in esilio: la voce degli scrittori migranti contro il fascismo", "Anna Di Giusto"),
            (D(2025, 10, 31), "15-18", "unita_didattiche", "Exsul: i tanti volti delle migrazioni", "Alice Bianchi"),
            (D(2025, 11, 1), "10-13", "lezione", "Immigrazione e diritto alla città nell'Europa degli anni 50: alcuni casi a confronto", "Michele Colucci"),
            (D(2025, 11, 1), "10-13", "lezione", "Mobilità e sfruttamento lavorativo in Italia (1949-2000)", "Donato Di Sanzo, Giovanni Ferrarese"),
            (D(2025, 11, 1), "10-13", "lezione", "Capacità organizzativa e di mobilitazione dei migranti in agricoltura e oltre", "Martina Lo Cascio"),
            (D(2025, 11, 1), "15-18", "unita_didattiche", "Con voci di donna. Il caso delle migrazioni femminili nel CAPS di Latina (1957-1989)", "Laura Pompili"),
            (D(2025, 11, 1), "15-18", "unita_didattiche", "Tutti siamo l'«altro». Identità, stereotipi e propaganda tra passato e presente", "Genny Catalano"),
            (D(2025, 11, 1), "15-18", "unita_didattiche", "El mundo en mis palabras", "Elisabetta Careri"),
            (D(2025, 11, 1), "15-18", "unita_didattiche", "Migrazione e ambiente: percorsi tra storia e letteratura", "Matteo Cionti"),
            (D(2025, 11, 2), "9.30", "visita", "Visita itinerante dell'isola", "Anthony Santilli"),
            (D(2025, 11, 2), "12", "chiusura", "Chiusura della Scuola", None),
        ],
        "allegati": [("Locandina e programma",
                      "https://www.ismed.cnr.it/wp-content/uploads/2025/10/Le-migrazioni-politiche-nellItalia-contemporanea.pdf")],
    },
]


def _persona(nome, cognome, affiliazione=None):
    """La stessa persona per tutte le edizioni (nome e cognome); l'affiliazione si riempie solo
    se manca, per non sovrascrivere quella corrente."""
    p = Persona.query.filter_by(nome=nome, cognome=cognome).first() or Persona(nome=nome, cognome=cognome)
    if affiliazione and not p.affiliazione:
        p.affiliazione = affiliazione
    db.session.add(p)
    return p


def _scarica(url):
    with urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": "scuola-ventotene"}),
                                timeout=20) as r:
        return r.read(20 * 1024 * 1024)


def carica(scarica=_scarica, avviso=print):
    """Carica le edizioni mancanti; ``scarica(url) -> bytes`` per gli allegati (nei test, finto).
    Restituisce gli anni caricati."""
    caricate = []
    for e in EDIZIONI:
        if Edizione.query.filter_by(numero=e["numero"]).first():
            avviso(f"{e['anno']}: già presente, non modificata.")
            continue
        ed = Edizione(numero=e["numero"], anno=e["anno"], slug=str(e["anno"]), titolo=TITOLO,
                      sottotitolo=SOTTOTITOLO, luogo="Ventotene", sede=SEDE,
                      data_inizio=e["inizio"], data_fine=e["fine"], posti_borsisti=e["posti"],
                      ammessi_uditori=True, stato="conclusa",
                      descrizione=e["descrizione"] + f"\n\nFonte: [pagina dell'evento sul sito CNR-ISMed]({e['fonte']}).")
        col = e.get("zotero") and ZoteroCollezione.query.filter_by(nome=e["zotero"], parent_key=None).first()
        ed.zotero_collection_key = col.key if col else None
        db.session.add(ed)
        for nome, cognome, aff in e["comitato"]:
            ed.persone.append(EdizionePersona(persona=_persona(nome, cognome, aff), ruolo="comitato"))
        for i, (giorno, ora, tipo, titolo, relatori) in enumerate(e["programma"]):
            db.session.add(ProgrammaVoce(edizione=ed, giorno=giorno, ora=ora, tipo=tipo,
                                         titolo=titolo, relatori=relatori, ordine=i))
        lezioni_dal_programma(ed, e["comitato"])
        ud_dal_programma(ed, e["comitato"])
        for titolo, url in e["allegati"]:
            try:
                dati = scarica(url)
                if not dati.startswith(b"%PDF"):
                    raise ValueError("non è un PDF")
                fs = FileStorage(io.BytesIO(dati), filename=url.rsplit("/", 1)[-1])
                info = salva_upload(fs, "materiali", {"pdf"})
            except Exception as ex:  # noqa: BLE001  (rete: l'edizione si carica lo stesso)
                avviso(f"{e['anno']}: allegato non scaricato ({ex}): {url}")
                continue
            m = Materiale(edizione=ed, titolo=titolo, autori="CNR-ISMed", tipo="bando",
                          visibilita="pubblico", stato="pubblicato", **info)
            db.session.add(m)
        db.session.commit()
        caricate.append(e["anno"])
    return caricate


def ud_dal_programma(ed, comitato=()):
    """Una UD (intervento di tipo ud) per ogni voce «unità didattiche» del programma con il nome
    del docente, se manca. Restituisce quante ne ha create (senza commit)."""
    return _dal_programma(ed, "unita_didattiche", "ud", comitato)


def lezioni_dal_programma(ed, comitato=()):
    """Una lezione per ogni voce «lezione» del programma, se manca, con tutti i relatori della
    voce come autori. Restituisce quante ne ha create (senza commit)."""
    return _dal_programma(ed, "lezione", "relazione", comitato)


def _dal_programma(ed, tipo_voce, tipo, comitato):
    db.session.flush()
    # cognomi composti («Di Sanzo»): valgono la divisione del comitato e le persone già nel sito
    noti = list(comitato) + [(p.nome, p.cognome, None) for p in Persona.query]
    # ponytail: l'intervento si riconosce dal titolo della voce (aggiorna_voce lo tiene allineato);
    # se l'admin cambia solo il titolo dell'intervento, ricreando dal programma ne nasce un altro
    esistenti = {iv.titolo: iv for iv in ed.interventi if iv.tipo == tipo}
    nuove = 0
    for v in sorted(ed.programma, key=lambda v: (v.ordine or 0, v.id or 0)):
        if v.tipo != tipo_voce or not v.relatori:
            continue
        iv = esistenti.get(v.titolo)
        if iv is None:
            iv = esistenti[v.titolo] = Intervento(edizione=ed, tipo=tipo, titolo=v.titolo, ordine=v.ordine or 0)
            db.session.add(iv)
            nuove += 1
        for nome_completo in v.relatori.split(", "):
            p = _persona(*_dividi(nome_completo.strip(), noti))
            iv.aggiungi_autore(ep_di(ed, p, RUOLO_AUTORE[tipo]))
        db.session.flush()
    return nuove


def _dividi(nome_completo, comitato):
    """Nome e cognome: se la persona è nel comitato si usa la divisione scritta lì (cognomi
    composti come «Di Sanzo»), altrimenti l'ultima parola è il cognome."""
    for nome, cognome, _ in comitato:
        if f"{nome} {cognome}" == nome_completo:
            return nome, cognome
    nome, _, cognome = nome_completo.rpartition(" ")
    return nome, cognome
