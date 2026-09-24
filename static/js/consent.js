// Analytics cookies only with the visitor's consent (Google Consent Mode v2).
// Google Tag Manager is not even downloaded until the visitor accepts; the
// choice is remembered in this browser and can be changed at any time from
// the "Ustawienia cookies" link in the footer.
(function () {
  const script = document.currentScript;
  const gtmId = script.dataset.gtmId;
  const policyUrl = script.dataset.policyUrl;
  const KEY = "monituj-analytics-consent";

  window.dataLayer = window.dataLayer || [];
  function gtag() {
    window.dataLayer.push(arguments);
  }
  // Everything is off until the visitor says otherwise; Monituj runs no ads,
  // so advertising storage stays off for good.
  gtag("consent", "default", {
    analytics_storage: "denied",
    ad_storage: "denied",
    ad_user_data: "denied",
    ad_personalization: "denied",
    wait_for_update: 500,
  });

  function read() {
    try {
      return window.localStorage.getItem(KEY);
    } catch {
      return null;
    }
  }

  function remember(value) {
    try {
      window.localStorage.setItem(KEY, value);
    } catch {
      // Private mode: the banner simply shows again next time.
    }
  }

  let loaded = false;
  function loadTagManager() {
    if (loaded || !gtmId) return;
    loaded = true;
    window.dataLayer.push({ "gtm.start": Date.now(), event: "gtm.js" });
    const tag = document.createElement("script");
    tag.async = true;
    tag.src = `https://www.googletagmanager.com/gtm.js?id=${encodeURIComponent(gtmId)}`;
    document.head.appendChild(tag);
  }

  function deleteAnalyticsCookies() {
    const host = window.location.hostname.replace(/^www\./, "");
    document.cookie.split(";").forEach((pair) => {
      const name = pair.split("=")[0].trim();
      if (!/^_ga/.test(name) && name !== "_gid") return;
      [host, `.${host}`, ""].forEach((domain) => {
        const scope = domain ? `; domain=${domain}` : "";
        document.cookie = `${name}=; Max-Age=0; path=/${scope}`;
      });
    });
  }

  function apply(choice) {
    if (choice === "granted") {
      gtag("consent", "update", { analytics_storage: "granted" });
      loadTagManager();
    } else {
      gtag("consent", "update", { analytics_storage: "denied" });
      deleteAnalyticsCookies();
    }
  }

  const text = (value) => (typeof noOrphans === "function" ? noOrphans(value) : value);

  function showBanner() {
    if (document.querySelector(".cookie-banner")) return;
    const banner = document.createElement("div");
    banner.className = "cookie-banner";
    banner.setAttribute("role", "dialog");
    banner.setAttribute("aria-label", "Zgoda na cookies analityczne");

    const copy = document.createElement("p");
    copy.className = "cookie-banner__text";
    const title = document.createElement("strong");
    title.textContent = "Cookies analityczne. ";
    copy.appendChild(title);
    copy.appendChild(
      document.createTextNode(
        text(
          "Za Twoją zgodą użyjemy Google Analytics (przez Google Tag Manager), " +
            "żeby wiedzieć, które strony Monituj są przydatne. Bez zgody nie " +
            "zapiszemy żadnych cookies analitycznych. "
        )
      )
    );
    const link = document.createElement("a");
    link.href = policyUrl;
    link.title = "Polityka cookies";
    link.textContent = "Polityka cookies";
    copy.appendChild(link);

    const actions = document.createElement("div");
    actions.className = "cookie-banner__actions";
    [
      ["granted", "Akceptuję", "btn-primary"],
      ["denied", "Odrzucam", "btn-dark"],
    ].forEach(([value, label, style]) => {
      const button = document.createElement("button");
      button.type = "button";
      button.className = `btn ${style} btn-sm`;
      button.textContent = label;
      button.addEventListener("click", () => {
        remember(value);
        apply(value);
        banner.remove();
      });
      actions.appendChild(button);
    });

    banner.append(copy, actions);
    document.body.appendChild(banner);
  }

  const choice = read();
  if (choice === "granted" || choice === "denied") {
    apply(choice);
  }

  document.addEventListener("DOMContentLoaded", () => {
    if (read() === null) showBanner();
    document.querySelectorAll("[data-cookie-settings]").forEach((button) => {
      button.addEventListener("click", showBanner);
    });
  });
})();
