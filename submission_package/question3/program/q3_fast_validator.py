"""问题三保存结果的独立快速复核。

先用线段包围盒与圆包围盒作常数时间筛查，仅对可能相交的航段求解析交区间；
再逐事件核验飞行、服务和等待均不与正时长管制区冲突。
"""

from __future__ import annotations

import argparse
import json
import math
from collections import Counter
from datetime import datetime
from pathlib import Path

import pandas as pd


REQ = {"I": 3, "II": 2, "III": 1}
TOL = 1.0e-7


def to_min(text: object) -> float:
    value = datetime.strptime(str(text).strip(), "%H:%M")
    return (value.hour - 8) * 60 + value.minute


def overlap(a0: float, a1: float, b0: float, b1: float) -> bool:
    return max(a0, b0) < min(a1, b1) - TOL


def bbox_maybe(a, b, center, radius) -> bool:
    return not (
        max(a[0], b[0]) < center[0] - radius
        or min(a[0], b[0]) > center[0] + radius
        or max(a[1], b[1]) < center[1] - radius
        or min(a[1], b[1]) > center[1] + radius
    )


def segment_inside_interval(a, b, center, radius):
    if not bbox_maybe(a, b, center, radius):
        return None
    dx, dy = b[0] - a[0], b[1] - a[1]
    fx, fy = a[0] - center[0], a[1] - center[1]
    aa = dx * dx + dy * dy
    bb = 2 * (fx * dx + fy * dy)
    cc = fx * fx + fy * fy - radius * radius
    disc = bb * bb - 4 * aa * cc
    if disc < -TOL:
        return None
    disc = max(0.0, disc)
    lo = max(0.0, (-bb - math.sqrt(disc)) / (2 * aa))
    hi = min(1.0, (-bb + math.sqrt(disc)) / (2 * aa))
    return None if lo > hi + TOL else (lo, hi)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--points", type=Path, required=True)
    parser.add_argument("--zones", type=Path, required=True)
    parser.add_argument("--solution", type=Path, required=True)
    args = parser.parse_args()

    result = json.loads(args.solution.read_text(encoding="utf-8"))
    points_book = pd.ExcelFile(args.points)
    zones_book = pd.ExcelFile(args.zones)
    assert set(result) == set(points_book.sheet_names) == set(zones_book.sheet_names)

    for case_name in points_book.sheet_names:
        points_df = pd.read_excel(points_book, sheet_name=case_name)
        zones_df = pd.read_excel(zones_book, sheet_name=case_name)
        coords = {0: (0.0, 0.0)}
        expected = {}
        for _, row in points_df.iterrows():
            point_id = int(row.Point_ID)
            coords[point_id] = (float(row.X_Coordinate), float(row.Y_Coordinate))
            expected[point_id] = REQ[str(row.Inspection_Level)]
        zones = []
        for _, row in zones_df.iterrows():
            start, end = to_min(row.Start_Time), to_min(row.End_Time)
            if end > start + TOL:
                zones.append((str(row.Zone_ID), (float(row.Center_X), float(row.Center_Y)), float(row.Radius), start, end))

        found = Counter()
        times = []
        for route in result[case_name]["routes"]:
            seq = [int(x) for x in route["sequence"]]
            assert seq[0] == seq[-1] == 0
            assert all(a != b for a, b in zip(seq[1:-1], seq[2:-1]))
            found.update(seq[1:-1])
            last_end = 0.0
            for event in route["events"]:
                start, end = float(event["start_min"]), float(event["end_min"])
                assert abs(start - last_end) < 2.0e-6
                assert end >= start - TOL
                if event["type"] == "flight":
                    a, b = coords[int(event["from"])], coords[int(event["to"])]
                    for zone_id, center, radius, z0, z1 in zones:
                        interval = segment_inside_interval(a, b, center, radius)
                        if interval is None:
                            continue
                        lo, hi = interval
                        assert not overlap(start + lo * (end - start), start + hi * (end - start), z0, z1), f"{case_name} UAV{route['uav']} flight conflicts {zone_id}"
                elif event["type"] in {"service", "wait"}:
                    node = int(event["node"])
                    if event["type"] == "wait" and node == 0:
                        last_end = end
                        continue
                    point = coords[node]
                    for zone_id, center, radius, z0, z1 in zones:
                        if math.dist(point, center) <= radius + TOL:
                            assert not overlap(start, end, z0, z1), f"{case_name} UAV{route['uav']} {event['type']} conflicts {zone_id}"
                last_end = end
            assert abs(last_end / 60 - float(route["time_h"])) < 2.0e-6
            times.append(last_end / 60)
        assert dict(found) == expected
        case = result[case_name]
        assert int(case["N"]) == len(case["routes"])
        assert abs(max(times) - float(case["Tmax"])) < 2.0e-6
        assert abs(min(times) - float(case["Tmin"])) < 2.0e-6
        assert abs(max(times) - min(times) - float(case["delta"])) < 2.0e-6
        print(f"{case_name}: PASSED")


if __name__ == "__main__":
    main()
