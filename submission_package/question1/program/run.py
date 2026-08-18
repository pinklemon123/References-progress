"""问题一统一入口：复核论文正式结果，或从附件 1 重新搜索。"""
from __future__ import annotations

import argparse
import json
import math
import os
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "src"))

# 多进程随机起点优先，避免每个工作进程再启动一组 BLAS/OpenMP 线程。
os.environ.setdefault("OMP_NUM_THREADS", "1")
os.environ.setdefault("OPENBLAS_NUM_THREADS", "1")
os.environ.setdefault("MKL_NUM_THREADS", "1")

import numpy as np
import pandas as pd
from scipy.optimize import linear_sum_assignment
from scipy.sparse.csgraph import minimum_spanning_tree

from uav_q1.exact_milp import result_as_dict, solve_fixed_n_exact
from uav_q1.excel_output import export_workbook
from uav_q1.solver_engine import REQ, SERVICE_H, SPEED, UNIT_KM, dist, rtime, solve
from uav_q1.validation import validate_all


def load_config() -> dict:
    return json.loads((ROOT / "config.json").read_text(encoding="utf-8"))


def pack_case(case_name: str, df: pd.DataFrame, routes: list[list[int]]) -> dict:
    points = df[["X_Coordinate", "Y_Coordinate"]].to_numpy(float)
    packed = []
    for uid, route in enumerate(routes, 1):
        point_ids = [int(df.iloc[i].Point_ID) for i in route]
        packed.append({
            "uav": uid,
            "sequence": [0, *point_ids, 0],
            "distance_km": dist(route, points) * UNIT_KM,
            "service_count": len(route),
            "time_h": rtime(route, points),
        })
    packed.sort(key=lambda x: x["time_h"], reverse=True)
    for uid, route in enumerate(packed, 1):
        route["uav"] = uid
    return {
        "N": len(packed),
        "Tmax": max(x["time_h"] for x in packed),
        "Tmin": min(x["time_h"] for x in packed),
        "routes": packed,
    }


def mst_lower_bound(df: pd.DataFrame, limit_h: float) -> int:
    points = df[["X_Coordinate", "Y_Coordinate"]].to_numpy(float)
    visits = df.Inspection_Level.map(REQ).to_numpy(int)
    augmented = np.vstack([[0.0, 0.0], points])
    matrix = np.linalg.norm(augmented[:, None, :] - augmented[None, :, :], axis=2) * UNIT_KM
    mst_km = float(minimum_spanning_tree(matrix).sum())
    total_lower_h = visits.sum() * SERVICE_H + mst_km / SPEED
    return max(1, math.ceil(total_lower_h / limit_h - 1e-12))


def _cycle_cover_lower_bound_km(df: pd.DataFrame, n_uav: int) -> float:
    """任务副本循环覆盖松弛；同物理点副本间以及基地副本间禁止直连。"""
    physical = np.repeat(
        np.arange(len(df), dtype=int),
        df.Inspection_Level.map(REQ).to_numpy(int),
    )
    points = df[["X_Coordinate", "Y_Coordinate"]].to_numpy(float)
    task_xy = points[physical]
    m = len(physical)
    size = m + int(n_uav)
    large = 1.0e12
    cost = np.full((size, size), large, dtype=float)
    task_cost = np.linalg.norm(task_xy[:, None, :] - task_xy[None, :, :], axis=2) * UNIT_KM
    task_cost[physical[:, None] == physical[None, :]] = large
    cost[:m, :m] = task_cost
    depot = np.linalg.norm(task_xy, axis=1) * UNIT_KM
    cost[:m, m:] = depot[:, None]
    cost[m:, :m] = depot[None, :]
    row, col = linear_sum_assignment(cost)
    chosen = cost[row, col]
    return math.inf if np.any(chosen >= large / 2) else float(chosen.sum())


