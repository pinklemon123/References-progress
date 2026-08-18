"""问题三增强算法的独立逐事件验证器。"""

from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path

import q3_solver as baseline
from q3_solver_enhanced import expected_copy_ids, task_point


TOL = 2.0e-6


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--points", type=Path, required=True)
    parser.add_argument("--zones", type=Path, required=True)
    parser.add_argument("--solution", type=Path, required=True)
    args = parser.parse_args()

    cases = baseline.load_cases(args.points, args.zones)
    result = json.loads(args.solution.read_text(encoding="utf-8"))
    assert set(result) == set(cases)
    for case_name, scenarios in result.items():
        data = cases[case_name]
        expected = expected_copy_ids(data)
        for scenario_name, case in scenarios.items():
            found_tasks: list[str] = []
            times: list[float] = []
            total_wait = 0.0
            for route in case["routes"]:
                task_sequence = route["task_sequence"]
                assert task_sequence[0] == task_sequence[-1] == "BASE"
                tasks = task_sequence[1:-1]
                found_tasks.extend(tasks)
                physical = [task_point(task) for task in tasks]
                assert route["sequence"] == [0, *physical, 0]
                assert all(a != b for a, b in zip(physical, physical[1:]))

                last_end = 0.0
                services: list[str] = []
                distance_km = 0.0
                for event in route["events"]:
                    start = float(event["start_min"])
                    end = float(event["end_min"])
                    assert abs(start - last_end) < TOL
                    assert end >= start - TOL
                    if event["type"] == "flight":
                        a = tuple(float(x) for x in event["from_xy"])
                        b = tuple(float(x) for x in event["to_xy"])
                        distance_km += float(event["distance_km"])
                        for zone in data.zones:
                            if not zone.active:
                                continue
                            interval = baseline.segment_circle_interval(a, b, zone)
                            if interval is None:
                                continue
                            lo, hi = interval
                            assert not baseline.overlaps(
                                start + lo * (end - start),
                                start + hi * (end - start),
                                zone.start_min,
                                zone.end_min,
                            ), f"{case_name}/{scenario_name}/UAV{route['uav']} flight conflicts {zone.zone_id}"
                    elif event["type"] in {"wait", "service"}:
                        xy = tuple(float(x) for x in event["node_xy"])
                        if event["type"] == "wait":
                            total_wait += end - start
                        else:
                            services.append(event["task_id"])
                            assert abs((end - start) - baseline.SERVICE_MIN) < TOL
                        for zone in data.zones:
                            if zone.active and baseline.point_inside(xy, zone):
                                assert not baseline.overlaps(start, end, zone.start_min, zone.end_min), (
                                    f"{case_name}/{scenario_name}/UAV{route['uav']} "
                                    f"{event['type']} conflicts {zone.zone_id}"
                                )
                    else:
                        raise AssertionError(f"未知事件类型 {event['type']}")
                    last_end = end
                assert services == tasks
                assert abs(distance_km - float(route["distance_km"])) < TOL
                assert abs(last_end / 60.0 - float(route["time_h"])) < TOL
                times.append(float(route["time_h"]))

            assert len(found_tasks) == len(set(found_tasks))
            assert set(found_tasks) == expected
            assert int(case["N"]) == len(case["routes"])
            assert abs(max(times) - float(case["Tmax"])) < TOL
            assert abs(min(times) - float(case["Tmin"])) < TOL
            assert abs(max(times) - min(times) - float(case["delta"])) < TOL
            assert abs(total_wait - float(case["total_wait_min"])) < TOL
            limit = float(case["stage_b"]["Tmax_limit_h"])
            assert float(case["Tmax"]) <= limit + TOL
            assert case["deadline_17_00"] is False
            print(f"{case_name}/{scenario_name}: PASSED")


if __name__ == "__main__":
    main()
