// Cennik → Kalkulator: how much time reminding clients by hand takes, and
// the plan that would do it instead. Counted in the browser - nothing is
// sent anywhere.
(function () {
  const box = document.querySelector("[data-calculator]");
  const data = document.getElementById("calculator-plans");
  if (!box || !data) return;
  const plans = JSON.parse(data.textContent);
  const number = (value, digits) =>
    value.toLocaleString("pl-PL", { maximumFractionDigits: digits });
  const input = (name) => Number(box.querySelector(`[data-input="${name}"]`).value);
  const out = (name) => box.querySelector(`[data-out="${name}"]`);
  const show = (name, text) => {
    box.querySelector(`[data-show="${name}"]`).textContent = text;
  };

  function update() {
    const clients = input("clients");
    const times = input("times");
    const minutes = input("minutes");
    const rate = input("rate");
    show("clients", number(clients, 0));
    show("times", number(times, 0));
    show("minutes", number(minutes, 0));
    show("rate", `${number(rate, 0)} zł`);

    const hours = (clients * times * minutes) / 60;
    // Half-hours under ten, whole hours above: "2,5 h", "38 h".
    const rounded = hours < 10 ? Math.round(hours * 2) / 2 : Math.round(hours);
    out("hours").textContent = `${number(rounded, 1)} h`;
    out("money").textContent = `${number(Math.round((hours * rate) / 10) * 10, 0)} zł`;

    // A request to every client at once fits in the plan.
    const plan = plans.find((p) => p.limit >= clients) || plans[plans.length - 1];
    if (plan.net === 0) {
      out("plan").textContent = `Wystarczy bezpłatny plan ${plan.name}`;
      out("payback").textContent = "";
      return;
    }
    out("plan").textContent = `Plan ${plan.name}: ${number(plan.net, 0)} zł netto miesięcznie`;
    const payback = Math.max(1, Math.round((plan.net / rate) * 60));
    out("payback").textContent =
      payback < hours * 60
        ? `Zwraca się, gdy zaoszczędzi Ci ${number(payback, 0)} min w miesiącu.`
        : "";
  }

  box.addEventListener("input", update);
  update();
})();
