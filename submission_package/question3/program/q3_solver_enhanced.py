"""问题三算法B：时变圆形禁飞区下的分层增强求解器。

与基准算法的区别：
1. 每次巡检使用唯一任务副本编号；
2. 对受阻转场比较“等待后直飞”和“边界离散可见图绕飞”；
3. 阶段A只搜索最小 Tmax，阶段B在给定 epsilon 容差内搜索最小 delta；
4. 固定问题二机队规模是正式方案，额外无人机仅作为敏感性分析。

圆边界用外扩采样环及直线弦近似。采样环半径除以 cos(pi/m)，保证相邻弦
不进入原禁飞圆内部；所有最终飞行事件仍由解析线段—圆—时间区间复核。
"""

from __future__ import annotations

import argparse
import csv
import heapq
import json
import math
import random
import time
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path

import q3_solver as baseline


TOL = 1.0e-9


@dataclass(frozen=True)
class GeoNode:
    label: str
    xy: tuple[float, float]


def task_point(task_id: str) -> int:
    return int(task_id.split("#", 1)[0][1:])


def build_unique_copies(initial_physical: list[list[int]]) -> tuple[list[list[str]], dict[str, int]]:
    counters: defaultdict[int, int] = defaultdict(int)
    mapping: dict[str, int] = {}
    routes: list[list[str]] = []
    for route in initial_physical:
        copies: list[str] = []
        for point in route:
            counters[point] += 1
            task_id = f"P{point:03d}#{counters[point]}"
            mapping[task_id] = point
            copies.append(task_id)
        routes.append(copies)
    return routes, mapping


def expected_copy_ids(data: baseline.CaseData) -> set[str]:
    return {
        f"P{point:03d}#{copy_no}"
        for point, count in data.expected_visits.items()
        for copy_no in range(1, count + 1)
    }


def valid_copy_route(route: list[str], mapping: dict[str, int]) -> bool:
    if not route:
        return False
    physical = [mapping[item] for item in route]
    return all(a != b for a, b in zip(physical, physical[1:]))


def validate_copy_routes(
    routes: list[list[str]], data: baseline.CaseData, mapping: dict[str, int]
) -> None:
    flat = [item for route in routes for item in route]
    assert len(flat) == len(set(flat)), "任务副本编号重复"
    assert set(flat) == expected_copy_ids(data), "任务副本缺失或多余"
    assert set(mapping) == expected_copy_ids(data)
    assert all(valid_copy_route(route, mapping) for route in routes)


def point_segment_distance(
    p: tuple[float, float], a: tuple[float, float], b: tuple[float, float]
) -> float:
    dx, dy = b[0] - a[0], b[1] - a[1]
    denom = dx * dx + dy * dy
    if denom <= TOL:
        return math.dist(p, a)
    lam = ((p[0] - a[0]) * dx + (p[1] - a[1]) * dy) / denom
    lam = min(1.0, max(0.0, lam))
    q = (a[0] + lam * dx, a[1] + lam * dy)
    return math.dist(p, q)


