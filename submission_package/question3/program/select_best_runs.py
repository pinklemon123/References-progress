"""按 (Tmax, delta, total_work) 词典序合并多轮问题三搜索结果。"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from q3_solver import write_csv


def key(case: dict) -> tuple[float, float, float]:
    return float(case["Tmax"]), float(case["delta"]), float(case["total_work_h"])


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--inputs", type=Path, nargs="+", required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    runs = [json.loads(path.read_text(encoding="utf-8")) for path in args.inputs]
    names = list(runs[0])
    assert all(list(run) == names for run in runs)
    selected = {name: min((run[name] for run in runs), key=key) for name in names}
    args.output_dir.mkdir(parents=True, exist_ok=True)
    output = args.output_dir / "q3_solution.json"
    output.write_text(json.dumps(selected, ensure_ascii=False, indent=2), encoding="utf-8")
    write_csv(selected, args.output_dir)
    for name, case in selected.items():
        print(name, key(case))


if __name__ == "__main__":
    main()
