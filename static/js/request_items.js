(function () {
  const input = document.getElementById("item-name-input");
  const addButton = document.getElementById("add-item-button");
  const list = document.getElementById("item-list");
  if (!input || !addButton || !list) return;

  function changed() {
    list.dispatchEvent(new CustomEvent("items:change", { bubbles: true }));
  }

  function has(name) {
    return Array.from(list.querySelectorAll('input[name="items"]')).some(
      (hidden) => hidden.value.toLowerCase() === name.toLowerCase(),
    );
  }

  function addItem(name) {
    const trimmed = name.trim();
    if (!trimmed || has(trimmed)) return;

    const li = document.createElement("li");
    li.className = "item-chip";

    const span = document.createElement("span");
    span.textContent = trimmed;

    const hidden = document.createElement("input");
    hidden.type = "hidden";
    hidden.name = "items";
    hidden.value = trimmed;

    const removeButton = document.createElement("button");
    removeButton.type = "button";
    removeButton.className = "btn btn-secondary btn-sm item-remove";
    removeButton.textContent = "Usuń";
    removeButton.addEventListener("click", () => {
      li.remove();
      changed();
    });

    li.appendChild(span);
    li.appendChild(hidden);
    li.appendChild(removeButton);
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

  const initialDataScript = document.getElementById("posted-items-data");
  if (initialDataScript) {
    try {
      JSON.parse(initialDataScript.textContent).forEach((name) => addItem(name));
    } catch {
      /* ignore malformed initial data */
    }
  }
})();
