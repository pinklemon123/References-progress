from __future__ import annotations

import sys
from pathlib import Path


SUBMISSION_ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(SUBMISSION_ROOT))
from formal_excel import export_formal_workbook


def export_workbook(results: dict, output_path: Path, config: dict) -> None:
    """兼容问题一原入口，输出赛题模板格式的正式路线表。"""
    del config
    export_formal_workbook(
        results,
        output_path,
        SUBMISSION_ROOT / "templates" / "result1_template.xlsx",
        problem=1,
    )
