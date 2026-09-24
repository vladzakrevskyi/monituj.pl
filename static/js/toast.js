// Mirrors apps/common/typography.py for text inserted by scripts: short
// Polish words are glued to the next one so they never end a line.
const ORPHAN_RE = /(^|[\s(„"])([aiouwz]|do|na|po|od|za|ze|we|ku|że|iż|bo|\d+)[ \t\n]+(?=\S)/gi;

function noOrphans(text) {
  if (!text) return text;
  const glued = String(text).replace(ORPHAN_RE, "$1$2\u00a0");
  return glued.replace(ORPHAN_RE, "$1$2\u00a0").replace(/(\S)[ \t\n]+(?=[–—-](\s|$))/g, "$1\u00a0");
}

function showToast(message, variant) {
  let stack = document.querySelector(".toast-stack");
  if (!stack) {
    stack = document.createElement("div");
    stack.className = "toast-stack";
    stack.setAttribute("aria-live", "polite");
    document.body.appendChild(stack);
  }

  const toast = document.createElement("div");
  toast.className = `toast${variant ? ` toast--${variant}` : ""}`;
  toast.setAttribute("role", variant === "error" ? "alert" : "status");

  const text = document.createElement("span");
  text.className = "toast__text";
  text.textContent = noOrphans(message);

  const close = document.createElement("button");
  close.type = "button";
  close.className = "toast__close";
  close.setAttribute("aria-label", "Zamknij");
  close.innerHTML =
    '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><path d="M6 6l12 12M18 6L6 18"/></svg>';
  close.addEventListener("click", () => toast.remove());

  toast.append(text, close);
  stack.appendChild(toast);
  setTimeout(() => toast.remove(), variant === "error" ? 6000 : 4000);
}

// Django messages from the previous request (e.g. "saved" after a redirect)
// are rendered as a hidden list and replayed as toasts.
document.querySelectorAll("[data-flash-messages] li").forEach((item) => {
  const level = item.dataset.level || "";
  const variant = level.includes("error") ? "error" : level.includes("success") ? "success" : "";
  showToast(item.textContent.trim(), variant);
});
