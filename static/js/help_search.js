// Centrum pomocy: answers under the search box while typing. The server
// searches (apps/help/search.py); Enter without a chosen answer opens the
// results page, as the form does without JavaScript.
(function () {
  const form = document.querySelector("[data-help-search]");
  if (!form) return;
  const input = form.querySelector("[data-help-input]");
  const list = form.querySelector("[data-help-results]");
  let timer = null;
  let active = -1;
  let last = "";

  function close() {
    list.hidden = true;
    input.setAttribute("aria-expanded", "false");
    active = -1;
  }

  function options() {
    return [...list.querySelectorAll("[role=option]")];
  }

  function highlight(index) {
    const items = options();
    items.forEach((item, i) => item.setAttribute("aria-selected", String(i === index)));
    active = index;
    if (items[index]) input.setAttribute("aria-activedescendant", items[index].id);
    else input.removeAttribute("aria-activedescendant");
  }

  function show(results, query) {
    list.replaceChildren();
    if (!results.length) {
      const empty = document.createElement("li");
      empty.className = "help-search__empty";
      empty.textContent = "Nic nie znaleźliśmy - spróbuj innymi słowami.";
      list.append(empty);
    }
    results.forEach((result, index) => {
      const item = document.createElement("li");
      item.setAttribute("role", "option");
      item.id = `help-option-${index}`;
      const link = document.createElement("a");
      link.href = result.url;
      const title = document.createElement("strong");
      title.textContent = result.title;
      const meta = document.createElement("span");
      meta.textContent = `${result.category} · ${result.summary}`;
      link.append(title, meta);
      item.append(link);
      list.append(item);
    });
    list.hidden = false;
    input.setAttribute("aria-expanded", "true");
    highlight(-1);
    last = query;
  }

  async function find(query) {
    try {
      const url = `${form.action}?format=json&q=${encodeURIComponent(query)}`;
      const response = await fetch(url, { headers: { Accept: "application/json" } });
      if (!response.ok) return;
      const data = await response.json();
      if (input.value.trim() === query) show(data.results, query);
    } catch {
      // Offline or the server is busy: the form still works.
    }
  }

  input.addEventListener("input", () => {
    clearTimeout(timer);
    const query = input.value.trim();
    if (query.length < 3) {
      close();
      return;
    }
    if (query === last && !list.hidden) return;
    timer = setTimeout(() => find(query), 180);
  });

  input.addEventListener("keydown", (event) => {
    const items = options();
    if (event.key === "ArrowDown" && items.length) {
      event.preventDefault();
      highlight((active + 1) % items.length);
    } else if (event.key === "ArrowUp" && items.length) {
      event.preventDefault();
      highlight(active <= 0 ? items.length - 1 : active - 1);
    } else if (event.key === "Enter" && active >= 0 && items[active]) {
      event.preventDefault();
      window.location.href = items[active].querySelector("a").href;
    } else if (event.key === "Escape") {
      close();
    }
  });

  document.addEventListener("click", (event) => {
    if (!form.contains(event.target)) close();
  });
})();
