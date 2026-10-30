// Ustawienia: one page of sections. Rows open their form in place, one at a
// time; a link to anything on the page (#logo, #haslo, #usun-konto) scrolls
// there and opens its row. The profile is edited straight away, with a live
// preview of what the client sees.
(function () {
  const rows = Array.from(document.querySelectorAll("details.set-row"));

  // Shows the element and opens its row.
  function reveal(id) {
    const target = id && document.getElementById(id);
    if (!target) return;
    const row = target.closest("details.set-row");
    if (row) row.open = true;
    (row || target).scrollIntoView({ block: "center" });
    const field = row && row.querySelector(".set-row__body input:not([type=hidden]), .set-row__body textarea");
    if (field) field.focus({ preventScroll: true });
  }

  rows.forEach((row) => {
    row.addEventListener("toggle", () => {
      if (!row.open) return;
      rows.forEach((other) => {
        if (other !== row) other.open = false;
      });
    });
  });

  document.querySelectorAll("[data-set-open]").forEach((link) => {
    link.addEventListener("click", (event) => {
      event.preventDefault();
      reveal(link.dataset.setOpen);
    });
  });

  // A row the server sent back with errors wins over the address.
  const failed = document.querySelector("details.set-row[open]");
  if (failed) {
    failed.scrollIntoView({ block: "center" });
  } else {
    reveal(decodeURIComponent(window.location.hash.slice(1)));
  }
  window.addEventListener("hashchange", () => {
    reveal(decodeURIComponent(window.location.hash.slice(1)));
  });

  document.querySelectorAll("[data-set-close]").forEach((button) => {
    button.addEventListener("click", () => {
      const row = button.closest("details.set-row");
      const form = row.querySelector("form[data-ajax-form]");
      if (form) {
        form.reset();
        FormErrors.clearAll(form);
      }
      row.open = false;
      row.querySelector("summary").focus();
    });
  });

  // Saved in a row: close it.
  document.querySelectorAll("details.set-row form[data-ajax-form]").forEach((form) => {
    form.addEventListener("ajax-form:success", () => {
      form.closest("details.set-row").open = false;
    });
  });

  // The profile: "Zapisz" only once something changed; the preview follows
  // what is typed.
  const profile = document.querySelector("form[data-set-profile]");
  if (!profile) return;
  const name = profile.elements.display_name;
  const firm = profile.elements.show_paying_firm;
  const save = profile.querySelector("[data-set-save]");
  const previewName = document.querySelector("[data-preview-name]");
  const previewInitial = document.querySelector("[data-preview-initial]");
  const previewFirm = document.querySelector("[data-preview-firm]");

  function preview() {
    const shown = name.value.trim().replace(/\s+/g, " ") || previewName.dataset.fallback;
    previewName.textContent = shown;
    if (previewInitial) previewInitial.textContent = shown.charAt(0).toUpperCase();
    previewFirm.hidden = !firm.checked;
  }

  function changed() {
    return name.value !== name.defaultValue || firm.checked !== firm.defaultChecked;
  }

  function sync() {
    save.hidden = !changed();
    preview();
  }

  profile.addEventListener("input", sync);
  profile.addEventListener("change", sync);
  profile.querySelector("[data-set-revert]").addEventListener("click", () => {
    profile.reset();
    FormErrors.clearAll(profile);
    sync();
  });
  profile.addEventListener("ajax-form:success", () => {
    // What is saved now is what "Anuluj" goes back to.
    name.defaultValue = name.value;
    firm.defaultChecked = firm.checked;
    sync();
  });
  // Errors from the server: keep the buttons to fix and save again.
  save.hidden = !(changed() || profile.querySelector(".errorlist"));
})();
