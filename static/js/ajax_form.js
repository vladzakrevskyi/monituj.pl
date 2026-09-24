const FormErrors = (function () {
  function buildList(messages) {
    const ul = document.createElement("ul");
    ul.className = "errorlist js-field-error";
    messages.forEach((message) => {
      const li = document.createElement("li");
      li.textContent = noOrphans(message);
      ul.appendChild(li);
    });
    return ul;
  }

  // Password inputs sit inside a wrapper with the show/hide button; the
  // error goes below that wrapper, not between the input and the button.
  function placement(anchor) {
    return anchor.closest(".password-field") || anchor;
  }

  // The error list goes right after the anchor element; a [data-error-for]
  // wrapper (e.g. the document list builder) can stand in for the input.
  function set(anchor, messages) {
    clearField(anchor);
    const inputs = anchor.matches("input, select, textarea")
      ? [anchor]
      : anchor.querySelectorAll("input:not([type=hidden]), select, textarea");
    inputs.forEach((input) => input.setAttribute("aria-invalid", "true"));
    placement(anchor).insertAdjacentElement("afterend", buildList(messages));
  }

  function clearField(anchor) {
    const next = placement(anchor).nextElementSibling;
    if (next && next.classList.contains("errorlist")) next.remove();
    const inputs = anchor.matches("input, select, textarea")
      ? [anchor]
      : anchor.querySelectorAll("[aria-invalid]");
    inputs.forEach((input) => input.removeAttribute("aria-invalid"));
  }

  function clearAll(form) {
    form.querySelectorAll(".errorlist").forEach((el) => el.remove());
    form
      .querySelectorAll("[aria-invalid]")
      .forEach((el) => el.removeAttribute("aria-invalid"));
  }

  function anchorFor(form, field) {
    return (
      form.querySelector(`[data-error-for="${field}"]`) ||
      form.querySelector(`[name="${field}"]:not([type=hidden])`)
    );
  }

  // Field errors go under their inputs; anything that belongs to no field
  // (rate limits, expired links, network trouble) is shown as a toast.
  function apply(form, error) {
    const fields = (error && error.fields) || {};
    const loose = [];
    let firstAnchor = null;
    Object.keys(fields).forEach((key) => {
      const messages = fields[key];
      if (!messages || !messages.length) return;
      const anchor = key === "__all__" ? null : anchorFor(form, key);
      if (anchor) {
        set(anchor, messages);
        firstAnchor = firstAnchor || anchor;
      } else {
        loose.push(...messages);
      }
    });
    if (!firstAnchor && !loose.length) {
      loose.push((error && error.message) || "Wystąpił błąd.");
    }
    loose.forEach((message) => showToast(message, "error"));
    if (firstAnchor) {
      const input = firstAnchor.matches("input, select, textarea")
        ? firstAnchor
        : firstAnchor.querySelector("input, select, textarea");
      if (input) input.focus({ preventScroll: false });
    }
  }

  // Editing a field clears its error straight away.
  document.addEventListener("input", (event) => {
    const input = event.target;
    if (!input.matches || !input.matches("[aria-invalid]")) return;
    const wrapper = input.closest("[data-error-for]");
    clearField(wrapper || input);
  });
  document.addEventListener("change", (event) => {
    const input = event.target;
    if (input.matches && input.matches("[aria-invalid]")) clearField(input);
  });

  return { set, clearField, clearAll, apply, anchorFor };
})();

(function () {
  function replaceWithMessage(form, title, message) {
    const card = form.closest(".card") || form.parentElement;
    card.innerHTML = "";
    const h1 = document.createElement("h1");
    h1.textContent = noOrphans(title) || "Gotowe";
    const p = document.createElement("p");
    p.className = "mb-0";
    p.textContent = noOrphans(message) || "";
    card.appendChild(h1);
    card.appendChild(p);
  }

  document.querySelectorAll("form[data-ajax-form]").forEach((form) => {
    form.addEventListener("submit", async (event) => {
      event.preventDefault();
      FormErrors.clearAll(form);

      const submitButton = event.submitter || form.querySelector('button[type="submit"]');
      if (submitButton && submitButton.classList.contains("is-loading")) return;
      ButtonLoader.start(submitButton);
      let leaving = false;

      const formData = new FormData(form);
      const method = (form.getAttribute("method") || "POST").toUpperCase();

      try {
        // form.action (the property) can resolve to a named <input
        // name="action"> instead of the URL string - getAttribute() always
        // reads the raw HTML attribute, sidestepping that shadowing.
        const actionUrl = form.getAttribute("action") || window.location.href;
        const response = await fetch(actionUrl, {
          method,
          headers: {
            "X-Requested-With": "XMLHttpRequest",
            "X-CSRFToken": formData.get("csrfmiddlewaretoken"),
          },
          body: formData,
        });
        let data = null;
        try {
          data = await response.json();
        } catch {
          data = null;
        }

        if (response.ok && data && data.success) {
          const payload = data.data || {};
          if (payload.redirect_url) {
            // Keep spinning until the next page replaces this one.
            leaving = true;
            window.location.href = payload.redirect_url;
            return;
          }
          if (form.dataset.replaceOnSuccess !== undefined) {
            replaceWithMessage(form, payload.title, payload.message);
            showToast(payload.title || "Gotowe.", "success");
            return;
          }
          showToast(payload.message || "Zmiany zostały zapisane.", "success");
          if (form.dataset.resetOnSuccess !== undefined) {
            form.reset();
          }
        } else if (data && data.error) {
          FormErrors.apply(form, data.error);
        } else {
          showToast("Wystąpił błąd. Spróbuj ponownie.", "error");
        }
      } catch {
        showToast("Wystąpił błąd połączenia. Spróbuj ponownie.", "error");
      } finally {
        if (!leaving) ButtonLoader.stop(submitButton);
      }
    });
  });
})();

// "Własny okres" reveals the custom day count; presets hide it.
document.querySelectorAll('select[name="retention_choice"]').forEach((select) => {
  const custom = select.form && select.form.querySelector('[name="retention_custom_days"]');
  if (!custom) return;
  const row = custom.closest("p") || custom;
  const sync = () => {
    row.hidden = select.value !== "custom";
  };
  select.addEventListener("change", () => {
    sync();
    if (!row.hidden) custom.focus();
  });
  sync();
});
