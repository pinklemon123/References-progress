"""根据问题一、问题二 JSON 生成论文用无人机工时对比矢量图。"""

import json
from pathlib import Path

from reportlab.lib.colors import HexColor
from reportlab.pdfgen import canvas


ROOT = Path(__file__).resolve().parents[3]
Q1 = ROOT / "submission_package" / "question1" / "results" / "solution.json"
Q2 = ROOT / "submission_package" / "question2" / "results" / "q2_solution.json"
OUT = ROOT / "generated_figures" / "q2_workload_comparison.pdf"


def draw_panel(c, x0, y0, width, height, case_name, q1_times, q2_times):
    left, right, bottom, top = 35, 10, 25, 29
    px, py = x0 + left, y0 + bottom
    pw, ph = width - left - right, height - bottom - top
    ymin, ymax = 7.4, 9.05
    blue, orange = HexColor("#8FB9D9"), HexColor("#D86B45")

    c.setFont("Helvetica-Bold", 9)
    c.drawCentredString(x0 + width / 2, y0 + height - 11, case_name)
    c.setFont("Helvetica", 6.5)
    delta1 = max(q1_times) - min(q1_times)
    delta2 = max(q2_times) - min(q2_times)
    c.drawCentredString(
        x0 + width / 2,
        y0 + height - 21,
        f"delta: {delta1:.4f} -> {delta2:.4f} h",
    )
    c.setStrokeColor(HexColor("#B7C9D6"))
    c.setLineWidth(0.35)
    for tick in (7.5, 8.0, 8.5, 9.0):
        yy = py + (tick - ymin) / (ymax - ymin) * ph
        c.line(px, yy, px + pw, yy)
        c.setFillColor(HexColor("#555555"))
        c.setFont("Helvetica", 6.5)
        c.drawRightString(px - 4, yy - 2, f"{tick:.1f}")
    yy9 = py + (9.0 - ymin) / (ymax - ymin) * ph
    c.setStrokeColor(HexColor("#A61C1C"))
    c.setDash(3, 2)
    c.line(px, yy9, px + pw, yy9)
    c.setDash()

    n = len(q1_times)
    group = pw / n
    bar = min(11, group * 0.26)
    for idx, (t1, t2) in enumerate(zip(q1_times, q2_times), start=1):
        center = px + (idx - 0.5) * group
        h1 = (t1 - ymin) / (ymax - ymin) * ph
        h2 = (t2 - ymin) / (ymax - ymin) * ph
        c.setFillColor(blue)
        c.rect(center - bar - 1, py, bar, h1, fill=1, stroke=0)
        c.setFillColor(orange)
        c.rect(center + 1, py, bar, h2, fill=1, stroke=0)
        c.setFillColor(HexColor("#333333"))
        c.setFont("Helvetica", 6.5)
        c.drawCentredString(center, py - 10, str(idx))

    c.setStrokeColor(HexColor("#333333"))
    c.setLineWidth(0.6)
    c.line(px, py, px, py + ph)
    c.line(px, py, px + pw, py)
    c.setFillColor(HexColor("#333333"))
    c.setFont("Helvetica", 6.5)
    c.drawCentredString(px + pw / 2, y0 + 3, "UAV ID")


def main():
    q1 = json.loads(Q1.read_text(encoding="utf-8"))
    q2 = json.loads(Q2.read_text(encoding="utf-8"))
    OUT.parent.mkdir(parents=True, exist_ok=True)
    page_w, page_h = 500, 350
    c = canvas.Canvas(str(OUT), pagesize=(page_w, page_h))
    c.setTitle("Q1-Q2 UAV workload comparison")
    panels = {
        "Case1": (20, 175),
        "Case2": (255, 175),
        "Case3": (20, 20),
        "Case4": (255, 20),
    }
    for case_name, (x, y) in panels.items():
        t1 = [route["time_h"] for route in q1[case_name]["routes"]]
        t2 = [route["time_h"] for route in q2[case_name]["routes"]]
        draw_panel(c, x, y, 225, 145, case_name, t1, t2)

    c.setFillColor(HexColor("#8FB9D9"))
    c.rect(165, 334, 10, 7, fill=1, stroke=0)
    c.setFillColor(HexColor("#333333"))
    c.setFont("Helvetica", 7)
    c.drawString(179, 334, "Question 1")
    c.setFillColor(HexColor("#D86B45"))
    c.rect(245, 334, 10, 7, fill=1, stroke=0)
    c.setFillColor(HexColor("#333333"))
    c.drawString(259, 334, "Question 2")
    c.setStrokeColor(HexColor("#A61C1C"))
    c.setDash(3, 2)
    c.line(330, 337, 343, 337)
    c.setDash()
    c.setFillColor(HexColor("#333333"))
    c.drawString(347, 334, "9 h limit")
    c.save()
    print(OUT)


if __name__ == "__main__":
    main()
