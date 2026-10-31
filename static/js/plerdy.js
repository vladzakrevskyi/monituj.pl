// Plerdy (heat maps, session recordings) - what its install snippet does,
// as a file: our Content-Security-Policy runs no inline scripts. Loaded only
// by static/js/consent.js, once the visitor accepts analytics cookies, at the
// end of <body>; the ids come from PLERDY_SITE_HASH and PLERDY_SUID
// (apps/common/cookies.py).
(function (w, d) {
  if (w.__plerdyCode) return;
  const data = d.currentScript.dataset;
  w.__plerdyCode = 1;
  w._protocol = w.location.protocol === "https:" ? "https://" : "http://";
  w._site_hash_code = data.siteHash;
  w._suid = Number(data.suid);
  const tag = d.createElement("script");
  tag.async = true;
  tag.referrerPolicy = "strict-origin-when-cross-origin";
  tag.src = `https://a.plerdy.com/public/js/click/main.js?v=${Math.random()}`;
  d.body.appendChild(tag);
})(window, document);
