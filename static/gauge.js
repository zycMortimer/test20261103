(function () {
  const $ = (id) => document.getElementById(id);
  const height = $("height"), weight = $("weight"), gauge = $("bmi-gauge");
  if (!height || !weight || !gauge) return;
  const MIN = Number(gauge.dataset.min), MAX = Number(gauge.dataset.max);
  const H = gauge.dataset.height.split(",").map(Number);
  const W = gauge.dataset.weight.split(",").map(Number);
  const CATEGORIES = JSON.parse(gauge.dataset.categories);
  const roundBuffer = new ArrayBuffer(8), roundView = new DataView(roundBuffer);

  function roundBmi(value) {
    roundView.setFloat64(0, value);
    const bits = roundView.getBigUint64(0);
    const exponent = Number((bits >> 52n) & 0x7ffn);
    const fraction = bits & ((1n << 52n) - 1n);
    const significand = exponent === 0 ? fraction : (1n << 52n) | fraction;
    const binaryExponent = (exponent === 0 ? 1 - 1023 : exponent - 1023) - 52;
    let numerator = significand * 10n, denominator = 1n;
    if (binaryExponent >= 0) numerator <<= BigInt(binaryExponent);
    else denominator <<= BigInt(-binaryExponent);
    let rounded = numerator / denominator;
    const remainder = numerator % denominator;
    if (remainder * 2n > denominator || (remainder * 2n === denominator && rounded % 2n === 1n)) rounded++;
    return Number(rounded) / 10;
  }

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
    const meters = h / 100;
    const bmi = roundBmi(w / (meters * meters));
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
  update();
})();
