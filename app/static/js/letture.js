// Ricerca dei libri mentre si scrive il titolo (PIANO_LETTURE.md, F4). Nessuna libreria.
// Uso: <input name="title" data-ricerca-url="/area/letture/cerca"> dentro un <form>.
// Scegliendo un risultato si compilano i campi del form con lo stesso nome
// (title, autori, date, publisher, ISBN, copertina_url, zotero_key).
(function () {
  "use strict";

  // "Anna Rossi" -> "Rossi, Anna" (le fonti online danno nome e cognome in quest'ordine)
  function cognomeNome(n) {
    n = n.trim();
    if (n.indexOf(",") >= 0 || n.indexOf(" ") < 0) return n;
    var i = n.lastIndexOf(" ");
    return n.slice(i + 1) + ", " + n.slice(0, i);
  }

  function imposta(form, nome, valore) {
    var el = form.elements[nome];
    if (el && valore !== undefined && valore !== null) el.value = valore; // anche i radio (RadioNodeList)
  }

  function compila(form, r) {
    var autori = Array.isArray(r.autori) ? r.autori.map(cognomeNome)
                                         : (r.autori || "").split("; ").filter(Boolean);
    imposta(form, "title", r.titolo);
    imposta(form, "autori", autori.join("\n"));
    imposta(form, "date", r.anno || "");
    if (r.editore) imposta(form, "publisher", r.editore);
    imposta(form, "ISBN", r.isbn || "");
    imposta(form, "copertina_url", r.copertina_url || "");
    imposta(form, "zotero_key", r.key || "");
  }

  function riga(r, form, lista) {
    var li = document.createElement("li");
    var b = document.createElement("button");
    b.type = "button";
    var autori = Array.isArray(r.autori) ? r.autori.join(", ") : (r.autori || "");
    b.textContent = r.titolo + (autori ? " — " + autori : "") + (r.anno ? " (" + r.anno + ")" : "");
    var nota = document.createElement("small");
    nota.textContent = r.key ? " Già in Zotero" : " " + r.fonte + (r.isbn ? " · ISBN " + r.isbn : "") +
                       (r.copertina_url ? " · copertina disponibile" : "");
    if (r.key) li.className = "in-zotero";
    b.appendChild(nota);
    b.addEventListener("click", function () { compila(form, r); lista.hidden = true; });
    li.appendChild(b);
    return li;
  }

  function attiva(input) {
    var form = input.form, timer = null, ultima = "";
    var lista = document.createElement("ul");
    lista.className = "risultati-ricerca";
    lista.hidden = true;
    lista.setAttribute("aria-live", "polite");
    input.setAttribute("autocomplete", "off");
    input.insertAdjacentElement("afterend", lista);

    function mostra(dati) {
      lista.innerHTML = "";
      (dati.zotero || []).forEach(function (r) { lista.appendChild(riga(r, form, lista)); });
      (dati.online || []).forEach(function (r) { lista.appendChild(riga(r, form, lista)); });
      if (dati.errore || !lista.children.length) {
        var li = document.createElement("li");
        li.textContent = dati.errore || "Nessun risultato: compila i campi a mano.";
        lista.appendChild(li);
      }
      lista.hidden = false;
    }

    input.addEventListener("input", function () {
      clearTimeout(timer);
      var q = input.value.trim();
      if (q.length < 3) { lista.hidden = true; return; }
      timer = setTimeout(function () {
        if (q === ultima) return;
        ultima = q;
        var isbn = form.elements.ISBN ? form.elements.ISBN.value : "";
        fetch(input.dataset.ricercaUrl + "?" + new URLSearchParams({ q: q, isbn: isbn }),
              { headers: { Accept: "application/json" }, credentials: "same-origin" })
          .then(function (r) { return r.json(); })
          .then(function (d) { if (input.value.trim() === q) mostra(d); })
          .catch(function () { mostra({ errore: "Ricerca non disponibile: compila i campi a mano." }); });
      }, 300);
    });
    input.addEventListener("keydown", function (e) { if (e.key === "Escape") lista.hidden = true; });
  }

  document.querySelectorAll("[data-ricerca-url]").forEach(attiva);
})();
