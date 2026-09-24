function getCookie(name) {
  const match = document.cookie.match(new RegExp(`(?:^|; )${name}=([^;]*)`));
  return match ? decodeURIComponent(match[1]) : null;
}

const STATUS_BADGE_CLASSES = {
  aktywny: "badge--progress",
  brak_dokumentow: "badge--missing",
  wszystko_dostarczone: "badge--complete",
  nieaktywny: "badge--neutral",
  w_trakcie: "badge--progress",
  kompletny: "badge--complete",
  po_terminie: "badge--overdue",
  brak: "badge--missing",
  dostarczony: "badge--progress",
  zaakceptowany: "badge--complete",
  odrzucony: "badge--overdue",
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
