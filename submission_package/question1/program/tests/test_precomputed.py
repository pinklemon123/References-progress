import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from uav_q1.validation import validate_all


class TestPrecomputedSolution(unittest.TestCase):
    def test_all_constraints(self):
        config = json.loads((ROOT / "config.json").read_text(encoding="utf-8"))
        result = json.loads((ROOT / "data" / "precomputed_solution.json").read_text(encoding="utf-8"))
        validate_all(ROOT / "input" / "附件1.xlsx", result, config)


if __name__ == "__main__":
    unittest.main()
