import json
import math
import os
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path
from uuid import UUID, uuid4

from flask import Flask, redirect, render_template, request, url_for

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


GAUGE_MIN, GAUGE_MAX = 10, 40
GAUGE_CENTER, GAUGE_RADIUS = 100, 80


def _gauge_point(bmi):
    angle = math.pi * (1 - (min(max(bmi, GAUGE_MIN), GAUGE_MAX) - GAUGE_MIN) / (GAUGE_MAX - GAUGE_MIN))
    return (
        round(GAUGE_CENTER + GAUGE_RADIUS * math.cos(angle), 2),
        round(GAUGE_CENTER - GAUGE_RADIUS * math.sin(angle), 2),
    )


def gauge_segments():
    """SVG arc paths for each BMI category on a 10–40 semicircular scale."""
    segments, lower = [], GAUGE_MIN
    for upper, label, tone, _icon in BMI_CATEGORIES:
        end = min(upper, GAUGE_MAX)
        (x1, y1), (x2, y2) = _gauge_point(lower), _gauge_point(end)
        segments.append({
            "tone": tone, "label": label,
            "path": f"M {x1} {y1} A {GAUGE_RADIUS} {GAUGE_RADIUS} 0 0 1 {x2} {y2}",
        })
        lower = end
    return segments


def gauge_angle(bmi):
    """Needle rotation in degrees: 0 points at the left end, 180 at the right end."""
    if bmi is None:
        return 0
    clamped = min(max(bmi, GAUGE_MIN), GAUGE_MAX)
    return round((clamped - GAUGE_MIN) / (GAUGE_MAX - GAUGE_MIN) * 180, 1)


def gauge_state(bmi):
    if bmi is None:
        return {"bmi": "--", "label": "", "tone": "", "angle": 0}
    return {"bmi": f"{bmi:.1f}", "angle": gauge_angle(bmi), **classify_bmi(bmi)}


def initial_gauge_state(result, height, weight):
    if calculate_bmi(height, weight) is None:
        return {**gauge_state(None), "error": bool(height or weight)}
    return {**gauge_state(float(result["bmi"]) if result else None), "error": False}


app = Flask(__name__)
app.config["DATA_DIR"] = os.environ.get("BMI_DATA_DIR", str(Path(app.root_path) / "data"))
DISPLAY_TIMEZONE = timezone(timedelta(hours=8))

HEALTH_SOURCES = (
    {
        "title": "國民健康署：成人 BMI 與健康體重",
        "url": "https://www.hpa.gov.tw/Pages/Detail.aspx?nodeid=542&pid=9737",
    },
    {
        "title": "WHO：健康飲食（英文）",
        "url": "https://www.who.int/news-room/fact-sheets/detail/healthy-diet",
    },
    {
        "title": "WHO：身體活動（英文）",
        "url": "https://www.who.int/news-room/fact-sheets/detail/physical-activity",
    },
)


