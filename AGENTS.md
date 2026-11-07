# AGENTS.md — Scuola di formazione di Ventotene

Istruzioni per agenti di sviluppo (Claude Code e simili). Leggere prima questo file, poi
[ARCHITETTURA.md](ARCHITETTURA.md) (ruoli, mappa del sito, modello dati, flussi) e
[README.md](README.md) (avvio in locale e deploy).

## Il progetto in breve

Sito della scuola di formazione per docenti di Ventotene (CNR-ISMed, Centro di ricerca e
documentazione sul confino politico e la detenzione Isole di Ventotene e Santo Stefano, ANPPIA).
Serve a: presentare l'edizione corrente (bando, programma, comitato), raccogliere le candidature
dei docenti (borsisti o uditori) con la proposta di unità didattica, far valutare le candidature
al comitato, archiviare i materiali delle edizioni passate e mostrare una bibliografia
sincronizzata da un gruppo Zotero.

Pochi utenti (decine), molte più letture che scritture: per questo **Flask + SQLite**.
Lingua del sito, del codice di dominio e dei commenti: **italiano**.

## Stack

- Python **3.10** (quello di sistema di Ubuntu 22.04; `.python-version`, `requires-python`), gestito con **uv**: niente sintassi o API 3.11+
- Flask 3, Flask-SQLAlchemy, Flask-Migrate (Alembic), Flask-Login, Flask-WTF (CSRF), WTForms, email-validator
- SQLite in `instance/ventotene.db` (WAL + foreign keys attivati in `app/extensions.py`)
- Jinja2 senza framework JS né build step; CSS scritto a mano in `app/static/css/style.css`;
  JS a mano solo dove serve (`app/static/js/letture.js`, ricerca dei libri), caricato con `{% block script %}`
- pyzotero (bibliografia), python-docx (conteggio caratteri), markdown (testi delle edizioni)
- Produzione: Ubuntu 22.04, Apache + mod_wsgi di sistema (3.10), progetto in `/var/www/scuolaventotene` con `venv/` (`wsgi.py`)

## Comandi

```bash
uv sync                                  # ambiente e dipendenze
export FLASK_APP=app:create_app          # (anche in .env)
uv run flask init-db                     # crea/aggiorna le tabelle (= flask db upgrade)
uv run flask db migrate -m "descrizione"  # nuova migrazione dopo una modifica ai modelli
uv run flask seed-2026                   # IV edizione dai dati del bando
uv run flask seed-precedenti             # edizioni 2023–2025 (app/edizioni_precedenti.py)
uv run flask crea-admin email@ismed.cnr.it
uv run flask prova-email tuo@indirizzo.it   # controlla la configurazione SMTP
uv run flask ud-dal-programma            # UD dei docenti delle edizioni passate dal programma
uv run flask importa-docenti FILE [--applica]  # account dei docenti passati da un elenco di email (file fuori dal repo)
uv run flask lezioni-dal-programma       # lezioni dei relatori dalle voci «lezione» del programma
uv run flask zotero-sync [--completa]    # bibliografia (in produzione gira in cron)
uv run flask zotero-copertine            # copertine per ISBN (in cron dopo il sync)
uv run flask zotero-verifica              # chiave, gruppo, permesso di scrittura
uv run flask --debug run                 # server di sviluppo
uv run pytest                            # test (cartella tests/)
```

Dipendenze: sempre `uv add <pacchetto>` (o `uv add --dev`), mai `pip install` a mano:
`pyproject.toml` e `uv.lock` devono restare allineati e `uv.lock` va committato.
`mod_wsgi` **non** va aggiunto alle dipendenze: è il pacchetto di sistema del server.

## Struttura

