# Sito della Scuola di formazione di Ventotene — architettura

## 1. Scelta del framework: Flask

| Criterio | Flask | FastAPI |
|---|---|---|
| Tipo di sito | Pagine HTML con template, form, sessioni: è il suo terreno | Pensato per API JSON; i template sono un'aggiunta |
| Form, CSRF, login | Flask-WTF e Flask-Login maturi e integrati | Da costruire a mano o con librerie meno consolidate |
| Deploy sui server CNR | WSGI: gira subito su Apache/mod_wsgi, come le altre app | ASGI: serve uvicorn/gunicorn dietro reverse proxy, un nuovo pezzo di infrastruttura |
| Concorrenza | Più che sufficiente per pochi utenti | Il vantaggio dell'async qui non si sente |
| Ecosistema | Esteso (Flask-SQLAlchemy, Flask-Admin, Flask-Mail…) | Ottimo per servizi API |

**Decisione: Flask 3 + Flask-SQLAlchemy + SQLite.** Se più avanti servisse un'API (per esempio un'app o un widget esterno), si aggiungono a Flask alcune rotte JSON, senza cambiare framework.

SQLite va bene con poche decine di utenti: ci sono più letture che scritture, la modalità WAL è attiva e le chiavi esterne sono abilitate. Il backup è la copia di `instance/ventotene.db` e della cartella `instance/uploads/`.

## 2. Ruoli

L'unico ruolo globale è **amministratore** (`Utente.admin`). Comitato, relatore e docente valgono
**per edizione**: sono le righe `EdizionePersona` (edizione, persona, ruolo) della persona collegata
all'account, più le candidature per i docenti. Una persona può essere relatore e comitato nel 2026 e
docente nel 2025. Permessi: `Utente.comitato_di(ed)`, `edizioni_comitato()`, `lezioni()`.

