"""根据已验证的结果文件绘制 Case 2 算法 A/B 实际航迹对比图。"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from reportlab.lib.colors import HexColor
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen import canvas

ROOT = Path(__file__).resolve().parents[3]
PROGRAM = Path(__file__).resolve().parent
sys.path.insert(0, str(PROGRAM))

import q3_solver as baseline  # noqa: E402


def bounds(case_data) -> tuple[float, float, float, float]:
    xs = [xy[0] for xy in case_data.coordinates.values()]
    ys = [xy[1] for xy in case_data.coordinates.values()]
    for zone in case_data.zones:
        xs.extend([zone.center[0] - zone.radius, zone.center[0] + zone.radius])
        ys.extend([zone.center[1] - zone.radius, zone.center[1] + zone.radius])
    return min(xs) - 3, max(xs) + 3, min(ys) - 3, max(ys) + 3


def mapper(area, data_bounds):
    x, y, width, height = area
    xmin, xmax, ymin, ymax = data_bounds
    scale = min(width / (xmax - xmin), height / (ymax - ymin))
    xpad = (width - (xmax - xmin) * scale) / 2
    ypad = (height - (ymax - ymin) * scale) / 2

    def transform(point):
        return x + xpad + (point[0] - xmin) * scale, y + ypad + (point[1] - ymin) * scale

    return transform, scale


def draw_panel(c, area, case_data, result, algorithm_b: bool, title: str, subtitle: str):
    transform, scale = mapper(area, bounds(case_data))
    x, y, width, height = area
    c.setFillColor(HexColor("#243447"))
    c.setFont("SimHei", 10)
    c.drawCentredString(x + width / 2, y + height + 27, title)
    c.setFillColor(HexColor("#666666"))
    c.setFont("SimHei", 8)
    c.drawCentredString(x + width / 2, y + height + 14, subtitle)
    c.setStrokeColor(HexColor("#D7DEE5"))
    c.rect(x, y, width, height, fill=0, stroke=1)

    for zone in case_data.zones:
        if not zone.active:
            continue
        cx, cy = transform(zone.center)
        c.setFillColor(HexColor("#FCE1DC"))
        c.setStrokeColor(HexColor("#C94C3A"))
        c.setLineWidth(0.7)
        c.circle(cx, cy, zone.radius * scale, fill=1, stroke=1)
        c.setFillColor(HexColor("#8B2E22"))
        c.setFont("Helvetica", 6)
        c.drawCentredString(cx, cy - 2, zone.zone_id)

    colors = [HexColor("#2A6FBB"), HexColor("#4C956C")]
    if algorithm_b:
        for route, color in zip(result["routes"], colors):
            for event in route["events"]:
                if event["type"] != "flight":
                    continue
                ax, ay = transform(event["from_xy"])
                bx, by = transform(event["to_xy"])
                detour = event.get("mode") == "boundary_visibility_detour"
                c.setStrokeColor(HexColor("#F28E2B") if detour else color)
                c.setLineWidth(1.7 if detour else 0.55)
                c.line(ax, ay, bx, by)
    else:
        for route, color in zip(result["routes"], colors):
            points = [transform(case_data.coordinates[int(node)]) for node in route["sequence"]]
            c.setStrokeColor(color)
            c.setLineWidth(0.55)
            for first, second in zip(points, points[1:]):
                c.line(first[0], first[1], second[0], second[1])

    base_x, base_y = transform((0.0, 0.0))
    c.setFillColor(HexColor("#222222"))
    c.rect(base_x - 2.4, base_y - 2.4, 4.8, 4.8, fill=1, stroke=0)
    c.setFont("SimHei", 6)
    c.drawString(base_x + 4, base_y - 1, "基地")


def main() -> None:
    points = ROOT / "submission_package/question1/program/input/附件1.xlsx"
    zones = ROOT / "submission_package/question3/program/input/附件2.xlsx"
    result_dir = ROOT / "submission_package/question3/results"
    case_data = baseline.load_cases(points, zones)["Case2"]
    algorithm_a = json.loads((result_dir / "q3_solution_algorithmA.json").read_text(encoding="utf-8"))["Case2"]
    algorithm_b = json.loads((result_dir / "q3_solution.json").read_text(encoding="utf-8"))["Case2"]["formal_fixed_N0"]

    output = ROOT / "generated_figures/q3_case2_ab_routes.pdf"
    pdfmetrics.registerFont(TTFont("SimHei", r"C:\Windows\Fonts\simhei.ttf"))
    c = canvas.Canvas(str(output), pagesize=(700, 330))
    c.setTitle("Case 2 算法A与算法B实际航迹比较")
    draw_panel(c, (32, 35, 302, 245), case_data, algorithm_a, False,
               "算法A：直飞--等待", "总等待189.297 min")
    draw_panel(c, (366, 35, 302, 245), case_data, algorithm_b, True,
               "算法B：等待或空间绕飞", "总等待47.645 min；橙色为绕行航段")
    c.setFillColor(HexColor("#555555"))
    c.setFont("SimHei", 7)
    c.drawCentredString(350, 15, "阴影圆为动态管制区的空间范围；是否生效仍由航段实际通过时刻判定")
    c.save()
    print(output)


if __name__ == "__main__":
    main()
