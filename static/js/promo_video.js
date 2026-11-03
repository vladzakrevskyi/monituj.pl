// The promo film (pages/_promo_video.html): the vertical cut on a phone held
// upright, chapter buttons that jump to a step, ?t=29 on /film/, and the hero
// button that plays it in a dialog. Without JavaScript the wide film plays as
// it is and the hero button scrolls to it.
(function () {
  const TALL = window.matchMedia("(max-width: 640px) and (orientation: portrait)");

  function setUp(figure) {
    const video = figure.querySelector("video");
    // Chosen once per page view - switching mid-film would start it over.
    const tall = TALL.matches && video.dataset.srcTall;
    if (tall) {
      video.poster = video.dataset.posterTall;
      figure.classList.add("promo-video--tall");
    }
    // The vertical file goes in on play, not on load: a search robot reads the
    // page as a phone and must find the same file as in the page's markup.
    const useCut = () => {
      if (tall && video.getAttribute("src") !== tall) video.src = tall;
    };
    const start = () => {
      useCut();
      video.play();
    };
    const seek = (at) => {
      if (video.readyState >= 1) {
        video.currentTime = at;
      } else {
        video.addEventListener("loadedmetadata", () => { video.currentTime = at; }, { once: true });
      }
    };
    // The browser's own play button, where it is not under ours.
    video.addEventListener("play", () => {
      if (tall && video.getAttribute("src") !== tall) start();
    });
    // A big play button over the poster - the browser's own is small.
    const play = figure.querySelector("[data-video-play]");
    if (play) {
      play.hidden = false;
      play.addEventListener("click", start);
      video.addEventListener("play", () => { play.hidden = true; });
    }
    const chapters = Array.from(figure.querySelectorAll("[data-chapter]"));
    const startOf = (button) => parseFloat(tall ? button.dataset.tall : button.dataset.wide);

    chapters.forEach((button) => {
      button.addEventListener("click", () => {
        useCut();
        seek(startOf(button));
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
    // /film/: the chapter links under the film, and ?t=29 from a search result
    // (seconds of the wide cut; a chapter's start maps onto the tall one).
    if (figure.hasAttribute("data-deep-link")) {
      document.querySelectorAll("[data-film-chapter]").forEach((link) => {
        link.addEventListener("click", (event) => {
          event.preventDefault();
          chapters[Number(link.dataset.filmChapter) - 1].click();
          figure.scrollIntoView({ block: "center" });
        });
      });
      const second = parseInt(new URLSearchParams(window.location.search).get("t"), 10);
      if (second >= 0) {
        const chapter = chapters.find((button) => Math.floor(parseFloat(button.dataset.wide)) === second);
        useCut();
        video.preload = "metadata";
        seek(chapter ? startOf(chapter) : second);
      }
    }
    return { video, start };
  }

  const films = new Map();
  document.querySelectorAll("[data-promo-video]").forEach((figure) => {
    films.set(figure, setUp(figure));
  });

  document.querySelectorAll("[data-video-open]").forEach((trigger) => {
    const dialog = document.getElementById(trigger.getAttribute("aria-controls"));
    if (!dialog || typeof dialog.showModal !== "function") return;
    const { video, start } = films.get(dialog.querySelector("[data-promo-video]"));
    trigger.addEventListener("click", (event) => {
      event.preventDefault();
      dialog.showModal();
      // Focus on the film (space pauses it), not a ring on the close button.
      video.focus({ preventScroll: true });
      start();
    });
    dialog.addEventListener("click", (event) => {
      if (event.target === dialog || event.target.closest("[data-video-close]")) dialog.close();
    });
    dialog.addEventListener("close", () => video.pause());
  });
})();
