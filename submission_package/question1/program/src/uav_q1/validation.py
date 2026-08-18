from __future__ import annotations

from collections import Counter
from pathlib import Path
import math
import pandas as pd


def validate_all(input_path: Path, results: dict, config: dict) -> None:
    required_map = config["level_required_visits"]
    speed = float(config["speed_kmh"])
    service_h = float(config["service_minutes_per_visit"]) / 60.0
    limit_h = float(config["maximum_work_hours"])
    book = pd.ExcelFile(input_path)
    assert set(results) == set(book.sheet_names), "结果中的 Case 与附件 1 不一致"

    for case_name in book.sheet_names:
        df = pd.read_excel(book, sheet_name=case_name)
        expected = {int(row.Point_ID): int(required_map[row.Inspection_Level]) for _, row in df.iterrows()}
        coordinates = {int(row.Point_ID): (float(row.X_Coordinate), float(row.Y_Coordinate)) for _, row in df.iterrows()}
        found = Counter()
        case = results[case_name]
        assert int(case["N"]) == len(case["routes"]), f"{case_name}: N 与路线行数不符"

        recalculated_times = []
        for route in case["routes"]:
            sequence = [int(x) for x in route["sequence"]]
            assert sequence[0] == sequence[-1] == 0, f"{case_name}: 路线必须以基地 0 为首尾"
            tasks = sequence[1:-1]
            assert all(tasks[i] != tasks[i + 1] for i in range(len(tasks) - 1)), \
                f"{case_name}: 同一点连续出现，未满足离开后返回规则"
            found.update(tasks)
            xy = [(0.0, 0.0), *[coordinates[x] for x in tasks], (0.0, 0.0)]
            coordinate_distance = sum(math.dist(xy[i], xy[i + 1]) for i in range(len(xy) - 1))
            distance_km = coordinate_distance * float(config["coordinate_unit_km"])
            work_h = distance_km / speed + len(tasks) * service_h
            assert abs(work_h - float(route["time_h"])) < 1e-6, f"{case_name}: 工作时间计算不一致"
            assert work_h <= limit_h + 1e-8, f"{case_name}: 存在超过 9 h 的路线"
            recalculated_times.append(work_h)

        assert dict(found) == expected, f"{case_name}: 巡检次数不满足 I/II/III=3/2/1"
        assert abs(max(recalculated_times) - float(case["Tmax"])) < 1e-6
        assert abs(min(recalculated_times) - float(case["Tmin"])) < 1e-6