class DetourRouter:
    def __init__(
        self,
        data: baseline.CaseData,
        ring_samples: int = 16,
        safety_margin: float = 0.0,
    ) -> None:
        if ring_samples < 8:
            raise ValueError("ring_samples 至少为 8")
        self.data = data
        self.ring_samples = ring_samples
        self.safety_margin = safety_margin
        self.path_cache: dict[tuple[int, int, tuple[int, ...]], list[GeoNode] | None] = {}

    def _zone_radius(self, zone: baseline.Zone) -> float:
        return zone.radius + self.safety_margin

    def _static_clear(
        self,
        a: tuple[float, float],
        b: tuple[float, float],
        obstacle_indices: tuple[int, ...],
    ) -> bool:
        for index in obstacle_indices:
            zone = self.data.zones[index]
            radius = self._zone_radius(zone)
            if point_segment_distance(zone.center, a, b) < radius - 1.0e-8:
                return False
        return True

    def _ring_nodes(self, obstacle_indices: tuple[int, ...]) -> list[GeoNode]:
        nodes: list[GeoNode] = []
        inflation = 1.0 / math.cos(math.pi / self.ring_samples)
        for index in obstacle_indices:
            zone = self.data.zones[index]
            radius = self._zone_radius(zone) * inflation + 1.0e-6
            for sample in range(self.ring_samples):
                angle = 2.0 * math.pi * sample / self.ring_samples
                xy = (
                    zone.center[0] + radius * math.cos(angle),
                    zone.center[1] + radius * math.sin(angle),
                )
                # 位于其他同时考虑的圆内部的采样点不能作为安全转向点。
                if any(
                    other != index
                    and math.dist(xy, self.data.zones[other].center)
                    < self._zone_radius(self.data.zones[other]) - 1.0e-8
                    for other in obstacle_indices
                ):
                    continue
                nodes.append(GeoNode(f"Z{index + 1}:B{sample}", xy))
        return nodes

    def _static_detour(
        self,
        a_id: int,
        b_id: int,
        obstacles: tuple[int, ...],
    ) -> list[GeoNode] | None:
        key = (a_id, b_id, obstacles)
        if key in self.path_cache:
            return self.path_cache[key]
        source = GeoNode(f"P{a_id}", self.data.coordinates[a_id])
        target = GeoNode(f"P{b_id}", self.data.coordinates[b_id])
        nodes = [source, target, *self._ring_nodes(obstacles)]
        if any(
            math.dist(source.xy, self.data.zones[index].center)
            < self._zone_radius(self.data.zones[index]) - 1.0e-8
            or math.dist(target.xy, self.data.zones[index].center)
            < self._zone_radius(self.data.zones[index]) - 1.0e-8
            for index in obstacles
        ):
            self.path_cache[key] = None
            return None

        adjacency: list[list[tuple[int, float]]] = [[] for _ in nodes]
        for i in range(len(nodes)):
            for j in range(i + 1, len(nodes)):
                if self._static_clear(nodes[i].xy, nodes[j].xy, obstacles):
                    distance = math.dist(nodes[i].xy, nodes[j].xy)
                    adjacency[i].append((j, distance))
                    adjacency[j].append((i, distance))

        dist = [math.inf] * len(nodes)
        previous = [-1] * len(nodes)
        dist[0] = 0.0
        heap: list[tuple[float, int]] = [(0.0, 0)]
        while heap:
            current, u = heapq.heappop(heap)
            if current > dist[u] + TOL:
                continue
            if u == 1:
                break
            for v, weight in adjacency[u]:
                candidate = current + weight
                if candidate < dist[v] - TOL:
                    dist[v] = candidate
                    previous[v] = u
                    heapq.heappush(heap, (candidate, v))
        if not math.isfinite(dist[1]):
            self.path_cache[key] = None
            return None
        order: list[int] = []
        cursor = 1
        while cursor >= 0:
            order.append(cursor)
            if cursor == 0:
                break
            cursor = previous[cursor]
        path = [nodes[index] for index in reversed(order)]
        self.path_cache[key] = path
        return path

    def _simulate_polyline(
        self,
        nodes: list[GeoNode],
        ready: float,
        service_at_target: bool,
        source_is_base: bool,
        mode: str,
    ) -> dict | None:
        now = ready
        total_distance = 0.0
        events: list[dict] = []
        for index, (left, right) in enumerate(zip(nodes, nodes[1:])):
            distance_km = math.dist(left.xy, right.xy) * baseline.UNIT_KM
            travel_min = distance_km / baseline.SPEED_KMH * 60.0
            last = index == len(nodes) - 2
            blocks = baseline.departure_blocks(
                left.xy,
                right.xy,
                travel_min,
                service_at_target and last,
                self.data.zones,
            )
            depart, reasons = baseline.earliest_departure(now, blocks)
            allow_base_wait = source_is_base and index == 0
            node_number = 0 if allow_base_wait else -1
            if not baseline.wait_is_safe(node_number, left.xy, now, depart, self.data.zones):
                return None
            if depart > now + TOL:
                events.append(
                    {
                        "type": "wait",
                        "node_label": left.label,
                        "node_xy": list(left.xy),
                        "start_min": now,
                        "end_min": depart,
                        "duration_min": depart - now,
                        "reason_zone_ids": reasons,
                        "mode": mode,
                    }
                )
            arrival = depart + travel_min
            events.append(
                {
                    "type": "flight",
                    "from_label": left.label,
                    "to_label": right.label,
                    "from_xy": list(left.xy),
                    "to_xy": list(right.xy),
                    "start_min": depart,
                    "end_min": arrival,
                    "duration_min": travel_min,
                    "distance_km": distance_km,
                    "mode": mode,
                }
            )
            total_distance += distance_km
            now = arrival
        return {
            "arrival_min": now,
            "distance_km": total_distance,
            "events": events,
            "mode": mode,
        }

    def travel(
        self,
        a_id: int,
        b_id: int,
        ready: float,
        service_at_target: bool,
    ) -> dict | None:
        direct_nodes = [
            GeoNode(f"P{a_id}", self.data.coordinates[a_id]),
            GeoNode(f"P{b_id}", self.data.coordinates[b_id]),
        ]
        direct = self._simulate_polyline(
            direct_nodes,
            ready,
            service_at_target,
            a_id == 0,
            "direct_or_wait",
        )
        if direct is not None and not any(event["type"] == "wait" for event in direct["events"]):
            return direct

        horizon = direct["arrival_min"] if direct is not None else max(
            (zone.end_min for zone in self.data.zones if zone.active), default=ready
        )
        obstacles = tuple(
            index
            for index, zone in enumerate(self.data.zones)
            if zone.active
            and baseline.overlaps(ready, max(ready + TOL, horizon), zone.start_min, zone.end_min)
        )
        detour = None
        if obstacles:
            path = self._static_detour(a_id, b_id, obstacles)
            if path is not None and len(path) > 2:
                detour = self._simulate_polyline(
                    path,
                    ready,
                    service_at_target,
                    a_id == 0,
                    "boundary_visibility_detour",
                )
        candidates = [item for item in (direct, detour) if item is not None]
        if not candidates:
            return None
        return min(candidates, key=lambda item: (item["arrival_min"], item["distance_km"]))