```
config.py            Config (da variabili d'ambiente / .env) e TestConfig (SQLite in memoria, CSRF off)
wsgi.py              entry point mod_wsgi (carica .env, crea l'app)
app/__init__.py      application factory create_app(), blueprint, handler 403/404/413
app/extensions.py    db (naming convention), migrate, login_manager, csrf, PRAGMA SQLite
app/models.py        tutti i modelli + dizionari di stati/tipi (STATI_*, TIPI_*, VISIBILITA, RUOLI)
app/forms.py         form WTForms
app/utils.py         decoratori di permesso, upload, conteggio caratteri, filtri Jinja, context processor
app/guida.py         guide (guide/*.md, markdown + indice), mappa pagina → sezione AIUTO, link «Guida»
app/zotero_sync.py   sync Zotero → sito, verifica chiave, normalizzazione ISBN/firma
app/zotero_scrittura.py  crea/aggiorna item book|webpage, controllo duplicati (ISBN, firma+anno, ricerca remota)
app/ricerca_libri.py     lookup: cache ZoteroItem + Google Books / Open Library (dal server, in parallelo, fusi per ISBN)
app/posta.py         email SMTP (Infomaniak) e token firmati per verifica email / reset password
app/edizioni_precedenti.py  dati delle edizioni 2023–2025 dalle pagine CNR-ISMed (flask seed-precedenti)
app/cli.py           comandi flask
app/views/           un blueprint per area: public, auth, area (/area), archivio, bibliografia, admin (/admin)
app/templates/       una cartella per blueprint; base.html e _macros.html condivisi
app/static/          css/style.css, js/letture.js, js/menu.js e font locali (ET Book, Inter, JetBrains Mono)
guide/               istruzioni: guida.md (docenti e relatori, pubblica), comitato.md (comitato e admin)
modelli/             carta intestata CNR-ISMed (.docx), per gli attestati (non ancora usata)
migrations/          migrazioni Alembic (Flask-Migrate), da committare
instance/            database e uploads/ — non versionata, non toccare a mano
```

## Convenzioni

**Dominio in italiano.** Modelli, tabelle, campi, rotte, funzioni e template usano nomi italiani
(`Utente`, `Candidatura`, `Edizione`, `Materiale`, `valutazioni`, `salva_upload`,
`problemi_invio`…). Mantenere lo stesso stile; l'inglese resta solo per le API delle librerie.

**Stati e vocabolari controllati** stanno in `app/models.py` come dizionari `chiave → etichetta`
e arrivano ai template tramite il context processor in `utils.register_template_utils`. Per un
nuovo stato o tipo: aggiungerlo al dizionario (e al context processor se è un dizionario nuovo),
non scrivere stringhe sparse nelle viste o nei template.
- Edizione: `bozza → aperta → chiusa → conclusa`
- Candidatura: `bozza → inviata → in_valutazione → ammessa | riserva | non_ammessa`, oppure `ritirata`
- Materiale: `in_revisione | pubblicato | rifiutato`; visibilità `pubblico | registrati | privato`
- PropostaLettura: `proposta → approvata | rifiutata`; tipi `book | webpage`; momento `iscrizione | post_scuola`

**Regole del bando** (non cambiarle senza che lo chieda l'utente): una candidatura per docente
per edizione (vincolo unico); proposta di UD tra `caratteri_min` e `caratteri_max` dell'edizione
(6000–8000 nel 2026), contata spazi inclusi; data di nascita, telefono, residenza ed email confermata obbligatori
per inviare; invio solo entro `scadenza_candidature`; dopo l'invio la proposta si modifica
fino alla scadenza o all'esito (`Candidatura.modificabile`), e una modifica che non passa
`problemi_invio` viene scartata; letture del docente in qualsiasi momento, massimo 10 in tutto,
finché la candidatura non è ritirata (`Candidatura.letture_aperte`), modificabili finché non
rivedute; valutazione su tre criteri 0–25
(originalità, potenzialità didattiche, valorizzazione delle fonti), massimo 75, una valutazione
per membro del comitato, graduatoria sulla media. I controlli sul contenuto prima dell'invio
stanno in `Candidatura.problemi_invio` (il conteggio caratteri vale solo per i .docx: per PDF/ODT
`n_caratteri` resta `None`), l'apertura delle candidature in `Edizione.candidature_aperte`:
estendere lì, non nelle viste.

**Ruoli e permessi.** `visitatore`, `docente`, `relatore`, `comitato`, `admin` (admin include
comitato; il relatore non entra nel back-office). Docente = insegnante che si candida; relatore =
storico che tiene una lezione: le sue lezioni sono `Utente.lezioni()` (via `Persona.utente_id`),
e ogni accesso a una lezione passa da lì. Il relatore vede le UD solo dei docenti **ammessi**
nelle edizioni in cui insegna (`area._relatore_di`), mai email, telefono, nascita, residenza.
UD senza candidatura (edizioni passate) = `EdizionePersona` con ruolo `docente` (`RUOLI_EDIZIONE`),
create dal programma (`ud_dal_programma`); l'account collegato per ora non dà permessi.
Pagina pubblica di lezione/UD: `public.intervento` (EP) e `public.unita_didattica` (solo
candidature ammesse, niente dati personali, abstract del docente come testo, mai `markdown`);
l'admin vi carica materiali e abstract (`admin.materiale_intervento`, `materiale_candidatura`,
`descrizione_intervento`) e apre le letture di ogni EP (`area._mia_lezione`).
Il docente carica materiali solo dalla propria candidatura dopo la scuola
(`Candidatura.dopo_la_scuola`), il relatore dalla propria lezione, lo staff da `/admin/materiali`.
Proteggere le viste con `@login_required`, `@comitato_required` o `@admin_required`
(`app/utils.py`); per i materiali usare `Materiale.visibile_a(user)`. Ogni nuova rotta del
back-office deve avere un decoratore di permesso.

