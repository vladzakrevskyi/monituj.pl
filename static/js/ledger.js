// The ledger lines above page and section heads number themselves in CSS
// ("03"); this tells CSS how many there are, so they read "03/09"
// (static/css/components.css, .eyebrow). Same selectors as there.
(function () {
  const main = document.querySelector("main");
  if (!main) return;
  const total = main.querySelectorAll(
    ".hero .eyebrow:not(.eyebrow--line), .page-hero .eyebrow, .help-hero .eyebrow, .section-head .eyebrow"
  ).length;
  if (!total) return;
  // One head only: "01/01" says nothing - the line stays, without a number.
  if (total === 1) {
    main.dataset.pozSingle = "";
    return;
  }
  main.style.setProperty("--poz-total", String(total));
  main.dataset.pozTotal = String(total);
})();
