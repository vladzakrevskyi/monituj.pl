(function () {
  const itemsList = document.getElementById("items-list");
  if (!itemsList) return;
  const token = itemsList.dataset.token;

  // Done for the recipient - "Nie dotyczy" included.
  const DELIVERED = new Set(["dostarczony", "zaakceptowany", "nie_dotyczy"]);
  const MISSING = new Set(["brak", "odrzucony"]);
  const REQUEST_STATUS_LABELS = {
    brak_dokumentow: "Nic nie przesłano",
    w_trakcie: "W trakcie",
    kompletny: "Kompletny",
    po_terminie: "Po terminie",
  };
  const DOWNLOAD_ICON =
    '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M12 4v11M7 10l5 5 5-5"/><path d="M5 20h14"/></svg>';

  function updateOverallProgress() {
    const items = itemsList.querySelectorAll(".request-item");
    let delivered = 0;
    items.forEach((el) => {
      if (DELIVERED.has(el.dataset.status)) delivered += 1;
    });
    const progressEl = document.getElementById("request-progress");
    if (progressEl) progressEl.textContent = `${delivered} z ${items.length}`;
    const done = document.querySelector("[data-done]");
    if (done) done.hidden = delivered !== items.length;
    // The request's own status follows - as RequestStatus on the server.
    const statusEl = document.getElementById("request-status-label");
    if (statusEl && statusEl.dataset.code !== "zamkniety") {
      let code;
      if (delivered === items.length) code = "kompletny";
      else if ("overdue" in statusEl.dataset) code = "po_terminie";
      else code = delivered ? "w_trakcie" : "brak_dokumentow";
      statusEl.dataset.code = code;
      statusEl.textContent = REQUEST_STATUS_LABELS[code] || statusEl.textContent;
      statusEl.className = `badge ${statusBadgeClass(code)}`;
    }
  }

  function applyItemStatus(itemId, status) {
    const el = itemsList.querySelector(`.request-item[data-item-id="${itemId}"]`);
    if (!el) return;
    el.dataset.status = status.code;
    // "Nie mam tego dokumentu" only while it's missing.
    const notApplicable = el.querySelector("[data-na]");
    if (notApplicable) notApplicable.hidden = !MISSING.has(status.code);
    const label = el.querySelector(".item-status-label");
    if (label) {
      label.textContent = status.label;
      label.className = `badge item-status-label ${statusBadgeClass(status.code)}`;
    }
    updateOverallProgress();
  }

  function addUploadedFileRow(itemId, doc) {
    const container = itemsList.querySelector(
      `.request-item[data-item-id="${itemId}"] .uploaded-files`
    );
    if (!container) return;
    const row = document.createElement("p");
    row.className = "uploaded-file";
    row.dataset.documentId = doc.id;
    const info = document.createElement("span");
    info.className = "uploaded-file__info";
    const link = document.createElement("a");
    link.className = "uploaded-file__link";
    link.href = doc.download_url;
    link.download = "";
    link.title = `Pobierz plik ${doc.original_filename}`;
    link.innerHTML = DOWNLOAD_ICON;
    link.append(doc.original_filename);
    const date = document.createElement("span");
    date.className = "uploaded-file__date";
    date.textContent = `Dodany: ${doc.uploaded_at_display}`;
    info.append(link, " ", date);
    row.appendChild(info);
    const deleteButton = document.createElement("button");
    deleteButton.type = "button";
    deleteButton.className = "btn btn-danger btn-sm delete-document";
    deleteButton.dataset.documentId = doc.id;
    deleteButton.textContent = "Usuń";
    row.appendChild(deleteButton);
    container.appendChild(row);
  }

  // Sends the form to the item's zone address; resolves when it's done,
  // well or not, so several files can go one after another.
  function send(zone, url, formData, successMessage) {
    const progress = zone.querySelector(".upload-progress");
    const errorBox = zone.querySelector(".upload-error");
    const trigger = zone.querySelector(".upload-trigger");
    ButtonLoader.start(trigger);
    errorBox.textContent = "";
    zone.classList.remove("has-error");
    progress.hidden = false;
    progress.value = 0;

    return new Promise((resolve) => {
      const xhr = new XMLHttpRequest();
      xhr.open("POST", url);
      xhr.setRequestHeader("X-CSRFToken", getCookie("csrftoken"));
      xhr.upload.addEventListener("progress", (event) => {
        if (event.lengthComputable) {
          progress.value = Math.round((event.loaded / event.total) * 100);
        }
      });
      const fail = (message) => {
        errorBox.textContent = message;
        zone.classList.add("has-error");
      };
      xhr.onload = () => {
        ButtonLoader.stop(trigger);
        progress.hidden = true;
        let payload = null;
        try {
          payload = JSON.parse(xhr.responseText);
        } catch {
          payload = null;
        }
        if (xhr.status >= 200 && xhr.status < 300 && payload && payload.success) {
          applyItemStatus(zone.dataset.itemId, payload.data.item.status);
          addUploadedFileRow(zone.dataset.itemId, payload.data.document);
          showToast(successMessage, "success");
          resolve(true);
        } else {
          fail(payload && payload.error ? payload.error.message : "Wystąpił błąd.");
          resolve(false);
        }
      };
      xhr.onerror = () => {
        ButtonLoader.stop(trigger);
        progress.hidden = true;
        fail("Wystąpił błąd połączenia.");
        resolve(false);
      };
      xhr.send(formData);
    });
  }

  async function uploadFiles(zone, files) {
    const trigger = zone.querySelector(".upload-trigger");
    if (trigger.classList.contains("is-loading")) return;
    for (const file of files) {
      const formData = new FormData();
      formData.append("file", await fitLimit(file));
      const sent = await send(
        zone,
        `/api/public/${token}/items/${zone.dataset.itemId}/upload/`,
        formData,
        "Dokument został przesłany."
      );
      if (!sent) return;
    }
  }

  // A page photo, smaller: a phone's 12-megapixel JPG becomes a few hundred
  // kilobytes. What the browser can't draw (HEIC on a computer) goes as it is.
  const PAGE_LONG_SIDE = 2200;
  async function shrink(file, longSide = PAGE_LONG_SIDE, quality = 0.85, name = "strona.jpg") {
    try {
      const bitmap = await createImageBitmap(file, { imageOrientation: "from-image" });
      const scale = Math.min(1, longSide / Math.max(bitmap.width, bitmap.height));
      const canvas = document.createElement("canvas");
      canvas.width = Math.round(bitmap.width * scale);
      canvas.height = Math.round(bitmap.height * scale);
      canvas.getContext("2d").drawImage(bitmap, 0, 0, canvas.width, canvas.height);
      bitmap.close();
      const blob = await new Promise((done) => canvas.toBlob(done, "image/jpeg", quality));
      return blob ? new File([blob], name, { type: "image/jpeg" }) : file;
    } catch {
      return file;
    }
  }

  // A photo over the upload limit (a 200-megapixel camera) is sent smaller
  // instead of refused - still sharp, 4000 px. Smaller files go untouched.
  const UPLOAD_LIMIT = 20 * 1024 * 1024;
  const PHOTO = /\.(jpe?g|png|heic|heif)$/i;
  function fitLimit(file) {
    if (file.size <= UPLOAD_LIMIT || !PHOTO.test(file.name)) return file;
    return shrink(file, 4000, 0.9, file.name.replace(/\.[^.]+$/, "") + ".jpg");
  }

  // "Zrób zdjęcia stron": pages collected one by one, sent as one PDF.
  function setUpPages(zone) {
    const open = zone.querySelector("[data-pages-open]");
    if (!open) return;
    const input = zone.querySelector("[data-pages-input]");
    const tray = zone.querySelector("[data-pages]");
    const list = zone.querySelector("[data-pages-list]");
    const sendButton = zone.querySelector("[data-pages-send]");
    let pages = [];

    function render() {
      list.querySelectorAll("img").forEach((img) => URL.revokeObjectURL(img.src));
      list.replaceChildren();
      pages.forEach((file, index) => {
        const item = document.createElement("li");
        item.className = "pages__page";
        const img = document.createElement("img");
        img.alt = `Strona ${index + 1}`;
        img.src = URL.createObjectURL(file);
        img.addEventListener("error", () => img.remove());
        const number = document.createElement("span");
        number.className = "pages__number";
        number.textContent = String(index + 1);
        const remove = document.createElement("button");
        remove.type = "button";
        remove.className = "pages__remove";
        remove.setAttribute("aria-label", `Usuń stronę ${index + 1}`);
        remove.textContent = "×";
        remove.addEventListener("click", () => {
          pages.splice(index, 1);
          render();
        });
        item.append(img, number, remove);
        list.append(item);
      });
      tray.hidden = pages.length === 0;
      open.hidden = pages.length > 0;
      zone.querySelector("[data-pages-count]").textContent = `(${pages.length})`;
      sendButton.textContent = `Wyślij jako PDF (${pages.length} str.)`;
    }

    open.addEventListener("click", () => input.click());
    zone.querySelector("[data-pages-add]").addEventListener("click", () => input.click());
    input.addEventListener("change", () => {
      pages = pages.concat([...input.files]);
      input.value = "";
      render();
    });
    zone.querySelector("[data-pages-cancel]").addEventListener("click", () => {
      pages = [];
      render();
    });
    sendButton.addEventListener("click", async () => {
      if (!pages.length || sendButton.classList.contains("is-loading")) return;
      ButtonLoader.start(sendButton);
      const formData = new FormData();
      for (const page of await Promise.all(pages.map(shrink))) {
        formData.append("pages", page, page.name);
      }
      const count = pages.length;
      const sent = await send(
        zone,
        `/api/public/${token}/items/${zone.dataset.itemId}/pages/`,
        formData,
        `Dokument (${count} str.) został przesłany.`
      );
      ButtonLoader.stop(sendButton);
      if (sent) {
        pages = [];
        render();
      }
    });
  }

  itemsList.querySelectorAll(".upload-zone").forEach((zone) => {
    const input = zone.querySelector(".upload-input");
    const trigger = zone.querySelector(".upload-trigger");

    trigger.addEventListener("click", () => input.click());
    input.addEventListener("change", () => {
      const files = [...input.files];
      input.value = "";
      if (files.length > 0) uploadFiles(zone, files);
    });

    zone.addEventListener("dragover", (event) => {
      event.preventDefault();
      zone.classList.add("drag-over");
    });
    zone.addEventListener("dragleave", () => zone.classList.remove("drag-over"));
    zone.addEventListener("drop", (event) => {
      event.preventDefault();
      zone.classList.remove("drag-over");
      if (event.dataTransfer.files.length > 0) {
        uploadFiles(zone, [...event.dataTransfer.files]);
      }
    });
    setUpPages(zone);
  });

  itemsList.addEventListener("click", async (event) => {
    const button = event.target.closest(".delete-document");
    if (!button) return;
    const confirmed = await Modal.confirm({
      title: "Usunąć dokument?",
      message: "Przesłany plik zostanie usunięty. Możesz później przesłać go ponownie.",
      confirmLabel: "Usuń plik",
      danger: true,
    });
    if (!confirmed) return;

    const documentId = button.dataset.documentId;
    const { ok, data } = await ButtonLoader.run(button, () =>
      apiFetch(`/api/public/documents/${documentId}/`, { method: "DELETE" })
    );
    if (ok) {
      button.closest(".uploaded-file").remove();
      applyItemStatus(data.data.item.id, data.data.item.status);
      showToast("Dokument usunięty.", "success");
    } else {
      showToast(data && data.error ? data.error.message : "Wystąpił błąd.", "error");
    }
  });

  // "Nie mam tego dokumentu": a reason, then the page shows the new state.
  async function sendNotApplicable(itemEl, method, reason) {
    const errorBox = itemEl.querySelector("[data-na-error]");
    const { ok, data } = await apiFetch(
      `/api/public/${token}/items/${itemEl.dataset.itemId}/not-applicable/`,
      method === "POST"
        ? { method, body: JSON.stringify({ reason }) }
        : { method }
    );
    if (ok) {
      window.location.reload();
      return;
    }
    const message = data && data.error ? data.error.message : "Wystąpił błąd.";
    if (errorBox) errorBox.textContent = message;
    else showToast(message, "error");
  }

  // A question: the answer in words (apps/requests/questions.py).
  itemsList.addEventListener("submit", async (event) => {
    const form = event.target.closest("[data-answer-form]");
    if (!form) return;
    event.preventDefault();
    const itemEl = form.closest(".request-item");
    const errorBox = form.querySelector("[data-answer-error]");
    const answer = form.querySelector("textarea").value.trim();
    if (!answer) {
      errorBox.textContent = "Napisz odpowiedź.";
      return;
    }
    const button = form.querySelector('button[type="submit"]');
    const { ok, data } = await ButtonLoader.run(button, () =>
      apiFetch(`/api/public/${token}/items/${itemEl.dataset.itemId}/answer/`, {
        method: "POST",
        body: JSON.stringify({ answer }),
      })
    );
    if (ok) {
      window.location.reload();
      return;
    }
    errorBox.textContent = data && data.error ? data.error.message : "Wystąpił błąd.";
  });
  itemsList.addEventListener("click", (event) => {
    const edit = event.target.closest("[data-answer-edit]");
    if (!edit) return;
    const form = edit.closest(".request-item").querySelector("[data-answer-form]");
    form.hidden = false;
    edit.hidden = true;
    form.querySelector("textarea").focus();
  });

  // An item without a file: "Zrobione" and its undo.
  async function sendConfirm(itemEl, method, button) {
    const errorBox = itemEl.querySelector("[data-confirm-error]");
    const { ok, data } = await ButtonLoader.run(button, () =>
      apiFetch(`/api/public/${token}/items/${itemEl.dataset.itemId}/confirm/`, { method })
    );
    if (ok) {
      window.location.reload();
      return;
    }
    const message = data && data.error ? data.error.message : "Wystąpił błąd.";
    if (errorBox) errorBox.textContent = message;
    else showToast(message, "error");
  }

  itemsList.addEventListener("click", (event) => {
    const itemEl = event.target.closest(".request-item");
    if (!itemEl) return;
    const done = event.target.closest("[data-confirm-done]");
    if (done) {
      sendConfirm(itemEl, "POST", done);
      return;
    }
    const undone = event.target.closest("[data-confirm-undo]");
    if (undone) {
      sendConfirm(itemEl, "DELETE", undone);
      return;
    }
    const open = event.target.closest("[data-na-open]");
    if (open) {
      const picker = itemEl.querySelector("[data-na-picker]");
      picker.hidden = !picker.hidden;
      open.setAttribute("aria-expanded", String(!picker.hidden));
      return;
    }
    const choice = event.target.closest("[data-na-reason]");
    if (choice) {
      ButtonLoader.start(choice);
      sendNotApplicable(itemEl, "POST", choice.dataset.naReason).finally(() =>
        ButtonLoader.stop(choice)
      );
      return;
    }
    if (event.target.closest("[data-na-undo]")) {
      sendNotApplicable(itemEl, "DELETE");
    }
  });

  itemsList.addEventListener("submit", (event) => {
    const form = event.target.closest("[data-na-other]");
    if (!form) return;
    event.preventDefault();
    const itemEl = form.closest(".request-item");
    const reason = form.querySelector("input").value.trim();
    if (!reason) {
      itemEl.querySelector("[data-na-error]").textContent = "Napisz krótko, dlaczego.";
      return;
    }
    sendNotApplicable(itemEl, "POST", reason);
  });
  // "Dodaj inny dokument": a file that isn't on the list.
  const extra = document.querySelector("[data-extra]");
  if (extra) {
    const openExtra = extra.querySelector("[data-extra-open]");
    const form = extra.querySelector("[data-extra-form]");
    openExtra.addEventListener("click", () => {
      form.hidden = !form.hidden;
      openExtra.setAttribute("aria-expanded", String(!form.hidden));
      if (!form.hidden) form.querySelector("input").focus();
    });
    form.addEventListener("submit", async (event) => {
      event.preventDefault();
      const errorBox = form.querySelector("[data-extra-error]");
      if (!form.querySelector('input[type="file"]').files.length) {
        errorBox.textContent = "Wybierz plik.";
        return;
      }
      const button = form.querySelector('button[type="submit"]');
      const response = await ButtonLoader.run(button, () =>
        fetch(`/api/public/${token}/extra/`, {
          method: "POST",
          headers: { "X-CSRFToken": getCookie("csrftoken") },
          body: new FormData(form),
        })
      );
      let payload = null;
      try {
        payload = await response.json();
      } catch {
        payload = null;
      }
      if (response.ok && payload && payload.success) {
        window.location.reload();
        return;
      }
      errorBox.textContent =
        payload && payload.error ? payload.error.message : "Wystąpił błąd.";
    });
  }
})();
