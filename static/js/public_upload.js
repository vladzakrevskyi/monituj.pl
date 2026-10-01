(function () {
  const itemsList = document.getElementById("items-list");
  if (!itemsList) return;
  const token = itemsList.dataset.token;

  // Done for the recipient - "Nie dotyczy" included.
  const DELIVERED = new Set(["dostarczony", "zaakceptowany", "nie_dotyczy"]);
  const MISSING = new Set(["brak", "odrzucony"]);
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

  function uploadFile(itemId, file, zone) {
    const progress = zone.querySelector(".upload-progress");
    const errorBox = zone.querySelector(".upload-error");
    const trigger = zone.querySelector(".upload-trigger");
    if (trigger.classList.contains("is-loading")) return;
    ButtonLoader.start(trigger);
    errorBox.textContent = "";
    zone.classList.remove("has-error");
    progress.hidden = false;
    progress.value = 0;

    const xhr = new XMLHttpRequest();
    xhr.open("POST", `/api/public/${token}/items/${itemId}/upload/`);
    xhr.setRequestHeader("X-CSRFToken", getCookie("csrftoken"));

    xhr.upload.addEventListener("progress", (event) => {
      if (event.lengthComputable) {
        progress.value = Math.round((event.loaded / event.total) * 100);
      }
    });

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
        applyItemStatus(itemId, payload.data.item.status);
        addUploadedFileRow(itemId, payload.data.document);
        showToast("Dokument został przesłany.", "success");
      } else {
        errorBox.textContent =
          payload && payload.error ? payload.error.message : "Wystąpił błąd.";
        zone.classList.add("has-error");
      }
    };

    xhr.onerror = () => {
      ButtonLoader.stop(trigger);
      progress.hidden = true;
      errorBox.textContent = "Wystąpił błąd połączenia.";
      zone.classList.add("has-error");
    };

    const formData = new FormData();
    formData.append("file", file);
    xhr.send(formData);
  }

  itemsList.querySelectorAll(".upload-zone").forEach((zone) => {
    const itemId = zone.dataset.itemId;
    const input = zone.querySelector(".upload-input");
    const trigger = zone.querySelector(".upload-trigger");

    trigger.addEventListener("click", () => input.click());
    input.addEventListener("change", () => {
      if (input.files.length > 0) {
        uploadFile(itemId, input.files[0], zone);
        input.value = "";
      }
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
        uploadFile(itemId, event.dataTransfer.files[0], zone);
      }
    });
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

  itemsList.addEventListener("click", (event) => {
    const itemEl = event.target.closest(".request-item");
    if (!itemEl) return;
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
      itemEl.querySelector("[data-na-error]").textContent =
        "Napisz krótko, dlaczego nie masz tego dokumentu.";
      return;
    }
    sendNotApplicable(itemEl, "POST", reason);
  });
})();
