(function () {
  const itemsList = document.getElementById("items-list");
  if (!itemsList) return;
  const token = itemsList.dataset.token;

  const DELIVERED = new Set(["dostarczony", "zaakceptowany"]);
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
  }

  function applyItemStatus(itemId, status) {
    const el = itemsList.querySelector(`.request-item[data-item-id="${itemId}"]`);
    if (!el) return;
    el.dataset.status = status.code;
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
})();
