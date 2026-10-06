// The promo film (pages/_promo_video.html): the vertical cut on a phone held
// upright, chapter buttons that jump to a step, and the hero button that
// plays it in a dialog. Without JavaScript the wide film plays as it is and
// the hero button scrolls to it.
(function () {
  const TALL = window.matchMedia("(max-width: 640px) and (orientation: portrait)");

  function setUp(figure) {
    const video = figure.querySelector("video");
    // Chosen once per page view - switching mid-film would start it over.
    const tall = TALL.matches && video.dataset.srcTall;
    if (tall) {
      video.src = video.dataset.srcTall;
      video.poster = video.dataset.posterTall;
      figure.classList.add("promo-video--tall");
    }
    // A big play button over the poster - the browser's own is small.
    const play = figure.querySelector("[data-video-play]");
    if (play) {
      play.hidden = false;
      play.addEventListener("click", () => video.play());
      video.addEventListener("play", () => { play.hidden = true; });
    }
    const chapters = Array.from(figure.querySelectorAll("[data-chapter]"));
    const startOf = (button) => parseFloat(tall ? button.dataset.tall : button.dataset.wide);

    chapters.forEach((button) => {
      button.addEventListener("click", () => {
        const at = startOf(button);
        if (video.readyState >= 1) {
          video.currentTime = at;
        } else {
          video.addEventListener("loadedmetadata", () => { video.currentTime = at; }, { once: true });
        }
        video.play();
      });
    });
    if (chapters.length) {
      video.addEventListener("timeupdate", () => {
        let current = null;
        chapters.forEach((button) => {
          if (startOf(button) <= video.currentTime + 0.25) current = button;
        });
        chapters.forEach((button) => button.toggleAttribute("aria-current", button === current));
      });
    }
    return video;
  }

  const films = new Map();
  document.querySelectorAll("[data-promo-video]").forEach((figure) => {
    films.set(figure, setUp(figure));
  });

  document.querySelectorAll("[data-video-open]").forEach((trigger) => {
    const dialog = document.getElementById(trigger.getAttribute("aria-controls"));
    if (!dialog || typeof dialog.showModal !== "function") return;
    const video = films.get(dialog.querySelector("[data-promo-video]"));
    trigger.addEventListener("click", (event) => {
      event.preventDefault();
      dialog.showModal();
      // Focus on the film (space pauses it), not a ring on the close button.
      video.focus({ preventScroll: true });
      video.play();
    });
    dialog.addEventListener("click", (event) => {
      if (event.target === dialog || event.target.closest("[data-video-close]")) dialog.close();
    });
    dialog.addEventListener("close", () => video.pause());
  });
})();
