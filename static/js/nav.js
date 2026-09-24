(function () {
  function closeAll() {
    document.querySelectorAll("[data-nav-target].is-open").forEach(function (el) {
      el.classList.remove("is-open");
    });
    document.querySelectorAll("[data-nav-toggle]").forEach(function (btn) {
      btn.setAttribute("aria-expanded", "false");
    });
    document.body.classList.remove("nav-open");
  }

  document.querySelectorAll("[data-nav-toggle]").forEach(function (button) {
    var target = document.querySelector(button.getAttribute("data-nav-toggle"));
    if (!target) return;

    button.addEventListener("click", function (event) {
      event.stopPropagation();
      var willOpen = !target.classList.contains("is-open");
      closeAll();
      if (willOpen) {
        target.classList.add("is-open");
        button.setAttribute("aria-expanded", "true");
        document.body.classList.add("nav-open");
      }
    });

    target.querySelectorAll("a, button:not([data-nav-toggle])").forEach(function (el) {
      el.addEventListener("click", closeAll);
    });
  });

  document.addEventListener("click", function (event) {
    var openTarget = document.querySelector("[data-nav-target].is-open");
    if (!openTarget) return;
    if (openTarget.contains(event.target)) return;
    if (event.target.closest("[data-nav-toggle]")) return;
    closeAll();
  });

  document.addEventListener("keydown", function (event) {
    if (event.key === "Escape") closeAll();
  });
})();

(function () {
  document.querySelectorAll("[data-disclosure]").forEach(function (button) {
    var panel = document.querySelector(button.getAttribute("data-disclosure"));
    if (!panel) return;
    button.addEventListener("click", function () {
      var open = panel.hidden;
      panel.hidden = !open;
      button.setAttribute("aria-expanded", open ? "true" : "false");
      if (open) {
        var first = panel.querySelector("input, select");
        if (first) first.focus();
      }
    });
  });
})();
