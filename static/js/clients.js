(function () {
  const tableBody = document.getElementById("clients-table-body");
  if (!tableBody) return;

  tableBody.addEventListener("click", async (event) => {
    const button = event.target.closest(".delete-client");
    if (!button) return;

    const confirmed = await Modal.confirm({
      title: "Usunąć klienta?",
      message: `Klient „${button.dataset.clientName}” zostanie trwale usunięty.`,
      confirmLabel: "Usuń klienta",
      danger: true,
    });
    if (!confirmed) return;

    const { ok, data } = await ButtonLoader.run(button, () =>
      apiFetch(`/api/clients/${button.dataset.clientId}/`, { method: "DELETE" })
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
      cell.colSpan = 7;
      cell.textContent = "Brak klientów.";
      row.appendChild(cell);
      tableBody.appendChild(row);
    }
    showToast("Klient został usunięty.", "success");
  });
})();
