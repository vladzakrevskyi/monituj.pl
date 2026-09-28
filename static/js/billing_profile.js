// "Dane do faktury" on the plan page. A firm types its NIP; what GUS (or the
// VAT register) knows about it is filled in and locked, what it doesn't
// know stays for the buyer to type. The server does the same again on save,
// whatever the browser sends. form[data-state]: "" (NIP not checked yet),
// "found" (some details from a register), "manual" (no register knows it).
(function () {
  const form = document.querySelector("[data-profile-form]");
  if (!form) return;
  const summary = document.querySelector("[data-profile-summary]");
  const field = (name) => form.querySelector(`[name="${name}"]`);
  const FIRM_FIELDS = ["company_name", "street", "post_code", "city"];

  function isCompany() {
    return form.querySelector('[name="kind"]:checked')?.value === "company";
  }

  function setState(state) {
    form.dataset.state = state;
  }

  // Locked details belong to the checked NIP: gone once it changes.
  function unlock() {
    FIRM_FIELDS.forEach((name) => {
      const input = field(name);
      if (input.readOnly) input.value = "";
      input.readOnly = false;
    });
  }

  function toggle(editing) {
    form.hidden = !editing;
    if (summary) summary.hidden = editing;
    if (editing) form.querySelector("input:not([type=hidden]):not([readonly])")?.focus();
  }

  document
    .querySelector("[data-profile-edit]")
    ?.addEventListener("click", () => toggle(true));
  form
    .querySelector("[data-profile-cancel]")
    ?.addEventListener("click", () => toggle(false));

  form.querySelectorAll('[name="kind"]').forEach((radio) =>
    radio.addEventListener("change", () => {
      unlock();
      setState("");
    })
  );
  field("tax_id").addEventListener("input", () => {
    if (form.dataset.state) {
      unlock();
      setState("");
    }
  });
  // The server asks for details it couldn't find: show the fields.
  form.addEventListener("ajax-form:error", (event) => {
    const fields = Object.keys(event.detail?.fields || {});
    if (isCompany() && !form.dataset.state && fields.some((n) => FIRM_FIELDS.includes(n))) {
      setState("manual");
    }
  });

  const lookup = form.querySelector("[data-registry-lookup]");
  lookup.addEventListener("click", async () => {
    // Errors go under the whole NIP row (input + button), not beside it.
    const nipRow = form.querySelector('[data-error-for="tax_id"]');
    FormErrors.clearField(nipRow);
    unlock();
    const response = await ButtonLoader.run(lookup, () =>
      fetch(form.dataset.registryUrl, {
        method: "POST",
        headers: {
          "X-CSRFToken": field("csrfmiddlewaretoken").value,
          "X-Requested-With": "XMLHttpRequest",
        },
        body: new URLSearchParams({ nip: field("tax_id").value }),
      })
        .then((r) => r.json().catch(() => null))
        .catch(() => null)
    );
    if (!response || !response.success) {
      if (response?.error?.code === "NOT_FOUND") {
        setState("manual");
        field("company_name").focus();
        return;
      }
      setState("");
      FormErrors.set(nipRow, [
        response?.error?.message || "Nie udało się sprawdzić NIP.",
      ]);
      return;
    }
    const data = response.data;
    const locked = data.locked || [];
    FIRM_FIELDS.forEach((name) => {
      const input = field(name);
      FormErrors.clearField(input);
      if (locked.includes(name)) {
        input.value = data[name];
        input.readOnly = true;
      }
    });
    form.querySelector("[data-registry-source]").textContent =
      `Dane z rejestru ${data.source}` +
      (data.status ? ` · VAT: ${data.status.toLowerCase()}` : "");
    setState(locked.length ? "found" : "manual");
    // The first detail the register didn't have, to type in.
    FIRM_FIELDS.map(field)
      .find((input) => !input.readOnly)
      ?.focus();
  });
})();
