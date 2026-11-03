import tempfile
import unittest
from unittest.mock import patch

from app import app, calculate_bmi, classify_bmi, gauge_angle, gauge_segments, gauge_state


class GaugeTests(unittest.TestCase):
    def setUp(self):
        self.client = app.test_client()

    def test_renders_semicircle_in_calculator_page(self):
        page = self.client.get("/").get_data(as_text=True)
        self.assertIn('id="bmi-gauge"', page)
        self.assertIn('id="gauge-needle"', page)
        self.assertIn(">--<", page)
        self.assertEqual(page.count('class="gauge-seg seg-'), 6)
        self.assertIn(".bmi-gauge", self.client.get("/static/style.css").get_data(as_text=True))

    def test_segments_cover_six_categories(self):
        self.assertEqual(
            [s["label"] for s in gauge_segments()],
            ["過輕", "正常", "過重", "輕度肥胖", "中度肥胖", "重度肥胖"],
        )

    def test_boundary_values(self):
        for bmi, label in ((18.5, "正常"), (24, "過重"), (27, "輕度肥胖"), (30, "中度肥胖"), (35, "重度肥胖")):
            with self.subTest(bmi=bmi):
                state = gauge_state(bmi)
                self.assertEqual(state["label"], label)
                self.assertEqual(state["angle"], gauge_angle(bmi))
        self.assertEqual(gauge_angle(10), 0)
        self.assertEqual(gauge_angle(40), 180)
        self.assertEqual(gauge_angle(99), 180)

    def test_invalid_resets_gauge(self):
        state = gauge_state(None)
        self.assertEqual((state["bmi"], state["angle"]), ("--", 0))

    def test_saved_record_shows_matching_bmi_on_gauge(self):
        import tempfile
        with tempfile.TemporaryDirectory() as directory:
            app.config["DATA_DIR"] = directory
            try:
                response = self.client.post(
                    "/", data={"name": "A", "height": "170", "weight": "65", "action": "calculate"},
                    follow_redirects=True,
                )
            finally:
                app.config["DATA_DIR"] = str(__import__("pathlib").Path(app.root_path) / "data")
        page = response.get_data(as_text=True)
        self.assertIn('id="gauge-bmi" class="gauge-bmi">22.5<', page)
        self.assertIn("rotate(75.0deg)", page)
        self.assertIn("gauge-normal", page)

    def test_out_of_range_saved_measurements_reset_gauge(self):
        with tempfile.TemporaryDirectory() as directory, patch.dict(app.config, DATA_DIR=directory):
            response = self.client.post(
                "/", data={"name": "A", "height": "20", "weight": "60", "action": "calculate"},
                follow_redirects=True,
            )
        page = response.get_data(as_text=True)
        self.assertIn('class="gauge-bmi">--<', page)
        self.assertRegex(page, r'<p id="gauge-error"[^>]*>請輸入有效的身高')
        self.assertIn('class="result-number bmi-obese">1500.0</span>', page)

    def test_live_gauge_initializes_after_registering_listeners(self):
        response = self.client.post("/", data={"name": "", "height": "170", "weight": "65"})
        page = response.get_data(as_text=True)
        script_response = self.client.get("/static/gauge.js")
        script = script_response.get_data(as_text=True)
        script_response.close()
        self.assertIn('value="170"', page)
        self.assertIn('value="65"', page)
        self.assertLess(
            script.index('weight.addEventListener("input", update);'),
            script.index("  update();"),
        )

    def test_live_rounding_matches_server_at_category_boundaries(self):
        for height, weight, bmi in (
            ("200", "95.8", 23.9),
            ("100", "18.45", 18.4),
            ("100", "18.55", 18.6),
            ("100", "23.95", 23.9),
            ("100", "24.05", 24.1),
        ):
            with self.subTest(height=height, weight=weight):
                self.assertEqual(calculate_bmi(height, weight), bmi)
        script_response = self.client.get("/static/gauge.js")
        script = script_response.get_data(as_text=True)
        script_response.close()
        self.assertIn("function roundBmi(value)", script)
        self.assertIn("const bmi = roundBmi(w / (meters * meters));", script)


class ClassifyBmiTests(unittest.TestCase):
    def test_boundaries(self):
        cases = (
            (18.4, "過輕"), (18.5, "正常"), (23.9, "正常"), (24, "過重"),
            (26.9, "過重"), (27, "輕度肥胖"), (29.9, "輕度肥胖"), (30, "中度肥胖"),
            (34.9, "中度肥胖"), (35, "重度肥胖"), (60, "重度肥胖"),
        )
        for bmi, label in cases:
            with self.subTest(bmi=bmi):
                self.assertEqual(classify_bmi(bmi)["label"], label)

    def test_distinct_tones(self):
        tones = {classify_bmi(b)["tone"] for b in (17, 20, 25, 28, 32, 40)}
        self.assertEqual(len(tones), 6)


class CalculateBmiTests(unittest.TestCase):
    def test_rounding(self):
        self.assertEqual(calculate_bmi("170", "65"), 22.5)
        self.assertEqual(calculate_bmi(160, 60), 23.4)

    def test_invalid_inputs(self):
        for height, weight in (
            ("", "60"), ("170", ""), ("0", "60"), ("170", "0"), ("-170", "60"),
            ("170", "-5"), ("abc", "60"), ("nan", "60"), ("20", "60"), ("400", "60"),
            ("170", "5"), ("170", "1000"), (None, None),
        ):
            with self.subTest(height=height, weight=weight):
                self.assertIsNone(calculate_bmi(height, weight))


class DashboardPageTests(unittest.TestCase):
    def setUp(self):
        self.client = app.test_client()

    def test_empty(self):
        response = self.client.get("/dashboard")
        self.assertEqual(response.status_code, 200)
        self.assertIn('id="dash-bmi" class="dash-bmi">--', response.get_data(as_text=True))

    def test_valid(self):
        response = self.client.get("/dashboard?height=170&weight=65")
        page = response.get_data(as_text=True)
        self.assertEqual(response.status_code, 200)
        self.assertIn(">22.5<", page)
        self.assertIn("正常", page)

    def test_invalid_shows_no_bmi_and_prompt(self):
        response = self.client.get("/dashboard?height=0&weight=60")
        page = response.get_data(as_text=True)
        self.assertEqual(response.status_code, 400)
        self.assertIn(">--<", page)
        self.assertIn("請輸入有效的身高", page)

    def test_home_links_to_dashboard(self):
        page = self.client.get("/").get_data(as_text=True)
        self.assertIn('href="/dashboard"', page)

    def test_dashboard_renders_visible_with_assets_and_fallbacks(self):
        page = self.client.get("/dashboard?height=170&weight=65").get_data(as_text=True)
        self.assertIn('id="dash-gauge"', page)
        self.assertIn(">22.5<", page)
        self.assertIn("<noscript>", page)
        self.assertIn('addEventListener("error"', page)
        self.assertIn('href="/"', page)
        css = self.client.get("/static/style.css")
        self.assertEqual(css.status_code, 200)
        css.close()
        self.assertIn(".dash-gauge", self.client.get("/static/style.css").get_data(as_text=True))


if __name__ == "__main__":
    unittest.main()
