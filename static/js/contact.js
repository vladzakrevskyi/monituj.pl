// The contact form's browser check (apps/contact/forms.py): on the first key,
// click or touch in the form, the page's time token goes - reversed - into
// the "human" field. A bot posting straight to the address never runs this,
// and its message is dropped without a word.
(function () {
  const form = document.querySelector("[data-contact-form]");
  if (!form) return;
  const issued = form.querySelector('input[name="issued"]');
  const human = form.querySelector('input[name="human"]');
  if (!issued || !human) return;

  function mark() {
    human.value = issued.value.split("").reverse().join("");
  }
  ["keydown", "input", "pointerdown", "touchstart"].forEach((type) => {
    form.addEventListener(type, mark, { once: true, passive: true });
  });
})();
