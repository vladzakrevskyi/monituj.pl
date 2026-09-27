// Document downloads (/api/documents/<id>/download/) go through fetch, so a
// problem (a file that can't be opened, no access, no connection) shows up as
// a toast instead of replacing the page with a raw error.
(function () {
  const SELECTOR = 'a[href^="/api/documents/"][href$="/download/"]';
  const FALLBACK = "Nie udało się pobrać pliku. Spróbuj ponownie.";

  function filenameFrom(disposition) {
    if (!disposition) return "";
    const encoded = /filename\*=(?:UTF-8|utf-8)''([^;]+)/.exec(disposition);
    if (encoded) {
      try {
        return decodeURIComponent(encoded[1].trim());
      } catch {
        // fall through to the plain name
      }
    }
    const plain = /filename="?([^";]+)"?/.exec(disposition);
    return plain ? plain[1].trim() : "";
  }

  function save(blob, name) {
    const url = URL.createObjectURL(blob);
    const anchor = document.createElement("a");
    anchor.href = url;
    anchor.download = name;
    anchor.hidden = true;
    document.body.appendChild(anchor);
    anchor.click();
    anchor.remove();
    setTimeout(() => URL.revokeObjectURL(url), 30000);
  }

  async function errorMessage(response) {
    try {
      const data = await response.json();
      return (data && data.error && data.error.message) || FALLBACK;
    } catch {
      return FALLBACK;
    }
  }

  document.addEventListener("click", async (event) => {
    const link = event.target.closest(SELECTOR);
    if (!link || event.defaultPrevented) return;
    // Ctrl/Cmd-click and friends keep the browser's own behaviour.
    if (event.button !== 0 || event.metaKey || event.ctrlKey || event.shiftKey || event.altKey) {
      return;
    }
    event.preventDefault();
    if (link.classList.contains("is-downloading")) return;
    link.classList.add("is-downloading");
    link.setAttribute("aria-busy", "true");
    try {
      const response = await fetch(link.href, {
        credentials: "same-origin",
        headers: { "X-Requested-With": "XMLHttpRequest" },
      });
      if (!response.ok) {
        showToast(await errorMessage(response), "error");
        return;
      }
      const name =
        filenameFrom(response.headers.get("Content-Disposition")) ||
        link.textContent.trim() ||
        "dokument";
      save(await response.blob(), name);
    } catch {
      showToast("Nie udało się pobrać pliku. Sprawdź połączenie z internetem.", "error");
    } finally {
      link.classList.remove("is-downloading");
      link.removeAttribute("aria-busy");
    }
  });
})();
