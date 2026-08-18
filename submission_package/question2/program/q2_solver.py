"""问题二：固定问题一无人机数量与完成时间上界的负载均衡优化。

Python 求解器只输出 JSON/CSV；result2.xlsx 由 build_result2.mjs 根据同一 JSON 生成。
工作时间仅包含实际飞行与有效巡检服务，不允许用等待时间改善均衡指标。
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
from pathlib import Path

import numpy as np
import pandas as pd


SPEED_KMH = 55.0
UNIT_KM = 0.1
SERVICE_H = 5.0 / 60.0
REQ = {"I": 3, "II": 2, "III": 1}
TOL = 1.0e-9


@dataclass(frozen=True)
class CaseData:
    point_ids: tuple[int, ...]
    coordinates: dict[int, tuple[float, float]]
    expected_visits: dict[int, int]
    distance_km: dict[tuple[int, int], float]


def load_case(book: pd.ExcelFile, case_name: str) -> CaseData:
    df = pd.read_excel(book, sheet_name=case_name)
    ids = tuple(int(x) for x in df["Point_ID"])
    coordinates = {
        int(row.Point_ID): (float(row.X_Coordinate), float(row.Y_Coordinate))
        for _, row in df.iterrows()
    }
    coordinates[0] = (0.0, 0.0)
    expected = {
        int(row.Point_ID): REQ[str(row.Inspection_Level)]
        for _, row in df.iterrows()
    }
    distance: dict[tuple[int, int], float] = {}
    for i in (0,) + ids:
        xi, yi = coordinates[i]
        for j in (0,) + ids:
            xj, yj = coordinates[j]
            distance[(i, j)] = math.hypot(xi - xj, yi - yj) * UNIT_KM
    return CaseData(ids, coordinates, expected, distance)


def route_valid(route: list[int]) -> bool:
    return bool(route) and all(a != b for a, b in zip(route, route[1:]))


def route_metrics(route: list[int], data: CaseData) -> tuple[float, float]:
    seq = [0] + route + [0]
    distance = sum(data.distance_km[(a, b)] for a, b in zip(seq, seq[1:]))
    return distance, distance / SPEED_KMH + len(route) * SERVICE_H


def all_metrics(routes: list[list[int]], data: CaseData) -> tuple[list[float], list[float]]:
    pairs = [route_metrics(route, data) for route in routes]
    return [x[0] for x in pairs], [x[1] for x in pairs]


def objective(times_h: list[float]) -> tuple[float, float, float]:
    return max(times_h) - min(times_h), max(times_h), sum(times_h)


def better(a: tuple[float, float, float], b: tuple[float, float, float]) -> bool:
    for x, y in zip(a, b):
        if x < y - TOL:
            return True
        if x > y + TOL:
            return False
    return False


def two_opt(route: list[int], data: CaseData, max_passes: int = 2) -> list[int]:
    """仅执行缩短飞行距离的合法 2-opt，不会人为延长轻载路线。"""
    best = route[:]
    if len(best) < 4:
        return best
    for _ in range(max_passes):
        changed = False
        for i in range(len(best) - 2):
            a = 0 if i == 0 else best[i - 1]
            b = best[i]
            for j in range(i + 1, len(best)):
                c = best[j]
                d = 0 if j == len(best) - 1 else best[j + 1]
                old = data.distance_km[(a, b)] + data.distance_km[(c, d)]
                new = data.distance_km[(a, c)] + data.distance_km[(b, d)]
                if new >= old - 1.0e-12:
                    continue
                candidate = best[:i] + list(reversed(best[i : j + 1])) + best[j + 1 :]
                if route_valid(candidate):
                    best = candidate
                    changed = True
                    break
            if changed:
                break
        if not changed:
            break
    return best


def normalize_changed(
    routes: list[list[int]], data: CaseData, changed: tuple[int, ...]
) -> list[list[int]]:
    result = [r[:] for r in routes]
    for idx in set(changed):
        result[idx] = two_opt(result[idx], data, max_passes=2)
    return result


def legal_remove(route: list[int], pos: int) -> bool:
    if len(route) <= 1:
        return False
    candidate = route[:pos] + route[pos + 1 :]
    return route_valid(candidate)


def legal_insert(route: list[int], node: int, pos: int) -> bool:
    left = None if pos == 0 else route[pos - 1]
    right = None if pos == len(route) else route[pos]
    return left != node and right != node


def choose_heavy_light(times_h: list[float], rng: random.Random) -> tuple[int, int]:
    order = sorted(range(len(times_h)), key=times_h.__getitem__)
    width = min(2, max(1, len(order) // 2))
    if rng.random() < 0.85:
        src = rng.choice(order[-width:])
        dst = rng.choice(order[:width])
    else:
        src, dst = rng.sample(order, 2)
    return src, dst


def propose(
    routes: list[list[int]], data: CaseData, rng: random.Random
) -> list[list[int]] | None:
    _, times = all_metrics(routes, data)
    src, dst = choose_heavy_light(times, rng)
    move = rng.random()
    candidate = [r[:] for r in routes]

    if move < 0.60:
        positions = [i for i in range(len(candidate[src])) if legal_remove(candidate[src], i)]
        if not positions:
            return None
        pos = rng.choice(positions)
        node = candidate[src].pop(pos)
        legal = [q for q in range(len(candidate[dst]) + 1) if legal_insert(candidate[dst], node, q)]
        if not legal:
            return None
        # 在合法位置中优先选择飞行距离增量较小的几个，再保留随机性。
        ranked = []
        for q in legal:
            left = 0 if q == 0 else candidate[dst][q - 1]
            right = 0 if q == len(candidate[dst]) else candidate[dst][q]
            inc = (
                data.distance_km[(left, node)]
                + data.distance_km[(node, right)]
                - data.distance_km[(left, right)]
            )
            ranked.append((inc, q))
        ranked.sort()
        q = rng.choice(ranked[: min(4, len(ranked))])[1]
        candidate[dst].insert(q, node)
        changed = (src, dst)
    else:
        i = rng.randrange(len(candidate[src]))
        j = rng.randrange(len(candidate[dst]))
        candidate[src][i], candidate[dst][j] = candidate[dst][j], candidate[src][i]
        if not route_valid(candidate[src]) or not route_valid(candidate[dst]):
            return None
        changed = (src, dst)

    candidate = normalize_changed(candidate, data, changed)
    if not all(route_valid(r) for r in candidate):
        return None
    return candidate


def anneal_seed(
    initial: list[list[int]],
    data: CaseData,
    cap_h: float,
    seed: int,
    iterations: int,
    deadline: float,
) -> tuple[list[list[int]], dict]:
    rng = random.Random(seed)
    current = [two_opt(r, data, max_passes=20) for r in initial]
    _, current_times = all_metrics(current, data)
    current_key = objective(current_times)
    if current_key[1] > cap_h + TOL:
        # 问题一初始路线必须始终可作为保底方案。
        current = [r[:] for r in initial]
        _, current_times = all_metrics(current, data)
        current_key = objective(current_times)
    best = [r[:] for r in current]
    best_key = current_key
    accepted = 0
    attempted = 0

    for iteration in range(iterations):
        if time.monotonic() >= deadline:
            break
        candidate = propose(current, data, rng)
        if candidate is None:
            continue
        attempted += 1
        _, times = all_metrics(candidate, data)
        key = objective(times)
        if key[1] > cap_h + TOL or key[1] > 9.0 + TOL:
            continue

        accept = better(key, current_key)
        if not accept:
            progress = iteration / max(1, iterations - 1)
            temperature = 0.02 * (1.0 - progress) + 0.00015
            loss = max(0.0, key[0] - current_key[0])
            loss += 0.20 * max(0.0, key[1] - current_key[1])
            loss += 0.002 * max(0.0, key[2] - current_key[2])
            accept = rng.random() < math.exp(-loss / temperature)
        if accept:
            current = candidate
            current_key = key
            accepted += 1
            if better(key, best_key):
                best = [r[:] for r in candidate]
                best_key = key

    return best, {
        "seed": seed,
        "attempted_moves": attempted,
        "accepted_moves": accepted,
        "best_delta_h": best_key[0],
        "best_Tmax_h": best_key[1],
        "best_total_h": best_key[2],
    }


def deterministic_polish(
    initial: list[list[int]], data: CaseData, cap_h: float, max_rounds: int = 80
) -> list[list[int]]:
    """系统枚举重载到轻载的单任务迁移，直到没有词典序改善。"""
    routes = [r[:] for r in initial]
    for _ in range(max_rounds):
        _, times = all_metrics(routes, data)
        old_key = objective(times)
        order = sorted(range(len(routes)), key=times.__getitem__)
        sources = order[-min(2, len(order)) :]
        targets = order[: min(2, len(order))]
        best_candidate = None
        best_key = old_key
        for src in sources:
            for dst in targets:
                if src == dst:
                    continue
                for i, node in enumerate(routes[src]):
                    if not legal_remove(routes[src], i):
                        continue
                    for q in range(len(routes[dst]) + 1):
                        if not legal_insert(routes[dst], node, q):
                            continue
                        candidate = [r[:] for r in routes]
                        candidate[src].pop(i)
                        candidate[dst].insert(q, node)
                        candidate = normalize_changed(candidate, data, (src, dst))
                        _, cand_times = all_metrics(candidate, data)
                        key = objective(cand_times)
                        if key[1] <= cap_h + TOL and key[1] <= 9.0 + TOL and better(key, best_key):
                            best_candidate = candidate
                            best_key = key
        if best_candidate is None:
            break
        routes = best_candidate
    # 最终把每条路线充分缩短，避免通过保留可消除的绕行来抬高 Tmin。
    return [two_opt(route, data, max_passes=100) for route in routes]


def validate_case(
    case_name: str,
    routes: list[list[int]],
    data: CaseData,
    q1_case: dict,
    epsilon_h: float,
) -> tuple[list[float], list[float]]:
    assert len(routes) == int(q1_case["N"]), f"{case_name}: 无人机数量发生变化"
    assert all(route_valid(r) for r in routes), f"{case_name}: 存在空路线或连续相同巡检点"
    actual = Counter(x for route in routes for x in route)
    assert actual == Counter(data.expected_visits), f"{case_name}: 巡检次数不一致"
    distances, times = all_metrics(routes, data)
    cap = float(q1_case["Tmax"]) + epsilon_h
    assert max(times) <= cap + 1.0e-8, f"{case_name}: 超过问题一完成时间上界"
    assert max(times) <= 9.0 + 1.0e-8, f"{case_name}: 超过9小时"
    return distances, times


def solve_case(
    case_name: str,
    data: CaseData,
    q1_case: dict,
    epsilon_h: float,
    seeds: int,
    iterations: int,
    time_limit_s: float,
) -> dict:
    initial = [list(map(int, route["sequence"][1:-1])) for route in q1_case["routes"]]
    validate_case(case_name, initial, data, q1_case, epsilon_h)
    cap = float(q1_case["Tmax"]) + epsilon_h
    deadline = time.monotonic() + time_limit_s
    best = [r[:] for r in initial]
    _, best_times = all_metrics(best, data)
    best_key = objective(best_times)
    history = []

    for offset in range(seeds):
        if time.monotonic() >= deadline:
            break
        routes, record = anneal_seed(
            initial, data, cap, 20260818 + offset, iterations, deadline
        )
        history.append(record)
        _, times = all_metrics(routes, data)
        key = objective(times)
        if better(key, best_key):
            best, best_key = routes, key

    best = deterministic_polish(best, data, cap)
    distances, times = validate_case(case_name, best, data, q1_case, epsilon_h)
    delta1 = float(q1_case["Tmax"]) - float(q1_case["Tmin"])
    delta2 = max(times) - min(times)
    route_records = []
    for k, (route, distance, work_h) in enumerate(zip(best, distances, times), start=1):
        route_records.append(
            {
                "uav": k,
                "sequence": [0] + route + [0],
                "distance_km": distance,
                "service_count": len(route),
                "time_h": work_h,
                "waiting_time_h": 0.0,
            }
        )
    return {
        "N": int(q1_case["N"]),
        "q1_Tmax_h": float(q1_case["Tmax"]),
        "q1_Tmin_h": float(q1_case["Tmin"]),
        "q1_delta_h": delta1,
        "epsilon_h": epsilon_h,
        "completion_time_cap_h": cap,
        "Tmax": max(times),
        "Tmin": min(times),
        "delta": delta2,
        "total_work_h": sum(times),
        "delta_reduction_h": delta1 - delta2,
        "delta_reduction_pct": 0.0 if delta1 <= TOL else (delta1 - delta2) / delta1,
        "objective_order": ["delta", "Tmax", "total_work_h"],
        "waiting_allowed": False,
        "routes": route_records,
        "search_history": history,
        "validation": "PASSED",
    }


def write_csv_outputs(results: dict, output_dir: Path) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    with (output_dir / "summary.csv").open("w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f)
        w.writerow(["Case", "N", "Tmax_h", "Tmin_h", "delta_h", "total_work_h"])
        for case_name, result in results.items():
            w.writerow([case_name, result["N"], result["Tmax"], result["Tmin"], result["delta"], result["total_work_h"]])
    with (output_dir / "comparison.csv").open("w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f)
        w.writerow(["Case", "q1_delta_h", "q2_delta_h", "reduction_h", "reduction_pct"])
        for case_name, result in results.items():
            w.writerow([case_name, result["q1_delta_h"], result["delta"], result["delta_reduction_h"], result["delta_reduction_pct"]])
    for case_name, result in results.items():
        max_len = max(len(route["sequence"]) for route in result["routes"])
        headers = ["UAV_ID"] + [f"Stop_{i}" for i in range(1, max_len + 1)] + ["Distance_km", "Service_Count", "Working_Time_h"]
        with (output_dir / f"{case_name}_routes.csv").open("w", newline="", encoding="utf-8-sig") as f:
            w = csv.writer(f)
            w.writerow(headers)
            for route in result["routes"]:
                padding = [""] * (max_len - len(route["sequence"]))
                w.writerow([route["uav"], *route["sequence"], *padding, route["distance_km"], route["service_count"], route["time_h"]])


def validate_saved(input_path: Path, q1_path: Path, q2_path: Path) -> None:
    q1 = json.loads(q1_path.read_text(encoding="utf-8"))
    q2 = json.loads(q2_path.read_text(encoding="utf-8"))
    book = pd.ExcelFile(input_path)
    assert set(q1) == set(q2) == set(book.sheet_names)
    for case_name in book.sheet_names:
        data = load_case(book, case_name)
        routes = [route["sequence"][1:-1] for route in q2[case_name]["routes"]]
        distances, times = validate_case(case_name, routes, data, q1[case_name], q2[case_name]["epsilon_h"])
        assert abs(max(times) - q2[case_name]["Tmax"]) < 1.0e-8
        assert abs(min(times) - q2[case_name]["Tmin"]) < 1.0e-8
        for saved, distance, work_h in zip(q2[case_name]["routes"], distances, times):
            assert abs(saved["distance_km"] - distance) < 1.0e-8
            assert abs(saved["time_h"] - work_h) < 1.0e-8
            assert saved["waiting_time_h"] == 0.0


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--q1-solution", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--epsilon", type=float, default=0.0)
    parser.add_argument("--seeds", type=int, default=8)
    parser.add_argument("--iterations", type=int, default=30000)
    parser.add_argument("--time-limit-per-case", type=float, default=45.0)
    parser.add_argument("--validate-only", action="store_true")
    args = parser.parse_args()

    output_json = args.output_dir / "q2_solution.json"
    if args.validate_only:
        validate_saved(args.input, args.q1_solution, output_json)
        print("问题二保存结果独立校验通过。")
        return

    if args.epsilon < 0:
        raise ValueError("epsilon 必须非负")
    q1 = json.loads(args.q1_solution.read_text(encoding="utf-8"))
    book = pd.ExcelFile(args.input)
    results = {}
    for case_name in book.sheet_names:
        started = time.monotonic()
        data = load_case(book, case_name)
        results[case_name] = solve_case(
            case_name,
            data,
            q1[case_name],
            args.epsilon,
            args.seeds,
            args.iterations,
            args.time_limit_per_case,
        )
        r = results[case_name]
        print(
            f"{case_name}: N={r['N']} Tmax={r['Tmax']:.6f} "
            f"Tmin={r['Tmin']:.6f} delta={r['delta']:.6f} "
            f"elapsed={time.monotonic()-started:.1f}s",
            flush=True,
        )
    args.output_dir.mkdir(parents=True, exist_ok=True)
    output_json.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
    write_csv_outputs(results, args.output_dir)
    validate_saved(args.input, args.q1_solution, output_json)
    print(f"问题二全部校验通过：{output_json}")


if __name__ == "__main__":
    main()
