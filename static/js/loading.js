// A spinner on the button that started a request: it blocks repeated clicks
// and shows that something is happening until the server answers.
const ButtonLoader = (function () {
  function start(button) {
    if (!button || button.classList.contains("is-loading")) return;
    button.classList.add("is-loading");
    button.setAttribute("aria-busy", "true");
    button.disabled = true;
  }

  function stop(button) {
    if (!button) return;
    button.classList.remove("is-loading");
    button.removeAttribute("aria-busy");
    button.disabled = false;
  }

  async function run(button, task) {
    start(button);
    try {
      return await task();
    } finally {
      stop(button);
    }
  }

  // Ordinary (non-AJAX) forms: the page is about to change, so the loader
  // simply stays until it does. Forms handled by scripts call
  // preventDefault() first and manage their own loader.
  document.addEventListener("submit", (event) => {
    const form = event.target;
    if (event.defaultPrevented || form.hasAttribute("data-no-loader")) return;
    if (form.dataset.submitting) {
      event.preventDefault();
      return;
    }
    form.dataset.submitting = "1";
    const button = event.submitter || form.querySelector('[type="submit"]');
    if (!button) return;
    button.classList.add("is-loading");
    button.setAttribute("aria-busy", "true");
    // Disabling right away would drop the button's own name/value from
    // the submitted data, so it waits until the browser has read them.
    setTimeout(() => {
      button.disabled = true;
    }, 0);
  });

  // Coming back with the browser's Back button restores the page as it was
  // left - with spinning buttons - so reset them.
  window.addEventListener("pageshow", (event) => {
    if (!event.persisted) return;
    document.querySelectorAll(".is-loading").forEach(stop);
    document
      .querySelectorAll("form[data-submitting]")
      .forEach((form) => delete form.dataset.submitting);
  });

  return { start, stop, run };
})();