def _schedule_copy_route_with_detours(
    route: list[str],
    mapping: dict[str, int],
    data: baseline.CaseData,
    router: DetourRouter,
) -> dict | None:
    if not valid_copy_route(route, mapping):
        return None
    now = 0.0
    distance_km = 0.0
    events: list[dict] = []
    physical = [mapping[item] for item in route]
    point_sequence = [0, *physical, 0]
    task_sequence = ["BASE", *route, "BASE"]
    for leg, (a_id, b_id) in enumerate(zip(point_sequence, point_sequence[1:]), start=1):
        movement = router.travel(a_id, b_id, now, b_id != 0)
        if movement is None:
            return None
        for event in movement["events"]:
            event = {"leg": leg, **event}
            events.append(event)
        now = movement["arrival_min"]
        distance_km += movement["distance_km"]
        if b_id != 0:
            task_id = route[leg - 1]
            events.append(
                {
                    "type": "service",
                    "task_id": task_id,
                    "point_id": b_id,
                    "node_xy": list(data.coordinates[b_id]),
                    "start_min": now,
                    "end_min": now + baseline.SERVICE_MIN,
                    "duration_min": baseline.SERVICE_MIN,
                }
            )
            now += baseline.SERVICE_MIN
    wait_min = sum(event["duration_min"] for event in events if event["type"] == "wait")
    detour_legs = len(
        {
            event["leg"]
            for event in events
            if event["type"] == "flight" and event.get("mode") == "boundary_visibility_detour"
        }
    )
    return {
        "sequence": point_sequence,
        "task_sequence": task_sequence,
        "distance_km": distance_km,
        "service_count": len(route),
        "flight_time_h": distance_km / baseline.SPEED_KMH,
        "wait_time_h": wait_min / 60.0,
        "time_h": now / 60.0,
        "return_clock": baseline.min_to_clock(now),
        "detour_leg_count": detour_legs,
        "used_baseline_handoff_fallback": False,
        "events": events,
    }