| Ruolo | Cosa può fare |
|---|---|
| Visitatore | Consulta l'edizione corrente, il programma, il bando, l'archivio pubblico e la bibliografia |
| Docente (registrato) | Gestisce il profilo, si candida (come borsista o uditore), carica la proposta di UD, invia materiali e vede quelli riservati ai registrati |
| Relatore | Storico che tiene una lezione: si registra, l'admin collega l'account alla sua lezione (scheda dell'edizione); dall'area personale carica i materiali della lezione (in revisione come gli altri). Indica la bibliografia della lezione (entra subito in Zotero, in «Relatori») e vede le UD dei docenti ammessi della sua edizione, senza i loro dati personali |
| Comitato | Accede al back-office solo per le edizioni del proprio comitato: ne legge le candidature, assegna i punteggi (ognuno i propri), vede graduatoria, letture proposte e materiali |
| Admin | Fa tutto ciò che fa il comitato e in più gestisce edizioni, programma, comitato, esiti, materiali, utenti e la sincronizzazione Zotero |

## 3. Mappa del sito

```
/                         home: edizione in vetrina + edizioni precedenti
/la-scuola                presentazione, chi può partecipare, come candidarsi
/edizioni/<anno>          bando, date, programma, comitato, invito alla lettura dell'edizione
/edizioni/<anno>/bando    PDF del bando
/edizioni/<anno>/interventi/<id>        pagina di una lezione o di una UD senza candidatura: abstract,
                          materiali, letture con copertine (riquadri di caricamento per l'admin)
/edizioni/<anno>/unita-didattiche/<id>  UD di una candidatura ammessa (nome, titolo, discipline, abstract)
/archivio                 elenco delle edizioni
/archivio/<anno>          indice di lezioni e UD (link alle loro pagine, con i conteggi) + altri materiali
/materiali/<id>/scarica   download controllato
/bibliografia             invito alla lettura (Zotero): ricerca, sezioni (con le sottosezioni), tag
/bibliografia/copertine/<key>   copertina locale di un item non nel cestino
/contatti  /privacy
/guida, /guida/comitato    istruzioni (guide/*.md); quella del comitato solo per comitato e admin
/registrati  /accedi  /esci (POST, con CSRF)
/verifica/<token>         conferma dell'email (link inviato alla registrazione; /verifica/reinvia per un nuovo link)
/password-dimenticata  /reimposta-password/<token>   reset password via email (link valido 1 ora, una volta)

/area/                    area personale del docente
/area/profilo
/area/candidatura/edizione/<slug>  bozza → invio; dopo l'invio modifica fino alla scadenza (Candidatura.modificabile)
/area/candidatura/<id>    riepilogo, controlli del bando, invio/ritiro
/area/candidatura/<id>/coautore, /invito  il titolare invita (o toglie) il co-autore; l'invitato accetta o rifiuta (POST)
/area/materiali/nuovo?lezione=<id>|?candidatura=<id>   materiale della propria lezione (relatore) o
                          del modulo dopo la scuola (docente ammesso); va in revisione

/admin/                   cruscotto (comitato e admin)
/admin/edizioni/nuova, /admin/edizioni/<id>     edizione + programma + persone
/admin/edizioni/<id>/candidature(.csv)          graduatoria ed export
/admin/candidature/<id>                          scheda, valutazione, esito
/admin/materiali                                 revisione e caricamento
/admin/letture[?edizione=<id>], /admin/letture/<id>   revisione delle letture proposte (comitato)
/area/candidatura/<id>/letture[?tipo=webpage|?p=<id>]   passo 3: invito alla lettura del docente
/area/candidatura/<id>/letture/<id>/elimina      (finché la candidatura è modificabile e la lettura non è riveduta; dopo la scuola solo le nuove)
/area/letture/cerca?q=…[&isbn=…]                 ricerca dei libri (JSON, utenti registrati, 30/min)
/admin/utenti                                    amministratore, attivazione, ruoli per edizione, eliminazione (account di prova)
/admin/email                                     email a relatori, docenti, comitato (anteprima, copia nascosta)
/admin/edizioni-persone/<id>/account             account collegato alla persona (admin)
/admin/interventi/<id>                           titolo e ordine della lezione o UD (admin, POST)
/admin/interventi/<id>/autori, /elimina          aggiunge o toglie un autore; elimina (admin, POST)
/admin/interventi/<id>/materiali, /descrizione   materiale e abstract dentro lezione/UD (admin, POST)
/admin/candidature/<id>/materiali                materiale dentro la UD di una candidatura ammessa (admin, POST)
/area/lezioni/<id>/letture[?tipo=webpage]         bibliografia della lezione (relatore; admin per ogni lezione/UD)
/area/lezioni/<id>/letture/<id>/elimina           toglie dal sito (il record resta in Zotero)
/area/lezioni/<id>/unita-didattiche               UD dei docenti ammessi (relatore)
/admin/bibliografia/<key>                        correggere una voce (scritta in Zotero) e la sua copertina (admin)
/admin/zotero/sync                               sincronizzazione manuale
```

## 4. Modello dati (SQLite)

```
utenti ─┬─< candidature >── edizioni ──< programma_voci
        │        └──< valutazioni >── utenti (comitato)
        │        └──< proposte_lettura ··· zotero_items (zotero_key)
        └─< materiali >── edizioni
edizioni ──< edizioni_persone >── persone ··· utenti (persone.utente_id: account della persona)
edizioni ──< interventi >──< intervento_autori >── edizioni_persone   (autori: stessa edizione)
                 └──< materiali, proposte_lettura (intervento_id)
candidature ──< materiali (candidatura_id: materiali del modulo, dopo la scuola)
edizioni.zotero_collection_key ··· zotero_collezioni
zotero_items >──< zotero_collezioni   (zotero_item_collezioni)
sync_stato (versione libreria Zotero, data ultima sync)
```

- **Edizione**: numero, anno, slug, titolo, sottotitolo, date, scadenza, data degli esiti, posti borsisti, uditori sì/no, limiti di caratteri (6000–8000), stato (`bozza → aperta → chiusa → conclusa`), bando e collezione Zotero collegata.
- **Candidatura**: titolare (`utente`), co-autore facoltativo (`coautore`, vale dopo `coautore_confermato`), UD creata all'ammissione (`intervento`, Intervento di tipo `ud` con gli autori), tipo (borsista o uditore), stato (`bozza → inviata → in_valutazione → ammessa | riserva | non_ammessa`, oppure `ritirata`), titolo dell'UD, discipline, file e numero di caratteri (calcolato automaticamente per i .docx). Ogni docente ha al massimo una candidatura per edizione.
- **Valutazione**: una per membro del comitato, con originalità, potenzialità didattiche e valorizzazione delle fonti (0–25 ciascuna, massimo 75). La graduatoria usa la media dei punteggi.
- **PropostaLettura**: libro (`book`) o sito (`webpage`) consigliato da un docente nella candidatura **oppure** dagli autori di un intervento (vincolo: esattamente una delle due); campi bibliografici in JSON (nomi Zotero più autori e curatori), copertina dal lookup, motivazione, momento (`iscrizione` = mentre la candidatura era modificabile, `post_scuola` = dopo la scadenza o l'esito), stato (`proposta | approvata | rifiutata`), nota del comitato e `zotero_key` dell'item collegato. Il legame docente↔libro esiste solo qui.
- **EdizionePersona**: ruolo di una persona in un'edizione, `comitato | relatore | docente` (`RUOLI_EDIZIONE`), una riga per (edizione, persona, ruolo). **Persona.utente_id** lega la persona all'account (uno per persona, vale per tutti i ruoli in tutte le edizioni).
- **Intervento**: lezione (`relazione`) o UD senza candidatura (`ud`) di un'edizione: titolo, `ordine`, `descrizione` (abstract in markdown), uno o più **autori** (`intervento_autori` → EdizionePersona della stessa edizione con il ruolo relatore o docente, controllato da `Intervento.aggiungi_autore`). Una persona può firmare più interventi nella stessa edizione. Le lezioni si creano salvando una voce «lezione» del programma, o con il pulsante «Crea le lezioni dal programma» / `flask lezioni-dal-programma`: una per voce, con tutti i relatori della voce come autori; il titolo della voce rinominata passa alla lezione. Le UD delle edizioni passate con `flask ud-dal-programma`.
- **ZoteroItem.copertina_path**: copia locale della copertina; `""` = cercata per ISBN e non trovata (`flask zotero-copertine`).
- **Materiale**: edizione, origine (intervento, candidatura di un docente, nessuna per lo staff), tipo (slide, relazione, UD, bando…), file o link, visibilità (`pubblico | registrati | privato`) e stato (`in_revisione | pubblicato | rifiutato`).

## 5. Flussi principali

**Candidatura**: il docente si registra (con consenso privacy), poi segue quattro passi (macro `passi` in `_macros.html`, senza JS): 1 profilo (data di nascita, telefono e residenza sono richiesti dal bando), 2 proposta (bozza con il file), 3 invito alla lettura (facoltativo ma consigliato: fino a 10 libri o siti in tutto, con la ricerca dei libri; si aggiungono anche dopo l'invio finché la candidatura non è ritirata e i contenuti dell'edizione sono aperti, `Candidatura.letture_aperte`, e si modificano finché non sono state rivedute), 4 riepilogo e invio. Dopo l'invio il docente modifica la proposta fino alla scadenza, o fino all'esito (`Candidatura.modificabile`: stato `bozza | inviata | in_valutazione` e candidature aperte); una modifica che non rispetta il bando viene scartata e resta la versione inviata. Il sistema controlla i requisiti; le letture non bloccano l'invio (nel riepilogo c'è solo un avviso) e sono elencate nell'email di conferma. Può inviare solo entro la scadenza. Poi il comitato valuta, l'admin assegna l'esito, e l'export CSV restituisce la graduatoria.

**Materiali**: l'admin pubblica direttamente da `/admin/materiali`. Il relatore carica dalla propria lezione; il docente dalla propria candidatura, solo **dopo la scuola** (`Candidatura.dopo_la_scuola`: ammessa, edizione chiusa o conclusa, contenuti aperti). **Chiusura dei contenuti** (`Edizione.chiusura_contenuti`, vuota = sempre aperti): dopo quella data materiali e letture di lezioni e UD si consultano soltanto, e solo l'admin li modifica (`Utente.puo_modificare`). Non c'è un caricamento libero. I materiali restano in revisione finché l'admin non li pubblica o rifiuta, scegliendo anche la visibilità (default pubblico). L'archivio dell'edizione li divide in «Lezioni», «Unità didattiche dei docenti» e «Altri materiali».

**Dopo la scuola**: il docente può continuare ad aggiungere letture (`momento = post_scuola`, sempre entro 10 in tutto), che vanno nella stessa coda del comitato e in «Docenti»; tutte si correggono o si eliminano finché non sono rivedute (`PropostaLettura.modificabile`).

**Bibliografia Zotero**: la bibliografia si cura nel gruppo Zotero, che resta la fonte di verità. Il sito ne tiene una copia locale aggiornata dalla sync. Il sito scrive in Zotero (`app/zotero_scrittura.py`) solo le letture proposte dai docenti e approvate dal comitato (solo tipi libro e pagina web, senza dati dei docenti). Gli item nel cestino Zotero non compaiono sul sito.
- Il comando `flask zotero-sync` gira in cron (per esempio ogni ora) e si può lanciare anche dal cruscotto; dopo di lui `flask zotero-copertine` scarica le copertine dei libri con ISBN (Open Library, Amazon per ISBN-10, poi Google Books, dal server; ogni fonte è indipendente, un errore di rete o di quota lascia il libro da riprovare; le immagini sotto 1 KB sono segnaposto e si scartano).
- La sincronizzazione è incrementale: usa `since=<versione>` per collezioni e record e `/deleted` per le rimozioni. La sincronizzazione completa con `--completa` riallinea tutto.
- Le citazioni arrivano già formattate dall'API (`include=bib`, stile CSL `chicago-author-date`, locale `it-IT`, entrambi configurabili).
- Le collezioni del gruppo diventano le "sezioni" della bibliografia; filtrare per una sezione include le sottosezioni (l'edizione mostra anche «Relatori» e «Docenti»). Ogni voce (macro `voce_biblio`, anche nella pagina dell'edizione) ha citazione, ISBN, link e la copertina locale se c'è, servita da `/bibliografia/copertine/<key>`; nessun dato del docente né motivazione. La scheda della candidatura del comitato elenca le letture con il link alla revisione. Ogni edizione può essere collegata a una collezione, che compare come invito alla lettura nella pagina dell'edizione.
- La chiave API deve avere il permesso di scrittura sul gruppo (controllo: `flask zotero-verifica`); per la sola lettura basta una chiave in lettura, o nessuna se il gruppo è pubblico.

**Struttura del gruppo Zotero**: una collezione per edizione (scelta da elenco in Modifica edizione, tra le collezioni radice sincronizzate); dentro due sottocollezioni, «Relatori» e «Docenti»; «Docenti» la crea il sito alla prima lettura approvata (`Edizione.zotero_docenti_key`). Lezione e unità didattica di ogni lettura le conosce solo il sito (`PropostaLettura`), che le raggruppa. La pagina pubblica dell'edizione mostra l'invito alla lettura come sotto-albero: prima i record della radice, poi una sezione per sottocollezione (anche le vecchie per lezione, come nel 2024), per ultima «Docenti». Le letture dei relatori entrano subito in «Relatori» (`Edizione.zotero_relatori_key`), senza tag e senza revisione; se ci sono possibili doppioni il relatore sceglie prima il record. Nella pagina dell'edizione «Relatori» è divisa per lezione (il legame lo conosce il sito); i record aggiunti a mano in Zotero restano sotto «Relatori». Togliere una lettura dal sito non la elimina da Zotero. **Riferimenti di base**: una collezione di primo livello non legata a nessuna edizione (key in `ZOTERO_COLLEZIONE_BASE`), con le sue sottocollezioni, compare in fondo all'invito alla lettura di ogni edizione, anche di quelle senza collezione; senza doppioni con le sezioni dell'edizione. In `/bibliografia` e nella ricerca dei libri è una collezione come le altre.

**Letture proposte** (PIANO_LETTURE.md): il docente indica libri e siti nella candidatura (passo 3); dopo l'invio vede lo stato e la nota del comitato. In `/admin/letture` il comitato vede le proposte delle candidature inviate, corregge la scheda e sceglie: collegarla a un record già in Zotero (doppioni trovati per ISBN, per titolo e anno, o dalla ricerca per titolo in Zotero) oppure crearne uno nuovo. Se sceglie «crea nuovo», il controllo si ripete all'approvazione: se è comparso un doppione che la pagina non mostrava (per esempio approvato intanto da un altro membro del comitato), la scheda torna con il doppione selezionato e chiede conferma. In entrambi i casi l'item entra nella sottocollezione «Docenti» dell'edizione con il tag `ZOTERO_TAG_PROPOSTE`, e la copertina viene scaricata in `uploads/copertine/` (solo da Google Books, Open Library, archive.org e Amazon). Serve che l'edizione abbia la sua collezione Zotero. Se in Zotero si fondono due item, la sync sposta le proposte sul superstite (`dc:replaces`). Una proposta rifiutata riporta la nota del comitato; una approvata si corregge direttamente in Zotero.

**Ricerca dei libri**: mentre si scrive il titolo (`letture.js`, 300 ms di pausa) il sito cerca nella copia locale di Zotero e, dal server, su Google Books e Open Library (timeout 5 s, in parallelo, risultati fusi per ISBN; se una fonte non risponde restano le altre). I risultati già in Zotero sono evidenziati; scegliendone uno si compilano i campi della scheda. Il browser non contatta servizi esterni: le copertine restano un indirizzo finché il comitato non approva. Per i siti web niente ricerca automatica (il titolo da un URL richiederebbe protezioni SSRF). La ricerca serve al docente (passo 3) e al comitato in `/admin/letture/<id>`.

## 6. Sicurezza e dati personali

- Email transazionali (`app/posta.py`, SMTP Infomaniak, solo testo): conferma dell'indirizzo alla registrazione, reset password, conferma dell'invio al docente con notifica ai referenti (`MAIL_NOTIFICHE`), esito al docente quando lo stato passa ad ammessa / riserva / non ammessa. Senza email confermata la candidatura non si può inviare. I link usano token firmati con la `SECRET_KEY` (itsdangerous); quello di reset decade appena cambia la password. Un errore SMTP finisce nel log e non blocca l'operazione.

- CSRF su tutti i form; password con hash (Werkzeug); cookie `HttpOnly` e `SameSite`, `Secure` in produzione.
- I file caricati sono salvati con un nome casuale fuori da `static/` e serviti solo attraverso rotte che controllano i permessi. Le estensioni ammesse sono limitate e la dimensione massima è configurabile (60 MB di default).
- Il sito tratta dati personali (data di nascita, residenza, telefono). Restano da definire con il DPO del CNR l'informativa e i tempi di conservazione (per esempio la cancellazione dei dati delle candidature N anni dopo l'edizione).

