# PIANO_LETTURE — iscrizione con "invito alla lettura", Zotero in lettura/scrittura, materiali post-scuola

Piano a fasi (una per sessione). Stato delle fasi: segnare qui sotto a ogni fine fase.

| Fase | Stato |
|---|---|
| F1 Zotero: configurazione e sync robusta | **fatta** (2026-11-06): `zotero-verifica`, cestino, guard, ISBN/firma; merge `dc:replaces` rimandato a F3 (servono i legami delle proposte) |
| F2 Zotero: scrittura | **fatta** (2026-11-06): `app/zotero_scrittura.py` (`crea_item`, `aggiorna_item`, `candidati_duplicati`), `FakeZot` in scrittura; nessuna rotta né migrazione |
| F3 Proposte di lettura e revisione del comitato | **fatta** (2026-11-06): `PropostaLettura` + migrazione, `/admin/letture` (collega o crea, rifiuta), `collega_item`, copertine con host ammessi, merge `dc:replaces` nella sync |
| F4 Lookup durante la digitazione | **fatta** (2026-11-06): `app/ricerca_libri.py`, `/area/letture/cerca`, `static/js/letture.js` (già attivo nella revisione del comitato); `GOOGLE_BOOKS_API_KEY` facoltativa (senza: 429 frequenti, resta Open Library); niente miniature esterne nel browser |
| F5 Flusso di iscrizione | **fatta** (2026-11-06): passi 1–4 (macro `passi`), `/area/candidatura/<id>/letture` (aggiungi/modifica/elimina in bozza, max 10, ricerca attiva), avviso nel riepilogo, letture nell'email di conferma, `la_scuola` e informativa aggiornate (Zotero, Google Books, Open Library senza dati personali) |
| R1 Struttura Zotero dell'edizione | **fatta** (2026-11-06): collezione dell'edizione scelta da elenco, sottocollezione «Docenti» creata dal sito (`zotero_docenti_key`), pagina edizione con il sotto-albero; struttura semplificata su richiesta (Edizione → Relatori, Docenti) |
| R2 Ruolo relatore e lezioni | **fatta** (2026-11-06): ruolo `relatore`, `Persona.utente_id`, lezione = `EdizionePersona` (`titolo_lezione`, `ordine`), `Materiale.lezione_id`; admin collega l'account nella scheda edizione; area «Le mie lezioni» con caricamento; archivio diviso per lezioni; `env.py` spegne le FK durante le migrazioni |
| R3 Bibliografia della lezione e UD per i relatori | **fatta** (2026-11-06): `PropostaLettura` di una candidatura **o** di una lezione (CHECK), letture dei relatori subito in «Relatori» (senza tag, conferma se ci sono doppioni), pagina edizione con «Relatori» divisa per lezione, UD dei docenti ammessi per i relatori, informativa aggiornata |
| F6 Dopo la scuola: altri libri e materiali | **fatta** (2026-11-06): `Candidatura.dopo_la_scuola` (ammessa, edizione chiusa/conclusa), `Materiale.candidatura_id` + migrazione, upload dalla candidatura (`?candidatura=`), upload libero chiuso, archivio con «Unità didattiche dei docenti», letture `post_scuola` (`PropostaLettura.modificabile`), informativa aggiornata |
| F7 Invito alla lettura pubblico | **fatta** (2026-11-06): filtro per sezione con le sottosezioni (edizione → «Relatori», «Docenti»), macro `voce_biblio` (copertina, ISBN, link) in `/bibliografia` e nella pagina edizione, `/bibliografia/copertine/<key>`, letture nella scheda candidatura del comitato; nessuna migrazione |
| F8 Sfogliare i materiali | da decidere |

## Riprendere da qui (stato al 2026-11-06)
- **Nessuna fase in corso.** F1–F7 e R1–R3 fatte, F8 rimandata. Fuori dal piano, dopo F7:
  edizioni 2023–2025 (`flask seed-precedenti`), sezione «Le edizioni» in `la_scuola.html`;
  attestati di frequenza rimandati (domande aperte in AGENTS.md, «Lavori aperti» 3).