def _baseline_handoff_fallback(
    route: list[str], mapping: dict[str, int], data: baseline.CaseData
) -> dict | None:
    """当逐航段绕飞评价陷入不安全驻留时，使用基准算法的反向等待传播。"""
    physical = [mapping[item] for item in route]
    scheduled = baseline.schedule_route(physical, data)
    if scheduled is None:
        safe_release = max((zone.end_min for zone in data.zones if zone.active), default=0.0)
        scheduled = baseline.schedule_route(physical, data, release_min=safe_release)
    if scheduled is None:
        return None
    service_cursor = 0
    converted: list[dict] = []
    for event in scheduled["events"]:
        item = dict(event)
        if event["type"] == "flight":
            a_id, b_id = int(event["from"]), int(event["to"])
            item.update(
                {
                    "from_label": f"P{a_id}",
                    "to_label": f"P{b_id}",
                    "from_xy": list(data.coordinates[a_id]),
                    "to_xy": list(data.coordinates[b_id]),
                    "mode": "direct_with_backward_handoff",
                }
            )
        elif event["type"] == "wait":
            node = int(event["node"])
            item.update(
                {
                    "node_label": f"P{node}",
                    "node_xy": list(data.coordinates[node]),
                    "mode": "direct_with_backward_handoff",
                }
            )
        elif event["type"] == "service":
            item.update(
                {
                    "task_id": route[service_cursor],
                    "point_id": int(event["node"]),
                    "node_xy": list(data.coordinates[int(event["node"])]),
                }
            )
            service_cursor += 1
        converted.append(item)
    return {
        **{key: value for key, value in scheduled.items() if key != "events"},
        "task_sequence": ["BASE", *route, "BASE"],
        "detour_leg_count": 0,
        "used_baseline_handoff_fallback": True,
        "events": converted,
    }


def schedule_copy_route(
    route: list[str],
    mapping: dict[str, int],
    data: baseline.CaseData,
    router: DetourRouter,
) -> dict | None:
    enhanced = _schedule_copy_route_with_detours(route, mapping, data, router)
    if enhanced is not None:
        return enhanced
    return _baseline_handoff_fallback(route, mapping, data)


class EnhancedEvaluator:
    def __init__(
        self,
        data: baseline.CaseData,
        mapping: dict[str, int],
        ring_samples: int,
        safety_margin: float,
    ) -> None:
        self.data = data
        self.mapping = mapping
        self.router = DetourRouter(data, ring_samples, safety_margin)
        self.cache: dict[tuple[str, ...], dict | None] = {}

    def route(self, tasks: list[str]) -> dict | None:
        key = tuple(tasks)
        if key not in self.cache:
            self.cache[key] = schedule_copy_route(tasks, self.mapping, self.data, self.router)
        return self.cache[key]

    def solution(self, routes: list[list[str]]) -> tuple[tuple[float, float, float], list[dict]] | None:
        schedules = [self.route(route) for route in routes]
        if any(item is None for item in schedules):
            return None
        valid = [item for item in schedules if item is not None]
        times = [item["time_h"] for item in valid]
        return (max(times), max(times) - min(times), sum(times)), valid


def propose(
    routes: list[list[str]],
    times: list[float],
    mapping: dict[str, int],
    rng: random.Random,
) -> list[list[str]] | None:
    candidate = [route[:] for route in routes]
    order = sorted(range(len(routes)), key=times.__getitem__)
    move = rng.random()
    if move < 0.42:
        src = rng.choice(order[-min(2, len(order)):]) if rng.random() < 0.8 else rng.randrange(len(routes))
        choices = [idx for idx in range(len(routes)) if idx != src]
        dst = rng.choice(order[: min(2, len(order))]) if rng.random() < 0.8 else rng.choice(choices)
        if len(candidate[src]) <= 1:
            return None
        task = candidate[src].pop(rng.randrange(len(candidate[src])))
        point = mapping[task]
        legal = [
            pos
            for pos in range(len(candidate[dst]) + 1)
            if (pos == 0 or mapping[candidate[dst][pos - 1]] != point)
            and (pos == len(candidate[dst]) or mapping[candidate[dst][pos]] != point)
        ]
        if not legal:
            return None
        candidate[dst].insert(rng.choice(legal), task)
    elif move < 0.68:
        a, b = rng.sample(range(len(routes)), 2)
        ia, ib = rng.randrange(len(candidate[a])), rng.randrange(len(candidate[b]))
        candidate[a][ia], candidate[b][ib] = candidate[b][ib], candidate[a][ia]
    elif move < 0.84:
        ridx = rng.randrange(len(routes))
        if len(candidate[ridx]) < 4:
            return None
        i, j = sorted(rng.sample(range(len(candidate[ridx])), 2))
        candidate[ridx][i : j + 1] = reversed(candidate[ridx][i : j + 1])
    else:
        a, b = rng.sample(range(len(routes)), 2)
        if len(candidate[a]) < 2 or len(candidate[b]) < 2:
            return None
        ia, ja = sorted(rng.sample(range(len(candidate[a]) + 1), 2))
        ib, jb = sorted(rng.sample(range(len(candidate[b]) + 1), 2))
        if ia == ja or ib == jb:
            return None
        seg_a, seg_b = candidate[a][ia:ja], candidate[b][ib:jb]
        candidate[a][ia:ja], candidate[b][ib:jb] = seg_b, seg_a
    if not all(valid_copy_route(route, mapping) for route in candidate):
        return None
    return candidate


