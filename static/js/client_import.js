// Klienci → Import z pliku.
(function () {
  // The file box: a chosen or dropped file goes up at once.
  const dropForm = document.querySelector("form[data-file-drop]");
  if (dropForm) {
    const zone = dropForm.querySelector(".file-drop");
    const input = dropForm.querySelector("input[type=file]");
    const title = dropForm.querySelector("[data-file-drop-title]");
    const button = dropForm.querySelector("[data-file-drop-button]");
    const send = () => {
      if (!input.files.length) return;
      zone.classList.add("is-loading");
      zone.classList.remove("has-error");
      title.textContent = input.files[0].name;
      button.textContent = "Wczytujemy…";
      dropForm.requestSubmit();
    };
    input.addEventListener("change", send);
    ["dragenter", "dragover"].forEach((type) =>
      zone.addEventListener(type, (event) => {
        event.preventDefault();
        zone.classList.add("drag-over");
      })
    );
    ["dragleave", "drop"].forEach((type) =>
      zone.addEventListener(type, () => zone.classList.remove("drag-over"))
    );
    zone.addEventListener("drop", (event) => {
      event.preventDefault();
      if (!event.dataTransfer.files.length) return;
      input.files = event.dataTransfer.files;
      send();
    });
  }

  // The columns: a changed one refreshes the preview at once, so the
  // "Odśwież podgląd" button is only a fallback.
  const columns = document.querySelector("form[data-autosubmit]");
  if (columns) {
    const fallback = columns.querySelector("[data-autosubmit-fallback]");
    if (fallback) fallback.hidden = true;
    columns.addEventListener("change", () => columns.requestSubmit());
  }

  // "Zaktualizuj ich dane" changes what the button says it will do.
  const update = document.querySelector("[data-update-existing]");
  const submit = document.querySelector("[data-import-submit]");
  if (update && submit) {
    const nothingNew = submit.dataset.new === "0";
    update.addEventListener("change", () => {
      submit.textContent = update.checked
        ? submit.dataset.labelUpdate
        : submit.dataset.label;
      submit.disabled = nothingNew && !update.checked;
    });
  }
})();
