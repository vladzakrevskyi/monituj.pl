// The no-account form: the date appears only for "Wybierz datę", the number
// of days only for a custom file keeping period.
(function () {
  const form = document.querySelector("form[data-ajax-form]");
  if (!form) return;
  const dateField = form.querySelector("[data-deadline-date]");
  const customDays = form.querySelector("[data-retention-custom]");
  const retention = form.querySelector('select[name="retention_choice"]');

  function update() {
    const choice = form.querySelector('input[name="deadline_choice"]:checked');
    if (dateField) dateField.hidden = !choice || choice.value !== "date";
    if (customDays && retention) customDays.hidden = retention.value !== "custom";
  }

  form.addEventListener("change", update);
  update();
})();
