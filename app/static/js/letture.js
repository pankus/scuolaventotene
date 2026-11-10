// Ricerca delle letture mentre si scrive il titolo (PIANO_LETTURE.md, F4). Nessuna libreria.
// Uso: <input name="title" data-ricerca-url="/area/letture/cerca" data-tipo="book"> dentro un <form>.
// Prima la bibliografia della scuola (Zotero); per i libri, con la casella, anche i cataloghi online.
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
    nota.textContent = r.key ? "Già nella bibliografia: sceglilo per non creare un doppione" : r.fonte + (r.isbn ? " · ISBN " + r.isbn : "") +
                       (r.copertina_url ? " · copertina disponibile" : "");
    if (r.key) li.className = "in-zotero";
    b.appendChild(nota);
    b.addEventListener("click", function () { compila(form, r); lista.hidden = true; });
    li.appendChild(b);
    return li;
  }

  function gruppo(testo) {
    var li = document.createElement("li");
    li.className = "gruppo";
    li.textContent = testo;
    return li;
  }

  function attiva(input) {
    var form = input.form, timer = null, ultima = "";
    var tipo = input.dataset.tipo || "book", online = null;
    var lista = document.createElement("ul");
    lista.className = "risultati-ricerca";
    lista.hidden = true;
    lista.setAttribute("aria-live", "polite");
    input.setAttribute("autocomplete", "off");
    input.insertAdjacentElement("afterend", lista);
    if (tipo === "book") {  // i cataloghi online hanno solo libri
      var etichetta = document.createElement("label");
      etichetta.className = "cerca-online";
      online = document.createElement("input");
      online.type = "checkbox";
      etichetta.appendChild(online);
      etichetta.appendChild(document.createTextNode(" cerca anche online (Google Books, Open Library)"));
      input.insertAdjacentElement("afterend", etichetta);
      online.addEventListener("change", function () { ultima = ""; cerca(0); });
    }

    function mostra(dati) {
      var zotero = dati.zotero || [], trovati = dati.online || [];
      lista.innerHTML = "";
      if (dati.errore) {
        var err = document.createElement("li");
        err.textContent = dati.errore;
        lista.appendChild(err);
      }
      lista.appendChild(gruppo("Nella bibliografia della scuola"));
      zotero.forEach(function (r) { lista.appendChild(riga(r, form, lista)); });
      if (!zotero.length) {
        var vuoto = document.createElement("li");
        vuoto.textContent = online && !online.checked
          ? "Non c'è nella bibliografia della scuola: spunta «cerca anche online» o compila i campi a mano."
          : "Non c'è nella bibliografia della scuola: compila i campi a mano.";
        lista.appendChild(vuoto);
      }
      if (online && online.checked) {
        lista.appendChild(gruppo("Online"));
        trovati.forEach(function (r) { lista.appendChild(riga(r, form, lista)); });
        if (!trovati.length) {
          var nessuno = document.createElement("li");
          nessuno.textContent = (dati.errori || []).length ? "Cataloghi online non raggiungibili." : "Nessun risultato online.";
          lista.appendChild(nessuno);
        }
      }
      lista.hidden = false;
    }

    function cerca(attesa) {
      clearTimeout(timer);
      var q = input.value.trim();
      if (q.length < 3) { lista.hidden = true; return; }
      timer = setTimeout(function () {
        if (q === ultima) return;
        ultima = q;
        var isbn = form.elements.ISBN ? form.elements.ISBN.value : "";
        var parametri = { q: q, isbn: isbn, tipo: tipo };
        if (online && online.checked) parametri.online = "1";
        fetch(input.dataset.ricercaUrl + "?" + new URLSearchParams(parametri),
              { headers: { Accept: "application/json" }, credentials: "same-origin" })
          .then(function (r) { return r.json(); })
          .then(function (d) { if (input.value.trim() === q) mostra(d); })
          .catch(function () { mostra({ errore: "Ricerca non disponibile: compila i campi a mano." }); });
      }, attesa);
    }

    input.addEventListener("input", function () { cerca(300); });
    input.addEventListener("keydown", function (e) { if (e.key === "Escape") lista.hidden = true; });
  }

  document.querySelectorAll("[data-ricerca-url]").forEach(attiva);
})();
