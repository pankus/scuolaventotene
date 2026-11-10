"""Istruzioni del sito (modello: la guida di Itinera). Le guide sono file markdown versionati in
``guide/``: si correggono nel repository, non dal browser. Ogni pagina dell'area personale e del
back-office ha un link «Guida» alla propria sezione (``AIUTO``); ``tests/test_guida.py`` controlla
che le pagine nuove siano in mappa e che i titoli esistano."""
from pathlib import Path

import markdown
from flask import request, url_for
from flask_login import current_user
from markdown.extensions.toc import slugify_unicode

CARTELLA = Path(__file__).resolve().parent.parent / "guide"

# slug -> file e titolo; "comitato" è riservata a comitato e admin
GUIDE = {
    "docenti": {"file": "guida.md", "titolo": "Guida", "riservata": False},
    "comitato": {"file": "comitato.md", "titolo": "Guida del comitato", "riservata": True},
}

# endpoint (o "blueprint.") -> (guida, titolo della sezione). Pagina nuova: aggiungerla qui.
AIUTO = {
    "auth.registrati": ("docenti", "Registrazione e conferma dell'email"),
    "auth.login": ("docenti", "Accesso e password"),
    "auth.password_dimenticata": ("docenti", "Accesso e password"),
    "auth.reimposta_password": ("docenti", "Accesso e password"),
    "area.dashboard": ("docenti", "L'area personale"),
    "area.profilo": ("docenti", "Il profilo"),
    "area.candidatura": ("docenti", "La proposta di unità didattica"),
    "area.letture": ("docenti", "Invito alla lettura"),
    "area.dettaglio": ("docenti", "Invio, ritiro ed esito"),
    "area.nuovo_materiale": ("docenti", "Materiali del modulo"),
    "area.letture_lezione": ("docenti", "Bibliografia della relazione"),
    "area.ud_lezione": ("docenti", "Unità didattiche dei docenti"),
    "bibliografia.index": ("docenti", "Archivio e invito alla lettura"),
    "archivio.": ("docenti", "Archivio e invito alla lettura"),
    "admin.dashboard": ("comitato", "Il cruscotto"),
    "admin.nuova_edizione": ("comitato", "Creare e modificare un'edizione"),
    "admin.modifica_edizione": ("comitato", "Creare e modificare un'edizione"),
    "admin.candidature": ("comitato", "Elenco e graduatoria"),
    "admin.candidature_csv": ("comitato", "Elenco e graduatoria"),
    "admin.candidatura": ("comitato", "Valutare una candidatura"),
    "admin.letture": ("comitato", "Revisione delle letture"),
    "admin.lettura": ("comitato", "Approvare: collegare o creare"),
    "admin.materiali": ("comitato", "Materiali"),
    "admin.utenti": ("comitato", "Utenti e ruoli"),
    "admin.email": ("comitato", "Scrivere ai partecipanti"),
    "admin.item_zotero": ("comitato", "Correggere una voce e la copertina"),
}
# pagine senza link: file e JSON, conferme via link, le guide stesse
SENZA_AIUTO = {"area.file_candidatura", "area.cerca_letture", "auth.verifica", "public.guida"}


def leggi(slug):
    """(html, indice) della guida; indice = [{livello, id, titolo}] dei titoli ## e ###."""
    g = GUIDE[slug]
    md = markdown.Markdown(extensions=["extra", "toc"],
                           extension_configs={"toc": {"slugify": slugify_unicode}})
    html = md.convert((CARTELLA / g["file"]).read_text(encoding="utf-8"))
    indice = []

    def visita(nodi):
        for n in nodi:
            if n["level"] in (2, 3):
                indice.append({"livello": n["level"], "id": n["id"], "titolo": n["name"]})
            visita(n["children"])
    visita(md.toc_tokens)
    return html, indice


def ancora(titolo):
    return slugify_unicode(titolo, "-")


def sezione(endpoint):
    if not endpoint or endpoint in SENZA_AIUTO:
        return None
    return AIUTO.get(endpoint) or AIUTO.get(endpoint.split(".")[0] + ".")


def registra(app):
    @app.template_global("aiuto")
    def aiuto():
        """{url, titolo} della sezione della guida per la pagina corrente, o None."""
        s = sezione(request.endpoint)
        if not s or (GUIDE[s[0]]["riservata"] and not
                     (current_user.is_authenticated and current_user.is_comitato)):
            return None
        return {"url": url_for("public.guida", slug=s[0]) + "#" + ancora(s[1]), "titolo": s[1]}
