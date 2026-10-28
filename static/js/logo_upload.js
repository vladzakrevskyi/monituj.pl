// Ustawienia, "Logo dla klientów": pick or drop a file and it is saved at
// once - a preview shows while it goes, as on the client's upload page.
(function () {
  const form = document.querySelector("[data-logo-form]");
  if (!form) return;
  const drop = form.querySelector("[data-logo-drop]");
  const input = form.querySelector("[data-logo-input]");
  const preview = form.querySelector("[data-logo-preview]");
  const hint = form.querySelector("[data-logo-hint]");
  const pick = form.querySelector("[data-logo-pick]");

  function save() {
    const file = input.files[0];
    if (!file) return;
    if (preview) {
      preview.src = URL.createObjectURL(file);
      preview.removeAttribute("width");
      preview.removeAttribute("height");
      preview.hidden = false;
    }
    const icon = form.querySelector(".logo-drop__icon");
    if (icon) icon.hidden = true;
    hint.textContent = `Zapisujemy logo: ${file.name}…`;
    pick.hidden = true;
    drop.classList.add("is-saving");
    form.submit();
  }

  input.addEventListener("change", save);
  drop.addEventListener("dragover", (event) => {
    event.preventDefault();
    drop.classList.add("drag-over");
  });
  drop.addEventListener("dragleave", () => drop.classList.remove("drag-over"));
  drop.addEventListener("drop", (event) => {
    event.preventDefault();
    drop.classList.remove("drag-over");
    if (!event.dataTransfer.files.length) return;
    input.files = event.dataTransfer.files;
    save();
  });
})();
