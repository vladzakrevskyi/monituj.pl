// On a phone the footer's link groups fold under their headings, so the
// footer is a few lines instead of a whole screen. Without this script all
// links simply stay visible.
(function () {
  var footer = document.querySelector(".site-footer");
  if (!footer) return;
  footer.classList.add("site-footer--foldable");
  footer.querySelectorAll(".site-footer__col").forEach(function (col, index) {
    var heading = col.querySelector("h4");
    if (!heading) return;
    var button = document.createElement("button");
    button.type = "button";
    button.className = "site-footer__toggle";
    button.textContent = heading.textContent;
    button.setAttribute("aria-expanded", "false");
    var links = document.createElement("div");
    links.className = "site-footer__links";
    links.id = "footer-links-" + index;
    button.setAttribute("aria-controls", links.id);
    while (heading.nextSibling) links.appendChild(heading.nextSibling);
    heading.textContent = "";
    heading.appendChild(button);
    col.appendChild(links);
    button.addEventListener("click", function () {
      var open = col.classList.toggle("is-open");
      button.setAttribute("aria-expanded", open ? "true" : "false");
    });
  });
})();
