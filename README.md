# Scuola di formazione di Ventotene — sito web

Flask + SQLite. Per architettura, ruoli, modello dati e flussi: vedi [ARCHITETTURA.md](ARCHITETTURA.md).

## Struttura

```
ventotene/
├── config.py               configurazione (variabili d'ambiente, .env)
├── wsgi.py                 entry point Apache/mod_wsgi
├── pyproject.toml          dipendenze (uv)
├── uv.lock                 versioni bloccate: da committare
├── migrations/             migrazioni dello schema (Flask-Migrate): da committare
├── guide/                  istruzioni del sito: guida.md (docenti e relatori), comitato.md
├── modelli/                carta intestata CNR-ISMed (.docx) per gli attestati
├── .env.example
├── instance/               (creata al primo avvio) ventotene.db + uploads/
└── app/
    ├── __init__.py         application factory, blueprint, errori
    ├── extensions.py       db, login, CSRF, PRAGMA SQLite
    ├── models.py           modello dati
    ├── forms.py            form WTForms
    ├── utils.py            permessi, upload, conteggio caratteri, filtri Jinja
    ├── zotero_sync.py      sincronizzazione incrementale del gruppo Zotero
    ├── zotero_scrittura.py scrittura in Zotero (letture approvate) e controllo duplicati
    ├── ricerca_libri.py    ricerca dei libri: cache Zotero + Google Books / Open Library
    ├── posta.py            email SMTP (Infomaniak) e token
    ├── guida.py            guide in markdown, indice, link «Guida» per pagina
    ├── edizioni_precedenti.py  dati delle edizioni 2023–2025 (flask seed-precedenti)
    ├── cli.py              init-db, crea-admin, seed-2026, seed-precedenti, ud-dal-programma, zotero-sync, zotero-copertine, zotero-verifica, prova-email
    ├── views/
    │   ├── public.py       home, edizione, la scuola, contatti, privacy, guide
    │   ├── auth.py         registrazione, accesso, verifica email, reset password
    │   ├── area.py         area personale: profilo, candidature, letture, materiali, lezioni dei relatori, ricerca libri
    │   ├── archivio.py     archivio edizioni e download
    │   ├── bibliografia.py invito alla lettura
    │   └── admin.py        back-office
    ├── templates/          public/ auth/ area/ archivio/ bibliografia/ admin/
    └── static/             css/style.css, js/letture.js, js/menu.js, font locali
```

## Avvio in locale (uv)

```bash
uv sync                       # crea .venv, installa le dipendenze e genera uv.lock
cp .env.example .env          # impostare SECRET_KEY, SESSION_COOKIE_SECURE=0 in locale, dati Zotero
export FLASK_APP=app:create_app
uv run flask init-db          # applica le migrazioni (= flask db upgrade)
uv run flask seed-2026        # IV edizione dai dati del bando
uv run flask seed-precedenti  # edizioni 2023–2025 dalle pagine CNR-ISMed (scarica call e locandine)
uv run flask ud-dal-programma # UD dei docenti dalle voci del programma (idempotente; già in seed-precedenti)
uv run flask zotero-copertine # copertine dei libri con ISBN (Open Library, Amazon, Google Books)
uv run flask crea-admin tuo@ismed.cnr.it
uv run flask --debug run
```

In locale si può lasciare vuoto `MAIL_SERVER`: le email (con i link di conferma e di reset)
compaiono nel terminale invece di partire.

Modifiche ai modelli: `uv run flask db migrate -m "descrizione"`, rileggere il file creato in
`migrations/versions/`, poi `uv run flask db upgrade` e committare la migrazione.

`uv.lock` va committato: è ciò che rende identico l'ambiente sul server.
Nuove dipendenze: `uv add <pacchetto>` (aggiorna `pyproject.toml` e `uv.lock`).

## Produzione (Apache + mod_wsgi)

