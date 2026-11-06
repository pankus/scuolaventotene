# PIANO_LETTURE — iscrizione con "invito alla lettura", Zotero in lettura/scrittura, materiali post-scuola

Piano a fasi (una per sessione). Stato delle fasi: segnare qui sotto a ogni fine fase.

| Fase | Stato |
|---|---|
| F1 Zotero: configurazione e sync robusta | **fatta** (2026-11-06): `zotero-verifica`, cestino, guard, ISBN/firma; merge `dc:replaces` rimandato a F3 (servono i legami delle proposte) |
| F2 Zotero: scrittura | **fatta** (2026-11-06): `app/zotero_scrittura.py` (`crea_item`, `aggiorna_item`, `candidati_duplicati`), `FakeZot` in scrittura; nessuna rotta né migrazione |
| F3 Proposte di lettura e revisione del comitato | **fatta** (2026-11-06): `PropostaLettura` + migrazione, `/admin/letture` (collega o crea, rifiuta), `collega_item`, copertine con host ammessi, merge `dc:replaces` nella sync |
| F4 Lookup durante la digitazione | **fatta** (2026-11-06): `app/ricerca_libri.py`, `/area/letture/cerca`, `static/js/letture.js` (già attivo nella revisione del comitato); `GOOGLE_BOOKS_API_KEY` facoltativa (senza: 429 frequenti, resta Open Library); niente miniature esterne nel browser |
| F5 Flusso di iscrizione | **fatta** (2026-11-06): passi 1–4 (macro `passi`), `/area/candidatura/<id>/letture` (aggiungi/modifica/elimina in bozza, max 10, ricerca attiva), avviso nel riepilogo, letture nell'email di conferma, `la_scuola` e informativa aggiornate (Zotero, Google Books, Open Library senza dati personali) |
| F6 Dopo la scuola: altri libri e materiali | da fare |
| F7 Invito alla lettura pubblico | da fare |
| F8 Sfogliare i materiali | da decidere |

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

## F6 — Dopo la scuola: altri libri e materiali del modulo
- Chi: candidature `ammessa` di edizioni `chiusa | conclusa` (default; da confermare all'inizio
  della fase).
- `Materiale.candidatura_id` (FK nullable) + migrazione; upload multiplo di PDF/PPT/PPTX/ODP dalla
  scheda candidatura (riuso di `salva_upload`, `ESTENSIONI_MATERIALI`, stato `in_revisione`,
  revisione esistente in `/admin/materiali`).
- Nuove letture con `momento = post_scuola`, stessa coda F3.
- Informativa privacy: aggiornare la parte "Materiali" se cambia cosa si pubblica.

## F7 — Invito alla lettura pubblico
- `/bibliografia`: copertine (locali), filtro per edizione (collezione), sezione "Proposti dai
  docenti" (tag), schede `book`/`webpage` con ISBN e link. Nessun nome del docente.
- Scheda candidatura (comitato) e area docente: le letture della candidatura.

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
