// Cookie consent per category (Google Consent Mode v2).
// Categories, tools and cookie names come from apps/common/cookies.py via the
// #cookie-consent-config block; the banner and the dialog are rendered by
// templates/base/_cookie_consent.html. Google Tag Manager is not even
// downloaded until the visitor agrees to at least one optional category, and
// every tag inside it checks the consent of its own category.
(function () {
  const script = document.currentScript;
  const gtmId = script.dataset.gtmId;
  const logUrl = script.dataset.logUrl;
  const configBlock = document.getElementById("cookie-consent-config");
  if (!gtmId || !configBlock) return;
  const config = JSON.parse(configBlock.textContent);
  const categories = Object.keys(config.categories);
  const MAX_AGE = 365 * 24 * 60 * 60 * 1000; // ask again after a year
  const LEGACY_KEY = "monituj-analytics-consent";

  window.dataLayer = window.dataLayer || [];
  function gtag() {
    window.dataLayer.push(arguments);
  }

  // Everything optional is off until the visitor says otherwise.
  const defaults = {
    ad_storage: "denied",
    ad_user_data: "denied",
    ad_personalization: "denied",
    analytics_storage: "denied",
    functionality_storage: "denied",
    personalization_storage: "denied",
    security_storage: "denied",
    wait_for_update: 500,
  };
  config.granted.forEach((type) => {
    defaults[type] = "granted";
  });
  gtag("consent", "default", defaults);

  function stored() {
    try {
      return JSON.parse(window.localStorage.getItem(config.storageKey)) || {};
    } catch {
      return {};
    }
  }

  function read() {
    const saved = stored();
    // A new tool or an old answer means asking again.
    if (saved.version !== config.version) return null;
    if (!(Date.now() - saved.at < MAX_AGE)) return null;
    return saved.choices;
  }

  // A random id for this browser's decisions, so the consent register on the
  // server can show what was chosen and when - without any personal data.
  function consentId() {
    const known = stored().id;
    if (typeof known === "string" && /^[0-9a-f-]{36}$/.test(known)) return known;
    if (window.crypto && typeof window.crypto.randomUUID === "function") {
      return window.crypto.randomUUID();
    }
    const bytes = window.crypto.getRandomValues(new Uint8Array(16));
    bytes[6] = (bytes[6] & 0x0f) | 0x40;
    bytes[8] = (bytes[8] & 0x3f) | 0x80;
    const hex = Array.from(bytes, (b) => b.toString(16).padStart(2, "0")).join("");
    return `${hex.slice(0, 8)}-${hex.slice(8, 12)}-${hex.slice(12, 16)}-${hex.slice(16, 20)}-${hex.slice(20)}`;
  }

  function remember(choices) {
    const id = consentId();
    try {
      window.localStorage.setItem(
        config.storageKey,
        JSON.stringify({ id, version: config.version, at: Date.now(), choices })
      );
      window.localStorage.removeItem(LEGACY_KEY);
    } catch {
      // Private mode: the banner simply shows again next time.
    }
    if (!logUrl) return;
    // keepalive: withdrawing consent reloads the page right after this.
    window
      .fetch(logUrl, {
        method: "POST",
        keepalive: true,
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ id, version: config.version, choices }),
      })
      .catch(() => {});
  }

  let loaded = false;
  function loadTagManager() {
    if (loaded) return;
    loaded = true;
    window.dataLayer.push({ "gtm.start": Date.now(), event: "gtm.js" });
    const tag = document.createElement("script");
    tag.async = true;
    tag.src = `https://www.googletagmanager.com/gtm.js?id=${encodeURIComponent(gtmId)}`;
    document.head.appendChild(tag);
  }

  // Cookies can sit on this host or on any parent domain (GA uses the top one).
  function cookieDomains() {
    const labels = window.location.hostname.split(".");
    const domains = [""];
    for (let i = 0; i < labels.length - 1; i += 1) {
      const domain = labels.slice(i).join(".");
      domains.push(domain, `.${domain}`);
    }
    return domains;
  }

  function matches(name, pattern) {
    return pattern.endsWith("*") ? name.startsWith(pattern.slice(0, -1)) : name === pattern;
  }

  function deleteCookies(patterns) {
    if (!patterns.length) return;
    document.cookie.split(";").forEach((pair) => {
      const name = pair.split("=")[0].trim();
      if (!name || !patterns.some((pattern) => matches(name, pattern))) return;
      cookieDomains().forEach((domain) => {
        const scope = domain ? `; domain=${domain}` : "";
        document.cookie = `${name}=; Max-Age=0; path=/${scope}`;
      });
    });
  }

  function apply(choices) {
    const update = {};
    categories.forEach((key) => {
      config.categories[key].consent.forEach((type) => {
        update[type] = choices[key] ? "granted" : "denied";
      });
      if (!choices[key]) deleteCookies(config.categories[key].cookies);
    });
    gtag("consent", "update", update);
    if (categories.some((key) => choices[key])) loadTagManager();
    // For GTM triggers on tools that don't read Consent Mode themselves.
    window.dataLayer.push({ event: "cookie_consent_update", cookie_consent: { ...choices } });
  }

  function all(value) {
    return Object.fromEntries(categories.map((key) => [key, value]));
  }

  let current = read();
  if (current) apply(current);

  document.addEventListener("DOMContentLoaded", () => {
    const banner = document.querySelector("[data-cookie-banner]");
    const dialog = document.querySelector("[data-cookie-dialog]");
    if (!banner || !dialog) return;
    const switches = dialog.querySelectorAll("[data-consent-category]");
    const overlay = document.querySelector("[data-cookie-overlay]");
    const lockable = banner.hasAttribute("data-cookie-lock") && overlay;

    // Until a decision: dim the page, stop scrolling, and make everything
    // but the banner and the settings dialog unreachable (clicks, Tab, screen
    // readers). Accepting and rejecting unlock it alike.
    function lock(on) {
      if (!lockable) return;
      overlay.hidden = !on;
      document.documentElement.classList.toggle("cookie-locked", on);
      Array.from(document.body.children).forEach((element) => {
        if ([banner, dialog, overlay].includes(element) || element.tagName === "SCRIPT") {
          return;
        }
        element.inert = on;
      });
    }

    function showBanner() {
      banner.hidden = false;
      lock(true);
      banner.focus({ preventScroll: true });
    }

    function decide(choices) {
      // Tags already running keep going until the page reloads, so taking
      // consent back reloads it - with the tools off from the first moment.
      const withdrawn =
        loaded && current && categories.some((key) => current[key] && !choices[key]);
      current = choices;
      remember(choices);
      banner.hidden = true;
      lock(false);
      if (dialog.open) dialog.close();
      apply(choices);
      if (withdrawn) window.location.reload();
    }

    function openSettings() {
      const choices = current || all(false);
      switches.forEach((input) => {
        input.checked = Boolean(choices[input.dataset.consentCategory]);
      });
      banner.hidden = true;
      if (typeof Modal !== "undefined") Modal.open(dialog);
      else dialog.showModal();
    }

    // Closed without a choice: the question still stands.
    dialog.addEventListener("close", () => {
      if (!current) showBanner();
    });

    document.addEventListener("click", (event) => {
      const target = event.target.closest(
        "[data-consent-accept], [data-consent-reject], [data-consent-save], " +
          "[data-consent-customize], [data-cookie-settings]"
      );
      if (!target) return;
      if (target.matches("[data-consent-accept]")) decide(all(true));
      else if (target.matches("[data-consent-reject]")) decide(all(false));
      else if (target.matches("[data-consent-save]")) {
        const choices = all(false);
        switches.forEach((input) => {
          choices[input.dataset.consentCategory] = input.checked;
        });
        decide(choices);
      } else openSettings();
    });

    if (!current) showBanner();
  });
})();
