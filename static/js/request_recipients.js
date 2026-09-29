// Editing a recurring request: the client list to tick (with a search) and
// the interval with its day. The list of requests: buttons that change
// something for clients ask first.
(function () {
  const form = document.querySelector("form[data-ajax-form]");
  if (!form) return;

  // --- the client list ---------------------------------------------------------
  const picker = form.querySelector("[data-client-picker]");
  if (picker) {
    const search = picker.querySelector("[data-client-search]");
    const items = Array.from(picker.querySelectorAll("li[data-search]"));
    search.addEventListener("input", () => {
      const query = search.value.trim().toLowerCase();
      items.forEach((item) => {
        item.hidden = query !== "" && !item.dataset.search.includes(query);
      });
    });
    // Enter in the search box filters; it must not send the form.
    search.addEventListener("keydown", (event) => {
      if (event.key === "Enter") event.preventDefault();
    });
    function tickAll(checked) {
      items.forEach((item) => {
        if (!checked || !item.hidden) item.querySelector("input").checked = checked;
      });
    }
    picker.querySelector("[data-select-visible]").addEventListener("click", () => tickAll(true));
    picker.querySelector("[data-select-none]").addEventListener("click", () => tickAll(false));
  }

  // --- the interval and its day ---------------------------------------------------
  const timing = form.querySelector("[data-timing]");
  if (timing) {
    const interval = timing.querySelector('select[name="interval"]');
    const workdays = timing.querySelector("[data-workdays-label]");
    function showTiming() {
      const value = interval.value;
      timing.querySelectorAll("[data-timing-for]").forEach((element) => {
        element.hidden = !element.dataset.timingFor.split(" ").includes(value);
      });
      workdays.textContent = value === "daily" ? workdays.dataset.daily : workdays.dataset.other;
    }
    interval.addEventListener("change", showTiming);
    showTiming();
  }
})();

document.querySelectorAll("form[data-confirm]").forEach((form) => {
  form.addEventListener("submit", async (event) => {
    if (form.dataset.confirmed || typeof Modal === "undefined") return;
    event.preventDefault();
    const confirmed = await Modal.confirm({
      title: "Na pewno?",
      message: form.dataset.confirm,
      confirmLabel: "Tak",
      danger: form.querySelector(".btn-danger") !== null,
    });
    if (!confirmed) return;
    form.dataset.confirmed = "1";
    form.requestSubmit();
  });
});