**File caricati.** Sempre tramite `salva_upload()` (nome casuale, estensioni da
`ESTENSIONI_PROPOSTE` / `ESTENSIONI_MATERIALI`, cartella `instance/uploads/`) ed
`elimina_upload()`. Mai salvare in `static/`, mai usare il nome originale come percorso, mai
servire file con `send_from_directory` senza prima controllare i permessi, come fanno
`archivio` (`/materiali/<id>/scarica`) e `area` (`/candidatura/<id>/file`).

**Form.** Ogni form è una classe in `app/forms.py` (Flask-WTF, quindi con CSRF). Nei template
includere sempre `{{ form.hidden_tag() }}`; per form scritti a mano, `csrf_token()`.

**Template e stile.** Estendere `base.html`; riusare le macro di `_macros.html` e le classi
esistenti in `style.css` prima di aggiungerne di nuove. Registro grafico: serif ET Book per i
testi, Inter per l'interfaccia, accento `#cf3f02` (variabili `--accento*` in `:root`). Usare le
variabili CSS, non colori scritti a mano. Niente CDN: font e risorse restano locali. Date
nei template con i filtri `data_it` e `giorno_it`; testi lunghi delle edizioni in markdown con il
filtro `markdown`.

**Guide.** Le istruzioni stanno in `guide/guida.md` (docenti e relatori) e `guide/comitato.md`
(comitato e admin), modello Itinera ma senza modifica dal browser: si correggono nel repository.
Pagina nuova in `area`, `admin` o `auth`: aggiungerla ad `AIUTO` in `app/guida.py` (endpoint →
titolo della sezione) e, se serve, scrivere la sezione; `test_guida.py` fallisce altrimenti.
Cambia un flusso descritto nelle guide: aggiornare anche la guida. Nella testata le variabili
di `base.html` hanno il prefisso `_` (`_ep`, `_u`…) per non coprire quelle dei template figli.

**Database.** Lo schema si gestisce con Flask-Migrate: le migrazioni stanno in
`migrations/versions/` e vanno committate. Dopo ogni modifica ai modelli:
`uv run flask db migrate -m "descrizione"`, rileggere il file generato (l'autogenerate non vede
tutto, per esempio i rinomini di colonna diventano drop + add, con perdita dei dati), poi
`uv run flask db upgrade`. `tests/test_migrazioni.py` fallisce se un modello cambia senza
migrazione. Su SQLite le modifiche passano in modalità batch (`render_as_batch`, la tabella viene
ricopiata) e i vincoli hanno nomi fissi (`naming_convention` in `app/extensions.py`): non
toglierla. `migrations/env.py` spegne le foreign key durante l'upgrade (il batch ricopia anche
le tabelle referenziate, come `edizioni` o `persone`) e alla fine lancia `PRAGMA
foreign_key_check`: se ci sono riferimenti rotti l'upgrade fallisce. Se un upgrade si ferma a
metà resta `_alembic_tmp_<tabella>`: controllare che sia vuota e la tabella vera intatta, poi
eliminarla. Per rinominare una colonna basta `RENAME COLUMN` nativo (vedi `b7d1c2e4f901`). Non usare `db.create_all()` sui database veri (solo i test lo fanno, in memoria).
Prima di una migrazione che tocca dati esistenti, backup: `sqlite3 instance/ventotene.db
".backup percorso.db"`. Mai cancellare `instance/ventotene.db` senza chiedere. Mantenere
`ondelete="CASCADE"` coerente con le relazioni esistenti.

**Email.** Sempre tramite `app/posta.py` (`invia_email` + template di solo testo in
`templates/email/`), mai `smtplib` nelle viste. SMTP Infomaniak (`MAIL_*` nel `.env`); con
`MAIL_SERVER` vuoto le email vanno nel log, così in locale e nei test non parte nulla. Nei test
`_spedisci` si sostituisce con monkeypatch (vedi `tests/test_email.py`). Le email non devono
contenere dati personali oltre a nome, titolo dell'UD ed esito.

