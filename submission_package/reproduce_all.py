"""一键校验论文正式路线并按官方模板生成 result1/2/3.xlsx。"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from pathlib import Path

from formal_excel import export_formal_workbook, verify_formal_workbook


ROOT = Path(__file__).resolve().parent
POINTS = ROOT / "question1" / "program" / "input" / "附件1.xlsx"
ZONES = ROOT / "question3" / "program" / "input" / "附件2.xlsx"
Q1_JSON = ROOT / "question1" / "results" / "solution.json"
Q2_JSON = ROOT / "question2" / "results" / "q2_solution.json"
Q3_JSON = ROOT / "question3" / "results" / "q3_solution.json"


def run_checked(label: str, command: list[str]) -> None:
    print(f"\n[{label}]", flush=True)
    subprocess.run(command, check=True, cwd=ROOT)


def load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def validate_saved_results() -> None:
    python = sys.executable
    run_checked(
        "1/3 问题一独立校验",
        [
            python,
            str(ROOT / "question1" / "program" / "validate.py"),
            "--input",
            str(POINTS),
            "--solution",
            str(Q1_JSON),
        ],
    )
    run_checked(
        "2/3 问题二独立校验",
        [
            python,
            str(ROOT / "question2" / "program" / "q2_solver.py"),
            "--input",
            str(POINTS),
            "--q1-solution",
            str(Q1_JSON),
            "--output-dir",
            str(ROOT / "question2" / "results"),
            "--validate-only",
        ],
    )
    run_checked(
        "3/3 问题三算法 B 独立逐事件校验",
        [
            python,
            str(ROOT / "question3" / "program" / "q3_enhanced_validator.py"),
            "--points",
            str(POINTS),
            "--zones",
            str(ZONES),
            "--solution",
            str(Q3_JSON),
        ],
    )


def generate_formal_results(output_dir: Path) -> list[Path]:
    sources = {
        1: load_json(Q1_JSON),
        2: load_json(Q2_JSON),
        3: load_json(Q3_JSON),
    }
    outputs = []
    for problem in (1, 2, 3):
        output = output_dir / f"result{problem}.xlsx"
        template = ROOT / "templates" / f"result{problem}_template.xlsx"
        export_formal_workbook(sources[problem], output, template, problem)
        verify_formal_workbook(output, sources[problem], problem)
        outputs.append(output)
        print(f"已生成并逐格核对：{output}")
    return outputs


def main() -> None:
    parser = argparse.ArgumentParser(
        description="校验已保存正式路线，并按赛题模板生成三个正式结果文件"
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=ROOT,
        help="正式 result1/2/3.xlsx 输出目录，默认是 submission_package 根目录",
    )
    parser.add_argument(
        "--validate-only",
        action="store_true",
        help="只校验 JSON，不重新生成 Excel",
    )
    args = parser.parse_args()

    started = time.perf_counter()
    validate_saved_results()
    if not args.validate_only:
        generate_formal_results(args.output_dir.resolve())
    elapsed = time.perf_counter() - started
    print(f"\n全部完成，用时 {elapsed:.2f} 秒。", flush=True)


if __name__ == "__main__":
    main()

