from __future__ import annotations

import base64
import html
import json
import shutil
import sys
import tempfile
import tkinter as tk
import webbrowser
from datetime import datetime
from pathlib import Path
from tkinter import filedialog, messagebox, simpledialog, ttk

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.lib.utils import ImageReader
from reportlab.platypus import (
    Image,
    PageBreak,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

from backend import DeviceChecklistBackend


def app_root() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent.parent


APP_ROOT = app_root()
DEFAULT_STORAGE = APP_ROOT / "data" / "devices"
DEFAULT_PHOTOS = APP_ROOT / "data" / "photos"
DEFAULT_REPORTS = APP_ROOT / "Reports"
DEFAULT_CONFIG = Path(__file__).resolve().parent / "checklist_config.json"
LOGO_CANDIDATES = [
    APP_ROOT / "logo.spg",
    APP_ROOT / "Logo.spg",
    APP_ROOT / "logo.png",
    APP_ROOT / "Logo.png",
    APP_ROOT / "logo.jpg",
    APP_ROOT / "Logo.jpg",
    APP_ROOT / "logo.jpeg",
    APP_ROOT / "Logo.jpeg",
]

DEVICE_STATUSES = {
    "received": "#ffffff",
    "recived": "#ffffff",
    "tested": "#fff2b8",
    "dismantled": "#ffd7a8",
    "dismanteled": "#ffd7a8",
    "notFixable": "#f6b8b8",
    "fixed": "#cfeecf",
}
EDITABLE_DEVICE_STATUSES = ["received", "tested", "dismantled", "notFixable", "fixed"]
STATUS_ALIASES = {
    "recived": "received",
    "dismanteled": "dismantled",
}


def resolve_config_path(config_path: Path) -> Path:
    candidates = [
        config_path,
        Path.cwd() / "checklist_config.json",
        Path(__file__).resolve().parent.parent / "checklist_config.json",
    ]
    for candidate in candidates:
        if candidate.exists():
            return candidate
    return config_path


def normalize_device_status(status: str) -> str:
    return STATUS_ALIASES.get(status, status)


def load_checklist_config(config_path: Path) -> tuple[dict[str, list[str]], dict[str, str]]:
    if not config_path.exists():
        raise FileNotFoundError(f"Checklist config not found: {config_path}")

    with config_path.open("r", encoding="utf-8") as config_file:
        config = json.load(config_file)

    checklists = config.get("checklists")
    status_after_checklist = config.get("status_after_checklist", {})

    if not isinstance(checklists, dict) or not checklists:
        raise ValueError("checklist_config.json must contain a non-empty 'checklists' object")

    cleaned_checklists: dict[str, list[str]] = {}
    for category, items in checklists.items():
        if not isinstance(category, str) or not category.strip():
            raise ValueError("Checklist category names must be non-empty strings")
        if not isinstance(items, list) or not all(isinstance(item, str) and item.strip() for item in items):
            raise ValueError(f"Checklist '{category}' must contain a list of non-empty item names")
        cleaned_checklists[category.strip()] = [item.strip() for item in items]

    if not isinstance(status_after_checklist, dict):
        raise ValueError("'status_after_checklist' must be an object")

    cleaned_statuses = {
        category: normalize_device_status(str(status_after_checklist.get(category, "tested")).strip())
        for category in cleaned_checklists
    }
    return cleaned_checklists, cleaned_statuses


class DeviceChecklistApp(tk.Tk):
    def __init__(
        self,
        storage_location: str | Path = DEFAULT_STORAGE,
        photos_location: str | Path = DEFAULT_PHOTOS,
        reports_location: str | Path = DEFAULT_REPORTS,
        config_path: str | Path = DEFAULT_CONFIG,
    ):
        super().__init__()
        self.title("Device Checklist Logger")
        self.geometry("1260x720")
        self.minsize(980, 560)

        self.backend = DeviceChecklistBackend(storage_location)
        self.photos_location = Path(photos_location)
        self.reports_location = Path(reports_location)
        self.photos_location.mkdir(parents=True, exist_ok=True)
        self.reports_location.mkdir(parents=True, exist_ok=True)
        self.config_path = resolve_config_path(Path(config_path))
        self.checklists, self.status_after_checklist = load_checklist_config(self.config_path)
        self.selected_file_name: str | None = None
        self.search_var = tk.StringVar()
        self.search_var.trace_add("write", lambda *_args: self.refresh_table())
        self.sort_column = "id"
        self.sort_reverse = False

        self._configure_style()
        self._build_layout()
        self.refresh_table()

    def _configure_style(self) -> None:
        self.configure(bg="#f2f2f2")

        style = ttk.Style(self)
        style.theme_use("clam")
        style.configure("Treeview", rowheight=32, font=("Segoe UI", 10), borderwidth=1)
        style.configure("Treeview.Heading", font=("Segoe UI", 10, "bold"), relief="raised")
        style.map("Treeview", background=[("selected", "#25466f")])

        style.configure("Blue.TButton", font=("Segoe UI", 10), padding=10)
        style.map("Blue.TButton", background=[("active", "#315985")])

    def _build_layout(self) -> None:
        title = tk.Label(
            self,
            text="Device Checklist Logger",
            bg="#f2f2f2",
            fg="#222222",
            font=("Segoe UI", 13, "bold"),
        )
        title.pack(anchor="w", padx=12, pady=(14, 8))

        main = tk.Frame(self, bg="#f2f2f2")
        main.pack(fill="both", expand=True, padx=10, pady=10)

        sidebar = tk.Frame(main, bg="#ffffff", bd=2, relief="groove", width=285)
        sidebar.pack(side="left", fill="y", padx=(0, 12))
        sidebar.pack_propagate(False)

        table_panel = tk.Frame(main, bg="#ffffff", bd=2, relief="groove")
        table_panel.pack(side="left", fill="both", expand=True)

        self._build_sidebar(sidebar)
        self._build_table(table_panel)

    def _build_sidebar(self, parent: tk.Frame) -> None:
        tk.Label(
            parent,
            text="Device",
            bg="#ffffff",
            fg="#222222",
            font=("Segoe UI", 10, "bold"),
        ).pack(anchor="w", padx=14, pady=(16, 6))

        self.selected_label = tk.Label(
            parent,
            text="No device selected",
            bg="#ffffff",
            fg="#333333",
            anchor="w",
            bd=1,
            relief="solid",
            padx=8,
            height=2,
        )
        self.selected_label.pack(fill="x", padx=14, pady=(0, 22))

        self._button(parent, "New Device", self.new_device, primary=True)
        self._button(parent, "Edit Device", self.edit_device, primary=True)
        self._button(parent, "Enter Form", self.enter_form, primary=True, tall=True)

        ttk.Separator(parent, orient="horizontal").pack(fill="x", padx=14, pady=22)

        self._button(parent, "Refresh Table", self.refresh_table)
        self._button(parent, "Print report", self.print_report)
        self._button(parent, "Delete Device", self.delete_device)
        self._button(parent, "Mark Not Fixable", self.mark_not_fixable)

    def _button(
        self,
        parent: tk.Frame,
        text: str,
        command,
        primary: bool = False,
        tall: bool = False,
    ) -> None:
        bg = "#23456f" if primary else "#ffffff"
        fg = "#ffffff" if primary else "#222222"
        button = tk.Button(
            parent,
            text=text,
            command=command,
            bg=bg,
            fg=fg,
            activebackground="#315985",
            activeforeground="#ffffff",
            bd=2,
            relief="ridge",
            font=("Segoe UI", 10, "bold" if tall else "normal"),
            height=3 if tall else 2,
        )
        button.pack(fill="x", padx=14, pady=7)

    def _build_table(self, parent: tk.Frame) -> None:
        search_bar = tk.Frame(parent, bg="#ffffff")
        search_bar.pack(fill="x", padx=10, pady=(10, 0))

        tk.Label(
            search_bar,
            text="Search",
            bg="#ffffff",
            fg="#222222",
            font=("Segoe UI", 10, "bold"),
        ).pack(side="left", padx=(0, 8))
        tk.Entry(search_bar, textvariable=self.search_var, font=("Segoe UI", 10)).pack(side="left", fill="x", expand=True)

        columns = ("id", "sn", "date", "status", "comment", "file")
        self.table = ttk.Treeview(parent, columns=columns, show="headings", selectmode="browse")

        headings = {
            "id": "ID",
            "sn": "SerialNumber",
            "date": "Date",
            "status": "Status",
            "comment": "Comment",
            "file": "CSV File",
        }
        widths = {"id": 70, "sn": 210, "date": 145, "status": 130, "comment": 230, "file": 320}

        for column in columns:
            self.table.heading(column, text=headings[column], command=lambda selected=column: self._sort_by(selected))
            self.table.column(column, width=widths[column], minwidth=70, anchor="center")

        for status, color in DEVICE_STATUSES.items():
            self.table.tag_configure(status, background=color)

        y_scroll = ttk.Scrollbar(parent, orient="vertical", command=self.table.yview)
        self.table.configure(yscrollcommand=y_scroll.set)

        self.table.pack(side="left", fill="both", expand=True, padx=(10, 0), pady=10)
        y_scroll.pack(side="right", fill="y", padx=(0, 10), pady=10)
        self.table.bind("<<TreeviewSelect>>", self._on_select)
        self.table.bind("<Double-1>", lambda _event: self.enter_form())

    def refresh_table(self) -> None:
        for row_id in self.table.get_children():
            self.table.delete(row_id)

        device_rows = []
        search_text = self.search_var.get().strip().lower()

        for path in self.backend.list_devices():
            try:
                sn, device_date, status, comment = self.backend._parse_device_file_name(path.name)
            except ValueError:
                continue

            row = {
                "sn": sn,
                "date": device_date,
                "status": status,
                "comment": comment,
                "file": path.name,
            }
            if search_text and search_text not in " ".join(row.values()).lower():
                continue
            device_rows.append(row)

        if self.sort_column == "id":
            if self.sort_reverse:
                device_rows.reverse()
        else:
            device_rows.sort(key=lambda row: row[self.sort_column].lower(), reverse=self.sort_reverse)

        for index, row in enumerate(device_rows, start=1):
            self.table.insert(
                "",
                "end",
                iid=row["file"],
                values=(index, row["sn"], row["date"], row["status"], row["comment"], row["file"]),
                tags=(row["status"],),
            )

        self.selected_file_name = None
        self.selected_label.config(text="No device selected")

    def new_device(self) -> None:
        sn = simpledialog.askstring("New Device", "Enter serial number:", parent=self)
        if not sn:
            return
        comment = simpledialog.askstring("New Device", "Enter device comment:", parent=self) or ""

        try:
            path = self.backend.AddNewDevice(sn=sn.strip(), status="received", comment=comment.strip())
            self._ensure_configured_checklist_items(path.name)
            self.refresh_table()
            self._select_device(path.name)
        except Exception as exc:
            messagebox.showerror("New Device", str(exc), parent=self)

    def edit_device(self) -> None:
        if not self.selected_file_name:
            messagebox.showinfo("Edit Device", "Select a device first.", parent=self)
            return

        editor = DeviceTitleEditor(self, self.backend, self.selected_file_name)
        self.wait_window(editor)
        self.refresh_table()

    def delete_device(self) -> None:
        if not self.selected_file_name:
            messagebox.showinfo("Delete Device", "Select a device first.", parent=self)
            return

        confirmed = messagebox.askyesno(
            "Delete Device",
            f"Delete {self.selected_file_name}?",
            parent=self,
        )
        if not confirmed:
            return

        try:
            self.backend.delete_device(self.selected_file_name)
            self.refresh_table()
        except Exception as exc:
            messagebox.showerror("Delete Device", str(exc), parent=self)

    def mark_not_fixable(self) -> None:
        self._change_selected_status("notFixable")

    def print_report(self) -> None:
        ReportMenu(self)

    def print_device_report(self) -> None:
        if not self.selected_file_name:
            messagebox.showinfo("Print Report", "Select a device first.", parent=self)
            return

        try:
            self._ensure_configured_checklist_items(self.selected_file_name)
            report_path = self._build_device_report(self.selected_file_name)
            opened = webbrowser.open(report_path.as_uri())
            if not opened:
                messagebox.showinfo("Print Report", f"Report created:\n{report_path}", parent=self)
        except Exception as exc:
            messagebox.showerror("Print Report", str(exc), parent=self)

    def print_all_devices_report(self) -> None:
        try:
            report_path = self._build_all_devices_report()
            opened = webbrowser.open(report_path.as_uri())
            if not opened:
                messagebox.showinfo("All Devices Report", f"Report created:\n{report_path}", parent=self)
        except Exception as exc:
            messagebox.showerror("All Devices Report", str(exc), parent=self)

    def enter_form(self) -> None:
        if not self.selected_file_name:
            messagebox.showinfo("Enter Form", "Select a device first.", parent=self)
            return

        self._ensure_configured_checklist_items(self.selected_file_name)

        ChecklistWindow(
            self,
            self.backend,
            self.selected_file_name,
            self.checklists,
            self.status_after_checklist,
            self.photos_location,
            self._after_checklist_saved,
        )

    def _after_checklist_saved(self, current_file_name: str) -> None:
        self.selected_file_name = current_file_name
        self.refresh_table()
        self._select_device(current_file_name)

    def _ensure_configured_checklist_items(self, csv_name: str) -> None:
        existing_rows = self.backend.list_items(csv_name)
        existing_keys = {(row["Category"], row["Item"]) for row in existing_rows}
        for category, items in self.checklists.items():
            for item in items:
                if (category, item) not in existing_keys:
                    self.backend.add_item(csv_name, category, item)

    def _change_selected_status(self, new_status: str) -> None:
        if not self.selected_file_name:
            messagebox.showinfo("Status", "Select a device first.", parent=self)
            return

        try:
            new_path = self.backend.ChangeTitle(self.selected_file_name, status=new_status)
            self.refresh_table()
            self._select_device(new_path.name)
        except Exception as exc:
            messagebox.showerror("Status", str(exc), parent=self)

    def _sort_by(self, column: str) -> None:
        if self.sort_column == column:
            self.sort_reverse = not self.sort_reverse
        else:
            self.sort_column = column
            self.sort_reverse = False
        self.refresh_table()

    def _select_device(self, file_name: str) -> None:
        if self.table.exists(file_name):
            self.table.selection_set(file_name)
            self.table.focus(file_name)
            self.table.see(file_name)
            self.selected_file_name = file_name
            self.selected_label.config(text=file_name)

    def _on_select(self, _event) -> None:
        selected = self.table.selection()
        if not selected:
            return
        self.selected_file_name = selected[0]
        self.selected_label.config(text=self.selected_file_name)

    def _build_device_report(self, file_name: str) -> Path:
        sn, device_date, _status, comment = self.backend._parse_device_file_name(file_name)
        rows = self.backend.list_items(file_name)
        report_path = self._report_path(file_name, sn, device_date)
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

        unchecked_rows = [row for row in rows if row["Status"] != "check"]
        story.append(Paragraph("Unchecked Items", heading_style))
        if unchecked_rows:
            story.append(self._rows_table(unchecked_rows, include_status=True))
        else:
            story.append(Paragraph("All checklist items are checked.", normal_style))

        story.extend([Spacer(1, 0.25 * inch), Paragraph("Final Test Checklist", heading_style)])
        final_rows = [row for row in rows if row["Category"] == "Final test"]
        if final_rows:
            story.append(self._rows_table(final_rows, include_status=True))
        else:
            story.append(Paragraph("No final test rows found.", normal_style))

        image_paths = self._device_photo_paths(file_name)
        story.append(PageBreak())
        story.append(Paragraph("Images", heading_style))
        if image_paths:
            for index, image_path in enumerate(image_paths, start=1):
                if index > 1:
                    story.append(Spacer(1, 0.2 * inch))
                story.append(Paragraph(image_path.name, normal_style))
                story.append(self._report_image(image_path))
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
        document.build(story, onFirstPage=self._draw_report_header, onLaterPages=self._draw_report_header)
        return report_path

    def _build_all_devices_report(self) -> Path:
        report_path = self._all_devices_report_path()
        report_path.parent.mkdir(parents=True, exist_ok=True)

        styles = getSampleStyleSheet()
        title_style = styles["Title"]
        normal_style = styles["BodyText"]

        device_rows = []
        for index, path in enumerate(self.backend.list_devices(), start=1):
            try:
                sn, device_date, status, comment = self.backend._parse_device_file_name(path.name)
            except ValueError:
                continue
            device_rows.append(
                {
                    "ID": str(index),
                    "Serial Number": sn,
                    "Date": device_date,
                    "Status": normalize_device_status(status),
                    "Comment": comment,
                    "CSV File": path.name,
                }
            )

        story = [
            Paragraph("All Devices Report", title_style),
            Paragraph(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M')}", normal_style),
            Spacer(1, 0.2 * inch),
        ]

        if device_rows:
            story.append(self._devices_table(device_rows))
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
        document.build(story, onFirstPage=self._draw_report_header, onLaterPages=self._draw_report_header)
        return report_path

    def _draw_report_header(self, canvas, document) -> None:
        logo_path = self._logo_path()
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

    def _logo_path(self) -> Path | None:
        for logo_path in LOGO_CANDIDATES:
            if logo_path.exists():
                return logo_path
        return None

    def _rows_table(self, rows: list[dict[str, str]], include_status: bool) -> Table:
        headers = ["Category", "Item", "Status", "Comment"] if include_status else ["Category", "Item", "Comment"]
        data = [headers]
        for row in rows:
            status = "Checked" if row["Status"] == "check" else "Unchecked"
            values = [row["Category"], row["Item"], status, row["Comment"]] if include_status else [
                row["Category"],
                row["Item"],
                row["Comment"],
            ]
            data.append(
                [
                    Paragraph(html.escape(str(value)).replace("\n", "<br/>"), getSampleStyleSheet()["BodyText"])
                    for value in values
                ]
            )

        table = Table(data, colWidths=[1.25 * inch, 2.25 * inch, 0.9 * inch, 2.25 * inch])
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
        return table

    def _devices_table(self, rows: list[dict[str, str]]) -> Table:
        headers = ["ID", "Serial Number", "Date", "Status", "Comment", "CSV File"]
        body_style = getSampleStyleSheet()["BodyText"]
        data = [headers]
        for row in rows:
            data.append(
                [
                    Paragraph(html.escape(str(row[header])).replace("\n", "<br/>"), body_style)
                    for header in headers
                ]
            )

        table = Table(data, colWidths=[0.4 * inch, 1.1 * inch, 0.9 * inch, 0.9 * inch, 1.2 * inch, 2.2 * inch])
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
        return table

    def _report_image(self, image_path: Path) -> Image:
        max_width = 7.0 * inch
        max_height = 8.5 * inch
        image = Image(str(image_path))
        width_scale = max_width / image.imageWidth
        height_scale = max_height / image.imageHeight
        scale = min(width_scale, height_scale, 1)
        image.drawWidth = image.imageWidth * scale
        image.drawHeight = image.imageHeight * scale
        return image

    def _report_path(self, file_name: str, sn: str, device_date: str) -> Path:
        device_stem = Path(file_name).stem
        safe_name = f"{self.backend._safe_title_part(sn)}-{self.backend._safe_title_part(device_date)}"
        report_folder = Path(tempfile.gettempdir()) / "DeviceChecklistReports" / device_stem
        return report_folder / f"{safe_name}.pdf"

    def _all_devices_report_path(self) -> Path:
        timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        report_folder = Path(tempfile.gettempdir()) / "DeviceChecklistReports"
        return report_folder / f"all-devices-{timestamp}.pdf"

    def _device_photo_paths(self, file_name: str) -> list[Path]:
        photo_folder = self.photos_location / Path(file_name).stem
        if not photo_folder.exists():
            return []
        image_suffixes = {".jpg", ".jpeg", ".png", ".bmp", ".gif"}
        return sorted(path for path in photo_folder.iterdir() if path.suffix.lower() in image_suffixes)


class ReportMenu(tk.Toplevel):
    def __init__(self, parent: DeviceChecklistApp):
        super().__init__(parent)
        self.parent = parent

        self.title("Reports")
        self.geometry("340x220")
        self.resizable(False, False)
        self.configure(bg="#ffffff")

        tk.Label(
            self,
            text="Choose report",
            bg="#ffffff",
            fg="#222222",
            font=("Segoe UI", 12, "bold"),
        ).pack(anchor="w", padx=18, pady=(18, 10))

        tk.Button(
            self,
            text="Selected device report",
            command=self._run_device_report,
            bg="#23456f",
            fg="#ffffff",
            activebackground="#315985",
            activeforeground="#ffffff",
            height=2,
        ).pack(fill="x", padx=18, pady=7)

        tk.Button(
            self,
            text="All devices table",
            command=self._run_all_devices_report,
            bg="#ffffff",
            fg="#222222",
            activebackground="#e8e8e8",
            height=2,
        ).pack(fill="x", padx=18, pady=7)

        tk.Button(self, text="Cancel", command=self.destroy, height=2).pack(fill="x", padx=18, pady=(14, 0))

        self.transient(parent)
        self.grab_set()

    def _run_device_report(self) -> None:
        self.destroy()
        self.parent.print_device_report()

    def _run_all_devices_report(self) -> None:
        self.destroy()
        self.parent.print_all_devices_report()


class DeviceTitleEditor(tk.Toplevel):
    def __init__(self, parent: DeviceChecklistApp, backend: DeviceChecklistBackend, file_name: str):
        super().__init__(parent)
        self.backend = backend
        self.file_name = file_name

        self.title("Edit Device")
        self.geometry("360x330")
        self.resizable(False, False)
        self.configure(bg="#ffffff")

        sn, device_date, status, comment = backend._parse_device_file_name(file_name)
        self.sn_var = tk.StringVar(value=sn)
        self.date_var = tk.StringVar(value=device_date)
        self.status_var = tk.StringVar(value=normalize_device_status(status))
        self.comment_var = tk.StringVar(value=comment)

        self._field("Serial number", self.sn_var)
        self._field("Date", self.date_var)
        self._field("Comment", self.comment_var)

        tk.Label(self, text="Status", bg="#ffffff", font=("Segoe UI", 10, "bold")).pack(
            anchor="w", padx=18, pady=(10, 4)
        )
        status_box = ttk.Combobox(
            self,
            textvariable=self.status_var,
            values=EDITABLE_DEVICE_STATUSES,
            state="readonly",
        )
        status_box.pack(fill="x", padx=18)

        tk.Button(
            self,
            text="Save",
            command=self.save,
            bg="#23456f",
            fg="#ffffff",
            height=2,
        ).pack(fill="x", padx=18, pady=20)

        self.transient(parent)
        self.grab_set()

    def _field(self, label: str, variable: tk.StringVar) -> None:
        tk.Label(self, text=label, bg="#ffffff", font=("Segoe UI", 10, "bold")).pack(
            anchor="w", padx=18, pady=(12, 4)
        )
        tk.Entry(self, textvariable=variable).pack(fill="x", padx=18)

    def save(self) -> None:
        try:
            self.backend.ChangeTitle(
                self.file_name,
                sn=self.sn_var.get().strip(),
                device_date=self.date_var.get().strip(),
                status=self.status_var.get().strip(),
                comment=self.comment_var.get().strip(),
            )
            self.destroy()
        except Exception as exc:
            messagebox.showerror("Edit Device", str(exc), parent=self)


class ChecklistWindow(tk.Toplevel):
    def __init__(
        self,
        parent: DeviceChecklistApp,
        backend: DeviceChecklistBackend,
        file_name: str,
        checklists: dict[str, list[str]],
        status_after_checklist: dict[str, str],
        photos_location: str | Path,
        on_saved,
    ):
        super().__init__(parent)
        self.backend = backend
        self.file_name = file_name
        self.checklists = checklists
        self.status_after_checklist = status_after_checklist
        self.photos_location = Path(photos_location)
        self.on_saved = on_saved
        self.category_names = list(self.checklists)
        self.category_index = self._first_incomplete_category_index()
        self.row_widgets: list[tuple[str, tk.BooleanVar, tk.StringVar]] = []
        self.checklist_font = ("Segoe UI", 12)
        self.checklist_heading_font = ("Segoe UI", 12, "bold")
        self.checklist_entry_font = ("Segoe UI", 12)

        self.title("Device Checklist")
        self.geometry("900x620")
        self.minsize(760, 500)
        self.configure(bg="#f2f2f2")

        self.header = tk.Label(
            self,
            bg="#f2f2f2",
            fg="#222222",
            font=("Segoe UI", 14, "bold"),
        )
        self.header.pack(anchor="w", padx=14, pady=(14, 8))

        content_panel = tk.Frame(self, bg="#ffffff", bd=2, relief="groove")
        content_panel.pack(fill="both", expand=True, padx=14, pady=(0, 10))

        self.content_canvas = tk.Canvas(content_panel, bg="#ffffff", highlightthickness=0)
        self.content_scrollbar = ttk.Scrollbar(
            content_panel,
            orient="vertical",
            command=self.content_canvas.yview,
        )
        self.content = tk.Frame(self.content_canvas, bg="#ffffff")
        self.content_window = self.content_canvas.create_window(
            (0, 0),
            window=self.content,
            anchor="n",
        )
        self.content_canvas.configure(yscrollcommand=self.content_scrollbar.set)
        self.content_canvas.pack(side="left", fill="both", expand=True)
        self.content_scrollbar.pack(side="right", fill="y")
        self.content.bind("<Configure>", self._update_scroll_region)
        self.content_canvas.bind("<Configure>", self._resize_scroll_content)
        self.content_canvas.bind("<Enter>", self._bind_mousewheel)
        self.content_canvas.bind("<Leave>", self._unbind_mousewheel)

        actions = tk.Frame(self, bg="#f2f2f2")
        actions.pack(fill="x", padx=14, pady=(0, 14))

        tk.Button(actions, text="Back", command=self.previous_category, width=16).pack(side="left")
        tk.Button(actions, text="Save", command=self.save_current, width=16).pack(side="left", padx=8)
        tk.Button(actions, text="Take Picture", command=self.take_picture, width=16).pack(side="left")
        tk.Button(
            actions,
            text="Complete And Continue",
            command=self.complete_current_category,
            bg="#23456f",
            fg="#ffffff",
            width=24,
            height=2,
        ).pack(side="right")

        self.render_category()
        self.protocol("WM_DELETE_WINDOW", self.close)
        self.transient(parent)
        self.grab_set()

    def _update_scroll_region(self, _event=None) -> None:
        self.content_canvas.configure(scrollregion=self.content_canvas.bbox("all"))

    def _resize_scroll_content(self, event) -> None:
        content_width = min(max(event.width - 36, 720), 1060)
        self.content_canvas.coords(self.content_window, event.width / 2, 0)
        self.content_canvas.itemconfigure(self.content_window, width=content_width)

    def _bind_mousewheel(self, _event=None) -> None:
        self.content_canvas.bind_all("<MouseWheel>", self._on_mousewheel)

    def _unbind_mousewheel(self, _event=None) -> None:
        self.content_canvas.unbind_all("<MouseWheel>")

    def _on_mousewheel(self, event) -> None:
        self.content_canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")

    def render_category(self) -> None:
        for child in self.content.winfo_children():
            child.destroy()
        self.row_widgets.clear()

        category = self.category_names[self.category_index]
        self.header.config(text=f"{self.file_name} - {category}")

        header = tk.Frame(self.content, bg="#e8e8e8")
        header.pack(fill="x", padx=18, pady=(12, 2))
        self._configure_checklist_grid(header)
        self._grid_cell(header, "Item", 0, bold=True)
        self._grid_cell(header, "Check", 1, bold=True, anchor="center")
        self._grid_cell(header, "Comment", 2, bold=True)

        rows = [row for row in self.backend.list_items(self.file_name) if row["Category"] == category]
        for row in rows:
            line = tk.Frame(self.content, bg="#ffffff")
            line.pack(fill="x", padx=18, pady=0)
            self._configure_checklist_grid(line)

            self._grid_cell(line, row["Item"], 0)

            checked_var = tk.BooleanVar(value=self._status_is_checked(row["Status"]))
            check_box = self._large_check_box(line, checked_var)
            check_box.grid(row=0, column=1, sticky="nsew", padx=6, pady=2)

            comment_var = tk.StringVar(value=row["Comment"])
            tk.Entry(
                line,
                textvariable=comment_var,
                font=self.checklist_entry_font,
            ).grid(row=0, column=2, sticky="ew", padx=(8, 0), pady=4, ipady=4)

            self.row_widgets.append((row["Item"], checked_var, comment_var))

        self.content_canvas.yview_moveto(0)

    def previous_category(self) -> None:
        self.save_current(show_message=False)
        if self.category_index > 0:
            self.category_index -= 1
            self.render_category()

    def save_current(self, show_message: bool = True) -> None:
        category = self.category_names[self.category_index]
        for item, checked_var, comment_var in self.row_widgets:
            self.backend.update_item(
                self.file_name,
                category,
                item,
                status=self._checked_status(checked_var),
                comment=comment_var.get(),
            )
        if show_message:
            messagebox.showinfo("Checklist", "Saved.", parent=self)

    def complete_current_category(self) -> None:
        self.save_current(show_message=False)
        category = self.category_names[self.category_index]

        rows = [row for row in self.backend.list_items(self.file_name) if row["Category"] == category]
        if any(row["Status"] != "check" for row in rows):
            proceed = messagebox.askyesno(
                "Checklist",
                "Some items are still unchecked. Continue anyway?",
                parent=self,
            )
            if not proceed:
                return

        new_status = self.status_after_checklist[category]
        new_path = self.backend.ChangeTitle(self.file_name, status=new_status)
        self.file_name = new_path.name

        if self.category_index < len(self.category_names) - 1:
            self.category_index += 1
            self.render_category()
            self.on_saved(self.file_name)
            return

        self.on_saved(self.file_name)
        messagebox.showinfo("Checklist", "All checklists completed.", parent=self)
        self.destroy()

    def take_picture(self) -> None:
        self.save_current(show_message=False)
        output_path = self._next_photo_path(".jpg")

        try:
            captured_path = self._capture_photo_with_camera(output_path)
        except ImportError:
            captured_path = self._attach_existing_photo()
        except Exception as exc:
            messagebox.showerror("Take Picture", str(exc), parent=self)
            return

        if captured_path:
            messagebox.showinfo("Take Picture", f"Saved photo:\n{captured_path}", parent=self)

    def _capture_photo_with_camera(self, output_path: Path) -> Path | None:
        try:
            import cv2  # noqa: F401
        except ImportError as exc:
            raise ImportError from exc

        camera_window = CameraCaptureWindow(self, output_path)
        self.wait_window(camera_window)
        if self.winfo_exists():
            self.grab_set()
        return camera_window.saved_path

    def _attach_existing_photo(self) -> Path | None:
        selected = filedialog.askopenfilename(
            parent=self,
            title="Select picture",
            filetypes=[
                ("Image files", "*.jpg *.jpeg *.png *.bmp *.gif"),
                ("All files", "*.*"),
            ],
        )
        if not selected:
            return None

        source_path = Path(selected)
        output_path = self._next_photo_path(source_path.suffix or ".jpg")
        output_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source_path, output_path)
        return output_path

    def _next_photo_path(self, suffix: str) -> Path:
        device_stem = Path(self.file_name).stem
        category = self.category_names[self.category_index]
        safe_category = self.backend._safe_title_part(category)
        timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        return self.photos_location / device_stem / f"{timestamp}_{safe_category}{suffix.lower()}"

    def close(self) -> None:
        try:
            self.save_current(show_message=False)
        except Exception as exc:
            messagebox.showerror("Checklist", f"Could not save before closing: {exc}", parent=self)
            return
        self.on_saved(self.file_name)
        self.destroy()

    def _first_incomplete_category_index(self) -> int:
        rows = self.backend.list_items(self.file_name)
        for index, category in enumerate(self.checklists):
            category_rows = [row for row in rows if row["Category"] == category]
            if any(row["Status"] != "check" for row in category_rows):
                return index
        return 0

    def _configure_checklist_grid(self, parent: tk.Frame) -> None:
        parent.grid_columnconfigure(0, weight=5, minsize=260)
        parent.grid_columnconfigure(1, weight=1, minsize=120)
        parent.grid_columnconfigure(2, weight=5, minsize=260)

    def _grid_cell(
        self,
        parent: tk.Frame,
        text: str,
        column: int,
        bold: bool = False,
        anchor: str = "w",
    ) -> tk.Label:
        label = self._cell(parent, text, bold=bold, anchor=anchor)
        label.grid(row=0, column=column, sticky="nsew", padx=8, pady=4)
        return label

    def _large_check_box(self, parent: tk.Frame, checked_var: tk.BooleanVar) -> tk.Canvas:
        box_size = 22
        canvas = tk.Canvas(
            parent,
            width=box_size + 18,
            height=box_size + 12,
            bg=parent["bg"],
            highlightthickness=0,
            cursor="hand2",
        )

        def draw_box(*_args) -> None:
            canvas.delete("all")
            left = 9
            top = 6
            right = left + box_size
            bottom = top + box_size
            fill = "#23456f" if checked_var.get() else "#ffffff"
            outline = "#23456f" if checked_var.get() else "#777777"
            canvas.create_rectangle(left, top, right, bottom, fill=fill, outline=outline, width=2)
            if checked_var.get():
                canvas.create_line(
                    left + 5,
                    top + 11,
                    left + 10,
                    top + 16,
                    right - 4,
                    top + 6,
                    fill="#ffffff",
                    width=3,
                    capstyle="round",
                    joinstyle="round",
                )

        def toggle(_event=None) -> None:
            checked_var.set(not checked_var.get())
            draw_box()

        canvas.bind("<Button-1>", toggle)
        checked_var.trace_add("write", draw_box)
        draw_box()
        return canvas

    def _cell(self, parent: tk.Frame, text: str, bold: bool = False, anchor: str = "w") -> tk.Label:
        return tk.Label(
            parent,
            text=text,
            bg=parent["bg"],
            fg="#222222",
            anchor=anchor,
            justify="left",
            wraplength=320,
            padx=10,
            pady=7,
            font=self.checklist_heading_font if bold else self.checklist_font,
        )

    def _status_is_checked(self, status: str) -> bool:
        return status == "check"

    def _checked_status(self, checked_var: tk.BooleanVar) -> str:
        return "check" if checked_var.get() else "no check"


class CameraCaptureWindow(tk.Toplevel):
    def __init__(self, parent: tk.Toplevel, output_path: Path):
        super().__init__(parent)
        import cv2

        self.cv2 = cv2
        self.output_path = output_path
        self.saved_path: Path | None = None
        self.current_frame = None
        self.photo_image = None
        self.running = True
        self.after_id: str | None = None

        self.title("Take Picture")
        self.geometry("820x620")
        self.minsize(640, 480)
        self.configure(bg="#f2f2f2")

        try:
            self.camera = self._open_camera()
        except Exception:
            self.destroy()
            raise

        self.preview = tk.Label(self, bg="#111111")
        self.preview.pack(fill="both", expand=True, padx=12, pady=(12, 8))

        actions = tk.Frame(self, bg="#f2f2f2")
        actions.pack(fill="x", padx=12, pady=(0, 12))

        tk.Button(
            actions,
            text="Save Photo",
            command=self.save_photo,
            bg="#23456f",
            fg="#ffffff",
            width=18,
            height=2,
        ).pack(side="right")
        tk.Button(actions, text="Cancel", command=self.close, width=14, height=2).pack(side="right", padx=(0, 8))

        self.bind("<Return>", lambda _event: self.save_photo())
        self.bind("<space>", lambda _event: self.save_photo())
        self.bind("<Escape>", lambda _event: self.close())
        self.protocol("WM_DELETE_WINDOW", self.close)
        self.transient(parent)
        self.grab_set()
        self.update_frame()

    def _open_camera(self):
        camera = self.cv2.VideoCapture(0, self.cv2.CAP_DSHOW)
        if not camera.isOpened():
            camera.release()
            camera = self.cv2.VideoCapture(0)
        if not camera.isOpened():
            raise RuntimeError("Could not open the camera.")

        camera.set(self.cv2.CAP_PROP_FRAME_WIDTH, 1280)
        camera.set(self.cv2.CAP_PROP_FRAME_HEIGHT, 720)
        return camera

    def update_frame(self) -> None:
        if not self.running:
            return

        ok, frame = self.camera.read()
        if ok:
            self.current_frame = frame
            preview_frame = self._fit_frame_to_preview(frame)
            ok, encoded = self.cv2.imencode(".png", preview_frame)
            if ok:
                image_data = base64.b64encode(encoded.tobytes()).decode("ascii")
                try:
                    self.photo_image = tk.PhotoImage(data=image_data, format="PNG")
                    self.preview.config(image=self.photo_image)
                except tk.TclError as exc:
                    self.running = False
                    messagebox.showerror("Take Picture", f"Could not display camera preview: {exc}", parent=self)
                    self.close()
                    return

        self.after_id = self.after(30, self.update_frame)

    def _fit_frame_to_preview(self, frame):
        max_width = max(self.preview.winfo_width(), 640)
        max_height = max(self.preview.winfo_height(), 420)
        height, width = frame.shape[:2]
        scale = min(max_width / width, max_height / height, 1)
        if scale == 1:
            return frame
        new_size = (max(1, int(width * scale)), max(1, int(height * scale)))
        return self.cv2.resize(frame, new_size, interpolation=self.cv2.INTER_AREA)

    def save_photo(self) -> None:
        if self.current_frame is None:
            messagebox.showerror("Take Picture", "No camera image is available yet.", parent=self)
            return

        self.output_path.parent.mkdir(parents=True, exist_ok=True)
        if not self.cv2.imwrite(str(self.output_path), self.current_frame):
            messagebox.showerror("Take Picture", "Could not save the photo.", parent=self)
            return

        self.saved_path = self.output_path
        self.close()

    def close(self) -> None:
        self.running = False
        if self.after_id:
            try:
                self.after_cancel(self.after_id)
            except tk.TclError:
                pass
        if hasattr(self, "camera"):
            self.camera.release()
        self.destroy()


if __name__ == "__main__":
    app = DeviceChecklistApp()
    app.mainloop()
