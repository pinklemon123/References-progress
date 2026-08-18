"""问题三：动态圆形飞行管制下的多无人机协同巡检优化。

固定问题一/二采用的无人机数量，以问题二路线为初始解；时间以 8:00 为
零点、分钟为单位。目标按 (Tmax, delta, total_work) 词典序优化。等待仅在
航段或下一巡检服务受管制时发生，不插入用于人为改善均衡性的空等待。
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import random
import time
from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path

import pandas as pd


SPEED_KMH = 55.0
UNIT_KM = 0.1
SERVICE_MIN = 5.0
REQ = {"I": 3, "II": 2, "III": 1}
TOL = 1.0e-9


@dataclass(frozen=True)
class Zone:
    zone_id: str
    center: tuple[float, float]
    radius: float
    start_min: float
    end_min: float

    @property
    def active(self) -> bool:
        return self.end_min > self.start_min + TOL


@dataclass(frozen=True)
class CaseData:
    coordinates: dict[int, tuple[float, float]]
    expected_visits: dict[int, int]
    zones: tuple[Zone, ...]


def clock_to_min(value: object) -> float:
    text = str(value).strip()
    parsed = datetime.strptime(text, "%H:%M")
    return (parsed.hour - 8) * 60 + parsed.minute


def min_to_clock(value: float) -> str:
    stamp = datetime(2000, 1, 1, 8, 0) + timedelta(minutes=value)
    return stamp.strftime("%H:%M:%S")


def load_cases(points_path: Path, zones_path: Path) -> dict[str, CaseData]:
    point_book = pd.ExcelFile(points_path)
    zone_book = pd.ExcelFile(zones_path)
    assert point_book.sheet_names == zone_book.sheet_names
    result: dict[str, CaseData] = {}
    for case_name in point_book.sheet_names:
        points = pd.read_excel(point_book, sheet_name=case_name)
        zones_df = pd.read_excel(zone_book, sheet_name=case_name)
        coordinates = {0: (0.0, 0.0)}
        expected: dict[int, int] = {}
        for _, row in points.iterrows():
            point_id = int(row.Point_ID)
            coordinates[point_id] = (float(row.X_Coordinate), float(row.Y_Coordinate))
            expected[point_id] = REQ[str(row.Inspection_Level)]
        zones = tuple(
            Zone(
                str(row.Zone_ID),
                (float(row.Center_X), float(row.Center_Y)),
                float(row.Radius),
                clock_to_min(row.Start_Time),
                clock_to_min(row.End_Time),
            )
            for _, row in zones_df.iterrows()
        )
        result[case_name] = CaseData(coordinates, expected, zones)
    return result


def point_inside(point: tuple[float, float], zone: Zone) -> bool:
    return math.dist(point, zone.center) <= zone.radius + 1.0e-10


def segment_circle_interval(
    a: tuple[float, float], b: tuple[float, float], zone: Zone
) -> tuple[float, float] | None:
    """返回线段位于闭圆内的参数区间，线段参数 lambda 属于 [0,1]。"""
    dx, dy = b[0] - a[0], b[1] - a[1]
    fx, fy = a[0] - zone.center[0], a[1] - zone.center[1]
    aa = dx * dx + dy * dy
    if aa <= TOL:
        return (0.0, 1.0) if point_inside(a, zone) else None
    bb = 2.0 * (fx * dx + fy * dy)
    cc = fx * fx + fy * fy - zone.radius * zone.radius
    disc = bb * bb - 4.0 * aa * cc
    if disc < -1.0e-10:
        return None
    disc = max(0.0, disc)
    root = math.sqrt(disc)
    lo = max(0.0, (-bb - root) / (2.0 * aa))
    hi = min(1.0, (-bb + root) / (2.0 * aa))
    if lo > hi + 1.0e-10:
        return None
    return lo, hi


def overlaps(a0: float, a1: float, b0: float, b1: float) -> bool:
    return max(a0, b0) < min(a1, b1) - 1.0e-9


def departure_blocks(
    a: tuple[float, float],
    b: tuple[float, float],
    travel_min: float,
    service_at_b: bool,
    zones: tuple[Zone, ...],
) -> list[tuple[float, float, str, str]]:
    blocks: list[tuple[float, float, str, str]] = []
    for zone in zones:
        if not zone.active:
            continue
        interval = segment_circle_interval(a, b, zone)
        if interval is not None:
            lo, hi = interval
            blocks.append(
                (
                    zone.start_min - hi * travel_min,
                    zone.end_min - lo * travel_min,
                    zone.zone_id,
                    "flight",
                )
            )
        if service_at_b and point_inside(b, zone):
            blocks.append(
                (
                    zone.start_min - travel_min - SERVICE_MIN,
                    zone.end_min - travel_min,
                    zone.zone_id,
                    "service",
                )
            )
    return blocks


def unsafe_handoff_blocks(
    current: tuple[float, float],
    current_travel_min: float,
    outgoing: list[tuple[float, float, str, str]],
    zones: tuple[Zone, ...],
) -> list[tuple[float, float, str, str]]:
    """把“到点服务后不能在管制圆内等待”的约束前移到上一航段出发时刻。"""
    holding_zones = [zone for zone in zones if zone.active and point_inside(current, zone)]
    if not holding_zones:
        return []
    offset = current_travel_min + SERVICE_MIN
    result: list[tuple[float, float, str, str]] = []
    for block_start, block_end, cause_id, _ in outgoing:
        for holding in holding_zones:
            # 若完成服务时刻 r 落入出站禁用区间，等待到 block_end；
            # 只要 [r, block_end) 与当前点所在管制区重叠，就必须在上一点延迟。
            unsafe_end = min(block_end, holding.end_min)
            if block_end > holding.start_min + TOL and block_start < unsafe_end - TOL:
                result.append(
                    (
                        block_start - offset,
                        unsafe_end - offset,
                        f"{holding.zone_id}/{cause_id}",
                        "handoff",
                    )
                )
    return result


def earliest_departure(
    ready: float, blocks: list[tuple[float, float, str, str]]
) -> tuple[float, list[str]]:
    depart = ready
    reasons: set[str] = set()
    for _ in range(len(blocks) + 2):
        covering = [item for item in blocks if item[0] - TOL <= depart < item[1] - TOL]
        if not covering:
            return depart, sorted(reasons)
        reasons.update(f"{zone_id}:{kind}" for _, _, zone_id, kind in covering)
        depart = max(item[1] for item in covering)
    raise RuntimeError("禁用出发区间合并未收敛")


def wait_is_safe(
    node: int, point: tuple[float, float], start: float, end: float, zones: tuple[Zone, ...]
) -> bool:
    if node == 0 or end <= start + TOL:
        return True
    for zone in zones:
        if zone.active and point_inside(point, zone) and overlaps(start, end, zone.start_min, zone.end_min):
            return False
    return True


def schedule_route(
    tasks: list[int], data: CaseData, debug: bool = False, release_min: float = 0.0
) -> dict | None:
    if not tasks or any(a == b for a, b in zip(tasks, tasks[1:])):
        return None
    sequence = [0] + tasks + [0]
    leg_data = []
    effective_blocks: list[list[tuple[float, float, str, str]]] = []
    for a_id, b_id in zip(sequence, sequence[1:]):
        a, b = data.coordinates[a_id], data.coordinates[b_id]
        distance = math.dist(a, b) * UNIT_KM
        travel = distance / SPEED_KMH * 60.0
        leg_data.append((a_id, b_id, a, b, distance, travel))
        effective_blocks.append(departure_blocks(a, b, travel, b_id != 0, data.zones))
    # 从路线末端向前传递：若下一航段会迫使无人机在管制圆内等待，
    # 则把相应禁用时段推回到上一安全节点的出发决策。
    for idx in range(len(leg_data) - 2, -1, -1):
        _, b_id, _, b, _, travel = leg_data[idx]
        if b_id != 0:
            effective_blocks[idx].extend(
                unsafe_handoff_blocks(b, travel, effective_blocks[idx + 1], data.zones)
            )

    now = release_min
    distance_km = 0.0
    wait_min = release_min
    events: list[dict] = []
    if release_min > TOL:
        events.append(
            {
                "type": "wait",
                "node": 0,
                "start_min": 0.0,
                "end_min": release_min,
                "duration_min": release_min,
                "reason_zone_ids": ["safe_release_after_all_zones"],
            }
        )
    for leg, (a_id, b_id, a, b, distance, travel) in enumerate(leg_data, start=1):
        blocks = effective_blocks[leg - 1]
        depart, reasons = earliest_departure(now, blocks)
        if not wait_is_safe(a_id, a, now, depart, data.zones):
            if debug:
                print(
                    f"unsafe wait: node={a_id}, ready={now:.3f}, depart={depart:.3f}, "
                    f"next={b_id}, reasons={reasons}",
                    flush=True,
                )
            return None
        if depart > now + TOL:
            events.append(
                {
                    "type": "wait",
                    "node": a_id,
                    "start_min": now,
                    "end_min": depart,
                    "duration_min": depart - now,
                    "reason_zone_ids": reasons,
                }
            )
            wait_min += depart - now
        arrival = depart + travel
        events.append(
            {
                "type": "flight",
                "leg": leg,
                "from": a_id,
                "to": b_id,
                "start_min": depart,
                "end_min": arrival,
                "duration_min": travel,
                "distance_km": distance,
            }
        )
        distance_km += distance
        now = arrival
        if b_id != 0:
            events.append(
                {
                    "type": "service",
                    "node": b_id,
                    "start_min": now,
                    "end_min": now + SERVICE_MIN,
                    "duration_min": SERVICE_MIN,
                }
            )
            now += SERVICE_MIN
    return {
        "sequence": sequence,
        "distance_km": distance_km,
        "service_count": len(tasks),
        "flight_time_h": distance_km / SPEED_KMH,
        "wait_time_h": wait_min / 60.0,
        "time_h": now / 60.0,
        "return_clock": min_to_clock(now),
        "events": events,
    }


def valid_tasks(tasks: list[int]) -> bool:
    return bool(tasks) and all(a != b for a, b in zip(tasks, tasks[1:]))


class Evaluator:
    def __init__(self, data: CaseData):
        self.data = data
        self.cache: dict[tuple[int, ...], dict | None] = {}

    def route(self, tasks: list[int]) -> dict | None:
        key = tuple(tasks)
        if key not in self.cache:
            result = schedule_route(tasks, self.data)
            if result is None:
                safe_release = max((zone.end_min for zone in self.data.zones if zone.active), default=0.0)
                result = schedule_route(tasks, self.data, release_min=safe_release)
            self.cache[key] = result
        return self.cache[key]

    def solution(self, routes: list[list[int]]) -> tuple[tuple[float, float, float], list[dict]] | None:
        schedules = [self.route(route) for route in routes]
        if any(item is None for item in schedules):
            return None
        valid = [item for item in schedules if item is not None]
        times = [item["time_h"] for item in valid]
        key = (max(times), max(times) - min(times), sum(times))
        return key, valid


def lex_better(a: tuple[float, ...], b: tuple[float, ...]) -> bool:
    for x, y in zip(a, b):
        if x < y - TOL:
            return True
        if x > y + TOL:
            return False
    return False


def propose(routes: list[list[int]], times: list[float], rng: random.Random) -> list[list[int]] | None:
    candidate = [route[:] for route in routes]
    move = rng.random()
    order = sorted(range(len(routes)), key=times.__getitem__)

    if move < 0.48:
        src = rng.choice(order[-min(2, len(order)):]) if rng.random() < 0.82 else rng.randrange(len(routes))
        choices = [idx for idx in range(len(routes)) if idx != src]
        dst = rng.choice(order[: min(2, len(order))]) if rng.random() < 0.82 else rng.choice(choices)
        if dst == src:
            dst = rng.choice(choices)
        if len(candidate[src]) <= 1:
            return None
        pos = rng.randrange(len(candidate[src]))
        node = candidate[src].pop(pos)
        legal = [
            q for q in range(len(candidate[dst]) + 1)
            if (q == 0 or candidate[dst][q - 1] != node)
            and (q == len(candidate[dst]) or candidate[dst][q] != node)
        ]
        if not legal:
            return None
        candidate[dst].insert(rng.choice(legal), node)
    elif move < 0.73:
        a, b = rng.sample(range(len(routes)), 2)
        ia, ib = rng.randrange(len(candidate[a])), rng.randrange(len(candidate[b]))
        candidate[a][ia], candidate[b][ib] = candidate[b][ib], candidate[a][ia]
    else:
        ridx = rng.randrange(len(routes))
        route = candidate[ridx]
        if len(route) < 4:
            return None
        i, j = sorted(rng.sample(range(len(route)), 2))
        if i == j:
            return None
        route[i : j + 1] = reversed(route[i : j + 1])

    if not all(valid_tasks(route) for route in candidate):
        return None
    return candidate


def search_seed(
    initial: list[list[int]],
    evaluator: Evaluator,
    seed: int,
    iterations: int,
    deadline: float,
) -> tuple[list[list[int]], tuple[float, float, float], dict]:
    rng = random.Random(seed)
    current = [route[:] for route in initial]
    evaluated = evaluator.solution(current)
    if evaluated is None:
        raise RuntimeError("问题二初始路线在问题三调度规则下不可行")
    current_key, current_schedules = evaluated
    best = [route[:] for route in current]
    best_key = current_key
    attempted = accepted = 0

    for iteration in range(iterations):
        if time.monotonic() >= deadline:
            break
        times = [item["time_h"] for item in current_schedules]
        candidate = propose(current, times, rng)
        if candidate is None:
            continue
        attempted += 1
        evaluated = evaluator.solution(candidate)
        if evaluated is None:
            continue
        key, schedules = evaluated
        accept = lex_better(key, current_key)
        if not accept:
            progress = iteration / max(1, iterations - 1)
            temperature = 0.12 * (1.0 - progress) + 0.002
            current_score = current_key[0] + 0.18 * current_key[1] + 0.002 * current_key[2]
            candidate_score = key[0] + 0.18 * key[1] + 0.002 * key[2]
            loss = max(0.0, candidate_score - current_score)
            accept = rng.random() < math.exp(-loss / temperature)
        if accept:
            current, current_key, current_schedules = candidate, key, schedules
            accepted += 1
            if lex_better(key, best_key):
                best, best_key = [route[:] for route in candidate], key

    return best, best_key, {
        "seed": seed,
        "attempted_moves": attempted,
        "accepted_moves": accepted,
        "Tmax_h": best_key[0],
        "delta_h": best_key[1],
        "total_work_h": best_key[2],
    }


def validate_counts(routes: list[list[int]], data: CaseData) -> None:
    found = Counter(node for route in routes for node in route)
    assert dict(found) == data.expected_visits
    assert all(valid_tasks(route) for route in routes)


def zone_summary(data: CaseData) -> dict:
    active = [zone for zone in data.zones if zone.active]
    involved = {
        node
        for node, point in data.coordinates.items()
        if node != 0 and any(point_inside(point, zone) for zone in active)
    }
    return {
        "zone_count": len(data.zones),
        "positive_duration_count": len(active),
        "zero_duration_count": len(data.zones) - len(active),
        "involved_point_count": len(involved),
        "involved_points": sorted(involved),
    }


def solve_case(
    case_name: str,
    data: CaseData,
    initial: list[list[int]],
    seeds: int,
    iterations: int,
    seconds: float,
) -> dict:
    validate_counts(initial, data)
    evaluator = Evaluator(data)
    baseline = evaluator.solution(initial)
    if baseline is None:
        for idx, route in enumerate(initial, start=1):
            if evaluator.route(route) is None:
                print(f"{case_name} UAV{idx} diagnostic", flush=True)
                schedule_route(route, data, debug=True)
        raise RuntimeError(f"{case_name}: 初始路线无法生成合法动态调度")
    best_routes = [route[:] for route in initial]
    best_key, _ = baseline
    history = []
    deadline = time.monotonic() + seconds
    for offset in range(seeds):
        routes, key, report = search_seed(
            initial,
            evaluator,
            20260818 + offset,
            iterations,
            deadline,
        )
        history.append(report)
        if lex_better(key, best_key):
            best_routes, best_key = routes, key
        if time.monotonic() >= deadline:
            break

    validate_counts(best_routes, data)
    final = evaluator.solution(best_routes)
    assert final is not None
    key, schedules = final
    routes_output = []
    for uav, schedule in enumerate(schedules, start=1):
        routes_output.append({"uav": uav, **schedule})
    return {
        "N": len(best_routes),
        "Tmax": key[0],
        "Tmin": min(item["time_h"] for item in schedules),
        "delta": key[1],
        "total_work_h": key[2],
        "total_wait_min": sum(item["wait_time_h"] * 60 for item in schedules),
        "latest_return": min_to_clock(key[0] * 60),
        "time_origin": "08:00",
        "deadline_17_00": False,
        "objective_order": ["Tmax", "delta", "total_work_h"],
        "zone_summary": zone_summary(data),
        "routes": routes_output,
        "search_history": history,
    }


def write_csv(results: dict, output_dir: Path) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    with (output_dir / "summary.csv").open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.writer(handle)
        writer.writerow(["Case", "N", "Tmax_h", "Tmin_h", "delta_h", "wait_min", "latest_return"])
        for case_name, case in results.items():
            writer.writerow([case_name, case["N"], case["Tmax"], case["Tmin"], case["delta"], case["total_wait_min"], case["latest_return"]])
    for case_name, case in results.items():
        with (output_dir / f"{case_name}_routes.csv").open("w", newline="", encoding="utf-8-sig") as handle:
            writer = csv.writer(handle)
            writer.writerow(["UAV", "Sequence", "Distance_km", "Service_Count", "Wait_min", "Work_h", "Return"])
            for route in case["routes"]:
                writer.writerow([route["uav"], "-".join(map(str, route["sequence"])), route["distance_km"], route["service_count"], route["wait_time_h"] * 60, route["time_h"], route["return_clock"]])


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--points", type=Path, required=True)
    parser.add_argument("--zones", type=Path, required=True)
    parser.add_argument("--q2-solution", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--seeds", type=int, default=5)
    parser.add_argument("--iterations", type=int, default=25000)
    parser.add_argument("--seconds-per-case", type=float, default=35.0)
    args = parser.parse_args()

    cases = load_cases(args.points, args.zones)
    q2 = json.loads(args.q2_solution.read_text(encoding="utf-8"))
    assert set(cases) == set(q2)
    results = {}
    for case_name, data in cases.items():
        initial = [[int(x) for x in route["sequence"][1:-1]] for route in q2[case_name]["routes"]]
        started = time.monotonic()
        results[case_name] = solve_case(
            case_name,
            data,
            initial,
            args.seeds,
            args.iterations,
            args.seconds_per_case,
        )
        elapsed = time.monotonic() - started
        case = results[case_name]
        print(
            f"{case_name}: N={case['N']}, Tmax={case['Tmax']:.6f} h, "
            f"Tmin={case['Tmin']:.6f} h, delta={case['delta']:.6f} h, "
            f"wait={case['total_wait_min']:.3f} min, elapsed={elapsed:.1f}s",
            flush=True,
        )

    args.output_dir.mkdir(parents=True, exist_ok=True)
    output = args.output_dir / "q3_solution.json"
    output.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
    write_csv(results, args.output_dir)
    print(output)


if __name__ == "__main__":
    main()