def stage_a_search(
    initial: list[list[str]],
    evaluator: EnhancedEvaluator,
    mapping: dict[str, int],
    rng: random.Random,
    iterations: int,
    deadline: float,
) -> tuple[list[list[str]], tuple[float, float, float], dict]:
    current = [route[:] for route in initial]
    evaluated = evaluator.solution(current)
    if evaluated is None:
        raise RuntimeError("增强算法无法调度初始路线")
    current_key, current_schedules = evaluated
    best, best_key = [route[:] for route in current], current_key
    attempted = accepted = 0
    for iteration in range(iterations):
        if time.monotonic() >= deadline:
            break
        candidate = propose(current, [item["time_h"] for item in current_schedules], mapping, rng)
        if candidate is None:
            continue
        attempted += 1
        evaluated = evaluator.solution(candidate)
        if evaluated is None:
            continue
        key, schedules = evaluated
        progress = iteration / max(1, iterations - 1)
        temperature = 0.10 * (1.0 - progress) + 0.001
        loss = key[0] - current_key[0]
        accept = loss < -TOL or rng.random() < math.exp(-max(0.0, loss) / temperature)
        if accept:
            current, current_key, current_schedules = candidate, key, schedules
            accepted += 1
            if key[0] < best_key[0] - TOL or (
                abs(key[0] - best_key[0]) <= TOL and key[2] < best_key[2] - TOL
            ):
                best, best_key = [route[:] for route in candidate], key
    return best, best_key, {
        "attempted_moves": attempted,
        "accepted_moves": accepted,
        "Tmax_star_h": best_key[0],
        "secondary_metrics_not_optimized": {"delta_h": best_key[1], "total_work_h": best_key[2]},
    }


def stage_b_search(
    stage_a_routes: list[list[str]],
    tmax_star: float,
    epsilon: float,
    evaluator: EnhancedEvaluator,
    mapping: dict[str, int],
    rng: random.Random,
    iterations: int,
    deadline: float,
) -> tuple[list[list[str]], tuple[float, float, float], dict]:
    threshold = (1.0 + epsilon) * tmax_star
    current = [route[:] for route in stage_a_routes]
    evaluated = evaluator.solution(current)
    assert evaluated is not None
    current_key, current_schedules = evaluated
    best, best_key = [route[:] for route in current], current_key
    attempted = accepted = rejected_by_threshold = 0
    for iteration in range(iterations):
        if time.monotonic() >= deadline:
            break
        candidate = propose(current, [item["time_h"] for item in current_schedules], mapping, rng)
        if candidate is None:
            continue
        attempted += 1
        evaluated = evaluator.solution(candidate)
        if evaluated is None:
            continue
        key, schedules = evaluated
        if key[0] > threshold + TOL:
            rejected_by_threshold += 1
            continue
        current_obj = (current_key[1], current_key[2], current_key[0])
        candidate_obj = (key[1], key[2], key[0])
        progress = iteration / max(1, iterations - 1)
        temperature = 0.06 * (1.0 - progress) + 0.0005
        loss = (candidate_obj[0] - current_obj[0]) + 0.002 * (
            candidate_obj[1] - current_obj[1]
        )
        accept = candidate_obj < current_obj or rng.random() < math.exp(-max(0.0, loss) / temperature)
        if accept:
            current, current_key, current_schedules = candidate, key, schedules
            accepted += 1
            if (key[1], key[2], key[0]) < (best_key[1], best_key[2], best_key[0]):
                best, best_key = [route[:] for route in candidate], key
    return best, best_key, {
        "epsilon": epsilon,
        "Tmax_limit_h": threshold,
        "attempted_moves": attempted,
        "accepted_moves": accepted,
        "rejected_by_Tmax_limit": rejected_by_threshold,
        "delta_h": best_key[1],
        "Tmax_h": best_key[0],
        "total_work_h": best_key[2],
    }


