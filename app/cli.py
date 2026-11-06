from datetime import date

import click

from .extensions import db
from .models import Edizione, EdizionePersona, Persona, ProgrammaVoce, Utente


def register_cli(app):
    @app.cli.command("init-db")
    def init_db():
        """Crea o aggiorna le tabelle applicando le migrazioni (come `flask db upgrade`)."""
        from flask_migrate import upgrade
        upgrade()
        click.echo("Database aggiornato all'ultima migrazione.")

    @app.cli.command("crea-admin")
    @click.argument("email")
    @click.option("--nome", default="Admin")
    @click.option("--cognome", default="Scuola")
    @click.password_option()
    def crea_admin(email, nome, cognome, password):
        """Crea (o promuove) un amministratore."""
        u = Utente.query.filter_by(email=email.lower()).first() or Utente(
            email=email.lower(), nome=nome, cognome=cognome)
        u.ruolo = "admin"
        u.email_verificata = True
        u.set_password(password)
        db.session.add(u)
        db.session.commit()
        click.echo(f"Amministratore {email} pronto.")

    @app.cli.command("prova-email")
    @click.argument("destinatario")
    def prova_email(destinatario):
        """Manda un'email di prova per controllare la configurazione SMTP."""
        from .posta import invia_email
        if not app.config["MAIL_SERVER"]:
            click.echo("MAIL_SERVER vuoto: l'email va solo nel log. Impostalo nel .env.")
        ok = invia_email(destinatario, "Prova SMTP – Scuola di Ventotene", "prova")
        click.echo("Inviata." if ok else "Invio fallito: vedi l'errore sopra.")

    @app.cli.command("zotero-sync")
    @click.option("--completa", is_flag=True, help="Riscarica tutta la libreria")
    def zotero_sync(completa):
        """Sincronizza la bibliografia dal gruppo Zotero (da usare in cron)."""
        from .zotero_sync import sincronizza
        s = sincronizza(completa=completa)
        click.echo(f"Collezioni: {s['collezioni']}  record: {s['item']}  cestino: {s['cestino']}  "
                   f"eliminati: {s['eliminati']}  versione: {s['versione']}")
        for a in s["avvisi"]:
            click.echo(f"ATTENZIONE: {a}")

    @app.cli.command("zotero-copertine")
    @click.option("--limite", default=50, show_default=True, help="Libri da controllare per giro")
    def zotero_copertine(limite):
        """Scarica in locale le copertine dei libri con ISBN (Open Library, Google Books)."""
        from .ricerca_libri import scarica_copertine
        fatte, senza = scarica_copertine(limite)
        click.echo(f"Copertine scaricate: {fatte}  non trovate: {senza}")

    @app.cli.command("zotero-verifica")
    def zotero_verifica():
        """Controlla chiave e gruppo Zotero: connessione, contenuto, permesso di scrittura."""
        from .zotero_sync import verifica
        try:
            v = verifica()
        except Exception as e:  # noqa: BLE001
            raise click.ClickException(f"Connessione a Zotero non riuscita: {e}") from e
        scrittura = {True: "sì", False: "NO (serve per salvare le letture approvate)",
                     None: "non verificabile (chiave assente o non valida)"}[v["scrittura"]]
        click.echo(f"Gruppo {app.config['ZOTERO_LIBRARY_ID']}: {v['item']} record, "
                   f"versione {v['versione']}, scrittura: {scrittura}")

    @app.cli.command("ud-dal-programma")
    def ud_programma():
        """Crea le UD dei docenti dalle voci «unità didattiche» del programma (idempotente)."""
        from .edizioni_precedenti import ud_dal_programma
        for ed in Edizione.query.order_by(Edizione.anno).all():
            n = ud_dal_programma(ed)
            if n:
                click.echo(f"{ed.anno}: {n} UD create.")
        db.session.commit()

    @app.cli.command("seed-precedenti")
    def seed_precedenti():
        """Carica le edizioni 2023–2025 dalle pagine CNR-ISMed (con locandine e call in PDF)."""
        from .edizioni_precedenti import carica
        anni = carica(avviso=click.echo)
        click.echo(f"Caricate: {', '.join(map(str, anni))}." if anni else "Nessuna edizione nuova.")

    @app.cli.command("seed-2026")
    def seed_2026():
        """Carica la IV edizione (2026) dai dati del bando."""
        if Edizione.query.filter_by(numero=4).first():
            click.echo("Edizione 2026 già presente.")
            return
        ed = Edizione(
            numero=4, anno=2026, slug="2026",
            titolo="Le migrazioni politiche nella storia contemporanea",
            sottotitolo="definizioni, confini, proposte didattiche",
            luogo="Ventotene",
            sede="Centro di ricerca e documentazione sul confino politico e la detenzione "
                 "Isole di Ventotene e Santo Stefano",
            data_inizio=date(2026, 10, 29), data_fine=date(2026, 11, 1),
            scadenza_candidature=date(2026, 7, 20), data_esiti=date(2026, 8, 20),
            posti_borsisti=8, ammessi_uditori=True, caratteri_min=6000, caratteri_max=8000,
            stato="chiusa",
            descrizione=(
                "La migrazione politica rappresenta uno dei temi più dibattuti nel dibattito "
                "pubblico. Obiettivo della scuola è approfondire in chiave storica l'evoluzione "
                "delle migrazioni politiche nel contesto globale contemporaneo, da metà Ottocento "
                "ai giorni nostri, individuando chiavi di lettura e percorsi didattici per la "
                "disseminazione in ambito scolastico.\n\n"
                "Al mattino relazioni di studiosi; al pomeriggio presentazione e discussione delle "
                "unità didattiche dei docenti selezionati (20 minuti ciascuno).\n\n"
                "Ai **8 docenti selezionati** sono rimborsate le spese di mezza pensione; "
                "trasporto e pranzi sono a carico dei partecipanti. Sono ammessi **uditori** "
                "senza rimborso. A tutti è rilasciato un attestato di frequenza."
            ),
        )
        db.session.add(ed)
        G = date
        voci = [
            (G(2026, 10, 29), "19", "accoglienza", "Accoglienza, saluti e presentazione della scuola", None),
            (G(2026, 10, 30), "9-13", "lezione", "L'asilo politico e le migrazioni contemporanee", "Stefano Gallo"),
            (G(2026, 10, 30), "9-13", "lezione", "L'emigrazione delle e dei palestinesi: tipologie e periodizzazioni", "Sofia Bacchini"),
            (G(2026, 10, 30), "9-13", "lezione", "Mappare le mobilità politiche con l'ausilio dell'IA", "Anthony Santilli, Francesco Di Filippo"),
            (G(2026, 10, 30), "15-18", "unita_didattiche", "Presentazione e discussione delle unità didattiche", None),
            (G(2026, 10, 31), "10-13", "lezione", "Giuseppe Di Vittorio e i paradigmi della mobilità tra lavoro e sindacato", "Michele Colucci"),
            (G(2026, 10, 31), "10-13", "lezione", "La \"profughizzazione\" della mobilità lavorativa in Italia", "Donato Di Sanzo, Giovanni Ferrarese"),
            (G(2026, 10, 31), "10-13", "lezione", "Bandiere e valigie. Italiani in Africa tra emigrazione, colonialismo e memoria storica", "Valentina Fusari"),
            (G(2026, 10, 31), "15-18", "unita_didattiche", "Presentazione e discussione delle unità didattiche", None),
            (G(2026, 11, 1), "9.30", "visita", "Visita itinerante nell'isola", "Anthony Santilli"),
            (G(2026, 11, 1), "12", "chiusura", "Chiusura della Scuola", None),
        ]
        for i, (g, ora, tipo, tit, rel) in enumerate(voci):
            db.session.add(ProgrammaVoce(edizione=ed, giorno=g, ora=ora, tipo=tipo,
                                         titolo=tit, relatori=rel, ordine=i))
        comitato = [
            ("Michele", "Colucci", "CNR-ISMed"), ("Francesco", "Di Filippo", "CNR-ISMed"),
            ("Donato", "Di Sanzo", "CNR-ISMed"), ("Giovanni", "Ferrarese", "CNR-ISMed"),
            ("Stefano", "Gallo", "CNR-ISMed"), ("Valentina", "Fusari", "Università di Torino"),
            ("Sofia", "Bacchini", "Università L'Orientale Napoli"),
            ("Anthony", "Santilli", "Centro di ricerca e documentazione sul confino politico "
                                    "e la detenzione Isole di Ventotene e Santo Stefano / ANPPIA"),
        ]
        for n, c, a in comitato:
            p = Persona(nome=n, cognome=c, affiliazione=a)
            db.session.add(p)
            db.session.add(EdizionePersona(edizione=ed, persona=p, ruolo="comitato"))
        db.session.commit()
        click.echo("IV edizione (2026) caricata.")
