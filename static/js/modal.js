const Modal = (function () {
  const CLOSE_ICON =
    '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><path d="M6 6l12 12M18 6L6 18"/></svg>';

  function closeButton() {
    const button = document.createElement("button");
    button.type = "button";
    button.className = "modal__close";
    button.setAttribute("aria-label", "Zamknij");
    button.setAttribute("data-modal-close", "");
    button.innerHTML = CLOSE_ICON;
    return button;
  }

  // The dialog box itself has no padding (content sits in .modal__inner), so
  // a click whose target is the <dialog> element landed on the backdrop.
  // data-modal-custom: a dialog with its own close button and looks (the
  // promo film) - left alone.
  function enhance(dialog) {
    if (dialog.dataset.modalReady || dialog.hasAttribute("data-modal-custom")) return;
    dialog.dataset.modalReady = "1";
    dialog.classList.add("modal");
    if (!dialog.querySelector(".modal__close")) {
      const header = dialog.querySelector(".modal__header");
      (header || dialog.firstElementChild || dialog).appendChild(closeButton());
    }
    dialog.addEventListener("click", (event) => {
      if (event.target === dialog || event.target.closest("[data-modal-close]")) {
        dialog.close("cancel");
      }
    });
  }

  function open(dialog) {
    enhance(dialog);
    dialog.showModal();
    const focusTarget = dialog.querySelector(
      "[autofocus], input:not([type=hidden]), textarea, select"
    );
    if (focusTarget) focusTarget.focus();
  }

  function build({ title, message, confirmLabel, cancelLabel, danger, field, option }) {
    const dialog = document.createElement("dialog");
    dialog.innerHTML = `
      <div class="modal__inner">
        <div class="modal__header"><h2></h2></div>
        <p class="modal__message"></p>
        <div class="modal__field" hidden>
          <label></label>
          <textarea rows="3"></textarea>
        </div>
        <label class="modal__option" hidden><input type="checkbox"> <span></span></label>
        <div class="modal-actions">
          <button type="button" class="btn" data-modal-confirm></button>
          <button type="button" class="btn btn-secondary" data-modal-close></button>
        </div>
      </div>`;
    dialog.querySelector("h2").textContent = noOrphans(title);
    const messageEl = dialog.querySelector(".modal__message");
    if (message) messageEl.textContent = noOrphans(message);
    else messageEl.remove();
    const confirmButton = dialog.querySelector("[data-modal-confirm]");
    confirmButton.textContent = confirmLabel || "Potwierdź";
    confirmButton.classList.add(danger ? "btn-danger-solid" : "btn-primary");
    dialog.querySelector(".modal-actions [data-modal-close]").textContent =
      cancelLabel || "Anuluj";
    if (field) {
      const wrap = dialog.querySelector(".modal__field");
      wrap.hidden = false;
      const id = `modal-field-${Date.now()}`;
      wrap.querySelector("label").textContent = field.label;
      wrap.querySelector("label").htmlFor = id;
      wrap.querySelector("textarea").id = id;
      wrap.querySelector("textarea").placeholder = field.placeholder || "";
    }
    if (option) {
      const wrap = dialog.querySelector(".modal__option");
      wrap.hidden = false;
      wrap.querySelector("span").textContent = noOrphans(option);
    }
    document.body.appendChild(dialog);
    enhance(dialog);
    return dialog;
  }

  function confirm(options) {
    return new Promise((resolve) => {
      const dialog = build(options);
      let result = false;
      dialog.querySelector("[data-modal-confirm]").addEventListener("click", () => {
        result = true;
        dialog.close();
      });
      dialog.addEventListener("close", () => {
        dialog.remove();
        resolve(result);
      });
      open(dialog);
      dialog.querySelector("[data-modal-confirm]").focus();
    });
  }

  // Like confirm, with one checkbox (options.option is its label).
  // -> null when cancelled, otherwise {checked}.
  function confirmWithOption(options) {
    return new Promise((resolve) => {
      const dialog = build(options);
      const box = dialog.querySelector(".modal__option input");
      let result = null;
      dialog.querySelector("[data-modal-confirm]").addEventListener("click", () => {
        result = { checked: box.checked };
        dialog.close();
      });
      dialog.addEventListener("close", () => {
        dialog.remove();
        resolve(result);
      });
      open(dialog);
      dialog.querySelector("[data-modal-confirm]").focus();
    });
  }

  function prompt(options) {
    return new Promise((resolve) => {
      const dialog = build(options);
      const textarea = dialog.querySelector("textarea");
      let result = null;
      dialog.querySelector("[data-modal-confirm]").addEventListener("click", () => {
        const value = textarea.value.trim();
        // field.optional: an empty answer is fine ("" - null still means
        // cancelled).
        if (!value && !options.field.optional) {
          FormErrors.set(textarea, [options.field.requiredMessage || "To pole jest wymagane."]);
          textarea.focus();
          return;
        }
        result = value;
        dialog.close();
      });
      textarea.addEventListener("input", () => FormErrors.clearField(textarea));
      dialog.addEventListener("close", () => {
        dialog.remove();
        resolve(result);
      });
      open(dialog);
    });
  }

  document.querySelectorAll("dialog").forEach(enhance);
  document.addEventListener("click", (event) => {
    const trigger = event.target.closest("[data-modal-open]");
    if (!trigger) return;
    const dialog = document.querySelector(trigger.getAttribute("data-modal-open"));
    if (dialog) open(dialog);
  });

  return { open, confirm, confirmWithOption, prompt, enhance };
})();

// <form data-confirm="Question?"> asks before sending, on every page.
// data-confirm-title and data-confirm-label name the dialog and its button;
// data-confirm-option adds a checkbox that sets the form's hidden input
// named by data-confirm-option-input to "1".
document.querySelectorAll("form[data-confirm]").forEach((form) => {
  form.addEventListener("submit", async (event) => {
    if (form.dataset.confirmed) return;
    event.preventDefault();
    const options = {
      title: form.dataset.confirmTitle || "Na pewno?",
      message: form.dataset.confirm,
      confirmLabel: form.dataset.confirmLabel || "Tak",
      danger: form.querySelector(".btn-danger, .btn-danger-solid") !== null,
    };
    if (form.dataset.confirmOption) {
      const answer = await Modal.confirmWithOption({
        ...options,
        option: form.dataset.confirmOption,
      });
      if (!answer) return;
      const input = form.querySelector(`input[name="${form.dataset.confirmOptionInput}"]`);
      if (input) input.value = answer.checked ? "1" : "";
    } else if (!(await Modal.confirm(options))) {
      return;
    }
    form.dataset.confirmed = "1";
    form.requestSubmit();
  });
});