def strong_lower_bound(df: pd.DataFrame, limit_h: float) -> dict:
    points = df[["X_Coordinate", "Y_Coordinate"]].to_numpy(float)
    demand = df.Inspection_Level.map(REQ).to_numpy(int)
    augmented = np.vstack([[0.0, 0.0], points])
    matrix_units = np.linalg.norm(augmented[:, None, :] - augmented[None, :, :], axis=2)
    mst_km = float(minimum_spanning_tree(matrix_units).sum()) * UNIT_KM
    repeated_degree_units = 0.0
    for idx, count in enumerate(demand, start=1):
        incident = np.delete(matrix_units[idx], idx)
        repeated_degree_units += int(count) * float(np.partition(incident, 1)[:2].sum())
    repeated_degree_km = repeated_degree_units * UNIT_KM / 2.0
    service_h = float(demand.sum()) * SERVICE_H
    farthest_h = float(np.max(2.0 * matrix_units[0, 1:] * UNIT_KM / SPEED + SERVICE_H))
    n = max(1, math.ceil(service_h / limit_h - 1e-12))
    while True:
        cycle_km = _cycle_cover_lower_bound_km(df, n)
        routing_km = max(mst_km, repeated_degree_km, cycle_km)
        aggregate_h = service_h + routing_km / SPEED
        makespan_lb = max(aggregate_h / n, farthest_h)
        if makespan_lb <= limit_h + 1e-12:
            break
        n += 1
    return {
        "N": int(n),
        "service_hours": service_h,
        "mst_km": mst_km,
        "repeated_degree_km": repeated_degree_km,
        "cycle_cover_km": cycle_km,
        "aggregate_work_hours": aggregate_h,
        "makespan_lower_bound_at_N": makespan_lb,
        "farthest_roundtrip_lower_bound_hours": farthest_h,
    }


def routes_from_saved(df: pd.DataFrame, case: dict) -> list[list[int]]:
    id_to_index = {int(row.Point_ID): i for i, row in df.iterrows()}
    routes = []
    for route in case["routes"]:
        routes.append([id_to_index[int(point_id)] for point_id in route["sequence"] if int(point_id) != 0])
    return routes


def solve_from_scratch(input_path: Path, quality: str, engine: str, config: dict) -> dict:
    book = pd.ExcelFile(input_path)
    results = {}
    seeds = int(config["quality_seeds"][quality])
    for case_name in book.sheet_names:
        df = pd.read_excel(book, sheet_name=case_name)
        lower = mst_lower_bound(df, float(config["maximum_work_hours"]))
        n = lower
        limit_h = float(config["maximum_work_hours"])
        max_n = lower + int(config.get("maximum_n_increment", 6))
        history = []
        all_smaller_proven_infeasible = True
        print(f"[{case_name}] strict search starts at lower bound N={n}; quality={quality}; engine={engine}", flush=True)
        while n <= max_n:
            heuristic_routes = None
            heuristic_obj = None
            if engine in {"heuristic", "hybrid"}:
                (heuristic_obj, heuristic_routes), _, _ = solve(case_name, df, n, seeds=seeds)
                print(f"[{case_name}] N={n}, heuristic best Tmax={heuristic_obj:.6f} h", flush=True)
                record = {
                    "N": n,
                    "heuristic_best_Tmax": float(heuristic_obj),
                    "heuristic_feasible": bool(heuristic_obj <= limit_h + 1e-9),
                }
                history.append(record)
                if heuristic_obj <= limit_h + 1e-9:
                    case = pack_case(case_name, df, heuristic_routes)
                    case["theoretical_lower_bound_N"] = lower
                    case["fleet_size_status"] = (
                        "PROVEN_MINIMUM" if all_smaller_proven_infeasible else "FEASIBLE_CANDIDATE"
                    )
                    case["makespan_status"] = "BEST_FOUND_NOT_PROVEN_OPTIMAL"
                    case["search_history"] = history
                    results[case_name] = case
                    break

            if engine in {"exact", "hybrid"}:
                exact = solve_fixed_n_exact(
                    df,
                    n,
                    limit_h=limit_h,
                    time_limit_s=float(config.get("exact_time_limit_seconds", 300)),
                    mip_rel_gap=float(config.get("exact_mip_relative_gap", 0.0)),
                )
                exact_record = result_as_dict(exact)
                exact_record["N"] = n
                if history and history[-1].get("N") == n:
                    history[-1]["exact"] = exact_record
                else:
                    history.append({"N": n, "exact": exact_record})
                print(f"[{case_name}] N={n}, exact status={exact.status}, objective={exact.objective_h}", flush=True)
                if exact.status in {"OPTIMAL", "FEASIBLE"} and exact.routes is not None:
                    case = pack_case(case_name, df, exact.routes)
                    case["theoretical_lower_bound_N"] = lower
                    case["fleet_size_status"] = (
                        "PROVEN_MINIMUM" if all_smaller_proven_infeasible else "FEASIBLE_CANDIDATE"
                    )
                    case["makespan_status"] = (
                        "PROVEN_OPTIMAL" if exact.status == "OPTIMAL" else "FEASIBLE_NOT_PROVEN_OPTIMAL"
                    )
                    case["search_history"] = history
                    results[case_name] = case
                    break
                if exact.status != "INFEASIBLE":
                    # UNKNOWN 不能当作不可行；继续向上寻找只会得到可行上界。
                    all_smaller_proven_infeasible = False
            else:
                # 启发式失败也不能当作不可行证明。
                all_smaller_proven_infeasible = False
            n += 1
        else:
            raise RuntimeError(
                f"{case_name}: 在 N={lower}..{max_n} 内没有找到可行方案；"
                "请提高搜索质量、精确求解时限或 maximum_n_increment"
            )
    return results


