# Scuola di formazione di Ventotene — sito web

Flask + SQLite. Per architettura, ruoli, modello dati e flussi: vedi [ARCHITETTURA.md](ARCHITETTURA.md).

## Struttura

```
ventotene/
├── config.py               configurazione (variabili d'ambiente, .env)
├── wsgi.py                 entry point Apache/mod_wsgi (venv/ sul server)
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
    ├── cli.py              init-db, crea-admin, seed-2026, seed-precedenti, ud-dal-programma, lezioni-dal-programma, zotero-sync, zotero-copertine, zotero-verifica, prova-email
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
uv run flask lezioni-dal-programma # lezioni dei relatori dalle voci «lezione» del programma (idempotente)
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

## Produzione (Ubuntu 22.04, Apache + mod_wsgi)

Il progetto gira su **Python 3.10**, quello di sistema di Ubuntu 22.04, con il mod_wsgi del
pacchetto (`libapache2-mod-wsgi-py3`, compilato contro 3.10): lo stesso delle altre app sullo
stesso Apache. In locale si usa la stessa versione (`.python-version`).

Prima installazione (utente del deploy con sudo; il progetto è suo, `instance/` è di `www-data`):

```bash
sudo apt install apache2 libapache2-mod-wsgi-py3 python3.10-venv sqlite3
curl -LsSf https://astral.sh/uv/install.sh | sh        # uv per l'utente del deploy

cd /var/www
sudo git clone https://github.com/pankus/scuolaventotene.git
sudo chown -R $USER:www-data scuolaventotene
cd scuolaventotene
uv venv venv --python /usr/bin/python3.10               # crea anche venv/bin/activate_this.py
UV_PROJECT_ENVIRONMENT=venv uv sync --frozen --no-dev

cp .env.example .env            # compilare: SECRET_KEY nuova, SESSION_COOKIE_SECURE=1, Zotero, MAIL_*
chmod 640 .env                  # gruppo www-data: Apache lo legge, gli altri no
mkdir -p instance/uploads
sudo chown -R www-data:www-data instance
sudo -u www-data venv/bin/flask --app app:create_app init-db
sudo -u www-data venv/bin/flask --app app:create_app crea-admin email@ismed.cnr.it
```

Senza `SECRET_KEY` (o con quella d'esempio) l'app non parte: con una chiave nota sessioni e
link di reset della password si potrebbero falsificare. Generarla con
`python3 -c "import secrets; print(secrets.token_hex(32))"`.

- `--frozen`: installa esattamente le versioni di `uv.lock`, senza riscriverlo
- `--no-dev`: esclude pytest
- `UV_PROJECT_ENVIRONMENT=venv`: sul server l'ambiente è `venv/` (come le altre app), non `.venv/`

Virtual host (`/etc/apache2/sites-available/scuolaventotene.conf`, poi `a2ensite`,
`a2enmod headers ssl`):

```apache
<VirtualHost *:443>
    ServerName scuolaventotene.example.it
    # niente DocumentRoot sul progetto: dall'esterno si vedono solo l'app e app/static

    WSGIDaemonProcess scuolaventotene user=www-data group=www-data processes=1 threads=5 \
        python-home=/var/www/scuolaventotene/venv python-path=/var/www/scuolaventotene
    WSGIProcessGroup scuolaventotene
    WSGIApplicationGroup %{GLOBAL}
    WSGIScriptAlias / /var/www/scuolaventotene/wsgi.py

    <Directory /var/www/scuolaventotene>
        Require all denied
        <Files wsgi.py>
            Require all granted
        </Files>
    </Directory>
    Alias /static /var/www/scuolaventotene/app/static
    <Directory /var/www/scuolaventotene/app/static>
        Require all granted
    </Directory>

    Header always set X-Content-Type-Options "nosniff"
    Header always set X-Frame-Options "SAMEORIGIN"
    Header always set Referrer-Policy "strict-origin-when-cross-origin"
    Header always set Strict-Transport-Security "max-age=31536000"

    SSLEngine on
    # SSLCertificateFile / SSLCertificateKeyFile come per le altre app
</VirtualHost>
```

Se un altro virtual host ha `DocumentRoot /var/www`, `.env`, `.git` e `instance/` sarebbero
scaricabili da lì: controllarlo (`grep -r DocumentRoot /etc/apache2/sites-enabled`) o mettere
il blocco `<Directory /var/www/scuolaventotene> Require all denied` anche in
`/etc/apache2/conf-available/` (vale per tutti i virtual host). Gli upload stanno in
`instance/uploads/` e passano solo dalle viste, che controllano i permessi.

Aggiornamento:

```bash
cd /var/www/scuolaventotene
git pull
sudo -u www-data sqlite3 instance/ventotene.db ".backup instance/backup-$(date +%F).db"
UV_PROJECT_ENVIRONMENT=venv uv sync --frozen --no-dev
sudo -u www-data venv/bin/flask --app app:create_app db upgrade   # migrazioni nuove
touch wsgi.py                                                    # ricarica il processo mod_wsgi
```

Log: `/var/log/apache2/error.log` (`wsgi.py` manda logging e stdout su stderr).

Ricerca dei libri: il server chiama `www.googleapis.com` e `openlibrary.org` (e scarica le
copertine da Google Books, Open Library, archive.org e Amazon images-na.ssl-images-amazon.com): servono le uscite HTTPS verso questi
host. `GOOGLE_BOOKS_API_KEY` è facoltativa ma consigliata: senza chiave Google risponde spesso
429 e restano solo i risultati di Open Library.

Email (Infomaniak): nel `.env` `MAIL_SERVER=mail.infomaniak.com`, `MAIL_PORT=465`, utente e
password della casella (con la 2FA serve una password per applicazione), `MAIL_MITTENTE` uguale
alla casella o a un suo alias, `MAIL_NOTIFICHE` con gli indirizzi dei referenti. Prova:

```bash
sudo -u www-data venv/bin/flask --app app:create_app prova-email tuo@indirizzo.it
```

Cron per la bibliografia (`sudo crontab -u www-data -e`, così il database resta di `www-data`):

```
0 * * * *  cd /var/www/scuolaventotene && venv/bin/flask --app app:create_app zotero-sync >> instance/zotero.log 2>&1
15 * * * * cd /var/www/scuolaventotene && venv/bin/flask --app app:create_app zotero-copertine >> instance/zotero.log 2>&1
```
