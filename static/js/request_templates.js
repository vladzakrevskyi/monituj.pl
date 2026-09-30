// "Zacznij od szablonu" reloads the form filled from the picked template;
// a list already typed in is lost, so that is asked first.
(function () {
  const select = document.querySelector("[data-template-select]");
  if (select) {
    const initial = select.value;
    select.addEventListener("change", () => {
      const typed = document.querySelectorAll('#item-list input[name="items"]').length;
      if (typed && !window.confirm("Zastąpić wpisaną listę dokumentów szablonem?")) {
        select.value = initial;
        return;
      }
      select.form.submit();
    });
  }

  // "Zapisz jako szablon": the name field shows once it is ticked.
  const box = document.querySelector('input[name="save_as_template"]');
  const title = document.querySelector("[data-save-template-title]");
  if (box && title) {
    box.addEventListener("change", () => {
      title.hidden = !box.checked;
    });
  }
})();
