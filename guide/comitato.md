# Guida del comitato

Il back-office della scuola (**Gestione**, nella barra in alto) per il **comitato scientifico**
e l'**amministrazione**. Per le pagine dei docenti e dei relatori vedi la
[guida generale](/guida).

## Ruoli: comitato e amministrazione

| Azione | Comitato | Admin |
|---|---|---|
| Vedere candidature, graduatoria, export CSV | sì | sì |
| Valutare le candidature | sì | sì |
| Rivedere le letture proposte dai docenti | sì | sì |
| Vedere i materiali in revisione | sì | sì |
| Assegnare l'esito delle candidature | | sì |
| Creare e modificare edizioni, programma, persone, lezioni | | sì |
| Pubblicare, rifiutare o eliminare materiali | | sì |
| Ruoli e attivazione degli utenti, sincronizzazione Zotero | | sì |

I relatori non entrano nel back-office: usano l'area personale.

### Il cruscotto

**Gestione** apre il cruscotto: candidature da valutare, materiali in revisione, letture da
rivedere, numero di utenti, le edizioni con il loro stato e il riquadro della bibliografia
Zotero (ultima sincronizzazione, pulsanti di sincronizzazione per l'admin).

## Edizioni

### Creare e modificare un'edizione

**Nuova edizione** oppure **Modifica** accanto a un'edizione nel cruscotto (solo admin). Campi principali:
numero, anno, **slug** (l'indirizzo: `/edizioni/2026`), titolo, date, **scadenza delle
candidature**, data degli esiti, posti borsisti, uditori sì/no, **caratteri minimi e massimi**
della proposta, presentazione in Markdown, bando in PDF.

Lo **stato** decide cosa vede il pubblico:

- *Bozza*: invisibile;
- *Candidature aperte*: si può inviare fino alla scadenza compresa;
- *Candidature chiuse*: niente più invii; i docenti ammessi possono caricare i materiali del
  modulo;
- *Conclusa (archivio)*: come chiusa, in archivio.

### Programma

Nella scheda dell'edizione: una voce per giorno e orario, con tipo, titolo, relatori e ordine.
**Aggiungi voce** (senza ordine va in fondo al suo giorno), **modifica**, **elimina**. Il numero
accanto alla maniglia ⠿ è la posizione: trascinando la riga si cambia l'ordine dentro lo stesso
giorno, e il nuovo ordine si salva subito. Per spostare una voce su un altro giorno, o senza mouse,
si cambiano giorno e ordine da «modifica».

### Comitato, relatori e lezioni

**Comitato scientifico e relatori**: nome, cognome, affiliazione, ruolo e, per i relatori, il
titolo della lezione. Ogni relatore aggiunto è una **lezione**: titolo, **ordine** (la
posizione nell'archivio e nella bibliografia) e **account del relatore**.
Se le lezioni sono già nel programma (voci *lezione* con i relatori, separati da virgola), l'admin
le crea tutte con `flask lezioni-dal-programma`: una per relatore, anche quando la lezione è a
due voci; il comando si può rilanciare, non crea doppioni.

Per collegare l'account: il relatore si registra dal sito, l'admin gli dà il ruolo
*Relatore* in **Utenti**, poi lo sceglie nella lezione e **Salva lezione**. Da quel momento il
relatore carica i materiali e la bibliografia della lezione e vede le UD dei docenti ammessi.

Ruolo **Docente (UD)**: l'unità didattica di un docente senza candidatura sul sito (edizioni
2023–2025, create dal programma con `flask ud-dal-programma`). Titolo e ordine si correggono
come per le lezioni; l'account del docente si può già collegare, ma per ora non gli dà accesso.

### Completare le edizioni passate

Ogni lezione e ogni UD ha la sua **pagina pubblica** (link dai titoli del programma
dell'edizione, dall'archivio e dall'elenco delle persone qui sopra): abstract, materiali e
letture consigliate con le copertine. L'admin, aperta la pagina, trova tre riquadri:
**Modifica l'abstract** (markdown), **Carica un materiale** (PDF, PowerPoint o link, già
pubblicato, con la visibilità scelta) e **Aggiungi letture**, che apre la stessa ricerca dei
libri dei relatori: le letture entrano subito in Zotero, in «Relatori» o «Docenti»
dell'edizione, senza il tag delle proposte. Per le UD delle candidature ammesse la pagina
mostra titolo, nome, discipline e abstract del docente, e l'admin può caricarvi i materiali.

### Collezione Zotero dell'edizione

Nella scheda dell'edizione si sceglie la **collezione Zotero** tra le collezioni radice
sincronizzate. Senza collezione le letture non si possono approvare. Le sottocollezioni
«Docenti» e «Relatori» le crea il sito alla prima lettura salvata.

## Candidature

### Elenco e graduatoria

Dal cruscotto, il numero di candidature **inviate** di un'edizione apre l'elenco: in ordine prima i borsisti, poi per **media** dei punteggi
(decrescente), a parità per data di invio. Le bozze non compaiono. **Esporta graduatoria CSV** scarica la
graduatoria con le medie per criterio (separatore `;`, apribile in Excel).

### Valutare una candidatura

Fino alla scadenza il docente può ancora modificare la candidatura inviata (proposta e letture
non ancora rivedute): conviene valutare dopo la scadenza, quando la versione è definitiva.
L'esito blocca comunque ogni modifica.

Nella scheda: dati del docente, unità didattica, documento, abstract, letture proposte e le
valutazioni già date. In **La mia valutazione** si assegnano tre punteggi da 0 a 25:

- **Originalità**;
- **Potenzialità didattiche**;
- **Valorizzazione delle fonti**.

Totale massimo 75; una valutazione per membro del comitato, modificabile. La prima valutazione
porta la candidatura da *inviata* a *in valutazione*.

### Esito

Solo l'admin: riquadro **Esito**, stato e note interne. Quando lo stato diventa *ammessa*,
*riserva* o *non ammessa* il docente riceve l'email con l'esito. Le note interne non vengono
mai mostrate al docente.

## Invito alla lettura

### Riferimenti di base

Libri e siti validi per tutte le edizioni stanno in Zotero in una collezione di primo livello,
«Riferimenti di base», fuori dalle collezioni delle edizioni (non nella radice del gruppo: lì ci
sono tutti gli item). Si aggiungono direttamente in Zotero; dopo la sincronizzazione compaiono
in fondo all'invito alla lettura di ogni edizione, come sezione in Bibliografia e nella ricerca
dei libri. La collezione la sceglie l'admin una volta sola, con la sua key nel `.env`
(`ZOTERO_COLLEZIONE_BASE`).

### Revisione delle letture

**Letture**: le proposte dei docenti dell'edizione scelta (prima quelle da rivedere), con tipo,
docente, momento (*con la candidatura* o *dopo la scuola*) e stato. Le proposte delle
candidature in bozza non compaiono finché il docente non invia. Le letture dei relatori non
passano da qui: entrano subito in «Relatori».

### Approvare: collegare o creare

Aprendo una proposta: a sinistra chi la propone e perché, a destra la **scheda da salvare in
Zotero**, che si può correggere (la ricerca dei libri funziona anche qui). Poi:

- **Già in Zotero?** Se il sito trova record simili li elenca, con il primo selezionato:
  approvando, il record esistente viene **collegato** all'edizione (aggiunto a «Docenti»), senza
  crearne un altro.
- **No, crea un nuovo record**: il sito crea l'item in Zotero, in «Docenti» con il tag delle
  proposte, e scarica la copertina.

In Zotero entrano solo i dati bibliografici: mai il nome del docente né la motivazione. Una
lettura approvata non si modifica più dal sito: eventuali correzioni si fanno in Zotero.

### Doppioni

I possibili doppioni si cercano per **ISBN** (ISBN-10 e ISBN-13 sono equivalenti), per
**titolo e anno**, e con una **ricerca per titolo** direttamente in Zotero (titoli simili, record
non ancora sincronizzati). Se si sceglie «crea nuovo» il controllo si ripete al momento
dell'approvazione: se nel frattempo è comparso un doppione (per esempio un collega ha appena
approvato lo stesso libro) la scheda torna con il doppione selezionato e chiede conferma.

Restano alla vostra valutazione i titoli molto diversi senza ISBN e le edizioni diverse dello
stesso libro. Gli item nel cestino di Zotero non vengono proposti. Se Zotero non risponde, il
sito controlla solo la copia locale e lo segnala.

### Rifiutare

**Rifiuta** con una nota facoltativa: il docente vede lo stato e la nota nella propria area.

## Materiali

**Materiali**: tutti i materiali, prima quelli in revisione, con l'origine (relatore e lezione,
docente e unità didattica, o staff). L'admin sceglie per ciascuno **stato** (*in revisione*,
*pubblicato*, *rifiutato*) e **visibilità** (*pubblico*, *solo utenti registrati*, *solo
comitato*) e può eliminarlo. Sotto l'elenco l'admin carica direttamente i materiali dello
staff, già pubblicati. Il materiale di una lezione o di una UD si carica invece dalla sua
pagina (vedi *Completare le edizioni passate*).