def add_uavs(initial: list[list[str]], extra: int) -> list[list[str]]:
    routes = [route[:] for route in initial]
    for _ in range(extra):
        src = max(range(len(routes)), key=lambda idx: len(routes[idx]))
        if len(routes[src]) <= 1:
            raise ValueError("无法继续拆分非空路线")
        midpoint = len(routes[src]) // 2
        new_route = routes[src][midpoint:]
        routes[src] = routes[src][:midpoint]
        routes.append(new_route)
    return routes


def solve_case_n(
    case_name: str,
    data: baseline.CaseData,
    initial: list[list[str]],
    mapping: dict[str, int],
    epsilon: float,
    ring_samples: int,
    safety_margin: float,
    stage_a_iterations: int,
    stage_b_iterations: int,
    seconds: float,
    seed: int,
) -> dict:
    validate_copy_routes(initial, data, mapping)
    evaluator = EnhancedEvaluator(data, mapping, ring_samples, safety_margin)
    started = time.monotonic()
    phase_deadline = started + seconds / 2.0
    rng = random.Random(seed)
    stage_a_routes, stage_a_key, stage_a_report = stage_a_search(
        initial, evaluator, mapping, rng, stage_a_iterations, phase_deadline
    )
    original_stage_a_tmax = stage_a_key[0]
    stage_b_routes, stage_b_key, stage_b_report = stage_b_search(
        stage_a_routes,
        stage_a_key[0],
        epsilon,
        evaluator,
        mapping,
        rng,
        stage_b_iterations,
        started + seconds,
    )
    refinements: list[dict] = []
    # 启发式阶段B可能在探索均衡解时发现更小的 Tmax。此时必须将其回代为
    # 新的阶段A当前最好值，并按收紧后的阈值重新执行阶段B，避免目标错位。
    for refinement in range(3):
        if stage_b_key[0] >= stage_a_key[0] - TOL:
            break
        refinements.append(
            {
                "round": refinement + 1,
                "old_Tmax_star_h": stage_a_key[0],
                "new_Tmax_star_h": stage_b_key[0],
            }
        )
        stage_a_routes = [route[:] for route in stage_b_routes]
        stage_a_key = stage_b_key
        stage_b_routes, stage_b_key, stage_b_report = stage_b_search(
            stage_a_routes,
            stage_a_key[0],
            epsilon,
            evaluator,
            mapping,
            rng,
            stage_b_iterations,
            time.monotonic() + max(2.0, seconds / 3.0),
        )
    stage_a_report["initial_Tmax_star_h"] = original_stage_a_tmax
    stage_a_report["Tmax_star_h"] = stage_a_key[0]
    stage_a_report["refined_from_stage_b"] = bool(refinements)
    stage_a_report["refinement_history"] = refinements
    validate_copy_routes(stage_b_routes, data, mapping)
    evaluated = evaluator.solution(stage_b_routes)
    assert evaluated is not None
    key, schedules = evaluated
    assert key[0] <= (1.0 + epsilon) * stage_a_key[0] + TOL
    return {
        "case": case_name,
        "N": len(stage_b_routes),
        "Tmax": key[0],
        "Tmin": min(item["time_h"] for item in schedules),
        "delta": key[1],
        "total_work_h": key[2],
        "total_wait_min": sum(item["wait_time_h"] * 60.0 for item in schedules),
        "latest_return": baseline.min_to_clock(key[0] * 60.0),
        "time_origin": "08:00",
        "deadline_17_00": False,
        "zone_policy": "half_open; zero-duration zones excluded",
        "task_copy_policy": "unique task IDs Pxxx#copy_no",
        "detour_model": {
            "type": "sampled boundary visibility graph",
            "ring_samples": ring_samples,
            "safety_margin_coordinate_units": safety_margin,
        },
        "stage_a": stage_a_report,
        "stage_b": stage_b_report,
        "routes": [
            {"uav": uav, **schedule}
            for uav, schedule in enumerate(schedules, start=1)
        ],
    }