def bmi_guidance(bmi):
    if bmi < 18.5:
        return {
            "label": "體重過輕",
            "tone": "low",
            "advice": "留意是否攝取足夠且均衡的營養，規律進食並搭配適度肌力活動；若體重持續下降，建議諮詢醫師或營養師。",
            "tips": (
                {"title": "飲食方向", "text": "規律進食，搭配全穀、蔬果及豆類、蛋、魚等蛋白質來源，留意營養是否足夠，不以含糖飲料取代正餐。"},
                {"title": "健康追蹤", "text": "留意體重變化；若沒有刻意減重卻持續變瘦，或有食慾不振，請向醫師或營養師尋求評估。"},
            ),
        }
    if bmi < 24:
        return {
            "label": "健康體位",
            "tone": "healthy",
            "advice": "維持均衡飲食與規律運動，並持續留意睡眠及生活習慣，幫助保持健康體位。",
            "tips": (
                {"title": "飲食方向", "text": "維持多樣、均衡的飲食，多選蔬果、全穀與豆類，少吃高糖、高鹽及油炸食品。"},
                {"title": "健康追蹤", "text": "持續留意體重與腰圍的變化；BMI 在正常範圍不代表所有健康指標都正常，仍應依個人狀況接受健康評估。"},
            ),
        }
    if bmi < 27:
        return {
            "label": "體重過重",
            "tone": "high",
            "advice": "可從減少含糖飲料、增加蔬菜與日常活動量開始，循序建立適合自己的健康習慣。",
            "tips": (
                {"title": "飲食方向", "text": "以水取代含糖飲料，多選蔬果、全穀與豆類，減少高糖、高鹽及油炸食品，循序調整飲食。"},
                {"title": "健康追蹤", "text": "留意體重與腰圍，若需要體重管理協助，可與醫師或營養師討論符合個人需求的計畫。"},
            ),
        }
    return {
        "label": "肥胖",
        "tone": "high",
        "advice": "建議與醫師或營養師討論適合自己的飲食及運動計畫，並留意血壓、血糖等健康指標。",
        "tips": (
            {"title": "飲食方向", "text": "從均衡飲食與減少含糖飲料開始，優先選擇少加工的食物，並由醫師或營養師協助規劃個人化體重管理。"},
            {"title": "健康追蹤", "text": "建議諮詢醫療專業人員，評估腰圍、血壓、血糖及血脂等指標；不要只用 BMI 判斷健康狀況。"},
        ),
    }


def parse_positive_number(value):
    try:
        number = float(value)
    except (TypeError, ValueError, OverflowError):
        return None
    return number if math.isfinite(number) and number > 0 else None


def valid_name(name):
    return isinstance(name, str) and 1 <= len(name) <= 80 and not any(
        ord(character) < 32 or ord(character) == 127 for character in name
    )


def read_record(path):
    with path.open(encoding="utf-8") as file:
        record = json.load(file)
    if not isinstance(record, dict):
        raise ValueError("BMI record must be an object")
    record_id = record.get("id")
    if not isinstance(record_id, str) or str(UUID(record_id)) != path.stem:
        raise ValueError("Invalid BMI record ID")
    if not valid_name(record.get("name")):
        raise ValueError("Invalid BMI record name")
    for field in ("height_cm", "weight_kg"):
        value = record.get(field)
        if type(value) not in (int, float) or parse_positive_number(value) is None:
            raise ValueError(f"Invalid BMI record {field}")
    bmi = record.get("bmi")
    if type(bmi) not in (int, float) or (bmi != 0 and parse_positive_number(bmi) is None):
        raise ValueError("Invalid BMI record bmi")
    if not isinstance(record.get("recorded_at"), str):
        raise ValueError("Invalid BMI record timestamp")
    recorded_at = datetime.fromisoformat(record["recorded_at"])
    if recorded_at.tzinfo is None:
        raise ValueError("BMI record timestamp must include a timezone")
    if record.get("category") != bmi_guidance(record["bmi"])["label"]:
        raise ValueError("Invalid BMI record category")
    return record


def load_records():
    directory = Path(app.config["DATA_DIR"])
    try:
        paths = list(directory.iterdir())
    except FileNotFoundError:
        return []
    records = [read_record(path) for path in paths if path.suffix == ".json"]
    return sorted(
        records,
        key=lambda record: (datetime.fromisoformat(record["recorded_at"]), record["id"]),
    )


def load_history(name):
    return [record for record in load_records() if record["name"] == name]


@app.context_processor
def gauge_context():
    rows = category_table()
    return {
        "gauge_segments": gauge_segments(),
        "gauge_categories_json": categories_json(rows),
        "gauge_state": initial_gauge_state,
        "gauge_min": GAUGE_MIN,
        "gauge_max": GAUGE_MAX,
        "height_range": HEIGHT_RANGE_CM,
        "weight_range": WEIGHT_RANGE_KG,
        "categories": rows,
    }


