from __future__ import annotations

import html
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Iterable

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.lib.utils import ImageReader
from reportlab.platypus import Image, PageBreak, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from backend import DeviceChecklistBackend
from config import LOGO_CANDIDATES
from photos import device_photo_paths


def build_device_report(
    backend: DeviceChecklistBackend,
    file_name: str,
    photos_location: str | Path,
) -> Path:
    sn, device_date, _status, comment = backend._parse_device_file_name(file_name)
    rows = backend.list_items(file_name)
    report_path = _report_path(backend, file_name, sn, device_date)
    report_path.parent.mkdir(parents=True, exist_ok=True)

    styles = getSampleStyleSheet()
    title_style = styles["Title"]
    heading_style = styles["Heading2"]
    normal_style = styles["BodyText"]

    story = [
        Paragraph("Device Report", title_style),
        Paragraph(f"Serial Number: {sn}", normal_style),
        Paragraph(f"Date: {device_date}", normal_style),
        Paragraph(f"Comment: {comment or '-'}", normal_style),
        Spacer(1, 0.2 * inch),
    ]

    problem_rows = [row for row in rows if row["Status"] != "check"]
    story.append(Paragraph("Problems Found", heading_style))
    if problem_rows:
        story.append(_rows_table(problem_rows, include_status=True))
    else:
        story.append(Paragraph("All checklist items are checked.", normal_style))

    story.extend([Spacer(1, 0.25 * inch), Paragraph("Final Test Checklist", heading_style)])
    final_rows = [row for row in rows if row["Category"] == "Final test"]
    if final_rows:
        story.append(_rows_table(final_rows, include_status=True))
    else:
        story.append(Paragraph("No final test rows found.", normal_style))

    image_paths = device_photo_paths(photos_location, file_name)
    story.append(PageBreak())
    story.append(Paragraph("Images", heading_style))
    if image_paths:
        for index, image_path in enumerate(image_paths, start=1):
            if index > 1:
                story.append(Spacer(1, 0.2 * inch))
            story.append(Paragraph(image_path.name, normal_style))
            story.append(_report_image(image_path))
    else:
        story.append(Paragraph("No images found for this device.", normal_style))

    document = SimpleDocTemplate(
        str(report_path),
        pagesize=A4,
        rightMargin=0.5 * inch,
        leftMargin=0.5 * inch,
        topMargin=0.9 * inch,
        bottomMargin=0.5 * inch,
    )
    document.build(story, onFirstPage=_draw_report_header, onLaterPages=_draw_report_header)
    return report_path


def build_all_devices_report(device_rows: Iterable[dict[str, str]]) -> Path:
    report_path = _all_devices_report_path()
    report_path.parent.mkdir(parents=True, exist_ok=True)

    styles = getSampleStyleSheet()
    title_style = styles["Title"]
    normal_style = styles["BodyText"]

    rows = []
    for index, row in enumerate(device_rows, start=1):
        rows.append(
            {
                "ID": str(index),
                "Serial Number": row["sn"],
                "Date": row["date"],
                "Status": row["status"],
                "Comment": row["comment"],
                "Last Updated": row["updated"],
                "CSV File": row["file"],
            }
        )

    story = [
        Paragraph("All Devices Report", title_style),
        Paragraph(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M')}", normal_style),
        Spacer(1, 0.2 * inch),
    ]

    if rows:
        story.append(_devices_table(rows))
    else:
        story.append(Paragraph("No devices found.", normal_style))

    document = SimpleDocTemplate(
        str(report_path),
        pagesize=A4,
        rightMargin=0.45 * inch,
        leftMargin=0.45 * inch,
        topMargin=0.9 * inch,
        bottomMargin=0.5 * inch,
    )
    document.build(story, onFirstPage=_draw_report_header, onLaterPages=_draw_report_header)
    return report_path


def _draw_report_header(canvas, document) -> None:
    logo_path = _logo_path()
    if not logo_path:
        return

    try:
        logo = ImageReader(str(logo_path))
        image_width, image_height = logo.getSize()
    except Exception:
        return

    max_width = 1.35 * inch
    max_height = 0.55 * inch
    scale = min(max_width / image_width, max_height / image_height, 1)
    draw_width = image_width * scale
    draw_height = image_height * scale
    x = document.leftMargin
    y = A4[1] - document.topMargin + 0.18 * inch
    canvas.drawImage(
        logo,
        x,
        y,
        width=draw_width,
        height=draw_height,
        preserveAspectRatio=True,
        mask="auto",
    )


def _logo_path() -> Path | None:
    for logo_path in LOGO_CANDIDATES:
        if logo_path.exists():
            return logo_path
    return None


def _rows_table(rows: list[dict[str, str]], include_status: bool) -> Table:
    headers = ["Category", "Item", "Status", "Comment"] if include_status else ["Category", "Item", "Comment"]
    data = [headers]
    body_style = getSampleStyleSheet()["BodyText"]
    for row in rows:
        status = "Checked" if row["Status"] == "check" else "Unchecked"
        values = [row["Category"], row["Item"], status, row["Comment"]] if include_status else [
            row["Category"],
            row["Item"],
            row["Comment"],
        ]
        data.append([Paragraph(html.escape(str(value)).replace("\n", "<br/>"), body_style) for value in values])

    table = Table(data, colWidths=[1.25 * inch, 2.25 * inch, 0.9 * inch, 2.25 * inch])
    _apply_table_style(table)
    return table


def _devices_table(rows: list[dict[str, str]]) -> Table:
    headers = ["ID", "Serial Number", "Date", "Status", "Comment", "Last Updated", "CSV File"]
    body_style = getSampleStyleSheet()["BodyText"]
    data = [headers]
    for row in rows:
        data.append([Paragraph(html.escape(str(row[header])).replace("\n", "<br/>"), body_style) for header in headers])

    table = Table(
        data,
        colWidths=[0.35 * inch, 0.95 * inch, 0.8 * inch, 0.75 * inch, 1.0 * inch, 1.15 * inch, 1.7 * inch],
    )
    _apply_table_style(table)
    return table


def _apply_table_style(table: Table) -> None:
    table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#e8e8e8")),
                ("GRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#bbbbbb")),
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f7f7f7")]),
            ]
        )
    )


def _report_image(image_path: Path) -> Image:
    max_width = 7.0 * inch
    max_height = 8.5 * inch
    image = Image(str(image_path))
    width_scale = max_width / image.imageWidth
    height_scale = max_height / image.imageHeight
    scale = min(width_scale, height_scale, 1)
    image.drawWidth = image.imageWidth * scale
    image.drawHeight = image.imageHeight * scale
    return image


def _report_path(backend: DeviceChecklistBackend, file_name: str, sn: str, device_date: str) -> Path:
    device_stem = Path(file_name).stem
    safe_name = f"{backend._safe_title_part(sn)}-{backend._safe_title_part(device_date)}"
    report_folder = Path(tempfile.gettempdir()) / "DeviceChecklistReports" / device_stem
    return report_folder / f"{safe_name}.pdf"


def _all_devices_report_path() -> Path:
    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    report_folder = Path(tempfile.gettempdir()) / "DeviceChecklistReports"
    return report_folder / f"all-devices-{timestamp}.pdf"
