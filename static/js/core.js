function getCookie(name) {
  const match = document.cookie.match(new RegExp(`(?:^|; )${name}=([^;]*)`));
  return match ? decodeURIComponent(match[1]) : null;
}

// Same as apps/common/templatetags/badges.py.
const STATUS_BADGE_CLASSES = {
  aktywny: "badge--progress",
  brak_dokumentow: "badge--progress",
  wszystko_dostarczone: "badge--complete",
  nieaktywny: "badge--neutral",
  w_trakcie: "badge--progress",
  kompletny: "badge--complete",
  po_terminie: "badge--overdue",
  brak: "badge--neutral",
  dostarczony: "badge--action",
  zaakceptowany: "badge--complete",
  odrzucony: "badge--overdue",
  nie_dotyczy: "badge--neutral",
  zamkniety: "badge--neutral",
  niepotwierdzony: "badge--neutral",
};

function statusBadgeClass(code) {
  return STATUS_BADGE_CLASSES[code] || "badge--neutral";
}

async function apiFetch(url, options = {}) {
  const headers = Object.assign(
    { "Content-Type": "application/json" },
    options.headers,
    { "X-CSRFToken": getCookie("csrftoken") }
  );
  const response = await fetch(url, Object.assign({}, options, { headers }));
  let data = null;
  try {
    data = await response.json();
  } catch {
    data = null;
  }
  return { ok: response.ok, status: response.status, data };
}

// "Przypomnij" on any page: <button data-remind-request="ID"
// data-client="Name">. The page hears "reminder-sent" when it went out.
document.addEventListener("click", async (event) => {
  const button = event.target.closest("[data-remind-request]");
  if (!button) return;
  const client = button.dataset.client;
  const confirmed = await Modal.confirm({
    title: "Wysłać przypomnienie?",
    message: client
      ? `${client} dostanie teraz e-mail z listą tego, czego brakuje.`
      : "Klient dostanie teraz e-mail z listą tego, czego brakuje.",
    confirmLabel: "Wyślij przypomnienie",
  });
  if (!confirmed) return;
  const { ok, data } = await ButtonLoader.run(button, () =>
    apiFetch(`/api/requests/${button.dataset.remindRequest}/remind/`, { method: "POST" })
  );
  if (!ok) {
    showToast(data && data.error ? data.error.message : "Wystąpił błąd.", "error");
    return;
  }
  showToast("Przypomnienie wysłane.", "success");
  button.dispatchEvent(new CustomEvent("reminder-sent", { bubbles: true }));
});
