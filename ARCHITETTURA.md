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

| Ruolo | Cosa può fare |
|---|---|
| Visitatore | Consulta l'edizione corrente, il programma, il bando, l'archivio pubblico e la bibliografia |
| Docente (registrato) | Gestisce il profilo, si candida (come borsista o uditore), carica la proposta di UD, invia materiali e vede quelli riservati ai registrati |
| Comitato | Accede al back-office, legge le candidature, assegna i punteggi (ognuno i propri) e vede la graduatoria |
| Admin | Fa tutto ciò che fa il comitato e in più gestisce edizioni, programma, comitato, esiti, materiali, utenti e la sincronizzazione Zotero |

## 3. Mappa del sito

```
/                         home: edizione in vetrina + edizioni precedenti
/la-scuola                presentazione, chi può partecipare, come candidarsi
/edizioni/<anno>          bando, date, programma, comitato, invito alla lettura dell'edizione
/edizioni/<anno>/bando    PDF del bando
/archivio                 elenco delle edizioni
/archivio/<anno>          materiali (PDF/PPT) dell'edizione, filtrati per visibilità
/materiali/<id>/scarica   download controllato
/bibliografia             invito alla lettura (Zotero): ricerca, sezioni, tag
/contatti  /privacy
/registrati  /accedi  /esci
/verifica/<token>         conferma dell'email (link inviato alla registrazione; /verifica/reinvia per un nuovo link)
/password-dimenticata  /reimposta-password/<token>   reset password via email (link valido 1 ora, una volta)

/area/                    area personale del docente
/area/profilo
/area/candidatura/<anno>  bozza → invio
/area/candidatura/<id>    riepilogo, controlli del bando, invio/ritiro
/area/materiali/nuovo     invio di un materiale (va in revisione)

/admin/                   cruscotto (comitato e admin)
/admin/edizioni/nuova, /admin/edizioni/<id>     edizione + programma + persone
/admin/edizioni/<id>/candidature(.csv)          graduatoria ed export
/admin/candidature/<id>                          scheda, valutazione, esito
/admin/materiali                                 revisione e caricamento
/admin/utenti                                    ruoli e attivazione
/admin/zotero/sync                               sincronizzazione manuale
```

## 4. Modello dati (SQLite)

```
utenti ─┬─< candidature >── edizioni ──< programma_voci
        │        └──< valutazioni >── utenti (comitato)
        └─< materiali >── edizioni
edizioni ──< edizioni_persone >── persone        (comitato / relatori)
edizioni.zotero_collection_key ··· zotero_collezioni
zotero_items >──< zotero_collezioni   (zotero_item_collezioni)
sync_stato (versione libreria Zotero, data ultima sync)
```

- **Edizione**: numero, anno, slug, titolo, sottotitolo, date, scadenza, data degli esiti, posti borsisti, uditori sì/no, limiti di caratteri (6000–8000), stato (`bozza → aperta → chiusa → conclusa`), bando e collezione Zotero collegata.
- **Candidatura**: tipo (borsista o uditore), stato (`bozza → inviata → in_valutazione → ammessa | riserva | non_ammessa`, oppure `ritirata`), titolo dell'UD, discipline, file e numero di caratteri (calcolato automaticamente per i .docx). Ogni docente ha al massimo una candidatura per edizione.
- **Valutazione**: una per membro del comitato, con originalità, potenzialità didattiche e valorizzazione delle fonti (0–25 ciascuna, massimo 75). La graduatoria usa la media dei punteggi.
- **Materiale**: edizione, tipo (slide, relazione, UD, bando…), file o link, visibilità (`pubblico | registrati | privato`) e stato (`in_revisione | pubblicato | rifiutato`).

## 5. Flussi principali

**Candidatura**: il docente si registra (con consenso privacy), completa il profilo (data di nascita, telefono e residenza sono richiesti dal bando), salva la bozza con il file, e il sistema controlla i requisiti. Può inviare solo entro la scadenza. Poi il comitato valuta, l'admin assegna l'esito, e l'export CSV restituisce la graduatoria.

**Materiali**: l'admin pubblica direttamente. Il docente invia il materiale, che resta in revisione finché l'admin non lo pubblica o lo rifiuta, scegliendo anche la visibilità.

**Bibliografia Zotero**: la bibliografia si cura nel gruppo Zotero, che resta la fonte di verità. Il sito ne tiene una copia locale aggiornata dalla sync. Con `app/zotero_scrittura.py` (fase F2 di PIANO_LETTURE.md) il sito può scrivere in Zotero: dalla fase F3 ci finiranno le letture proposte dai docenti e approvate dal comitato (solo tipi libro e pagina web, senza dati dei docenti). Gli item nel cestino Zotero non compaiono sul sito.
- Il comando `flask zotero-sync` gira in cron (per esempio ogni ora) e si può lanciare anche dal cruscotto.
- La sincronizzazione è incrementale: usa `since=<versione>` per collezioni e record e `/deleted` per le rimozioni. La sincronizzazione completa con `--completa` riallinea tutto.
- Le citazioni arrivano già formattate dall'API (`include=bib`, stile CSL `chicago-author-date`, locale `it-IT`, entrambi configurabili).
- Le collezioni del gruppo diventano le "sezioni" della bibliografia. Ogni edizione può essere collegata a una collezione, che compare come invito alla lettura nella pagina dell'edizione.
- Basta una chiave API in sola lettura, oppure nessuna chiave se il gruppo è pubblico.

## 6. Sicurezza e dati personali

- Email transazionali (`app/posta.py`, SMTP Infomaniak, solo testo): conferma dell'indirizzo alla registrazione, reset password, conferma dell'invio al docente con notifica ai referenti (`MAIL_NOTIFICHE`), esito al docente quando lo stato passa ad ammessa / riserva / non ammessa. Senza email confermata la candidatura non si può inviare. I link usano token firmati con la `SECRET_KEY` (itsdangerous); quello di reset decade appena cambia la password. Un errore SMTP finisce nel log e non blocca l'operazione.

- CSRF su tutti i form; password con hash (Werkzeug); cookie `HttpOnly` e `SameSite`, `Secure` in produzione.
- I file caricati sono salvati con un nome casuale fuori da `static/` e serviti solo attraverso rotte che controllano i permessi. Le estensioni ammesse sono limitate e la dimensione massima è configurabile (60 MB di default).
- Il sito tratta dati personali (data di nascita, residenza, telefono). Restano da definire con il DPO del CNR l'informativa e i tempi di conservazione (per esempio la cancellazione dei dati delle candidature N anni dopo l'edizione).

## 7. Da fare (prossimi passi)

1. Testi istituzionali (la scuola, storia, partner), loghi CNR-ISMed, Centro Ventotene e ANPPIA, informativa privacy.
2. Caricamento delle edizioni 2023–2025 e dei relativi materiali.
3. Attestati di frequenza in PDF generati dal sito (borsisti e uditori).
4. Opzionale: campi per la registrazione delle presenze, export degli iscritti e degli uditori.
