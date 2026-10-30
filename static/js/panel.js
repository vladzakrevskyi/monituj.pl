// The panel's shared behaviour: lists search as you type, "⋯" menus,
// and list rows that open with a click anywhere on them.
(function () {
  // Search as you type: the list reloads a moment after the last key and
  // the cursor comes back to the field.
  const FOCUS_KEY = "live-search-focus";
  document.querySelectorAll("form[data-live-search]").forEach((form) => {
    const input = form.querySelector('input[name="q"]');
    if (!input) return;
    let timer = null;
    let sent = input.value;
    const send = () => {
      if (input.value.trim() === sent.trim()) return;
      sent = input.value;
      try {
        sessionStorage.setItem(FOCUS_KEY, "1");
      } catch {
        // Private window: the cursor just doesn't come back.
      }
      form.requestSubmit();
    };
    input.addEventListener("input", () => {
      clearTimeout(timer);
      timer = setTimeout(send, 500);
    });
    let back = false;
    try {
      back = sessionStorage.getItem(FOCUS_KEY) === "1";
      sessionStorage.removeItem(FOCUS_KEY);
    } catch {
      back = false;
    }
    if (back) {
      input.focus();
      input.setSelectionRange(input.value.length, input.value.length);
    }
  });

  // "⋯" menus: one open at a time; a click outside or Escape closes them.
  // The list is placed against the screen, so a table's rounded, clipped
  // edges don't cut it off; it opens upwards when there's no room below.
  const menus = Array.from(document.querySelectorAll("details.menu"));
  function place(menu) {
    const list = menu.querySelector(".menu__list");
    const toggle = menu.querySelector("summary").getBoundingClientRect();
    list.style.position = "fixed";
    const width = list.offsetWidth;
    const height = list.offsetHeight;
    const left = Math.max(8, Math.min(toggle.right - width, window.innerWidth - width - 8));
    const below = toggle.bottom + 6;
    const top = below + height > window.innerHeight - 8 ? toggle.top - height - 6 : below;
    list.style.left = `${left}px`;
    list.style.top = `${Math.max(8, top)}px`;
    list.style.right = "auto";
  }
  menus.forEach((menu) => {
    menu.addEventListener("toggle", () => {
      if (!menu.open) return;
      menus.forEach((other) => {
        if (other !== menu) other.open = false;
      });
      place(menu);
    });
  });
  const closeAll = () => {
    menus.forEach((menu) => {
      menu.open = false;
    });
  };
  window.addEventListener("resize", closeAll);
  window.addEventListener(
    "scroll",
    (event) => {
      // Scrolling inside the open list itself is fine.
      if (event.target instanceof Element && event.target.closest(".menu__list")) return;
      closeAll();
    },
    true
  );
  document.addEventListener("click", (event) => {
    menus.forEach((menu) => {
      if (menu.open && !menu.contains(event.target)) menu.open = false;
    });
  });
  document.addEventListener("keydown", (event) => {
    if (event.key !== "Escape") return;
    menus.forEach((menu) => {
      if (!menu.open) return;
      menu.open = false;
      menu.querySelector("summary").focus();
    });
  });

  // A row with data-href opens on a click anywhere; links, buttons and
  // checkboxes in it keep working as they are.
  document.querySelectorAll("[data-href]").forEach((row) => {
    row.addEventListener("click", (event) => {
      if (event.target.closest("a, button, input, label, select, textarea, summary, form")) return;
      if (window.getSelection().toString()) return;
      if (event.metaKey || event.ctrlKey) {
        window.open(row.dataset.href, "_blank", "noopener");
      } else {
        window.location.href = row.dataset.href;
      }
    });
  });
})();