def write_summary(results: dict, output_dir: Path) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    with (output_dir / "summary_enhanced.csv").open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.writer(handle)
        writer.writerow(
            [
                "Case",
                "Scenario",
                "N",
                "StageA_TmaxStar_h",
                "Epsilon",
                "Final_Tmax_h",
                "Final_Tmin_h",
                "Final_delta_h",
                "Wait_min",
                "Detour_legs",
                "Latest_return",
            ]
        )
        for case_name, scenarios in results.items():
            for scenario_name, item in scenarios.items():
                writer.writerow(
                    [
                        case_name,
                        scenario_name,
                        item["N"],
                        item["stage_a"]["Tmax_star_h"],
                        item["stage_b"]["epsilon"],
                        item["Tmax"],
                        item["Tmin"],
                        item["delta"],
                        item["total_wait_min"],
                        sum(route["detour_leg_count"] for route in item["routes"]),
                        item["latest_return"],
                    ]
                )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--points", type=Path, required=True)
    parser.add_argument("--zones", type=Path, required=True)
    parser.add_argument("--q2-solution", type=Path, required=True)
    parser.add_argument(
        "--baseline-q3-solution",
        type=Path,
        help="可选：算法A的 q3_solution.json；提供后作为算法B的必选初始种子",
    )
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--epsilon", type=float, default=0.005)
    parser.add_argument("--ring-samples", type=int, default=16)
    parser.add_argument("--safety-margin", type=float, default=0.0)
    parser.add_argument("--stage-a-iterations", type=int, default=800)
    parser.add_argument("--stage-b-iterations", type=int, default=800)
    parser.add_argument("--seconds-per-case", type=float, default=45.0)
    parser.add_argument("--extra-uavs", type=int, default=0)
    args = parser.parse_args()
    if not 0.0 <= args.epsilon <= 0.05:
        raise ValueError("epsilon 建议位于 [0,0.05]")
    if args.extra_uavs < 0:
        raise ValueError("extra-uavs 不能为负")

    cases = baseline.load_cases(args.points, args.zones)
    q2 = json.loads(args.q2_solution.read_text(encoding="utf-8"))
    assert set(cases) == set(q2)
    baseline_q3 = None
    if args.baseline_q3_solution is not None:
        baseline_q3 = json.loads(args.baseline_q3_solution.read_text(encoding="utf-8"))
        assert set(cases) == set(baseline_q3)
    results: dict[str, dict] = {}
    for case_index, (case_name, data) in enumerate(cases.items()):
        seed_source = baseline_q3[case_name] if baseline_q3 is not None else q2[case_name]
        physical = [
            [int(value) for value in route["sequence"][1:-1]]
            for route in seed_source["routes"]
        ]
        initial, mapping = build_unique_copies(physical)
        expected = expected_copy_ids(data)
        if set(mapping) != expected:
            raise RuntimeError(f"{case_name}: 问题二路线与任务副本需求不一致")
        scenarios: dict[str, dict] = {}
        scenario_routes = [route[:] for route in initial]
        for extra in range(args.extra_uavs + 1):
            scenario_name = "formal_fixed_N0" if extra == 0 else f"sensitivity_N0_plus_{extra}"
            result = solve_case_n(
                case_name,
                data,
                scenario_routes,
                mapping,
                args.epsilon,
                args.ring_samples,
                args.safety_margin,
                args.stage_a_iterations,
                args.stage_b_iterations,
                args.seconds_per_case,
                20260818 + 1000 * case_index + extra,
            )
            scenarios[scenario_name] = result
            print(
                f"{case_name} {scenario_name}: N={result['N']} "
                f"Tmax*={result['stage_a']['Tmax_star_h']:.6f} "
                f"Tmax={result['Tmax']:.6f} delta={result['delta']:.6f} "
                f"wait={result['total_wait_min']:.3f}",
                flush=True,
            )
            # 机队规模敏感性采用逐级热启动：下一规模从当前已优化方案拆出一条
            # 新路线，而不是每次回到未经优化的原始路线重新硬拆。
            if extra < args.extra_uavs:
                optimized_routes = [route["task_sequence"][1:-1] for route in result["routes"]]
                scenario_routes = add_uavs(optimized_routes, 1)
        results[case_name] = scenarios

    args.output_dir.mkdir(parents=True, exist_ok=True)
    output = args.output_dir / "q3_enhanced_solution.json"
    output.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
    write_summary(results, args.output_dir)
    print(output)


if __name__ == "__main__":
    main()