Il progetto è fissato su **Python 3.14** (`.python-version`, `requires-python`).
mod_wsgi deve essere compilato contro lo stesso Python del `.venv`: il pacchetto della
distribuzione (`libapache2-mod-wsgi-py3`) usa il Python 3.10 di sistema, quindi va sostituito
con mod_wsgi installato nel virtualenv.

Server: **Ubuntu 22.04**. Python 3.14 è installato con uv in una cartella di sistema
(non nella home di un utente), così Apache può leggerlo.

```bash
sudo apt install apache2-dev build-essential          # apxs e compilatore per mod_wsgi
export UV_PYTHON_INSTALL_DIR=/opt/uv/python           # leggibile da www-data; metterlo anche nel profilo dell utente di deploy
sudo -E uv python install 3.14
PY=$(uv python find 3.14)
$PY -c 'import sysconfig; print(sysconfig.get_config_var("Py_ENABLE_SHARED"))'   # deve dare 1

cd /srv/ventotene
git pull
uv sync --frozen --no-dev --inexact --python 3.14
uv pip install mod_wsgi                       # compila mod_wsgi contro il Python del .venv
ldd $(.venv/bin/mod_wsgi-express module-location) | grep libpython   # libpython deve essere trovata
sqlite3 instance/ventotene.db ".backup instance/backup-$(date +%F).db"   # prima di migrare
.venv/bin/flask --app app:create_app db upgrade    # applica le migrazioni nuove (dopo ogni git pull)
.venv/bin/mod_wsgi-express module-config      # righe LoadModule / WSGIPythonHome per Apache
```

Dopo un `uv python upgrade 3.14` (nuova patch di sicurezza): rilanciare `uv sync` e
`uv pip install --reinstall mod_wsgi`, poi riavviare Apache.

- `--frozen`: installa esattamente le versioni di `uv.lock`, senza riscriverlo
- `--no-dev`: esclude pytest e gli altri strumenti di sviluppo
- `--inexact`: non rimuove mod_wsgi, che è installato a parte e non sta nel lock
  (si compila contro Apache, quindi non si può risolvere sul Mac)
- disattivare il modulo di sistema (`a2dismod wsgi`) e mettere l'output di `module-config`
  in `/etc/apache2/mods-available/wsgi_venv.load`, poi `a2enmod wsgi_venv`

```apache
WSGIDaemonProcess ventotene python-home=/srv/ventotene/.venv python-path=/srv/ventotene
WSGIProcessGroup ventotene
WSGIScriptAlias / /srv/ventotene/wsgi.py
<Directory /srv/ventotene>
    <Files wsgi.py> Require all granted </Files>
</Directory>
Alias /static /srv/ventotene/app/static
```

Il file `.env` contiene la `SECRET_KEY` e la chiave Zotero: `chmod 640 .env`, proprietario
l'utente del deploy, gruppo `www-data`; non va mai in git (è già nel `.gitignore`).

L'utente di Apache deve poter scrivere in `instance/` (database, file WAL, uploads).

Ricerca dei libri: il server chiama `www.googleapis.com` e `openlibrary.org` (e scarica le
copertine da Google Books, Open Library, archive.org e Amazon images-na.ssl-images-amazon.com): servono le uscite HTTPS verso questi
host. `GOOGLE_BOOKS_API_KEY` è facoltativa ma consigliata: senza chiave Google risponde spesso
429 e restano solo i risultati di Open Library.

Email (Infomaniak): nel `.env` `MAIL_SERVER=mail.infomaniak.com`, `MAIL_PORT=465`, utente e
password della casella (con la 2FA serve una password per applicazione), `MAIL_MITTENTE` uguale
alla casella o a un suo alias, `MAIL_NOTIFICHE` con gli indirizzi dei referenti. Prova:

```bash
.venv/bin/flask --app app:create_app prova-email tuo@indirizzo.it
```

Cron per la bibliografia:

```
0 * * * *  cd /srv/ventotene && .venv/bin/flask --app app:create_app zotero-sync >> instance/zotero.log 2>&1
15 * * * * cd /srv/ventotene && .venv/bin/flask --app app:create_app zotero-copertine >> instance/zotero.log 2>&1
```
