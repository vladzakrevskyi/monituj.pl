// Bulk actions for a list (<form data-bulk>): tick rows or the whole page
// (the table's header checkbox, or the phone row above the cards); a bar
// then shows at the bottom of the screen with the page checkbox again,
// "select everything matching the filters on all pages" ("all" - the server
// finds them again from the filters sent along), "clear" and "delete".
// The confirmation's texts come from the form: data-confirm-title ({n} is
// the count), data-confirm-message, data-confirm-label and optionally
// data-confirm-option - a checkbox that sets [data-bulk-option] to "1".
(function () {
  const form = document.querySelector("[data-bulk]");
  if (!form) return;
  const rows = [...document.querySelectorAll("[data-select-row]")];
  const pageBoxes = [...document.querySelectorAll("[data-select-page]")];
  const count = form.querySelector("[data-bulk-count]");
  const everything = form.querySelector("[data-bulk-everything]");
  const allInput = form.querySelector("[data-bulk-all]");
  const optionInput = form.querySelector("[data-bulk-option]");
  const total = Number(form.dataset.total);

  const ticked = () => rows.filter((row) => row.checked).length;
  const allPages = () => allInput.value === "1";

  function update() {
    const n = ticked();
    pageBoxes.forEach((box) => {
      box.checked = n > 0 && n === rows.length;
      box.indeterminate = n > 0 && n < rows.length;
    });
    form.hidden = n === 0;
    count.textContent = allPages()
      ? `Zaznaczono wszystkie: ${total}`
      : `Zaznaczono: ${n}`;
    if (everything) everything.hidden = allPages() || n !== rows.length;
  }

  function tickAll(value) {
    rows.forEach((row) => {
      row.checked = value;
    });
    allInput.value = "";
    update();
  }

  rows.forEach((row) =>
    row.addEventListener("change", () => {
      allInput.value = "";
      update();
    })
  );
  pageBoxes.forEach((box) => box.addEventListener("change", () => tickAll(box.checked)));
  form.querySelector("[data-bulk-clear]").addEventListener("click", () => tickAll(false));
  if (everything) {
    everything.addEventListener("click", () => {
      allInput.value = "1";
      update();
    });
  }

  form.addEventListener("submit", async (event) => {
    if (form.dataset.confirmed) return;
    event.preventDefault();
    const n = allPages() ? total : ticked();
    const options = {
      title: form.dataset.confirmTitle.replace("{n}", n),
      message: form.dataset.confirmMessage,
      confirmLabel: form.dataset.confirmLabel || "Usuń",
      danger: true,
    };
    if (form.dataset.confirmOption) {
      const answer = await Modal.confirmWithOption({
        ...options,
        option: form.dataset.confirmOption,
      });
      if (!answer) return;
      if (optionInput) optionInput.value = answer.checked ? "1" : "";
    } else if (!(await Modal.confirm(options))) {
      return;
    }
    form.dataset.confirmed = "1";
    form.requestSubmit();
  });

  update();
})();