def run_ten_minute_plan(
    input_path: Path,
    config: dict,
    total_seconds: float,
    workers: int,
    candidate_k: int,
    resume_from: Path | None = None,
) -> tuple[dict, dict]:
    """在统一墙钟预算内验证热启动并并行改善四个固定车队规模。"""
    started = time.monotonic()
    deadline = started + float(total_seconds)
    reserve = min(float(config.get("ten_minute_save_reserve_seconds", 45)), total_seconds * 0.2)
    saved_results = json.loads((ROOT.parent / "results" / "solution.json").read_text(encoding="utf-8"))
    validate_all(input_path, saved_results, config)
    if resume_from is not None:
        resumed = json.loads(resume_from.read_text(encoding="utf-8"))
        validate_all(input_path, resumed, config)
        saved_results = resumed
        print(f"续搜方案独立校验通过：{resume_from}", flush=True)
    else:
        print("已有 4,2,5,4 方案独立校验通过；开始强下界与并行改进。", flush=True)

    book = pd.ExcelFile(input_path)
    weights = {k: float(v) for k, v in config.get("ten_minute_case_weights", {}).items()}
    process_order = [name for name in ["Case2", "Case4", "Case1", "Case3"] if name in book.sheet_names]
    improved: dict[str, dict] = {}
    report = {
        "mode": "ten-minute",
        "requested_total_seconds": float(total_seconds),
        "workers": int(workers),
        "candidate_neighborhood_size": int(candidate_k),
        "gpu_used": False,
        "cases": {},
    }

    for position, case_name in enumerate(process_order):
        df = pd.read_excel(book, sheet_name=case_name)
        lower = strong_lower_bound(df, float(config["maximum_work_hours"]))
        initial = saved_results[case_name]
        n_uav = int(initial["N"])
        if n_uav < int(lower["N"]):
            raise AssertionError(f"{case_name}: 已有 N={n_uav} 小于严格下界 {lower['N']}")
        warm_routes = routes_from_saved(df, initial)
        prior_history = list(initial.get("search_history", []))
        original_warm_tmax = float(initial.get("warm_start_Tmax", initial["Tmax"]))

        now = time.monotonic()
        usable = max(1.0, deadline - now - reserve)
        remaining_names = process_order[position:]
        denominator = sum(weights.get(name, 1.0) for name in remaining_names)
        budget = max(1.0, usable * weights.get(case_name, 1.0) / max(denominator, 1e-9))
        status = "PROVEN_MINIMUM" if n_uav == int(lower["N"]) else "FEASIBLE_CANDIDATE"
        print(
            f"[{case_name}] strict lower bound={lower['N']}, fixed N={n_uav}, "
            f"fleet status={status}, search budget={budget:.1f}s, workers={workers}",
            flush=True,
        )
        case_started = time.monotonic()
        (obj, routes), _, _, history = solve(
            case_name,
            df,
            n_uav,
            seeds=4096,
            time_limit_s=budget,
            workers=workers,
            warm_routes=warm_routes,
            candidate_k=candidate_k,
            progress=True,
            return_history=True,
        )
        packed = pack_case(case_name, df, routes)
        packed["theoretical_lower_bound_N"] = int(lower["N"])
        packed["lower_bound_details"] = lower
        packed["fleet_size_status"] = status
        packed["makespan_status"] = "BEST_FOUND_NOT_PROVEN_OPTIMAL"
        packed["search_history"] = prior_history + history
        packed["warm_start_Tmax"] = original_warm_tmax
        packed["improvement_hours"] = float(original_warm_tmax - packed["Tmax"])
        improved[case_name] = packed
        report["cases"][case_name] = {
            "N": n_uav,
            "lower_bound": lower,
            "fleet_size_status": status,
            "budget_seconds": budget,
            "actual_seconds": time.monotonic() - case_started,
            "warm_start_Tmax": original_warm_tmax,
            "resume_input_Tmax": float(initial["Tmax"]),
            "best_Tmax": float(packed["Tmax"]),
            "improvement_hours": float(original_warm_tmax - packed["Tmax"]),
            "completed_starts_this_run": len([x for x in history if x.get("seed") is not None]),
            "completed_starts": len([x for x in prior_history + history if x.get("seed") is not None]),
        }

    ordered = {name: improved[name] for name in book.sheet_names}
    validate_all(input_path, ordered, config)
    report["elapsed_seconds"] = time.monotonic() - started
    report["validation"] = "PASSED"
    return ordered, report


