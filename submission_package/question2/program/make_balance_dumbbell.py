"""由问题二结构化结果生成工时极差哑铃图（矢量 PDF）。"""

import json
from pathlib import Path

from reportlab.lib.colors import HexColor
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen import canvas


ROOT = Path(__file__).resolve().parents[3]
DATA = ROOT / "submission_package" / "question2" / "results" / "q2_solution.json"
OUT = ROOT / "generated_figures" / "q2_balance_improvement_dumbbell.pdf"
FONT = Path(r"C:\Windows\Fonts\simhei.ttf")


def x_coord(value, left, width, maximum=5.0):
    return left + value / maximum * width


def main():
    data = json.loads(DATA.read_text(encoding="utf-8"))
    pdfmetrics.registerFont(TTFont("SimHei", str(FONT)))

    page_w, page_h = 660, 350
    left, right, bottom, top = 70, 95, 48, 45
    plot_w = page_w - left - right
    plot_h = page_h - bottom - top
    cases = ["Case 1", "Case 2", "Case 3", "Case 4"]
    keys = ["Case1", "Case2", "Case3", "Case4"]
    blue = HexColor("#66A6D1")
    orange = HexColor("#D96637")
    green = HexColor("#19865B")
    grid = HexColor("#D8E0E8")
    line = HexColor("#AEB8C2")
    dark = HexColor("#222222")

    c = canvas.Canvas(str(OUT), pagesize=(page_w, page_h))
    c.setTitle("问题一与问题二工作时间极差对比")

    for tick in range(6):
        x = x_coord(tick, left, plot_w)
        c.setStrokeColor(grid)
        c.setLineWidth(0.55)
        c.line(x, bottom, x, bottom + plot_h)
        c.setFillColor(dark)
        c.setFont("Helvetica", 9)
        c.drawCentredString(x, bottom - 17, str(tick))

    row_gap = plot_h / 4
    for index, (case, key) in enumerate(zip(cases, keys)):
        y = bottom + plot_h - (index + 0.5) * row_gap
        q1 = data[key]["q1_delta_h"] * 60
        q2 = data[key]["delta"] * 60
        pct = data[key]["delta_reduction_pct"] * 100
        x1 = x_coord(q1, left, plot_w)
        x2 = x_coord(q2, left, plot_w)

        c.setFillColor(dark)
        c.setFont("Helvetica", 10)
        c.drawRightString(left - 12, y - 3, case)
        c.setStrokeColor(line)
        c.setLineWidth(3.0)
        c.line(x2, y, x1, y)
        c.setFillColor(blue)
        c.circle(x1, y, 5.4, fill=1, stroke=0)
        c.setFillColor(orange)
        c.circle(x2, y, 5.4, fill=1, stroke=0)

        c.setFont("Helvetica", 9)
        c.setFillColor(blue)
        c.drawCentredString(x1, y + 11, f"{q1:.2f}")
        c.setFillColor(orange)
        c.drawCentredString(x2, y - 18, f"{q2:.2f}")
        c.setFillColor(green)
        c.setFont("SimHei", 9)
        c.drawString(left + plot_w + 10, y - 3, f"下降 {pct:.1f}%")

    legend_y = page_h - 22
    c.setFillColor(blue)
    c.circle(255, legend_y, 5, fill=1, stroke=0)
    c.setFillColor(dark)
    c.setFont("SimHei", 10)
    c.drawString(266, legend_y - 3, "问题一方案")
    c.setFillColor(orange)
    c.circle(365, legend_y, 5, fill=1, stroke=0)
    c.setFillColor(dark)
    c.drawString(376, legend_y - 3, "问题二方案")
    c.setFont("SimHei", 10)
    c.drawCentredString(
        left + plot_w / 2,
        13,
        "单架无人机最长与最短工作时间之差 δ（min，越小越均衡）",
    )
    c.save()
    print(OUT)


if __name__ == "__main__":
    main()
