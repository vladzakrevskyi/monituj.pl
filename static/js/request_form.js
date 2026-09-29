// "Nowa prośba o dokumenty": three steps (what, from whom, by when) and the
// rest folded under "Więcej ustawień". The picker takes one client or many
// (and new ones by e-mail), the summary under the form says in words what
// will happen, and the button says it too.
(function () {
  const form = document.querySelector("form[data-request-form]");
  if (!form) return;
  const $ = (selector) => form.querySelector(selector);
  const $$ = (selector) => Array.from(form.querySelectorAll(selector));
  const EMAIL = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
  const dayMonth = new Intl.DateTimeFormat("pl-PL", { day: "numeric", month: "long" });

  function readJson(id, fallback) {
    const element = document.getElementById(id);
    try {
      return element ? JSON.parse(element.textContent) : fallback;
    } catch {
      return fallback;
    }
  }

  function element(tag, className, text) {
    const node = document.createElement(tag);
    if (className) node.className = className;
    if (text !== undefined) node.textContent = text;
    return node;
  }

  // --- 2. from whom ---------------------------------------------------------------
  const clients = readJson("client-options", []);
  const input = $("[data-recipient-input]");
  const tokens = $("[data-tokens]");
  const options = $("[data-options]");
  const hiddenBox = $("[data-recipient-inputs]");
  const newBox = $("[data-new-recipients]");
  const newRows = $("[data-new-rows]");
  const picked = new Map();
  let shown = [];
  let active = -1;

  function byKey(container, key) {
    return Array.from(container.children).find((child) => child.dataset.key === key);
  }

  function addToken(key, label, note) {
    const token = element("li", "recipient-token");
    token.dataset.key = key;
    token.appendChild(element("span", "recipient-token__name", label));
    if (note) token.appendChild(element("span", "recipient-token__note", note));
    const remove = element("button", "recipient-token__remove", "×");
    remove.type = "button";
    remove.setAttribute("aria-label", `Usuń: ${label}`);
    remove.addEventListener("click", () => removeRecipient(key));
    token.appendChild(remove);
    tokens.appendChild(token);
  }

  function addClient(client) {
    const key = `c${client.id}`;
    if (picked.has(key)) return;
    picked.set(key, { kind: "client", name: client.name });
    const hidden = element("input");
    hidden.type = "hidden";
    hidden.name = "clients";
    hidden.value = client.id;
    hidden.dataset.key = key;
    hiddenBox.appendChild(hidden);
    addToken(key, client.name, client.email);
    update();
  }

  function addNew(email) {
    const lower = email.toLowerCase();
    const known = clients.find((client) => client.email.toLowerCase() === lower);
    if (known) return addClient(known);
    const key = `n${lower}`;
    if (picked.has(key)) return;
    picked.set(key, { kind: "new", name: email });
    const row = element("div", "new-recipient");
    row.dataset.key = key;
    row.appendChild(element("span", "new-recipient__email", email));
    const name = element("input");
    name.type = "text";
    name.name = "new_clients_name";
    name.maxLength = 255;
    name.placeholder = "Nazwa, np. Jan Kowalski";
    name.setAttribute("aria-label", `Nazwa klienta ${email}`);
    const hidden = element("input");
    hidden.type = "hidden";
    hidden.name = "new_clients_email";
    hidden.value = email;
    row.append(name, hidden);
    newRows.appendChild(row);
    newBox.hidden = false;
    addToken(key, email, "nowy klient");
    update();
  }

  function removeRecipient(key) {
    picked.delete(key);
    [tokens, hiddenBox, newRows].forEach((container) => byKey(container, key)?.remove());
    newBox.hidden = newRows.children.length === 0;
    update();
    input.focus();
  }

  function renderOptions() {
    const query = input.value.trim().toLowerCase();
    shown = clients
      .filter((client) => !picked.has(`c${client.id}`))
      .filter(
        (client) =>
          !query ||
          client.name.toLowerCase().includes(query) ||
          client.email.toLowerCase().includes(query),
      )
      .slice(0, 8)
      .map((client) => ({ client }));
    const typed = input.value.trim();
    if (EMAIL.test(typed) && !clients.some((c) => c.email.toLowerCase() === query)) {
      shown.push({ email: typed });
    }
    options.replaceChildren(
      ...shown.map((option, index) => {
        const item = element("li", "recipient-option");
        item.setAttribute("role", "option");
        if (option.client) {
          item.append(
            element("span", "recipient-option__name", option.client.name),
            element("span", "recipient-option__email", option.client.email),
          );
        } else {
          item.append(element("span", "recipient-option__name", `+ Dodaj nowego klienta: ${option.email}`));
        }
        // mousedown: before the input loses focus and hides the list.
        item.addEventListener("mousedown", (event) => {
          event.preventDefault();
          choose(index);
        });
        return item;
      }),
    );
    if (!shown.length && query) {
      options.appendChild(
        element("li", "recipient-option recipient-option--hint", "Nie ma takiego klienta – wpisz pełny adres e-mail, żeby dodać nowego."),
      );
    }
    active = shown.length ? 0 : -1;
    highlight();
    const open = document.activeElement === input && options.children.length > 0;
    options.hidden = !open;
    input.setAttribute("aria-expanded", String(open));
  }

  function highlight() {
    Array.from(options.children).forEach((item, index) => {
      item.classList.toggle("is-active", index === active);
    });
  }

  function choose(index) {
    const option = shown[index];
    if (!option) return;
    if (option.client) addClient(option.client);
    else addNew(option.email);
    input.value = "";
    renderOptions();
  }

  function addEmails(text) {
    const emails = text.split(/[\s,;]+/).filter((part) => EMAIL.test(part));
    emails.forEach(addNew);
    return emails.length;
  }

  input.addEventListener("input", renderOptions);
  input.addEventListener("focus", renderOptions);
  input.addEventListener("blur", () => {
    // A typed address counts even without Enter.
    if (EMAIL.test(input.value.trim())) {
      addNew(input.value.trim());
      input.value = "";
    }
    options.hidden = true;
    input.setAttribute("aria-expanded", "false");
  });
  input.addEventListener("keydown", (event) => {
    if (event.key === "ArrowDown" || event.key === "ArrowUp") {
      event.preventDefault();
      if (!shown.length) return;
      active = (active + (event.key === "ArrowDown" ? 1 : -1) + shown.length) % shown.length;
      highlight();
    } else if (event.key === "Enter" || event.key === "," || event.key === ";") {
      if (event.key === "Enter" || EMAIL.test(input.value.trim())) event.preventDefault();
      if (active >= 0 && event.key === "Enter") choose(active);
      else if (EMAIL.test(input.value.trim())) {
        addNew(input.value.trim());
        input.value = "";
        renderOptions();
      }
    } else if (event.key === "Backspace" && !input.value && tokens.lastElementChild) {
      removeRecipient(tokens.lastElementChild.dataset.key);
    } else if (event.key === "Escape") {
      options.hidden = true;
    }
  });
  input.addEventListener("paste", (event) => {
    const text = (event.clipboardData || window.clipboardData).getData("text");
    if (text.split(/[\s,;]+/).filter((part) => EMAIL.test(part)).length > 1) {
      event.preventDefault();
      addEmails(text);
      renderOptions();
    }
  });
  $("[data-picker-box]").addEventListener("click", (event) => {
    if (event.target === event.currentTarget || event.target === tokens) input.focus();
  });

  // --- 3. by when ---------------------------------------------------------------------
  const repeat = $('input[name="schedule"]');
  const repeatSettings = $('[data-schedule="recurring"]');
  const interval = $('select[name="interval"]');
  const workdays = $("[data-workdays-label]");
  const WEEKDAYS_ON = ["w poniedziałek", "we wtorek", "w środę", "w czwartek", "w piątek", "w sobotę", "w niedzielę"];

  function deadlineChoice() {
    return $('input[name="deadline_choice"]:checked')?.value || "none";
  }

  function timingText() {
    const value = interval.value;
    if (value === "daily") {
      return $('input[name="workdays_only"]').checked ? "codziennie w dni robocze" : "codziennie";
    }
    const weekday = WEEKDAYS_ON[Number($('select[name="weekday"]').value)];
    if (value === "weekly") return `co tydzień ${weekday}`;
    if (value === "biweekly") return `co 2 tygodnie ${weekday}`;
    const day = $('select[name="month_day"]').value;
    return day === "31" ? "co miesiąc, ostatniego dnia" : `co miesiąc, ${day}. dnia`;
  }

  function showDeadline() {
    const recurringOn = repeat.checked;
    $$("[data-deadline-option]").forEach((option) => {
      const value = option.dataset.deadlineOption;
      option.hidden = (value === "date" && recurringOn) || (value === "days" && !recurringOn);
    });
    const checked = $('input[name="deadline_choice"]:checked');
    if (!checked || checked.closest("[data-deadline-option]").hidden) {
      $('input[name="deadline_choice"][value="14"]').checked = true;
    }
    $$("[data-deadline-extra]").forEach((extra) => {
      extra.hidden = extra.dataset.deadlineExtra !== deadlineChoice();
    });
  }

  function showTiming() {
    const value = interval.value;
    $$("[data-timing-for]").forEach((field) => {
      field.hidden = !field.dataset.timingFor.split(" ").includes(value);
    });
    workdays.textContent = value === "daily" ? workdays.dataset.daily : workdays.dataset.other;
    repeatSettings.hidden = !repeat.checked;
    $("[data-timing-summary]").textContent = repeat.checked ? `– ${timingText()}` : "";
  }

  $("[data-insert-month]").addEventListener("click", () => {
    const name = $('input[name="name"]');
    if (!name.value.includes("{miesiąc}")) name.value = `${name.value.trim()} {miesiąc}`.trim();
    name.focus();
    update();
  });

  // --- more settings ---------------------------------------------------------------------
  const REMINDER_HINTS = {
    gentle: "Pierwsze po 3 dniach, potem co 5 dni, najwyżej 2.",
    standard: "Pierwsze po 2 dniach, potem co 3 dni, najwyżej 3.",
    frequent: "Pierwsze następnego dnia, potem co 2 dni, najwyżej 5.",
    custom: "Ustaw własny rytm przypomnień.",
    off: "Klient dostanie tylko pierwszą wiadomość z prośbą.",
  };
  const REMINDER_NAMES = {
    gentle: "łagodne",
    standard: "standardowe",
    frequent: "częste",
    custom: "własne",
    off: "wyłączone",
  };

  function reminderPreset() {
    return $('input[name="reminder_preset"]:checked')?.value || "standard";
  }

  function showMore() {
    const preset = reminderPreset();
    $("[data-reminder-hint]").textContent = REMINDER_HINTS[preset] || "";
    $("[data-reminder-custom]").hidden = preset !== "custom";
    const retention = $('select[name="retention_choice"]');
    const days =
      retention.value === "custom"
        ? `${$('input[name="retention_custom_days"]').value || "?"} dni`
        : retention.options[retention.selectedIndex].text.replace(" (domyślnie)", "");
    const passwordOn = !$("[data-single-once-only]").hidden && $('input[name="password"]').value;
    $("[data-more-summary]").textContent =
      `Przypomnienia: ${REMINDER_NAMES[preset]} · pliki: ${days} · ${passwordOn ? "z hasłem" : "bez hasła"}`;
  }

  // --- the summary and the button ---------------------------------------------------------
  function deadlineText() {
    const choice = deadlineChoice();
    if (repeat.checked) {
      if (choice === "7" || choice === "14") return `termin ${choice} dni po każdej wysyłce`;
      if (choice === "days") {
        const days = $('input[name="deadline_days"]').value;
        return days ? `termin ${days} dni po każdej wysyłce` : "";
      }
      if (choice === "day10") return "termin do 10. dnia miesiąca";
      return "bez terminu";
    }
    if (choice === "7" || choice === "14") {
      const date = new Date();
      date.setDate(date.getDate() + Number(choice));
      return `termin ${dayMonth.format(date)}`;
    }
    if (choice === "day10") return "termin do 10. dnia miesiąca";
    if (choice === "date") {
      const value = $('input[name="deadline"]').value;
      return value ? `termin ${dayMonth.format(new Date(`${value}T12:00`))}` : "";
    }
    return "bez terminu";
  }

  // "do klienta: Anna Nowak", "do 3 klientów" - no declension needed.
  function whom() {
    const count = picked.size;
    if (count === 1) return `do klienta: ${picked.values().next().value.name}`;
    return `do ${count} klientów`;
  }

  function update() {
    const count = picked.size;
    $("[data-single-once-only]").hidden = count > 1 || repeat.checked;
    showDeadline();
    showTiming();
    showMore();

    const name = $('input[name="name"]').value.trim() || "Prośba o dokumenty";
    const summary = $("[data-summary]");
    const submit = $("[data-submit]");
    const deadline = deadlineText();
    if (!count) {
      summary.textContent = "Wybierz, od kogo potrzebujesz dokumentów.";
    } else if (repeat.checked) {
      const first = $('input[name="send_first_now"]').checked
        ? " Pierwsza wysyłka od razu."
        : "";
      summary.textContent =
        `Będziemy wysyłać „${name}” ${whom()}, ${timingText()} (od 8:00)` +
        `${deadline ? ` – ${deadline}` : ""}.${first}`;
    } else {
      summary.textContent = `Wyślemy „${name}” ${whom()}${deadline ? ` – ${deadline}` : ""}.`;
    }
    if (repeat.checked) {
      submit.textContent = `Zapisz i wysyłaj ${timingText().split(",")[0]}`;
    } else {
      submit.textContent = count > 1 ? `Wyślij do ${count} klientów` : "Wyślij prośbę";
    }
  }

  form.addEventListener("input", update);
  form.addEventListener("change", update);
  document.getElementById("item-list")?.addEventListener("items:change", update);

  const preselected = readJson("preselected-client", null);
  const start = clients.find((client) => client.id === preselected);
  if (start) addClient(start);
  update();
})();