@app.get("/users")
def users():
    latest_records = {}
    storage_error = None
    status = 200
    try:
        for record in load_records():
            latest_records[record["name"]] = record
    except (OSError, ValueError) as error:
        app.logger.error("Unable to load BMI users: %s", error)
        storage_error = "無法讀取用戶名單，請聯絡管理員檢查 data 資料夾的權限與 JSON 格式。"
        status = 503
    return render_template(
        "users.html",
        users=[latest_records[name] for name in sorted(latest_records)],
        storage_error=storage_error,
    ), status


@app.get("/dashboard")
def dashboard():
    height_input = request.args.get("height", "").strip()
    weight_input = request.args.get("weight", "").strip()
    result = error = None
    if height_input or weight_input:
        bmi = calculate_bmi(height_input, weight_input)
        if bmi is None:
            error = (
                f"請輸入有效的身高（{HEIGHT_RANGE_CM[0]}–{HEIGHT_RANGE_CM[1]} 公分）"
                f"與體重（{WEIGHT_RANGE_KG[0]}–{WEIGHT_RANGE_KG[1]} 公斤）。"
            )
        else:
            result = {"bmi": f"{bmi:.1f}", **classify_bmi(bmi)}
    rows = category_table()
    return render_template(
        "dashboard.html", height_input=height_input, weight_input=weight_input,
        result=result, error=error, categories=rows, categories_json=categories_json(rows),
        height_range=HEIGHT_RANGE_CM, weight_range=WEIGHT_RANGE_KG,
    ), (400 if error else 200)


def save_record(name, height, weight, bmi):
    directory = Path(app.config["DATA_DIR"])
    directory.mkdir(parents=True, exist_ok=True)
    record = {
        "id": str(uuid4()),
        "name": name,
        "recorded_at": datetime.now(timezone.utc).isoformat(),
        "height_cm": height,
        "weight_kg": weight,
        "bmi": bmi,
        "category": bmi_guidance(bmi)["label"],
    }
    # Publish complete, immutable records so simultaneous requests cannot lose updates.
    temporary_path = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w", encoding="utf-8", dir=directory, suffix=".tmp", delete=False
        ) as file:
            temporary_path = Path(file.name)
            json.dump(record, file, ensure_ascii=False, indent=2, allow_nan=False)
            file.write("\n")
            file.flush()
            os.fsync(file.fileno())
        os.replace(temporary_path, directory / f'{record["id"]}.json')
    finally:
        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)
    return record


def history_chart(records):
    width = max(640, len(records) * 115 + 100)
    left, top, plot_height = 65, 25, 230
    plot_width = width - left - 65
    maximum = max(30, *(record["bmi"] for record in records))
    padded_maximum = maximum * 1.05
    if maximum > 30 and math.isfinite(padded_maximum):
        maximum = padded_maximum

    def y_position(bmi):
        return round(top + (1 - bmi / maximum) * plot_height, 2)

    points = []
    for index, record in enumerate(records):
        timestamp = datetime.fromisoformat(record["recorded_at"]).astimezone(DISPLAY_TIMEZONE)
        points.append({
            **record,
            "x": round(left + plot_width * index / max(1, len(records) - 1), 2),
            "y": y_position(record["bmi"]),
            "date": timestamp.strftime("%Y/%m/%d"),
            "time": timestamp.strftime("%H:%M:%S"),
            "display_bmi": f'{record["bmi"]:.1f}',
        })
    return {
        "width": width,
        "left": left,
        "right": width - 65,
        "top": top,
        "bottom": top + plot_height,
        "points": points,
        "line": " ".join(f'{point["x"]},{point["y"]}' for point in points),
        "ticks": [
            {"y": y_position(maximum * (index / 4)), "label": f"{maximum * (index / 4):.3g}"}
            for index in range(5)
        ],
        "thresholds": [
            {"y": y_position(bmi), "label": str(bmi)} for bmi in (18.5, 24, 27)
        ],
        "healthy_top": y_position(24),
        "healthy_height": round(y_position(18.5) - y_position(24), 2),
    }