## Utenti e ruoli

Solo admin. **Utenti**: per ogni account ruolo (*docente*, *relatore*, *comitato*, *admin*) e
attivo sì/no; un account disattivato non può più entrare. Non si può cambiare il proprio ruolo.
**Elimina** cancella l'account (per esempio uno creato per prova) con candidature, letture e
file caricati; non vale per chi ha valutato candidature o caricato materiali: quelli si disattivano.
Il primo admin si crea dal server con `flask crea-admin`.

Gli account dei **docenti delle edizioni passate** si creano dal server con `flask importa-docenti`
da un elenco di email (vedi README), già collegati alla loro UD. Non parte nessuna email: per
entrare il docente usa **Password dimenticata** con quell'indirizzo, sceglie la password e l'email
risulta confermata.

## Scrivere ai partecipanti

Solo admin, dal cruscotto o dal menu: **Scrivi ai partecipanti**. Si sceglie l'edizione (o tutte) e
i gruppi: *relatori* (lezioni con un account collegato), *docenti* (UD delle edizioni passate con un
account e candidature ammesse), *comitato scientifico* (persone del comitato con un account e utenti
con ruolo comitato o admin); tutti e tre = tutti. **Anteprima dei destinatari** mostra a chi andrà
e chi resta fuori perché non ha un account; solo dopo compare **Invia**. Le email partono dal mittente
del sito, con i destinatari in copia nascosta e in copia (Cc) gli indirizzi delle notifiche
(`MAIL_NOTIFICHE` nel `.env`). Chi risponde scrive in automatico al mittente e a quegli indirizzi. Non scrivere nel testo dati personali
dei partecipanti (date di nascita, telefoni, indirizzi).

