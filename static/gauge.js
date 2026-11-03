(function () {
  const $ = (id) => document.getElementById(id);
  const height = $("height"), weight = $("weight"), gauge = $("bmi-gauge");
  if (!height || !weight || !gauge) return;
  const MIN = Number(gauge.dataset.min), MAX = Number(gauge.dataset.max);
  const H = gauge.dataset.height.split(",").map(Number);
  const W = gauge.dataset.weight.split(",").map(Number);
  const CATEGORIES = JSON.parse(gauge.dataset.categories);

  function update() {
    const h = parseFloat(height.value), w = parseFloat(weight.value);
    const blank = height.value === "" && weight.value === "";
    const ok = h >= H[0] && h <= H[1] && w >= W[0] && w <= W[1];
    gauge.className = "bmi-gauge";
    if (!ok) {
      $("gauge-bmi").textContent = "--";
      $("gauge-label").textContent = "";
      $("gauge-needle").style.transform = "rotate(0deg)";
      $("gauge-error").hidden = blank;
      return;
    }
    const bmi = Math.round((w / ((h / 100) ** 2)) * 10 + Number.EPSILON) / 10;
    const c = CATEGORIES.find((x) => x.upper !== null && bmi < x.upper) || CATEGORIES[CATEGORIES.length - 1];
    const clamped = Math.min(Math.max(bmi, MIN), MAX);
    gauge.classList.add("gauge-" + c.tone);
    $("gauge-bmi").textContent = bmi.toFixed(1);
    $("gauge-label").textContent = c.label;
    $("gauge-needle").style.transform = "rotate(" + ((clamped - MIN) / (MAX - MIN) * 180).toFixed(1) + "deg)";
    $("gauge-error").hidden = true;
  }
  height.addEventListener("input", update);
  weight.addEventListener("input", update);
})();