def main() -> None:
    parser = argparse.ArgumentParser(description="多无人机协同巡检问题一求解器")
    parser.add_argument(
        "--mode",
        choices=["reproduce", "reproduce-final", "search", "solve", "ten-minute"],
        default="reproduce-final",
        help=(
            "reproduce/reproduce-final 复核论文正式路线；search/solve 重新搜索；"
            "ten-minute 按统一短时预算并行改进"
        ),
    )
    parser.add_argument("--quality", choices=["fast", "standard", "thorough"], default="standard")
    parser.add_argument("--engine", choices=["heuristic", "hybrid", "exact"], default="hybrid",
                        help="heuristic 仅搜索；hybrid 搜索失败后精确判定；exact 仅精确 MILP")
    parser.add_argument("--total-time-limit", type=float, default=None, metavar="SECONDS",
                        help="ten-minute 模式的统一墙钟预算，默认读取 config.json")
    parser.add_argument("--workers", type=int, default=None,
                        help="并行随机起点进程数，默认读取 config.json")
    parser.add_argument("--candidate-k", type=int, default=None,
                        help="候选近邻数量，默认读取 config.json")
    parser.add_argument("--input", type=Path, default=ROOT / "input" / "附件1.xlsx")
    parser.add_argument("--output-dir", type=Path, default=None)
    parser.add_argument("--resume-from", type=Path, default=None,
                        help="ten-minute 模式从已校验的 solution.json 继续热启动搜索")
    args = parser.parse_args()

    config = load_config()
    report = None
    if args.mode in {"reproduce", "reproduce-final"}:
        results = json.loads((ROOT.parent / "results" / "solution.json").read_text(encoding="utf-8"))
    elif args.mode in {"search", "solve"}:
        results = solve_from_scratch(args.input, args.quality, args.engine, config)
    else:
        total_seconds = float(
            args.total_time_limit
            if args.total_time_limit is not None
            else config.get("ten_minute_total_seconds", 600)
        )
        workers = int(args.workers if args.workers is not None else config.get("parallel_workers", 4))
        candidate_k = int(
            args.candidate_k
            if args.candidate_k is not None
            else config.get("candidate_neighborhood_size", 24)
        )
        if total_seconds <= 30 or workers < 1 or candidate_k < 1:
            parser.error("ten-minute 参数要求总时间>30 秒、workers>=1、candidate-k>=1")
        os.environ["LOKY_MAX_CPU_COUNT"] = str(workers)
        results, report = run_ten_minute_plan(
            args.input, config, total_seconds, workers, candidate_k, args.resume_from
        )

    validate_all(args.input, results, config)
    output_dir = args.output_dir or (ROOT / ("outputs_10min" if args.mode == "ten-minute" else "outputs"))
    output_dir.mkdir(parents=True, exist_ok=True)
    json_path = output_dir / "solution.json"
    xlsx_path = output_dir / "result1.xlsx"
    json_path.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
    export_workbook(results, xlsx_path, config)
    if report is not None:
        (output_dir / "search_report.json").write_text(
            json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
        )
    print(f"Validation passed.\nJSON: {json_path}\nExcel: {xlsx_path}")


if __name__ == "__main__":
    main()
