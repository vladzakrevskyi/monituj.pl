(function () {
  const input = document.getElementById("item-name-input");
  const addButton = document.getElementById("add-item-button");
  const list = document.getElementById("item-list");
  if (!input || !addButton || !list) return;

  function addItem(name) {
    const trimmed = name.trim();
    if (!trimmed) return;

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
    removeButton.addEventListener("click", () => li.remove());

    li.appendChild(span);
    li.appendChild(hidden);
    li.appendChild(removeButton);
    list.appendChild(li);
  }

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
