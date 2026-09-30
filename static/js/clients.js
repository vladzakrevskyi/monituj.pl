(function () {
  const tableBody = document.getElementById("clients-table-body");
  if (!tableBody) return;

  tableBody.addEventListener("click", async (event) => {
    const button = event.target.closest(".delete-client");
    if (!button) return;

    // A client with requests goes together with all of them - how an owner
    // answers the client's request to erase their data (RODO art. 17).
    const requests = Number(button.dataset.requestCount || 0);
    const confirmed = await Modal.confirm(
      requests
        ? {
            title: "Usunąć klienta z całą historią?",
            message:
              `Razem z klientem „${button.dataset.clientName}” usuniemy ` +
              `wszystkie wysłane mu prośby (${requests}), przesłane pliki i ` +
              "historię, a z próśb cyklicznych zniknie jego adres. Linki u " +
              "klienta przestaną działać. Tego nie można cofnąć.",
            confirmLabel: "Usuń klienta i prośby",
            danger: true,
          }
        : {
            title: "Usunąć klienta?",
            message: `Klient „${button.dataset.clientName}” zostanie trwale usunięty.`,
            confirmLabel: "Usuń klienta",
            danger: true,
          }
    );
    if (!confirmed) return;

    const query = requests ? "?with_history=1" : "";
    const { ok, data } = await ButtonLoader.run(button, () =>
      apiFetch(`/api/clients/${button.dataset.clientId}/${query}`, { method: "DELETE" })
    );
    if (!ok) {
      showToast(data && data.error ? data.error.message : "Wystąpił błąd.", "error");
      return;
    }
    button.closest("tr").remove();
    if (!tableBody.querySelector("tr[data-client-id]")) {
      const row = document.createElement("tr");
      row.className = "table-empty";
      const cell = document.createElement("td");
      cell.colSpan = 8;
      cell.textContent = "Brak klientów.";
      row.appendChild(cell);
      tableBody.appendChild(row);
    }
    showToast(
      requests ? "Klient i wszystkie jego prośby zostały usunięte." : "Klient został usunięty.",
      "success"
    );
  });
})();