## Bibliografia Zotero

### Struttura del gruppo

Zotero è la fonte di verità: il sito ne tiene una copia locale. Per ogni edizione:

```
Edizione 2026     collezione dell'edizione
├─ Relatori       letture dei relatori, divise per lezione nel sito
└─ Docenti        letture dei docenti approvate, con il tag delle proposte
```

Lezione e unità didattica di ogni lettura le conosce solo il sito. Si può lavorare in Zotero
come sempre (correggere, spostare, fondere doppioni): alla sincronizzazione il sito si adegua,
e se due item vengono fusi le proposte passano al superstite.

### Correggere una voce e la copertina

Solo admin. In **Invito alla lettura** e nelle pagine di lezioni e UD ogni voce ha il link
**modifica**. La pagina ha due parti:

- **Scheda** (libri e siti web): titolo, autori e curatori (uno per riga, «Cognome, Nome»),
  anno, editore, ISBN… **Salva in Zotero** scrive nel gruppo e aggiorna il sito con la risposta
  di Zotero. Se intanto qualcuno ha cambiato la voce in Zotero, il salvataggio si ferma: ricarica
  la pagina e ripeti. Gli altri tipi (articoli, capitoli…) si correggono in Zotero.
- **Copertina** (solo sul sito, non va in Zotero): **Cerca per ISBN** (Open Library, poi Amazon,
  per ultimo Google Books; una fonte che non risponde si salta e il messaggio dice quale),
  **Scarica dall'indirizzo** (solo immagini di Open Library, Google Books, archive.org o Amazon),
  **Carica l'immagine** (jpg, png, webp o gif, massimo 2 MB) oppure **togli la copertina**: una
  copertina tolta non viene più cercata dal comando automatico. Le copertine dei libri con ISBN
  si cercano anche da sole, ogni ora, con `flask zotero-copertine`.

### Sincronizzazione

Gira in automatico (cron). Dal cruscotto l'admin può lanciare **Sincronizza modifiche**
(incrementale, veloce) o **Sincronizzazione completa** (riallinea tutto, utile dopo grandi
riorganizzazioni). Gli item nel cestino di Zotero spariscono dal sito.
