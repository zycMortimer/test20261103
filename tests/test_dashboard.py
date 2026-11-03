import unittest

from app import app
from dashboard import calculate_bmi, classify_bmi


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


if __name__ == "__main__":
    unittest.main()
