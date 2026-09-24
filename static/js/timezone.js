// Tells the server the visitor's time zone, so dates and reminder times
// follow it. The cookie holds only the zone name, e.g. "Europe/Warsaw".
(function () {
  let zone = "";
  try {
    zone = Intl.DateTimeFormat().resolvedOptions().timeZone || "";
  } catch {
    return;
  }
  if (!zone || document.cookie.includes(`tz=${encodeURIComponent(zone)}`)) return;
  const secure = location.protocol === "https:" ? "; Secure" : "";
  document.cookie = `tz=${encodeURIComponent(zone)}; path=/; max-age=31536000; SameSite=Lax${secure}`;
})();
