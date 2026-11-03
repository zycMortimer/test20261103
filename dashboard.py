import json
import math

HEIGHT_RANGE_CM = (50, 250)
WEIGHT_RANGE_KG = (10, 500)

# (exclusive upper bound, label, tone, icon); evaluated in order on the rounded BMI.
BMI_CATEGORIES = (
    (18.5, "過輕", "underweight", "▽"),
    (24, "正常", "normal", "✓"),
    (27, "過重", "overweight", "△"),
    (30, "輕度肥胖", "obese-1", "▲"),
    (35, "中度肥胖", "obese-2", "⚠"),
    (float("inf"), "重度肥胖", "obese-3", "⛔"),
)


def _number(value):
    try:
        number = float(value)
    except (TypeError, ValueError, OverflowError):
        return None
    return number if math.isfinite(number) else None


def calculate_bmi(height_cm, weight_kg):
    """Return BMI rounded to one decimal, or None when inputs are invalid."""
    height = _number(height_cm)
    weight = _number(weight_kg)
    if height is None or weight is None:
        return None
    if not HEIGHT_RANGE_CM[0] <= height <= HEIGHT_RANGE_CM[1]:
        return None
    if not WEIGHT_RANGE_KG[0] <= weight <= WEIGHT_RANGE_KG[1]:
        return None
    return round(weight / (height / 100) ** 2, 1)


def classify_bmi(bmi):
    for upper, label, tone, icon in BMI_CATEGORIES:
        if bmi < upper:
            return {"label": label, "tone": tone, "icon": icon}
    raise ValueError("BMI must be a number")


def category_table():
    rows, lower = [], None
    for upper, label, tone, icon in BMI_CATEGORIES:
        if lower is None:
            text = f"< {upper:g}"
        elif upper == float("inf"):
            text = f"≥ {lower:g}"
        else:
            text = f"{lower:g} – {upper:g}"
        rows.append({"label": label, "tone": tone, "icon": icon, "upper": upper, "range": text})
        lower = upper
    return rows


def categories_json(rows):
    # JSON has no Infinity; the page script treats a null bound as the last category.
    safe = [{**row, "upper": None if row["upper"] == float("inf") else row["upper"]} for row in rows]
    return json.dumps(safe, ensure_ascii=False).replace("<", "\\u003c")
