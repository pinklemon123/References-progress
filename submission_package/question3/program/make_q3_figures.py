"""生成问题三正文所用的两张矢量示意图。"""

from pathlib import Path

from reportlab.lib.colors import HexColor
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen import canvas


ROOT = Path(__file__).resolve().parents[3]
OUT = ROOT / "generated_figures"
FONT = Path(r"C:\Windows\Fonts\simhei.ttf")


def arrow(c, x1, y1, x2, y2, color="#44546A", width=1.2):
    c.setStrokeColor(HexColor(color))
    c.setFillColor(HexColor(color))
    c.setLineWidth(width)
    c.line(x1, y1, x2, y2)
    dx, dy = x2 - x1, y2 - y1
    length = max((dx * dx + dy * dy) ** 0.5, 1.0)
    ux, uy = dx / length, dy / length
    px, py = -uy, ux
    size = 7
    c.line(x2, y2, x2 - size * ux + 3 * px, y2 - size * uy + 3 * py)
    c.line(x2, y2, x2 - size * ux - 3 * px, y2 - size * uy - 3 * py)


def principle_figure():
    path = OUT / "q3_spatiotemporal_principle.pdf"
    c = canvas.Canvas(str(path), pagesize=(620, 350))
    c.setTitle("航段与动态圆形禁飞区的时空耦合判定")
    dark, red, blue, gray = map(HexColor, ["#243447", "#D95F5F", "#4C91C6", "#9AA6B2"])

    c.setFont("SimHei", 11)
    c.setFillColor(dark)
    c.drawString(38, 326, "空间判定")
    c.setFillColor(red)
    c.setFillAlpha(0.18)
    c.circle(315, 247, 68, fill=1, stroke=0)
    c.setFillAlpha(1)
    c.setStrokeColor(red)
    c.setLineWidth(1.6)
    c.circle(315, 247, 68, fill=0, stroke=1)
    c.setFillColor(red)
    c.setFont("SimHei", 10)
    c.drawString(326, 296, "动态管制圆 Z_k")
    arrow(c, 75, 222, 548, 276, color="#243447", width=1.8)
    c.setFillColor(dark)
    c.circle(75, 222, 4.5, fill=1, stroke=0)
    c.circle(548, 276, 4.5, fill=1, stroke=0)
    c.setFont("Helvetica-Bold", 10)
    c.drawCentredString(66, 205, "i")
    c.drawCentredString(557, 260, "j")
    for x, y, label in [(249, 242, "λ-"), (380, 257, "λ+")]:
        c.setFillColor(blue)
        c.circle(x, y, 4, fill=1, stroke=0)
        c.setFont("SimHei", 9)
        c.drawCentredString(x, y - 16, label)
    c.setFont("SimHei", 9)
    c.setFillColor(dark)
    c.drawString(93, 292, "端点均在圆外，航段仍可能穿过管制区")

    c.setStrokeColor(gray)
    c.setLineWidth(0.7)
    c.line(38, 178, 582, 178)
    c.setFillColor(dark)
    c.setFont("SimHei", 11)
    c.drawString(38, 155, "时间判定")
    x0, x1, y = 78, 552, 92
    arrow(c, x0, y, x1, y, color="#44546A", width=1.2)
    c.setFont("Helvetica", 8)
    for value in range(0, 601, 120):
        x = x0 + value / 600 * (x1 - x0)
        c.line(x, y - 3, x, y + 3)
        c.drawCentredString(x, y - 15, str(value))
    c.setFont("SimHei", 8)
    c.drawString(555, y - 3, "min")
    a0, a1 = x0 + 180 / 600 * (x1 - x0), x0 + 390 / 600 * (x1 - x0)
    c.setFillColor(red)
    c.rect(a0, y + 30, a1 - a0, 13, fill=1, stroke=0)
    c.setFillColor(dark)
    c.setFont("SimHei", 8)
    c.drawString(a0, y + 47, "管制生效区间 [αk, βk)")
    f0, f1 = x0 + 145 / 600 * (x1 - x0), x0 + 330 / 600 * (x1 - x0)
    c.setFillColor(blue)
    c.rect(f0, y + 8, f1 - f0, 13, fill=1, stroke=0)
    c.setFillColor(dark)
    c.drawString(f0, y - 32, "原计划航段在圆内的时段与管制重叠")
    c.setFillColor(HexColor("#E28E2C"))
    c.rect(a1, y + 8, 100, 13, fill=1, stroke=0)
    c.setFillColor(dark)
    c.drawString(a1, y + 24, "延迟至下一可行出发时刻")
    c.save()


def box(c, x, y, w, h, text, fill="#EEF5FA"):
    c.setFillColor(HexColor(fill))
    c.setStrokeColor(HexColor("#58748C"))
    c.setLineWidth(0.8)
    c.roundRect(x, y, w, h, 6, fill=1, stroke=1)
    c.setFillColor(HexColor("#243447"))
    c.setFont("SimHei", 9)
    lines = text.split("\n")
    start = y + h / 2 + (len(lines) - 1) * 6 - 3
    for idx, line in enumerate(lines):
        c.drawCentredString(x + w / 2, start - idx * 12, line)


def flow_figure():
    path = OUT / "q3_solver_flowchart.pdf"
    c = canvas.Canvas(str(path), pagesize=(620, 350))
    c.setTitle("问题三时间依赖多无人机协同巡检求解流程")
    c.setFont("SimHei", 11)
    c.setFillColor(HexColor("#243447"))
    c.drawCentredString(310, 329, "问题三时间依赖协同巡检求解流程")
    cols = [35, 225, 415]
    titles = ["数据与几何预处理", "时间依赖路线评价", "多起点优化与输出"]
    for x, title in zip(cols, titles):
        c.setFillColor(HexColor("#1F4E78"))
        c.roundRect(x, 285, 170, 28, 5, fill=1, stroke=0)
        c.setFillColor(HexColor("#FFFFFF"))
        c.setFont("SimHei", 9)
        c.drawCentredString(x + 85, 295, title)
    ys = [222, 145, 68]
    left = ["读取任务副本与管制区", "统一8:00时间原点\n处理零时长Z8", "解析线段-圆相交区间"]
    middle = ["构造航段禁用出发区间", "计算最早可行出发\n及必要安全等待", "复算飞行、服务与返回时刻"]
    right = ["以问题二路线为初始解", "变邻域与模拟退火\n词典序优化(Tmax, δ)", "独立复核并输出\nJSON、CSV；正式表统一生成"]
    for x, texts in zip(cols, [left, middle, right]):
        for y, text in zip(ys, texts):
            box(c, x, y, 170, 46, text)
        arrow(c, x + 85, 222, x + 85, 191)
        arrow(c, x + 85, 145, x + 85, 114)
    arrow(c, 205, 91, 225, 245)
    arrow(c, 395, 91, 415, 245)
    c.setFont("SimHei", 8)
    c.setFillColor(HexColor("#666666"))
    c.drawCentredString(310, 25, "加速几何复核的完整实现置于附录，正文仅保留模型层次与输入输出关系")
    c.save()


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    pdfmetrics.registerFont(TTFont("SimHei", str(FONT)))
    principle_figure()
    flow_figure()
    print(OUT / "q3_spatiotemporal_principle.pdf")
    print(OUT / "q3_solver_flowchart.pdf")


if __name__ == "__main__":
    main()
