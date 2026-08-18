"""固定无人机数量下的精确 MILP 模型。

该模块不替代快速启发式算法，而是用于区分：

* OPTIMAL：已证明固定 N 下的最优最长工作时间；
* INFEASIBLE：已证明固定 N 无法在 9 小时内完成；
* FEASIBLE：时限内得到可行解，但尚未证明最优；
* UNKNOWN：时限内既没有可行解，也没有不可行证明。

模型把每一次巡检展开成一个任务副本。同一物理点的任务副本之间不建立
直接弧，因此同一无人机不能靠原地停留重复计数，但可以在访问其他点后返回。
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np
import pandas as pd
from scipy.optimize import Bounds, LinearConstraint, milp
from scipy.sparse import coo_matrix

from .solver_engine import REQ, SERVICE_H, SPEED, UNIT_KM, rtime


@dataclass
class ExactResult:
    status: str
    message: str
    routes: list[list[int]] | None
    objective_h: float | None
    dual_bound_h: float | None
    mip_gap: float | None
    node_count: int | None


class _Rows:
    """稀疏线性约束构造器。"""

    def __init__(self) -> None:
        self.row: list[int] = []
        self.col: list[int] = []
        self.data: list[float] = []
        self.lb: list[float] = []
        self.ub: list[float] = []

    def add(self, terms: dict[int, float], lb: float, ub: float) -> None:
        rid = len(self.lb)
        for col, value in terms.items():
            if abs(value) > 1e-15:
                self.row.append(rid)
                self.col.append(col)
                self.data.append(float(value))
        self.lb.append(float(lb))
        self.ub.append(float(ub))

    def constraint(self, nvar: int) -> LinearConstraint:
        matrix = coo_matrix(
            (self.data, (self.row, self.col)),
            shape=(len(self.lb), nvar),
        ).tocsr()
        return LinearConstraint(matrix, np.asarray(self.lb), np.asarray(self.ub))


def _task_copies(df: pd.DataFrame) -> tuple[np.ndarray, np.ndarray]:
    """返回每个任务副本对应的物理行号和坐标。"""
    physical: list[int] = []
    for i, level in enumerate(df["Inspection_Level"]):
        physical.extend([i] * REQ[str(level)])
    physical_arr = np.asarray(physical, dtype=int)
    points = df[["X_Coordinate", "Y_Coordinate"]].to_numpy(float)
    return physical_arr, points[physical_arr]


def solve_fixed_n_exact(
    df: pd.DataFrame,
    n_uav: int,
    limit_h: float = 9.0,
    time_limit_s: float = 300.0,
    mip_rel_gap: float = 0.0,
) -> ExactResult:
    """用完整弧集 MILP 求固定 ``n_uav`` 的 min-max 路径。

    SciPy/HiGHS 返回 status=2 时才记为严格不可行。达到时限且没有解时记为
    UNKNOWN，程序不得据此排除当前 N。
    """
    physical, task_xy = _task_copies(df)
    m = len(physical)
    if n_uav < 1 or n_uav > m:
        raise ValueError("n_uav 必须位于 1 和任务副本总数之间")

    # 节点 0 为基地；1..m 为任务副本。相同物理点的副本之间禁止直接转移。
    xy = np.vstack([[0.0, 0.0], task_xy])
    arcs: list[tuple[int, int]] = []
    for i in range(m + 1):
        for j in range(m + 1):
            if i == j or (i == 0 and j == 0):
                continue
            if i > 0 and j > 0 and physical[i - 1] == physical[j - 1]:
                continue
            arcs.append((i, j))
    a_count = len(arcs)
    out_arcs: list[list[int]] = [[] for _ in range(m + 1)]
    in_arcs: list[list[int]] = [[] for _ in range(m + 1)]
    for a, (i, j) in enumerate(arcs):
        out_arcs[i].append(a)
        in_arcs[j].append(a)

    # 变量块：[x 二元弧][f 连续单商品流][y 二元分配][Cmax]。
    x0 = 0
    f0 = n_uav * a_count
    y0 = f0 + n_uav * a_count
    c_idx = y0 + n_uav * m
    nvar = c_idx + 1

    def xid(k: int, a: int) -> int:
        return x0 + k * a_count + a

    def fid(k: int, a: int) -> int:
        return f0 + k * a_count + a

    def yid(k: int, i: int) -> int:
        # i 是 1..m 的任务节点号。
        return y0 + k * m + (i - 1)

    c = np.zeros(nvar)
    c[c_idx] = 1.0
    integrality = np.zeros(nvar, dtype=np.uint8)
    integrality[x0:f0] = 1
    integrality[y0:c_idx] = 1
    lower = np.zeros(nvar)
    upper = np.full(nvar, np.inf)
    upper[x0:f0] = 1.0
    upper[f0:y0] = float(m)
    upper[y0:c_idx] = 1.0
    upper[c_idx] = float(limit_h)

    rows = _Rows()

    # 每个任务副本恰由一架无人机完成。
    for i in range(1, m + 1):
        rows.add({yid(k, i): 1.0 for k in range(n_uav)}, 1.0, 1.0)

    # 每架无人机都从基地出发一次并返回一次；任务点入度=出度=分配变量。
    for k in range(n_uav):
        rows.add({xid(k, a): 1.0 for a in out_arcs[0]}, 1.0, 1.0)
        rows.add({xid(k, a): 1.0 for a in in_arcs[0]}, 1.0, 1.0)
        for i in range(1, m + 1):
            out_terms = {xid(k, a): 1.0 for a in out_arcs[i]}
            out_terms[yid(k, i)] = -1.0
            rows.add(out_terms, 0.0, 0.0)
            in_terms = {xid(k, a): 1.0 for a in in_arcs[i]}
            in_terms[yid(k, i)] = -1.0
            rows.add(in_terms, 0.0, 0.0)

    # 单商品流消除不经过基地的子回路。
    for k in range(n_uav):
        depot_terms: dict[int, float] = {}
        for a in out_arcs[0]:
            depot_terms[fid(k, a)] = depot_terms.get(fid(k, a), 0.0) + 1.0
        for a in in_arcs[0]:
            depot_terms[fid(k, a)] = depot_terms.get(fid(k, a), 0.0) - 1.0
        for i in range(1, m + 1):
            depot_terms[yid(k, i)] = -1.0
        rows.add(depot_terms, 0.0, 0.0)

        for i in range(1, m + 1):
            terms: dict[int, float] = {yid(k, i): -1.0}
            for a in in_arcs[i]:
                terms[fid(k, a)] = terms.get(fid(k, a), 0.0) + 1.0
            for a in out_arcs[i]:
                terms[fid(k, a)] = terms.get(fid(k, a), 0.0) - 1.0
            rows.add(terms, 0.0, 0.0)

        for a in range(a_count):
            rows.add({fid(k, a): 1.0, xid(k, a): -float(m)}, -np.inf, 0.0)

    arc_time = np.asarray([
        np.linalg.norm(xy[i] - xy[j]) * UNIT_KM / SPEED for i, j in arcs
    ])

    def time_terms(k: int) -> dict[int, float]:
        terms = {xid(k, a): float(arc_time[a]) for a in range(a_count)}
        for i in range(1, m + 1):
            terms[yid(k, i)] = SERVICE_H
        return terms

    # Cmax 上界已经固定为 9 小时；同时以 Cmax 为第二阶段目标。
    all_time_terms = [time_terms(k) for k in range(n_uav)]
    for terms in all_time_terms:
        terms = dict(terms)
        terms[c_idx] = -1.0
        rows.add(terms, -np.inf, 0.0)

    # 对同质无人机按工作时长降序编号，削减车辆置换对称性。
    for k in range(n_uav - 1):
        terms = dict(all_time_terms[k + 1])
        for idx, value in all_time_terms[k].items():
            terms[idx] = terms.get(idx, 0.0) - value
        rows.add(terms, -np.inf, 0.0)

    # 同一物理点的副本无差别：按所分配的无人机编号排序，削减副本对称性。
    for p in np.unique(physical):
        copies = np.flatnonzero(physical == p) + 1
        for left, right in zip(copies[:-1], copies[1:]):
            terms: dict[int, float] = {}
            for k in range(n_uav):
                terms[yid(k, int(left))] = float(k)
                terms[yid(k, int(right))] = -float(k)
            rows.add(terms, -np.inf, 0.0)

    result = milp(
        c=c,
        integrality=integrality,
        bounds=Bounds(lower, upper),
        constraints=rows.constraint(nvar),
        options={
            "time_limit": float(time_limit_s),
            "mip_rel_gap": float(mip_rel_gap),
            "presolve": True,
        },
    )

    status_map = {0: "OPTIMAL", 1: "LIMIT", 2: "INFEASIBLE", 3: "UNBOUNDED", 4: "ERROR"}
    raw_status = status_map.get(int(result.status), "ERROR")
    if raw_status == "INFEASIBLE":
        return ExactResult("INFEASIBLE", result.message, None, None,
                           getattr(result, "mip_dual_bound", None),
                           getattr(result, "mip_gap", None),
                           getattr(result, "mip_node_count", None))
    if result.x is None:
        return ExactResult("UNKNOWN", result.message, None, None,
                           getattr(result, "mip_dual_bound", None),
                           getattr(result, "mip_gap", None),
                           getattr(result, "mip_node_count", None))

    vector = np.asarray(result.x)
    routes: list[list[int]] = []
    for k in range(n_uav):
        route: list[int] = []
        current = 0
        for _ in range(m + 1):
            chosen = [a for a in out_arcs[current] if vector[xid(k, a)] > 0.5]
            if len(chosen) != 1:
                return ExactResult("UNKNOWN", "MILP 解的弧结构无法提取为单一路线", None,
                                   None, getattr(result, "mip_dual_bound", None),
                                   getattr(result, "mip_gap", None),
                                   getattr(result, "mip_node_count", None))
            _, nxt = arcs[chosen[0]]
            if nxt == 0:
                break
            route.append(int(physical[nxt - 1]))
            current = nxt
        else:
            return ExactResult("UNKNOWN", "路线提取超过任务节点数", None, None,
                               getattr(result, "mip_dual_bound", None),
                               getattr(result, "mip_gap", None),
                               getattr(result, "mip_node_count", None))
        routes.append(route)

    physical_points = df[["X_Coordinate", "Y_Coordinate"]].to_numpy(float)
    objective = max(rtime(route, physical_points) for route in routes)
    final_status = "OPTIMAL" if raw_status == "OPTIMAL" else "FEASIBLE"
    return ExactResult(final_status, result.message, routes, objective,
                       getattr(result, "mip_dual_bound", None),
                       getattr(result, "mip_gap", None),
                       getattr(result, "mip_node_count", None))


def result_as_dict(result: ExactResult) -> dict[str, Any]:
    def number(value: Any) -> float | int | None:
        if value is None:
            return None
        if isinstance(value, (int, np.integer)):
            return int(value)
        return float(value)

    return {
        "status": result.status,
        "message": result.message,
        "objective_h": number(result.objective_h),
        "dual_bound_h": number(result.dual_bound_h),
        "mip_gap": number(result.mip_gap),
        "node_count": number(result.node_count),
    }
