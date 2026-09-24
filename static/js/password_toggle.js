// An eye button inside every password field shows or hides what was typed.
(function () {
  const EYE =
    '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M2 12s3.5-7 10-7 10 7 10 7-3.5 7-10 7S2 12 2 12z"/><circle cx="12" cy="12" r="3"/></svg>';
  const EYE_OFF =
    '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M9.9 4.24A9.1 9.1 0 0112 4c6.5 0 10 7 10 7a17.6 17.6 0 01-2.16 3.19M6.61 6.61A17.4 17.4 0 002 12s3.5 7 10 7a9.7 9.7 0 005.39-1.61"/><path d="M14.12 14.12a3 3 0 11-4.24-4.24"/><path d="M2 2l20 20"/></svg>';

  function enhance(input) {
    if (input.closest(".password-field")) return;
    const wrapper = document.createElement("span");
    wrapper.className = "password-field";
    input.parentNode.insertBefore(wrapper, input);
    wrapper.appendChild(input);

    const button = document.createElement("button");
    button.type = "button";
    button.className = "password-field__toggle";
    wrapper.appendChild(button);

    function render(visible) {
      input.type = visible ? "text" : "password";
      button.innerHTML = visible ? EYE_OFF : EYE;
      button.setAttribute("aria-label", visible ? "Ukryj hasło" : "Pokaż hasło");
      button.setAttribute("aria-pressed", visible ? "true" : "false");
      button.title = visible ? "Ukryj hasło" : "Pokaż hasło";
    }

    button.addEventListener("click", () => {
      const start = input.selectionStart;
      const end = input.selectionEnd;
      render(input.type === "password");
      input.focus();
      try {
        input.setSelectionRange(start, end);
      } catch {
        // Some browsers don't expose the selection of password fields.
      }
    });
    // Never submit or leave a page with the password shown in plain text.
    if (input.form) input.form.addEventListener("submit", () => render(false));
    render(false);
  }

  document.querySelectorAll('input[type="password"]').forEach(enhance);
})();
