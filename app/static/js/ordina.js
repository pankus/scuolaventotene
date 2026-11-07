// Riordino col trascinamento: <table data-ordina="url">, righe <tr draggable data-id>.
// Si sposta solo dentro lo stesso <tbody> (un giorno del programma); al rilascio manda gli id
// nell'ordine nuovo. Se il salvataggio fallisce la pagina si ricarica dallo stato salvato.
(function () {
  document.querySelectorAll("table[data-ordina]").forEach(function (tabella) {
    var trascinata = null;

    function salva() {
      var dati = new FormData();
      dati.append("csrf_token", document.querySelector("input[name=csrf_token]").value);
      tabella.querySelectorAll("tr[data-id]").forEach(function (tr, i) {
        dati.append("id", tr.dataset.id);
        var n = tr.querySelector(".posizione");
        if (n) n.textContent = i + 1;
      });
      fetch(tabella.dataset.ordina, { method: "POST", body: dati, credentials: "same-origin" })
        .then(function (r) { if (!r.ok) location.reload(); })
        .catch(function () { location.reload(); });
    }

    tabella.addEventListener("dragstart", function (e) {
      trascinata = e.target.closest("tr[data-id]");
      if (!trascinata) return;
      trascinata.classList.add("trascinata");
      e.dataTransfer.effectAllowed = "move";
      e.dataTransfer.setData("text/plain", trascinata.dataset.id);
    });

    tabella.addEventListener("dragover", function (e) {
      var sotto = e.target.closest("tr[data-id]");
      if (!trascinata || !sotto || sotto === trascinata || sotto.parentNode !== trascinata.parentNode) return;
      e.preventDefault();
      var r = sotto.getBoundingClientRect();
      var dopo = e.clientY > r.top + r.height / 2;
      sotto.parentNode.insertBefore(trascinata, dopo ? sotto.nextSibling : sotto);
    });

    tabella.addEventListener("drop", function (e) { e.preventDefault(); });

    tabella.addEventListener("dragend", function () {
      if (!trascinata) return;
      trascinata.classList.remove("trascinata");
      trascinata = null;
      salva();
    });
  });
})();
