from __future__ import annotations

import json
import math
import shutil
from pathlib import Path

from PIL import Image, ImageDraw

from generate_advanced_report_diagrams import BUILDERS
from generate_report_diagrams import Diagram, PALETTE, font, hex_to_rgb


OUT_ROOT = Path("report_diagrams_high_level")
PNG_DIR = OUT_ROOT / "png"
SVG_DIR = OUT_ROOT / "svg"
CONTACT_SHEET = OUT_ROOT / "high_level_contact_sheet.png"
INDEX = OUT_ROOT / "high_level_diagram_index.md"
MANIFEST = OUT_ROOT / "high_level_diagram_manifest.json"
ALIGNMENT = OUT_ROOT / "high_level_alignment_notes.md"
PACKAGE = OUT_ROOT / "high_level_report_diagrams_package.zip"


DECLUTTER_LABEL_SLUGS = {
    "dfd_level2_system_data_flow",
    "uml_component_dependency",
    "deployment_network_runtime",
    "event_store_traceability_erd",
    "safety_fault_tree_and_controls",
}


def tidy_diagram(d: Diagram) -> Diagram:
    if d.slug in DECLUTTER_LABEL_SLUGS:
        for arrow in d.arrows:
            arrow.label = ""
            arrow.width = min(arrow.width, 3)
    return d


def build_contact_sheet(png_paths: list[Path]) -> None:
    thumb_w, thumb_h = 430, 242
    cols = 2
    rows = math.ceil(len(png_paths) / cols)
    sheet = Image.new("RGB", (cols * 500, rows * 330 + 92), hex_to_rgb(PALETTE["bg"]))
    draw = ImageDraw.Draw(sheet)
    draw.text(
        (32, 24),
        "High-Level Report Diagrams - 高階圖表精選",
        fill=hex_to_rgb(PALETTE["ink"]),
        font=font(31, True),
    )
    for idx, path in enumerate(png_paths):
        img = Image.open(path).convert("RGB")
        img.thumbnail((thumb_w, thumb_h), Image.Resampling.LANCZOS)
        col = idx % cols
        row = idx // cols
        x = col * 500 + 35
        y = row * 330 + 96
        draw.rounded_rectangle(
            (x - 10, y - 10, x + thumb_w + 10, y + thumb_h + 50),
            radius=18,
            fill=(255, 255, 255),
            outline=(203, 213, 225),
        )
        sheet.paste(img, (x, y))
        draw.text((x, y + thumb_h + 14), path.stem, fill=hex_to_rgb(PALETTE["ink"]), font=font(18))
    sheet.save(CONTACT_SHEET)


def write_index(diagrams: list[Diagram]) -> None:
    rows = [
        "# 高階圖表精選包",
        "",
        "這一包圖表比一般流程圖更進階，適合放在第三章系統設計、第四章系統實作與初步測試規劃，也可挑幾張放進簡報。",
        "",
        "| 編號 | 圖名 | 建議章節 | 用途 | PNG | SVG |",
        "| --- | --- | --- | --- | --- | --- |",
    ]
    manifest = []
    for idx, d in enumerate(diagrams, start=1):
        number = f"H{idx:02d}"
        png = PNG_DIR / f"{number}_{d.slug}.png"
        svg = SVG_DIR / f"{number}_{d.slug}.svg"
        rows.append(f"| {number} | {d.title} | {d.chapter} | {d.description} | `{png}` | `{svg}` |")
        manifest.append(
            {
                "number": number,
                "title": d.title,
                "slug": d.slug,
                "chapter": d.chapter,
                "description": d.description,
                "png": str(png),
                "svg": str(svg),
            }
        )
    INDEX.write_text("\n".join(rows), encoding="utf-8")
    MANIFEST.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")


def write_alignment_notes() -> None:
    ALIGNMENT.write_text(
        "\n".join(
            [
                "# 高階圖表文案校準說明",
                "",
                "- 這組圖表延續目前報告文案，不宣稱第四章已有正式使用者實驗結果。",
                "- TMflow 與 TM5-700 實機控制一律以 RobotFacade、FakeRobot、後續整合與安全規劃描述。",
                "- Vision/FEN 圖表保留 YOLOv8、SAHI、BoardMapper、FEN validation，但不宣稱辨識完全正確。",
                "- 測試矩陣定位為初步測試、品質驗證與後續研究資料規劃。",
                "- DFD、UML、State Machine、ERD、Fault Tree 等圖表可凸顯系統工程深度，適合口試或報告審查使用。",
            ]
        ),
        encoding="utf-8",
    )


def clean_outputs() -> None:
    PNG_DIR.mkdir(parents=True, exist_ok=True)
    SVG_DIR.mkdir(parents=True, exist_ok=True)
    for folder, suffix in ((PNG_DIR, ".png"), (SVG_DIR, ".svg")):
        for old in folder.glob(f"*{suffix}"):
            old.unlink()
    for old in (CONTACT_SHEET, INDEX, MANIFEST, ALIGNMENT, PACKAGE):
        if old.exists():
            old.unlink()


def package_outputs() -> None:
    tmp_base = OUT_ROOT.parent / "_high_level_report_diagrams_package_tmp"
    tmp_zip = tmp_base.with_suffix(".zip")
    if tmp_zip.exists():
        tmp_zip.unlink()
    shutil.make_archive(str(tmp_base), "zip", root_dir=OUT_ROOT, base_dir=".")
    tmp_zip.replace(PACKAGE)


def main() -> int:
    clean_outputs()
    diagrams = [tidy_diagram(builder()) for builder in BUILDERS]
    png_paths: list[Path] = []
    for idx, d in enumerate(diagrams, start=1):
        number = f"H{idx:02d}"
        png = PNG_DIR / f"{number}_{d.slug}.png"
        svg = SVG_DIR / f"{number}_{d.slug}.svg"
        d.render_png(png)
        d.render_svg(svg)
        png_paths.append(png)
    build_contact_sheet(png_paths)
    write_index(diagrams)
    write_alignment_notes()
    package_outputs()
    print(
        json.dumps(
            {
                "diagrams": len(diagrams),
                "png_dir": str(PNG_DIR),
                "svg_dir": str(SVG_DIR),
                "index": str(INDEX),
                "alignment": str(ALIGNMENT),
                "contact_sheet": str(CONTACT_SHEET),
                "package": str(PACKAGE),
            },
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
