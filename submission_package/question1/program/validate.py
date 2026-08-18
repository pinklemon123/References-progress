"""单独校验问题一 solution.json。"""
import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "src"))
from uav_q1.validation import validate_all

parser = argparse.ArgumentParser()
parser.add_argument("--input", type=Path, default=ROOT / "input" / "附件1.xlsx")
parser.add_argument("--solution", type=Path, default=ROOT.parent / "results" / "solution.json")
args = parser.parse_args()

config = json.loads((ROOT / "config.json").read_text(encoding="utf-8"))
solution = json.loads(args.solution.read_text(encoding="utf-8"))
validate_all(args.input, solution, config)
try:
    sys.stdout.reconfigure(encoding="utf-8")
except (AttributeError, OSError):
    pass
print("全部校验通过。")