**Zotero.** Logica portata da Itinera (`~/gitrepo/itinera/app/biblio/`, vedi PIANO_LETTURE.md).
Zotero è la fonte di verità: la cache locale (`ZoteroItem`, `ZoteroCollezione`) si scrive solo con
ciò che risponde l'API. Sync in `app/zotero_sync.py`: versione della libreria letta *prima* dei
download, collezioni sempre complete (cestino propagato alle sotto-collezioni, nessuna
cancellazione se Zotero ne restituisce zero), record incrementali (`since`), item del cestino
tenuti con `eliminato=True` (vanno chiesti a `/items/trash`), eliminati definitivi da `/deleted`.
`ZoteroItem.isbn` (13 cifre, `normalizza_isbn`) e `firma` (`firma()`) servono per i doppioni.
Citazioni già formattate (`include=bib`). La chiave ha permesso di scrittura (controllo:
`flask zotero-verifica`); la scrittura è in `app/zotero_scrittura.py` (`crea_item` con tag `ZOTERO_TAG_PROPOSTE`,
`aggiorna_item` con 412 → `ErroreScrittura`, `candidati_duplicati`): solo campi bibliografici,
mai dati del docente; la usa la revisione del comitato (`/admin/letture`, `collega_item` per i
record già presenti), che scrive nella sottocollezione «Docenti» dell'edizione
(`crea_collezione`, `Edizione.zotero_docenti_key`); struttura: Edizione → «Relatori», «Docenti»; più una collezione di primo livello dei
riferimenti di base (`ZOTERO_COLLEZIONE_BASE`), in fondo all'invito alla lettura di ogni edizione.
Logica comune in `zotero_scrittura.py`: `sottocollezione_edizione`, `scelte_duplicati`,
`salva_lettura` (docenti con il tag, relatori senza, subito in «Relatori»). Struttura del gruppo e ruolo relatore in
PIANO_LETTURE.md (R1–R3): docente = insegnante candidato, relatore = storico delle lezioni. Copertine solo con `salva_copertina()` (`app/utils.py`: host ammessi anche
nei redirect, solo immagini tra 1 KB e 2 MB; fonti per ISBN in `ricerca_libri._copertine_per_isbn`: Open Library, Amazon per ISBN-10, Google Books, ognuna isolata) o `carica_copertina()` (file dell'admin, firma del
formato controllata), sostituite con `sostituisci_copertina()`; `copertina_path=""` = nessuna,
da non cercare più. L'admin corregge una voce da `/admin/bibliografia/<key>` (`aggiorna_item`). Ricerca dei libri in `app/ricerca_libri.py`
(`/area/letture/cerca`): le API esterne si chiamano solo dal server, il browser non carica
immagini esterne (nei risultati solo testo). Nei test solo `FakeZot`
(`tests/conftest.py`), mai il gruppo vero: `TestConfig` usa un ID finto.

## Sicurezza e dati personali

