import unittest
from collections import Counter

from src.competitive_intelligence import (
    PRICE_BANDS,
    WEIGHT_SCENARIOS,
    family_name,
    price_band,
    share_overlap,
)


class MetricTests(unittest.TestCase):
    def test_overlap_is_one_hundred_for_identical_profiles(self):
        profile = Counter({"降噪": 3, "连接": 1})
        self.assertAlmostEqual(share_overlap(profile, profile, 4, 4), 100.0)

    def test_overlap_is_zero_for_disjoint_profiles(self):
        self.assertEqual(share_overlap(Counter({"连接": 2}), Counter({"音质": 5}), 2, 5), 0.0)

    def test_overlap_is_symmetric(self):
        left, right = Counter({"A": 3, "B": 1}), Counter({"A": 1, "C": 3})
        self.assertAlmostEqual(share_overlap(left, right, 4, 4), share_overlap(right, left, 4, 4))

    def test_price_band_edges(self):
        self.assertEqual(price_band(99.99), "<100")
        self.assertEqual(price_band(100), "100-199")
        self.assertEqual(price_band(200), "200-399")
        self.assertEqual(price_band(400), "400+")
        self.assertEqual(len(PRICE_BANDS), 4)

    def test_product_family_removes_brand_prefix(self):
        product = {"brand": "声屿", "product_name": "声屿轻羽Buds"}
        self.assertEqual(family_name(product), "轻羽Buds")

    def test_weight_scenarios_all_sum_to_one_hundred(self):
        for weights in WEIGHT_SCENARIOS.values():
            self.assertEqual(sum(weights.values()), 100)


if __name__ == "__main__":
    unittest.main()
