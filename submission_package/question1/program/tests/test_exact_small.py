from __future__ import annotations

import sys
import unittest
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from uav_q1.exact_milp import solve_fixed_n_exact


class ExactMilpSmallTest(unittest.TestCase):
    def test_two_points_one_uav(self) -> None:
        df = pd.DataFrame({
            "Point_ID": [1, 2],
            "X_Coordinate": [1.0, 0.0],
            "Y_Coordinate": [0.0, 1.0],
            "Inspection_Level": ["III", "III"],
        })
        result = solve_fixed_n_exact(df, 1, time_limit_s=20)
        self.assertEqual(result.status, "OPTIMAL")
        self.assertIsNotNone(result.routes)
        self.assertEqual(sorted(result.routes[0]), [0, 1])
        self.assertLess(result.objective_h, 9.0)

    def test_same_point_copies_are_not_adjacent(self) -> None:
        # I 级点需要三次，另一个 III 级点可作为离开后的中间访问点。
        df = pd.DataFrame({
            "Point_ID": [1, 2],
            "X_Coordinate": [1.0, 2.0],
            "Y_Coordinate": [0.0, 0.0],
            "Inspection_Level": ["I", "III"],
        })
        result = solve_fixed_n_exact(df, 2, time_limit_s=20)
        self.assertIn(result.status, {"OPTIMAL", "FEASIBLE"})
        self.assertIsNotNone(result.routes)
        for route in result.routes:
            self.assertTrue(all(route[i] != route[i + 1] for i in range(len(route) - 1)))
        visits = [node for route in result.routes for node in route]
        self.assertEqual(visits.count(0), 3)
        self.assertEqual(visits.count(1), 1)


if __name__ == "__main__":
    unittest.main()
