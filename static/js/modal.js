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
  function enhance(dialog) {
    if (dialog.dataset.modalReady) return;
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

  function build({ title, message, confirmLabel, cancelLabel, danger, field }) {
    const dialog = document.createElement("dialog");
    dialog.innerHTML = `
      <div class="modal__inner">
        <div class="modal__header"><h2></h2></div>
        <p class="modal__message"></p>
        <div class="modal__field" hidden>
          <label></label>
          <textarea rows="3"></textarea>
        </div>
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

  function prompt(options) {
    return new Promise((resolve) => {
      const dialog = build(options);
      const textarea = dialog.querySelector("textarea");
      let result = null;
      dialog.querySelector("[data-modal-confirm]").addEventListener("click", () => {
        const value = textarea.value.trim();
        if (!value) {
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

  return { open, confirm, prompt, enhance };
})();
