"""Merge the final paper body and appendix while fixing four visible PDF defects.

The body source is expected to contain 25 manuscript pages followed by an old
appendix page.  Only pages 1--25 are retained.  The replacement appendix is
then appended in full, yielding a 51-page submission PDF.
"""

from __future__ import annotations

import argparse
import io
import shutil
import subprocess
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont
from pypdf import PdfReader, PdfWriter
from reportlab.lib.utils import ImageReader
from reportlab.pdfgen import canvas


PAGE_WIDTH = 595.28
PAGE_HEIGHT = 841.89
DEFAULT_POPPLER = Path(
    r"C:\Users\pinkl\.cache\codex-runtimes\codex-primary-runtime\dependencies"
    r"\native\poppler\Library\bin\pdftoppm.exe"
)
CHINESE_FONT = Path(r"C:\Windows\Fonts\simsun.ttc")
MONO_FONT = Path(r"C:\Windows\Fonts\consola.ttf")


def render_page(poppler: Path, source: Path, page_number: int, target: Path, dpi: int) -> None:
    prefix = target.with_suffix("")
    subprocess.run(
        [
            str(poppler),
            "-f",
            str(page_number),
            "-l",
            str(page_number),
            "-r",
            str(dpi),
            "-png",
            "-singlefile",
            str(source),
            str(prefix),
        ],
        check=True,
    )


def draw_fitted_text(
    draw: ImageDraw.ImageDraw,
    xy: tuple[float, float],
    text: str,
    font_path: Path,
    start_size: int,
    max_width: float,
) -> None:
    size = start_size
    while size >= 12:
        font = ImageFont.truetype(str(font_path), size=size)
        box = draw.textbbox(xy, text, font=font, anchor="lt")
        if box[2] - box[0] <= max_width:
            draw.text(xy, text, fill="black", font=font, anchor="lt")
            return
        size -= 1
    raise RuntimeError(f"Replacement text does not fit: {text}")


def patch_raster(
    image_path: Path,
    dpi: int,
    rectangles: list[tuple[float, float, float, float]],
    lines: list[tuple[float, float, str, Path, float, float]],
) -> None:
    scale = dpi / 72.0
    image = Image.open(image_path).convert("RGB")
    draw = ImageDraw.Draw(image)
    for x0, top, x1, bottom in rectangles:
        draw.rectangle(
            (x0 * scale, top * scale, x1 * scale, bottom * scale),
            fill="white",
        )
    for x, top, text, font_path, point_size, max_width in lines:
        draw_fitted_text(
            draw,
            (x * scale, top * scale),
            text,
            font_path,
            round(point_size * scale),
            max_width * scale,
        )
    image.save(image_path, format="PNG", optimize=True)


def image_as_pdf_page(image_path: Path) -> object:
    buffer = io.BytesIO()
    pdf = canvas.Canvas(buffer, pagesize=(PAGE_WIDTH, PAGE_HEIGHT))
    pdf.drawImage(
        ImageReader(str(image_path)),
        0,
        0,
        width=PAGE_WIDTH,
        height=PAGE_HEIGHT,
        preserveAspectRatio=False,
        mask="auto",
    )
    pdf.showPage()
    pdf.save()
    buffer.seek(0)
    return PdfReader(buffer).pages[0]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--body", type=Path, required=True)
    parser.add_argument("--appendix", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--poppler", type=Path, default=DEFAULT_POPPLER)
    parser.add_argument("--dpi", type=int, default=240)
    args = parser.parse_args()

    body = PdfReader(str(args.body))
    appendix = PdfReader(str(args.appendix))
    if len(body.pages) < 26:
        raise ValueError("Body PDF must contain 25 manuscript pages and an old appendix page.")
    if len(appendix.pages) != 26:
        raise ValueError("Replacement appendix must contain exactly 26 pages.")

    args.output.parent.mkdir(parents=True, exist_ok=True)
    temp = args.output.parent / "_merge_work"
    temp.mkdir(parents=True, exist_ok=True)
    if True:
        body_copy = temp / "body.pdf"
        appendix_copy = temp / "appendix.pdf"
        shutil.copyfile(args.body, body_copy)
        shutil.copyfile(args.appendix, appendix_copy)
        jobs = {
            "body_09": (body_copy, 9),
            "body_19": (body_copy, 19),
            "body_20": (body_copy, 20),
            "appendix_01": (appendix_copy, 1),
        }
        images: dict[str, Path] = {}
        for name, (source, number) in jobs.items():
            target = temp / f"{name}.png"
            render_page(args.poppler, source, number, target, args.dpi)
            images[name] = target

        scale = args.dpi / 72.0
        patch_raster(
            images["body_09"],
            args.dpi,
            [(68, 559, 527, 578)],
            [
                (
                    70,
                    561,
                    "固定无人机数量下的完整优化流程及相关源程序见附录B。",
                    CHINESE_FONT,
                    11.0,
                    455,
                )
            ],
        )
        patch_raster(
            images["body_19"],
            args.dpi,
            [(68, 484, 595, 522)],
            [
                (
                    70,
                    486,
                    "可复算的结构化结果保存于q3_solution.json；算法A的对照结果另存为",
                    CHINESE_FONT,
                    10.5,
                    455,
                ),
                (
                    70,
                    505,
                    "result3_algorithmA.xlsx和q3_solution_algorithmA.json。",
                    CHINESE_FONT,
                    10.5,
                    455,
                ),
            ],
        )
        patch_raster(
            images["body_20"],
            args.dpi,
            [(68, 251, 527, 288)],
            [
                (
                    70,
                    253,
                    "等同于对全局最优性的证明。算法B的逐事件独立验证程序和算法A的快速解析",
                    CHINESE_FONT,
                    10.8,
                    455,
                ),
                (
                    70,
                    272,
                    "校验程序见附录D。",
                    CHINESE_FONT,
                    10.8,
                    455,
                ),
            ],
        )
        patch_raster(
            images["appendix_01"],
            args.dpi,
            [(120, 653, 310, 670)],
            [
                (
                    123,
                    655,
                    "AI_tool_usage_details.pdf",
                    MONO_FONT,
                    10.2,
                    185,
                )
            ],
        )

        replacements = {name: image_as_pdf_page(path) for name, path in images.items()}
        writer = PdfWriter()
        for index in range(25):
            if index == 8:
                writer.add_page(replacements["body_09"])
            elif index == 18:
                writer.add_page(replacements["body_19"])
            elif index == 19:
                writer.add_page(replacements["body_20"])
            else:
                writer.add_page(body.pages[index])
        for index, page in enumerate(appendix.pages):
            writer.add_page(replacements["appendix_01"] if index == 0 else page)

        with args.output.open("wb") as stream:
            writer.write(stream)

    merged = PdfReader(str(args.output))
    if len(merged.pages) != 51:
        raise RuntimeError(f"Expected 51 pages, got {len(merged.pages)}")
    print(f"Created final PDF ({len(merged.pages)} pages)")


if __name__ == "__main__":
    main()