- `.env` contiene `SECRET_KEY` e la chiave Zotero: non leggerlo per riportarne il contenuto,
  non committarlo, non stampare i suoi valori. Le nuove variabili vanno in `.env.example`
  (con valore vuoto o d'esempio) e in `config.py`.
- Il sito tratta dati personali (data di nascita, residenza, telefono). Non loggarli, non
  esporli in pagine pubbliche, non metterli nei dati di test reali. L'export CSV della
  graduatoria è solo per comitato/admin.
- Cookie `HttpOnly` e `SameSite=Lax`; `Secure` in produzione (`SESSION_COOKIE_SECURE=1`).

## Test

Cartella `tests/`, pytest (`uv run pytest`). `conftest.py` crea l'app con
`create_app(TestConfig)` (SQLite in memoria, CSRF disattivato) e `UPLOAD_FOLDER` su `tmp_path`,
e offre gli helper `crea_utente`, `crea_edizione`, `login`.
- `test_regole.py`: `candidature_aperte`, `problemi_invio` (profilo, UD, limiti caratteri),
  `conta_caratteri`, `Materiale.visibile_a`, graduatoria (`admin._graduatoria`).
- `test_rotte.py`: permessi admin/comitato/docente/anonimo, candidature di altri, invio,
  download dei materiali.
- `test_zotero.py`, `test_zotero_scrittura.py`: sync, scrittura, duplicati, con `FakeZot`.
- `test_ricerca_libri.py`: lookup con `_json` finto (mai le API vere), fusione per ISBN, fonte giù,
  limite di 30 ricerche al minuto.
- `test_iscrizione.py`: passi della candidatura, letture del docente (valori della ricerca
  verificati, limite, modificabili dopo l'invio fino alla scadenza, email di conferma),
  `Candidatura.modificabile`, modifica della proposta dopo l'invio (scartata se fuori bando).
- `test_relatori.py`: account del relatore collegato alla lezione (solo admin), materiali e
  bibliografia della lezione (solo le proprie, doppioni, niente tag), pagina edizione per lezione,
  UD dei docenti ammessi senza dati personali, vincolo `una_origine`.
- `test_guida.py`: ogni pagina di area/admin/auth ha la sua sezione in `AIUTO`, i titoli
  esistono, guida del comitato riservata, menu dell'account, `/esci` solo POST.
- `test_letture.py`: revisione delle letture (permessi, collega/crea, nessun dato del docente
  nel payload Zotero), copertine, merge `dc:replaces`.
- `test_dopo_scuola.py`: `Candidatura.dopo_la_scuola`, materiali del modulo (solo la propria
  candidatura ammessa, niente upload libero), archivio, letture `post_scuola`.
- `test_ud.py`: UD dal programma, pagine di lezione/UD (permessi, 404, niente dati personali),
  materiali e abstract caricati dall'admin, copertine per ISBN (`scarica_copertine` con fonti finte).
- `test_item_admin.py`: voce della bibliografia corretta dall'admin (permessi, scrittura in
  Zotero, 412), copertina caricata/tolta/rifiutata, ricerca per ISBN che non perde la vecchia.
- `test_bibliografia.py`: sezioni con sottosezioni, copertine (solo item vivi), ISBN e link,
  nessun dato del docente, letture nella scheda candidatura del comitato.

Per i test di rotta usare un client per utente (`client_di` in `test_rotte.py`). La fixture
azzera `g._login_user` a ogni richiesta: l'app context resta aperto per tutto il test e
Flask lo riusa, quindi senza azzerarlo l'utente passerebbe da un client all'altro.
Nuove regole del bando o nuove rotte del back-office: aggiungere il test corrispondente.

## Lavori aperti (da ARCHITETTURA.md §7)

1. Testi istituzionali: in `public/la_scuola.html` restano `[DA COMPLETARE]` storia e obiettivi
   e la presentazione dei tre enti promotori (testi dell'utente). «Le edizioni» è scritta
   (2023–2026, solo fatti dalle pagine ISMed e dai dati caricati): aggiornarla a ogni nuova
   edizione. Loghi CNR-ISMed / Centro Ventotene / ANPPIA ancora da avere.
   Informativa privacy: bozza art. 13 GDPR in `public/privacy.html` (titolare CNR via ISMed,
   server CNR, email via Infomaniak); i punti `[DA VERIFICARE]` e i tempi di conservazione
   vanno confermati con il DPO del CNR. Se cambiano i dati raccolti, i destinatari o i cookie,
   aggiornare l'informativa.
2. Edizioni 2023–2025: caricate con `flask seed-precedenti` (programma, comitato, lezioni,
   call e locandine in PDF; 2024 collegata alla collezione Zotero «2024»). Nel programma le UD
   portano il nome del docente, come sulle pagine ISMed. Mancano i materiali delle lezioni e
   delle UD (slide, testi) e gli account dei relatori da collegare alle lezioni.
3. Attestati di frequenza in PDF generati dal sito (borsisti e uditori): rimandati, decisioni
   aperte (tecnica: docx + LibreOffice o fpdf2; chi riceve; firmatario e ore). Carta intestata
   CNR-ISMed in `modelli/Carta_intestata_accessibile_ita.docx`.
4. Opzionale: registrazione presenze, export iscritti e uditori.

**In corso: [PIANO_LETTURE.md](PIANO_LETTURE.md)**: invito alla lettura, Zotero in lettura e
scrittura, ricerca dei libri, relatori, materiali dopo la scuola. Fatte F1–F7 e R1–R3; prossima
**F8**, rimandata dall'utente: si riprende solo quando lo chiede (domande aperte nel piano). Una fase per sessione: leggere la sezione «Riprendere da qui» e la tabella di stato in cima
al piano, fare la prima fase "da fare", aggiornare tabella e «Riprendere da qui», un commit per
fase (remote `origin` su GitHub, github.com/pankus/scuolaventotene; push solo quando lo chiede l'utente).

## Come lavorare

- Prima di modificare, leggere i file coinvolti (modello, form, vista, template): le quattro
  parti di solito cambiano insieme.
- Dopo una modifica: avviare l'app (`uv run flask --debug run`) e controllare le pagine
  toccate e lanciare `uv run pytest`.
- Modifiche piccole e coerenti con il codice esistente; niente nuove dipendenze o framework
  (JS, ORM, CSS) senza chiedere.
- Aggiornare `ARCHITETTURA.md` quando cambiano ruoli, rotte, modello dati o flussi, e
  `README.md` quando cambiano comandi o deploy.