@app.route("/", methods=["GET", "POST"])
def index():
    name_input = ""
    height_input = ""
    weight_input = ""
    errors = {}
    result = None
    history = []
    storage_error = None
    history_notice = None
    status = 200

    if request.method == "POST":
        name_input = request.form.get("name", "").strip()
        height_input = request.form.get("height", "").strip()
        weight_input = request.form.get("weight", "").strip()
        if not valid_name(name_input):
            errors["name"] = "請輸入 1 至 80 個字的姓名，且不可包含控制字元。"
        if request.form.get("action") == "history":
            if not errors:
                try:
                    history = load_history(name_input)
                    if history:
                        return redirect(url_for("index", record=history[-1]["id"]), code=303)
                    history_notice = "這個姓名尚無 BMI 紀錄，請先輸入身高與體重計算。"
                except (OSError, ValueError) as error:
                    app.logger.error("Unable to load BMI history: %s", error)
                    storage_error = "無法讀取歷史紀錄，請聯絡管理員檢查 data 資料夾的權限與 JSON 格式。"
                    status = 503
            return render_template(
                "index.html", name_input=name_input, height_input=height_input,
                weight_input=weight_input, errors=errors, result=None,
                health_sources=HEALTH_SOURCES, chart=None, storage_error=storage_error,
                history_notice=history_notice,
            ), status
        height = parse_positive_number(height_input)
        weight = parse_positive_number(weight_input)

        if height is None:
            errors["height"] = "請輸入大於 0 的有效身高（公分）。"
        if weight is None:
            errors["weight"] = "請輸入大於 0 的有效體重（公斤）。"

        if not errors:
            height_meters = height / 100
            height_squared = height_meters * height_meters
            if not math.isfinite(height_squared) or height_squared == 0:
                errors["height"] = "無法使用這組數值計算 BMI，請檢查身高與體重。"
            else:
                bmi = weight / height_squared
                if not math.isfinite(bmi) or bmi == 0:
                    errors["weight"] = "無法使用這組數值計算 BMI，請檢查身高與體重。"
                else:
                    displayed_bmi = round(bmi, 1)
                    result = {"bmi": f"{displayed_bmi:.1f}", **bmi_guidance(displayed_bmi)}
                    try:
                        load_history(name_input)
                        record = save_record(name_input, height, weight, displayed_bmi)
                        return redirect(url_for("index", record=record["id"]), code=303)
                    except (OSError, ValueError) as error:
                        app.logger.error("Unable to save BMI record: %s", error)
                        storage_error = "BMI 已計算，但本次紀錄未儲存。請聯絡管理員檢查 data 資料夾的權限與 JSON 格式。"
                        status = 503
    elif request.args.get("record"):
        try:
            record_id = str(UUID(request.args["record"]))
            record = read_record(Path(app.config["DATA_DIR"]) / f"{record_id}.json")
            name_input = record["name"]
            height_input = str(record["height_cm"])
            weight_input = str(record["weight_kg"])
            result = {"bmi": f'{record["bmi"]:.1f}', **bmi_guidance(record["bmi"])}
            history = load_history(name_input)
        except FileNotFoundError:
            storage_error = "找不到這筆 BMI 紀錄。"
            status = 404
        except (OSError, ValueError) as error:
            app.logger.error("Unable to load BMI record: %s", error)
            storage_error = "無法讀取 BMI 紀錄，請確認紀錄連結有效，或聯絡管理員檢查 JSON 格式。"
            status = 503

    return render_template(
        "index.html",
        name_input=name_input,
        height_input=height_input,
        weight_input=weight_input,
        errors=errors,
        result=result,
        health_sources=HEALTH_SOURCES,
        chart=history_chart(history) if history else None,
        storage_error=storage_error,
        history_notice=history_notice,
    ), status


if __name__ == "__main__":
    app.run(debug=True)
