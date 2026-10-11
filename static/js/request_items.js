(function () {
  const input = document.getElementById("item-name-input");
  const addButton = document.getElementById("add-item-button");
  const list = document.getElementById("item-list");
  if (!input || !addButton || !list) return;

  function changed() {
    list.dispatchEvent(new CustomEvent("items:change", { bubbles: true }));
  }

  // An item the client only confirms - no file - is posted as its name with
  // this at the end (apps/requests/item_kinds.py); typed that way, it counts too.
  const CONFIRM_SUFFIX = " (bez pliku)";

  function split(text) {
    const trimmed = text.trim();
    if (trimmed.toLowerCase().endsWith(CONFIRM_SUFFIX.trim())) {
      const name = trimmed.slice(0, -CONFIRM_SUFFIX.trim().length).trim();
      if (name) return { name, confirm: true };
    }
    return { name: trimmed, confirm: false };
  }

  function has(name) {
    const wanted = split(name).name.toLowerCase();
    return Array.from(list.querySelectorAll('input[name="items"]')).some(
      (hidden) => split(hidden.value).name.toLowerCase() === wanted,
    );
  }

  function addItem(text) {
    const { name, confirm } = split(text);
    if (!name || has(name)) return;

    const li = document.createElement("li");
    li.className = "item-chip";

    const span = document.createElement("span");
    span.className = "item-chip__name";
    span.textContent = name;

    const hidden = document.createElement("input");
    hidden.type = "hidden";
    hidden.name = "items";

    const kind = document.createElement("button");
    kind.type = "button";
    kind.className = "item-kind-toggle";
    kind.textContent = "Bez pliku";
    kind.title = "Klient nie przesyła tu pliku - tylko potwierdza, że to zrobił";

    function setConfirm(on) {
      hidden.value = on ? name + CONFIRM_SUFFIX : name;
      kind.setAttribute("aria-pressed", String(on));
      li.classList.toggle("item-chip--confirm", on);
    }
    setConfirm(confirm);
    kind.addEventListener("click", () => {
      setConfirm(kind.getAttribute("aria-pressed") !== "true");
      changed();
    });

    const removeButton = document.createElement("button");
    removeButton.type = "button";
    removeButton.className = "btn btn-secondary btn-sm item-remove";
    removeButton.textContent = "Usuń";
    removeButton.addEventListener("click", () => {
      li.remove();
      changed();
    });

    const actions = document.createElement("span");
    actions.className = "item-chip__actions";
    actions.append(kind, removeButton);

    li.appendChild(span);
    li.appendChild(hidden);
    li.appendChild(actions);
    list.appendChild(li);
    changed();
  }

  // Suggested documents ("+ Faktury sprzedaży") add with a click.
  document.querySelectorAll("[data-suggest]").forEach((chip) => {
    chip.addEventListener("click", () => addItem(chip.dataset.suggest));
  });
  function syncSuggestions() {
    document.querySelectorAll("[data-suggest]").forEach((chip) => {
      chip.hidden = has(chip.dataset.suggest);
    });
  }
  list.addEventListener("items:change", syncSuggestions);

  addButton.addEventListener("click", () => {
    addItem(input.value);
    input.value = "";
    input.focus();
  });

  input.addEventListener("keydown", (event) => {
    if (event.key === "Enter") {
      event.preventDefault();
      addItem(input.value);
      input.value = "";
    }
  });

  // What the toggle on every row means - said once, under the list.
  const hint = document.createElement("p");
  hint.className = "form-hint text-muted item-kind-hint";
  hint.textContent =
    "„Bez pliku” - klient niczego nie przesyła, tylko potwierdza, że to zrobił " +
    "(np. nadał biuru uprawnienia w KSeF albo podpisał pełnomocnictwo online).";
  list.insertAdjacentElement("afterend", hint);

  const initialDataScript = document.getElementById("posted-items-data");
  if (initialDataScript) {
    try {
      JSON.parse(initialDataScript.textContent).forEach((name) => addItem(name));
    } catch {
      /* ignore malformed initial data */
    }
  }
})();
