// Menu dell'account (<details class="utente">): si chiude con un clic fuori o con Esc.
(function () {
  var menu = document.querySelector("details.utente");
  if (!menu) return;
  document.addEventListener("click", function (e) {
    if (menu.open && !menu.contains(e.target)) menu.open = false;
  });
  document.addEventListener("keydown", function (e) {
    if (e.key === "Escape" && menu.open) {
      menu.open = false;
      menu.querySelector("summary").focus();
    }
  });
})();
