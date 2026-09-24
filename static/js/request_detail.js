(function () {
  const tableBody = document.getElementById("items-table-body");
  if (!tableBody) return;
  const requestId = document.querySelector("table[data-request-id]").dataset.requestId;

  function errorMessage(data) {
    return data && data.error ? data.error.message : "Wystąpił błąd.";
  }

  function applyRowUpdate(row, item, rejectionReason) {
    row.dataset.status = item.status.code;
    const label = row.querySelector(".item-status-label");
    label.textContent = item.status.label;
    label.className = `badge item-status-label ${statusBadgeClass(item.status.code)}`;
    const note = row.querySelector(".item-rejection");
    note.textContent = rejectionReason || "";
    note.hidden = !rejectionReason;
    row.querySelector(".cell-actions").innerHTML = "";
  }

  tableBody.addEventListener("click", async (event) => {
    const acceptButton = event.target.closest(".accept-item");
    const rejectButton = event.target.closest(".reject-item");
    const button = acceptButton || rejectButton;
    if (!button) return;

    const itemId = button.dataset.itemId;
    const itemName = button.dataset.itemName;
    const row = tableBody.querySelector(`tr[data-item-id="${itemId}"]`);

    if (acceptButton) {
      const confirmed = await Modal.confirm({
        title: "Zaakceptować dokument?",
        message: `Dokument „${itemName}” zostanie oznaczony jako zaakceptowany.`,
        confirmLabel: "Zaakceptuj",
      });
      if (!confirmed) return;
      const { ok, data } = await ButtonLoader.run(button, () =>
        apiFetch(`/api/requests/${requestId}/items/${itemId}/accept/`, {
          method: "POST",
        })
      );
      if (ok) {
        applyRowUpdate(row, data.data.item);
        showToast("Dokument zaakceptowany.", "success");
      } else {
        showToast(errorMessage(data), "error");
      }
      return;
    }

    const reason = await Modal.prompt({
      title: "Odrzucić dokument?",
      message: `Klient zobaczy powód odrzucenia dokumentu „${itemName}” i będzie mógł przesłać go ponownie.`,
      confirmLabel: "Odrzuć dokument",
      danger: true,
      field: {
        label: "Powód odrzucenia",
        placeholder: "Np. skan jest nieczytelny",
        requiredMessage: "Podaj powód odrzucenia.",
      },
    });
    if (!reason) return;
    const { ok, data } = await ButtonLoader.run(button, () =>
      apiFetch(`/api/requests/${requestId}/items/${itemId}/reject/`, {
        method: "POST",
        body: JSON.stringify({ reason }),
      })
    );
    if (ok) {
      applyRowUpdate(row, data.data.item, reason);
      showToast("Dokument odrzucony.", "success");
    } else {
      showToast(errorMessage(data), "error");
    }
  });

  const remindButton = document.getElementById("send-reminder");
  if (remindButton) {
    remindButton.addEventListener("click", async () => {
      const confirmed = await Modal.confirm({
        title: "Wysłać przypomnienie?",
        message: "Klient dostanie teraz email z przypomnieniem o brakujących dokumentach.",
        confirmLabel: "Wyślij przypomnienie",
      });
      if (!confirmed) return;
      const { ok, data } = await ButtonLoader.run(remindButton, () =>
        apiFetch(`/api/requests/${remindButton.dataset.requestId}/remind/`, {
          method: "POST",
        })
      );
      if (!ok) {
        showToast(errorMessage(data), "error");
        return;
      }
      showToast("Przypomnienie wysłane.", "success");
      const history = document.getElementById("reminders-history");
      const emptyItem = history.querySelector("li");
      if (emptyItem && emptyItem.textContent === "Brak wysłanych przypomnień.") {
        emptyItem.remove();
      }
      const item = document.createElement("li");
      const time = document.createElement("span");
      time.className = "history-time";
      time.textContent = new Date().toLocaleString("pl-PL");
      const label = document.createElement("span");
      label.textContent = "Ręczne";
      item.append(time, label);
      history.prepend(item);
    });
  }

  const sendLinkForm = document.getElementById("send-link-form");
  if (sendLinkForm) {
    const emailInput = document.getElementById("send-link-email");
    sendLinkForm.addEventListener("submit", async (event) => {
      event.preventDefault();
      FormErrors.clearAll(sendLinkForm);
      const submitButton = sendLinkForm.querySelector('button[type="submit"]');
      if (submitButton.classList.contains("is-loading")) return;
      const { ok, data } = await ButtonLoader.run(submitButton, () =>
        apiFetch(`/api/requests/${sendLinkForm.dataset.requestId}/send-link/`, {
          method: "POST",
          body: JSON.stringify({ email: emailInput.value }),
        })
      );
      if (ok) {
        showToast(`Link wysłany na ${data.data.email}.`, "success");
        return;
      }
      const emailErrors = ["EMAIL_REQUIRED", "INVALID_EMAIL"];
      if (data && data.error && emailErrors.includes(data.error.code)) {
        FormErrors.set(emailInput, [errorMessage(data)]);
        emailInput.focus();
      } else {
        showToast(errorMessage(data), "error");
      }
    });
  }
})();

// Closing a request is a real change for the recipient - ask first.
document.querySelectorAll("form[data-confirm-close]").forEach((form) => {
  form.addEventListener("submit", async (event) => {
    if (form.dataset.confirmed) return;
    event.preventDefault();
    const confirmed = await Modal.confirm({
      title: "Zamknąć prośbę?",
      message:
        "Odbiorca nie będzie mógł przesyłać plików, a przypomnienia przestaną być wysyłane. Przesłane pliki zostaną w panelu. Prośbę możesz później otworzyć ponownie.",
      confirmLabel: "Zamknij prośbę",
      danger: true,
    });
    if (!confirmed) return;
    form.dataset.confirmed = "1";
    form.requestSubmit();
  });
});