## 7. Da fare (prossimi passi)

1. Testi istituzionali (storia e obiettivi, enti promotori; «Le edizioni» è scritta), loghi CNR-ISMed, Centro Ventotene e ANPPIA, verifica dell'informativa privacy con il DPO.
2. Edizioni 2023–2025 caricate (`flask seed-precedenti`, dati in `app/edizioni_precedenti.py`); UD dei docenti create dal programma (`flask ud-dal-programma`); mancano i materiali di lezioni e UD (l'admin li carica dalla pagina di ciascuna) e gli account di relatori e docenti.
3. Attestati di frequenza in PDF (borsisti e uditori): rimandati. Da decidere: tecnica (carta intestata `modelli/*.docx` compilata e convertita con LibreOffice, oppure fpdf2), chi li riceve (frequenza segnata dall'admin o tutti gli ammessi), firmatario e monte ore.
4. Opzionale: campi per la registrazione delle presenze, export degli iscritti e degli uditori.
5. [PIANO_LETTURE.md](PIANO_LETTURE.md): fatte F1–F7 e R1–R3; F8 (sfogliare i materiali) rimandata. Stato e punto di ripresa in cima al file.
6. Ristrutturazione di ruoli e interventi (novembre 2026), cose da finire:
   - **Produzione**: backup, `flask db upgrade` (prima su una copia), `flask ud-dalle-candidature`; riagganciare al comitato di ogni edizione gli account segnalati dalla migrazione; fissare la chiusura dei contenuti della 2026.
   - **Docenti autori di UD senza candidatura** (edizioni passate): l'account collegato non dà ancora permessi sulla UD. Per aprirli basta che `area._mia_lezione` usi `Utente.interventi()` invece di `lezioni()` (e che le pagine dicano «UD» invece di «lezione»).
   - **Più di un co-autore per UD**: `Intervento` ne regge N, la candidatura uno solo (`coautore_id`); servirebbe una tabella di co-autori della candidatura.
   - **UD in due e posti borsisti**: quanti posti conta una UD in due lo decide il comitato a mano; da fissare con l'utente se va nel bando o nel sito.
   - **Titolo della UD ammessa**: l'Intervento creato all'ammissione copia `titolo_ud`; se il docente o l'admin lo cambiano dopo, i due titoli divergono (la pagina pubblica usa quello della candidatura).
   - **Lezioni dal programma**: si riconoscono dal titolo della voce; se l'admin cambia solo il titolo della lezione, ricreandole dal programma ne nasce un'altra (`ponytail:` in `_dal_programma`).
   - **Sposta in un'altra edizione** (`/admin/utenti`): rifiutato se la lezione ha altri autori; eventualmente spostare l'intervento intero con tutti gli autori.
   - **Informativa**: aggiornata (co-autore, comitato per edizione); va riletta con il DPO insieme agli altri `[DA VERIFICARE]`.