- **F8 rimandata dall'utente** (2026-11-06). Quando si riprende: prototipo con file **di prova**
  generati qui (scelta dell'utente); ancora da chiedere se sul server CNR si può installare
  LibreOffice e cosa conta di più (testo selezionabile, mobile, accessibilità, nessuna
  installazione). In locale ci sono LibreOffice (`/Applications/LibreOffice.app`) e `pdftoppm`.
- Fatto dopo F7: doppioni delle letture (comitato e relatori, campo `visti`), testata con menu
  dell'account e «Gestione» in evidenza, guide in `guide/` con link «Guida» per pagina.
- Doppioni (dopo F7, 2026-11-06): la ricerca remota per titolo ora tiene anche i record già in
  cache (prima scartati: un titolo simile ma non uguale passava senza avviso); all'approvazione
  con «crea nuovo» il comitato rivede la scheda se è comparso un doppione non mostrato (campo
  `visti`). Restano: titoli molto diversi senza ISBN (decide il comitato), item nel cestino non
  proposti, con Zotero giù solo la cache.
- F7: nessuna migrazione. Il filtro per sezione ora include le sottosezioni (prima la
  collezione di un'edizione mostrava solo i record della radice). Nel DB locale nessuna
  copertina è ancora scaricata (serve una lettura approvata con copertina): la rotta è
  verificata solo dai test.
- F6 (decisioni dell'utente, 2026-11-06): caricano dopo la scuola le candidature `ammessa` di
  edizioni `chiusa | conclusa` (borsisti e uditori); materiali dei docenti pubblici di default;
  `/area/materiali/nuovo` senza `?lezione=` né `?candidatura=` risponde 404 (lo staff carica
  da `/admin/materiali`). Un file per invio (si ripete per più file). Limite di 10 letture per
  momento (iscrizione e dopo la scuola contano a parte).
- Ruoli: **docente** = insegnante che si candida; **relatore** = storico che tiene una lezione
  (account proprio, ruolo assegnato dall'admin, collegato alla lezione). Vedi «Struttura Zotero
  e relatori» qui sotto.
- Zotero: Edizione → «Relatori» e «Docenti» (niente collezioni per lezione: lezione e UD le
  conosce il sito). Letture dei docenti: revisione del comitato. Letture dei relatori: dirette.
- Git: repository **locale**, senza remote (creato il 2026-11-06). Un commit per fase,
  `Co-Authored-By` in coda.
- Database locale: migrazioni fino a `388437ba29c9`; backup prima di ogni fase in
  `instance/backup/`. Edizioni: 2023–2025 (concluse, da `seed-precedenti`; 2024 con la collezione Zotero
  «2024»), 2026 (conclusa), 2027 (aperta, creata dall'utente per le prove). Backup prima
  delle edizioni precedenti: `instance/backup/prima-edizioni-precedenti.db`.
- Note pratiche emerse provando:
  - dopo una modifica al `.env` il server di sviluppo va **riavviato** a mano (il reloader di
    `--debug` eredita le variabili vecchie);
  - Google Books senza `GOOGLE_BOOKS_API_KEY` risponde quasi sempre 429: resta Open Library;
  - per approvare letture l'edizione deve avere la collezione Zotero (Modifica edizione, elenco
    delle collezioni radice sincronizzate): crearla in Zotero e sincronizzare;
  - la collezione 2024 ha ancora una sottocollezione per lezione (struttura vecchia): la pagina
    dell'edizione la mostra lo stesso; riorganizzarla in Zotero è facoltativo;
  - slug numerici delle edizioni ("2027"): la candidatura sta in
    `/area/candidatura/edizione/<slug>` (prima collideva con `/area/candidatura/<id>`).
- Da verificare con il DPO: i punti `[DA VERIFICARE]` dell'informativa, compresi i nuovi su
  relatori, Zotero, Google Books e Open Library.
- Non provato in un browser vero: la ricerca dei libri (`letture.js`) e i passi della
  candidatura sono verificati solo dai test e dall'HTML generato.

## Context
L'utente vuole questo percorso del docente:
1. vede il bando aperto e si registra;
2. conferma l'email e compila la candidatura (già fatto);
3. indica libri e siti web consigliati (sezione **invito alla lettura**, facoltativa ma raccomandata);
4. mentre scrive il titolo, un **lookup** cerca a) se il titolo è già in Zotero, b) online (titolo,
   autori, ISBN, copertina…) per completare la scheda;
5. la fase di iscrizione si chiude così (lettura → invio candidatura);
6. dopo la scuola rientra e carica altri libri e soprattutto i **materiali del suo modulo**
   (PDF, PowerPoint), da rendere **sfogliabili** nel sito (soluzione da decidere più avanti);
7. in Zotero finiscono solo i tipi **book** e **webpage**.

Zotero diventa **lettura e scrittura**, portando da Itinera (`~/gitrepo/itinera/app/biblio/`) sync,
scrittura e dedup. Oggi il sito ha solo una sync in sola lettura (`app/zotero_sync.py`).

Decisioni dell'utente:
- libri proposti → **revisione del comitato**, poi scrittura in Zotero;
- ogni libro è legato alla **candidatura** e confluisce nell'invito alla lettura dell'edizione;
- **nessun nome del docente in Zotero**: il legame docente↔libro resta solo nel DB del sito;
- viewer dei materiali: **da decidere** (ultima fase, con prototipo).

Una fase per sessione; ognuna lascia il sito funzionante, con test e una migrazione Alembic
quando cambia lo schema. Ordine pensato per dipendenze: F1→F2→F3→F4 sono la catena Zotero;
F5–F7 costruiscono sopra; F8 è indipendente.

## Cosa si porta da Itinera (e cosa no)
| Itinera | Qui |
|---|---|
| `biblio/sync.py` 3 fasi, `version` letta prima del download, cestino come sotto-albero, `vanished_guard`, merge Zotero via `relations["dc:replaces"]` | sì, dentro `app/zotero_sync.py` esistente |
| `biblio/write.py` `create_item` / `update_item` (If-Unmodified-Since-Version, 412 → "ricarica"), `_refresh` (si salva solo ciò che risponde Zotero), `parse_creators` | sì, nuovo `app/zotero_scrittura.py`, solo `book` e `webpage` |
| `biblio/dedup.py` firma `titolo|tipo` normalizzata + `years_compatible`, controllo remoto `zot.items(q=titolo)` | sì, più **ISBN normalizzato** (Itinera non lo usa) |
| `tools/test_fonti.py` `FakeZot` | sì, in `tests/` come fixture pytest |
| config Zotero cifrata nel DB (`zoterodb`), `can_write()` via `key_info()` | **no** la tabella: restano le variabili `.env`; **sì** `can_write` in un comando di verifica |
| `BiblioPending` (coda di sync) | sostituita dalla coda proposte del comitato (F3) |
| tipi archivistici, citazioni persona↔fonte, `with_for_update` | no |

Itinera **non** ha lookup online né copertine: F4 è nuova.

Lookup online senza nuove dipendenze: `urllib.request` + `json` (stdlib), timeout 5 s. Fonti:
Google Books API (senza chiave a basso volume) e Open Library (`search.json`, copertine
`covers.openlibrary.org/b/isbn/…`). Le chiamate partono **dal server** (l'IP del docente non va a
Google). Copertine **scaricate in locale** quando il libro viene approvato (regola "niente risorse
esterne" di AGENTS.md).

---

## F1 — Zotero: configurazione e sync robusta
- `.env`/`config.py`: la `ZOTERO_API_KEY` deve avere **write** sul gruppo; nuova
  `ZOTERO_TAG_PROPOSTE` (default `proposta-docenti`).
- `flask zotero-verifica`: connessione, numero di item, `last_modified_version`, scrittura sì/no
  (porta `check_connection`/`can_write` di `itinera/app/cli/zotero.py:17-72`).
- `zotero_sync.py`: aggiungere cestino (`zot.trash(since)`), `vanished_guard`, propagazione del
  cestino alle sotto-collezioni, merge `dc:replaces` (sposta i legami delle proposte, F3).
- `ZoteroItem`: nuove colonne `isbn` (normalizzato a 13 cifre), `firma` (indice), `copertina_path`.
  Migrazione.
- Test: `FakeZot` in `tests/conftest.py`; sync incrementale, cancellazioni, cestino, guard.

## F2 — Zotero: scrittura
- `app/zotero_scrittura.py` (porta di `itinera/app/biblio/write.py:18-305`, ridotto):
  - `TIPI = {"book": [...titolo, autori, curatori, data, editore, luogo, ISBN, collana, url],
    "webpage": [autori, titolo, websiteTitle, url, accessDate]}`;
  - `crea_item(zot, tipo, campi, autori, collezioni, tag)`; `aggiorna_item(…, versione)` con 412 →
    errore leggibile; `_aggiorna_cache(key)` riscarica l'item e lo salva in `ZoteroItem`;
  - `candidati_duplicati(…)`: ISBN uguale, oppure firma uguale con anni compatibili, più
    `zot.items(q=titolo, limit=5)` remoto.
- Gli item creati vanno nella collezione dell'edizione (`Edizione.zotero_collection_key`) con tag
  `ZOTERO_TAG_PROPOSTE`. Nessun dato del docente.
- Test con `FakeZot`: creazione, duplicato per ISBN/firma, 412, solo tipi ammessi.

## F3 — Proposte di lettura e revisione del comitato
- Modello `PropostaLettura`: `candidatura_id` (FK, CASCADE), `tipo` (`book|webpage`), `campi` (JSON:
  titolo, autori, anno, editore, luogo, isbn, url, sito), `copertina_url` (dal lookup),
  `motivazione` (perché il docente lo consiglia, facoltativa), `zotero_key` (se è già in Zotero o
  dopo l'approvazione), `stato` (`proposta | approvata | rifiutata`), `momento`
  (`iscrizione | post_scuola`), `nota_comitato`, date. Stati in `models.py` come dizionari
  (`STATI_PROPOSTA`), nel context processor.
- Back-office `/admin/letture`: coda per edizione; **approva** → se `zotero_key` c'è già, solo
  legame; altrimenti controllo duplicati (F2), il comitato può correggere i campi, poi `crea_item`;
  scarica la copertina in `instance/uploads/copertine/` con `salva_upload`-like (nome casuale,
  solo immagini, dimensione massima); **rifiuta** con nota. `@comitato_required`.
- Migrazione + test (permessi, approvazione con FakeZot, nessun nome del docente nel payload Zotero).

## F4 — Lookup durante la digitazione
- `GET /area/letture/cerca?q=…[&isbn=…]` (`@login_required`, limite: query ≥ 3 caratteri, max ~30
  richieste/minuto per utente) → JSON
  `{"zotero": [{key, titolo, autori, anno, isbn}], "online": [{fonte, titolo, autori, anno,
  editore, isbn, copertina_url}]}`.
  - a) cache locale `ZoteroItem` (titolo/autori ilike, ISBN esatto) — veloce, niente rete;
  - b) Google Books + Open Library in parallelo leggero (thread), risultati fusi per ISBN,
    timeout 5 s; un errore di una fonte non blocca l'altra.
- Webpage: niente lookup automatico per ora (si inseriscono URL, titolo, sito a mano). Fetch del
  titolo da URL rimandato: richiede protezione SSRF.
- JS a mano, senza librerie (`app/static/js/letture.js`): debounce 300 ms, lista risultati sotto il
  campo, scelta → compila i campi del form; "Già in Zotero" evidenziato.
- Test: risposte di Google/Open Library finte (monkeypatch di `urllib.request.urlopen`), fusione per
  ISBN, normalizzazione ISBN-10→13, fonte giù.

## F5 — Flusso di iscrizione
- Pagina candidatura a **passi**: 1 Profilo · 2 Proposta UD · 3 Invito alla lettura (consigliato) ·
  4 Riepilogo e invio. Riuso di `area/candidatura.html` e `_macros.html`, niente wizard JS.
- Passo 3: elenco proposte della candidatura + form con lookup (F4); si può saltare.
  Nel riepilogo, se non ci sono letture: avviso "consigliato", **non** blocco (`problemi_invio`
  invariato). Le proposte si modificano finché la candidatura è in bozza.
- Email di conferma invio: elenca anche le letture proposte.
- Aggiornare `la_scuola.html` ("Come candidarsi").

## Struttura Zotero e relatori (R1–R3, decise il 2026-11-06)
Ruoli: **docente** = insegnante che si candida; **relatore** = storico che tiene una lezione, con
account proprio. Struttura del gruppo Zotero (scelta dell'utente: semplice, niente
sottocollezioni per lezione):
```
Edizione 2026          collezione dell'edizione (Edizione.zotero_collection_key)
├─ Relatori            letture dei relatori (Edizione.zotero_relatori_key, R3)
└─ Docenti             letture dei docenti approvate (Edizione.zotero_docenti_key),
                       nessun nome, tag ZOTERO_TAG_PROPOSTE
```
Lezione e unità didattica di ogni lettura le conosce solo il sito (`PropostaLettura.lezione_id` /
`candidatura_id`): è il sito a raggrupparle. La collezione 2024 ha ancora una sottocollezione per
lezione: la pagina dell'edizione la mostra lo stesso (una sezione per sottocollezione); va
riorganizzata a mano in Zotero se la si vuole uniforme. Materiali dei relatori
(`Materiale.lezione_id`, R2) distinti da quelli dei docenti (`Materiale.candidatura_id`, F6).

### R2 — Ruolo relatore e lezioni
- `RUOLI["relatore"]`, `Utente.is_relatore`; `Persona.utente_id` (FK nullable, unica, SET NULL):
  l'admin assegna il ruolo in `/admin/utenti` e collega la persona nella scheda dell'edizione.
- `EdizionePersona` (ruolo relatore) = la lezione: `titolo_lezione`, `ordine` (niente
  collezione Zotero per lezione).
- Materiali della lezione: `Materiale.lezione_id` (FK SET NULL), caricamento dall'area del
  relatore, revisione esistente in `/admin/materiali`.

### R3 — Bibliografia della lezione e UD per i relatori
- `PropostaLettura` con `candidatura_id` **oppure** `lezione_id` (CHECK: esattamente uno); il
  relatore propone con la stessa ricerca (F4) e la lettura entra **direttamente** in Zotero, senza
  revisione del comitato (decisione dell'utente, 2026-11-06), nella sottocollezione «Relatori»
  (`Edizione.zotero_relatori_key`, creata come «Docenti»). Nel sito le letture si raggruppano per
  lezione.
- Il relatore vede le candidature **ammesse** delle proprie edizioni: titolo, discipline,
  abstract, file della UD; mai email, telefono, nascita, residenza. `file_candidatura` esteso.
- Informativa privacy: i relatori vedono nome e UD dei docenti ammessi.

## F6 — Dopo la scuola: altri libri e materiali del modulo
- Chi: candidature `ammessa` di edizioni `chiusa | conclusa` (default; da confermare all'inizio
  della fase).
- `Materiale.candidatura_id` (FK nullable, SET NULL) + migrazione: i materiali dei docenti si
  distinguono così da quelli dei relatori (`Materiale.lezione_id`, R2) e dello staff (nessuno dei
  due). Upload multiplo di PDF/PPT/PPTX/ODP dalla scheda candidatura (riuso di `salva_upload`,
  `ESTENSIONI_MATERIALI`, stato `in_revisione`, revisione esistente in `/admin/materiali`, che
  mostra già l'origine). Riuso di `area.nuovo_materiale` con un parametro come `?lezione=`.
- Archivio dell'edizione: oggi «Lezioni» e «Altri materiali»; aggiungere «Unità didattiche dei
  docenti» per i materiali con `candidatura_id`.
- Nuove letture con `momento = post_scuola` su candidature non in bozza: oggi
  `/area/candidatura/<id>/letture` è modificabile solo in bozza; aprire l'aggiunta (non la
  modifica delle letture già decise) per le candidature ammesse. Stessa coda del comitato (F3),
  destinazione «Docenti».
- Informativa privacy: aggiornare la parte "Materiali" se cambia cosa si pubblica.

## F7 — Invito alla lettura pubblico
- Già fatto altrove: la pagina dell'edizione mostra l'invito alla lettura per sezioni (radice,
  «Relatori» per lezione, «Docenti», R1/R3); l'area docente mostra le letture della candidatura
  con stato e nota (F5).
- Da fare: `/bibliografia` con copertine (locali, `ZoteroItem.copertina_path`, servite con un
  controllo come i file), filtro per edizione (collezione) e per «Relatori»/«Docenti», schede
  `book`/`webpage` con ISBN e link; nessun nome del docente.
- Scheda candidatura del comitato (`admin/candidatura.html`): le letture della candidatura con
  link alla revisione.

## F8 — Sfogliare i materiali (decisione + prototipo)
- Prototipo di 1 sessione su 2–3 file veri, poi scelta tra:
  a) PPT/PPTX/ODP → PDF con LibreOffice headless sul server (cron/CLI, non nella richiesta) +
     PDF.js locale (unico viewer);
  b) pagine/slide → immagini (galleria, anteprime), più leggero, niente testo selezionabile;
  c) solo PDF nel viewer del browser, PPT in download.
- Criteri: dipendenze sul server CNR (LibreOffice), peso, accessibilità, ricerca nel testo.

---

## Per ogni fase
- Leggere modello, form, vista e template coinvolti; `ARCHITETTURA.md` aggiornato con rotte/modello.
- Migrazione: `uv run flask db migrate -m …`, rilettura, `upgrade`; `tests/test_migrazioni.py` verde.
- `uv run pytest`; prova a mano con `uv run flask --debug run` sulle pagine toccate.
- Mai test contro il gruppo Zotero vero: `FakeZot`. Prova reale solo con `flask zotero-verifica` e
  su una collezione di prova.
- Fine fase: aggiornare questa lista in AGENTS.md ("Lavori aperti") con lo stato.

## Prima di F1 (dall'utente)
- Chiave API Zotero con permesso di scrittura sul gruppo (zotero.org/settings/keys) nel `.env`.
- Collezione Zotero per l'edizione 2026 e la sua key in `Edizione.zotero_collection_key`.
