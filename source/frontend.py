from __future__ import annotations

import base64
import csv
import tkinter as tk
import webbrowser
from pathlib import Path
from tkinter import filedialog, messagebox, simpledialog, ttk

from backend import DeviceChecklistBackend
from config import (
    CHECKLIST_START_BY_STATUS,
    DEFAULT_CONFIG,
    DEFAULT_PHOTOS,
    DEFAULT_REPORTS,
    DEFAULT_STORAGE,
    DEVICE_STATUSES,
    EDITABLE_DEVICE_STATUSES,
    STATUS_FILTER_OPTIONS,
    load_checklist_config,
    normalize_device_status,
    resolve_config_path,
)
from photos import copy_photo, device_photo_paths, next_photo_path
from reports import build_all_devices_report, build_device_report


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
        self.geometry("1440x820")
        self.minsize(1180, 620)

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
        self.status_filter_var = tk.StringVar(value="All")
        self.status_filter_var.trace_add("write", lambda *_args: self.refresh_table())
        self.sort_column = "id"
        self.sort_reverse = False
        self.counter_labels: dict[str, tk.Label] = {}
        self.filter_buttons: dict[str, tk.Button] = {}
        self.visible_device_rows: list[dict[str, str | float]] = []

        self._configure_style()
        self._build_layout()
        self.refresh_table()

    def _configure_style(self) -> None:
        self.configure(bg="#f2f2f2")

        style = ttk.Style(self)
        style.theme_use("clam")
        style.configure("Treeview", rowheight=28, font=("Segoe UI", 10), borderwidth=1)
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

        sidebar = tk.Frame(main, bg="#ffffff", bd=2, relief="groove", width=250)
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
            height=1,
        )
        self.selected_label.pack(fill="x", padx=12, pady=(0, 16))

        self._button(parent, "New Device", self.new_device, primary=True)
        self._button(parent, "Edit Device", self.edit_device, primary=True)
        self._button(parent, "Enter Form", self.enter_form, primary=True, tall=True)
        self._button(parent, "Reports", self.print_report)

        ttk.Separator(parent, orient="horizontal").pack(fill="x", padx=12, pady=16)

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
            height=2 if tall else 1,
        )
        button.pack(fill="x", padx=12, pady=5)

    def _build_table(self, parent: tk.Frame) -> None:
        self._build_dashboard(parent)
        self._build_status_filters(parent)

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
        tk.Button(
            search_bar,
            text="↻",
            command=self.refresh_table,
            width=3,
            height=1,
            bg="#ffffff",
            fg="#222222",
            activebackground="#e8e8e8",
        ).pack(side="left", padx=(8, 0))

        table_area = tk.Frame(parent, bg="#ffffff")
        table_area.pack(fill="both", expand=True, padx=10, pady=10)

        columns = ("id", "sn", "date", "status", "comment", "updated", "file")
        self.table = ttk.Treeview(table_area, columns=columns, show="headings", selectmode="extended")

        headings = {
            "id": "ID",
            "sn": "SerialNumber",
            "date": "Date",
            "status": "Status",
            "comment": "Comment",
            "updated": "Last Updated",
            "file": "CSV File",
        }
        widths = {"id": 50, "sn": 155, "date": 110, "status": 105, "comment": 170, "updated": 135, "file": 235}

        for column in columns:
            self.table.heading(column, text=headings[column], command=lambda selected=column: self._sort_by(selected))
            self.table.column(column, width=widths[column], minwidth=50, anchor="center")

        for status, color in DEVICE_STATUSES.items():
            self.table.tag_configure(status, background=color)

        y_scroll = ttk.Scrollbar(table_area, orient="vertical", command=self.table.yview)
        x_scroll = ttk.Scrollbar(table_area, orient="horizontal", command=self.table.xview)
        self.table.configure(yscrollcommand=y_scroll.set, xscrollcommand=x_scroll.set)

        self.table.grid(row=0, column=0, sticky="nsew")
        y_scroll.grid(row=0, column=1, sticky="ns")
        x_scroll.grid(row=1, column=0, sticky="ew")
        table_area.grid_rowconfigure(0, weight=1)
        table_area.grid_columnconfigure(0, weight=1)
        self.table.bind("<<TreeviewSelect>>", self._on_select)
        self.table.bind("<Double-1>", lambda _event: self.enter_form())

    def _build_dashboard(self, parent: tk.Frame) -> None:
        dashboard = tk.Frame(parent, bg="#ffffff")
        dashboard.pack(fill="x", padx=10, pady=(10, 0))

        for status in STATUS_FILTER_OPTIONS:
            tile = tk.Frame(dashboard, bg="#f7f7f7", bd=1, relief="solid")
            tile.pack(side="left", fill="x", expand=True, padx=(0, 6))
            tk.Label(
                tile,
                text=status,
                bg="#f7f7f7",
                fg="#333333",
                font=("Segoe UI", 9, "bold"),
            ).pack(anchor="w", padx=8, pady=(5, 0))
            value = tk.Label(
                tile,
                text="0",
                bg="#f7f7f7",
                fg="#222222",
                font=("Segoe UI", 14, "bold"),
            )
            value.pack(anchor="w", padx=8, pady=(0, 5))
            self.counter_labels[status] = value

    def _build_status_filters(self, parent: tk.Frame) -> None:
        filters = tk.Frame(parent, bg="#ffffff")
        filters.pack(fill="x", padx=10, pady=(10, 0))

        tk.Label(
            filters,
            text="Status",
            bg="#ffffff",
            fg="#222222",
            font=("Segoe UI", 10, "bold"),
        ).pack(side="left", padx=(0, 8))

        for status in STATUS_FILTER_OPTIONS:
            button = tk.Button(
                filters,
                text=status,
                command=lambda selected=status: self.status_filter_var.set(selected),
                height=1,
                padx=10,
            )
            button.pack(side="left", padx=(0, 5))
            self.filter_buttons[status] = button

    def refresh_table(self) -> None:
        for row_id in self.table.get_children():
            self.table.delete(row_id)

        all_rows = self._device_table_rows()
        self._update_dashboard(all_rows)
        self._update_filter_buttons()

        device_rows = []
        search_text = self.search_var.get().strip().lower()
        status_filter = self.status_filter_var.get()

        for row in all_rows:
            if status_filter != "All" and row["status"] != status_filter:
                continue
            searchable = " ".join(row[column] for column in ("sn", "date", "status", "comment", "updated", "file"))
            if search_text and search_text not in searchable.lower():
                continue
            device_rows.append(row)

        if self.sort_column == "id":
            if self.sort_reverse:
                device_rows.reverse()
        else:
            device_rows.sort(
                key=lambda row: row["updated_ts"] if self.sort_column == "updated" else row[self.sort_column].lower(),
                reverse=self.sort_reverse,
            )

        self.visible_device_rows = []
        for index, row in enumerate(device_rows, start=1):
            visible_row = {**row, "id": str(index)}
            self.visible_device_rows.append(visible_row)
            self.table.insert(
                "",
                "end",
                iid=row["file"],
                values=(
                    index,
                    row["sn"],
                    row["date"],
                    row["status"],
                    row["comment"],
                    row["updated"],
                    row["file"],
                ),
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

    def export_visible_devices(self) -> None:
        export_rows = self._selected_device_rows() or self.visible_device_rows
        if not export_rows:
            messagebox.showinfo("Export Table CSV", "No devices to export.", parent=self)
            return

        output = filedialog.asksaveasfilename(
            parent=self,
            title="Export device table",
            defaultextension=".csv",
            filetypes=[("CSV files", "*.csv"), ("All files", "*.*")],
        )
        if not output:
            return

        headers = ["ID", "Serial Number", "Date", "Status", "Comment", "Last Updated", "CSV File"]
        try:
            with Path(output).open("w", newline="", encoding="utf-8") as csv_file:
                writer = csv.writer(csv_file)
                writer.writerow(headers)
                for row in export_rows:
                    writer.writerow(
                        [
                            row["id"],
                            row["sn"],
                            row["date"],
                            row["status"],
                            row["comment"],
                            row["updated"],
                            row["file"],
                        ]
                    )
            messagebox.showinfo("Export Table CSV", f"Exported:\n{output}", parent=self)
        except Exception as exc:
            messagebox.showerror("Export Table CSV", str(exc), parent=self)

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

    def preview_photos(self) -> None:
        selected_files = self._selected_file_names()
        if not selected_files:
            messagebox.showinfo("Preview Photos", "Select a device first.", parent=self)
            return

        image_paths = []
        for file_name in selected_files:
            image_paths.extend(device_photo_paths(self.photos_location, file_name))
        if not image_paths:
            messagebox.showinfo("Preview Photos", "No photos found for the selected device(s).", parent=self)
            return

        PhotoPreviewWindow(self, image_paths)

    def print_report(self) -> None:
        ReportMenu(self)

    def print_device_report(self) -> None:
        selected_files = self._selected_file_names()
        if not selected_files:
            messagebox.showinfo("Print Report", "Select a device first.", parent=self)
            return

        try:
            created_paths = []
            for file_name in selected_files:
                self._ensure_configured_checklist_items(file_name)
                report_path = build_device_report(self.backend, file_name, self.photos_location)
                created_paths.append(report_path)
                webbrowser.open(report_path.as_uri())
            if created_paths:
                messagebox.showinfo("Print Report", f"Created {len(created_paths)} report(s).", parent=self)
        except Exception as exc:
            messagebox.showerror("Print Report", str(exc), parent=self)

    def print_all_devices_report(self) -> None:
        try:
            report_rows = self._selected_device_rows() or self.visible_device_rows
            if not report_rows:
                messagebox.showinfo("All Devices Report", "No devices to include.", parent=self)
                return
            report_path = build_all_devices_report(report_rows)
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

    def _device_table_rows(self) -> list[dict[str, str | float]]:
        rows = []
        for summary in self.backend.list_device_summaries():
            normalized_status = normalize_device_status(str(summary["status"]))
            rows.append(
                {
                    "sn": str(summary["sn"]),
                    "date": str(summary["date"]),
                    "status": normalized_status,
                    "comment": str(summary["comment"]),
                    "updated": str(summary["updated"]),
                    "updated_ts": summary["updated_ts"],
                    "file": str(summary["file"]),
                }
            )
        return rows

    def _update_dashboard(self, rows: list[dict[str, str]]) -> None:
        counts = {status: 0 for status in STATUS_FILTER_OPTIONS}
        counts["All"] = len(rows)
        for row in rows:
            if row["status"] in counts:
                counts[row["status"]] += 1

        for status, label in self.counter_labels.items():
            label.config(text=str(counts.get(status, 0)))

    def _update_filter_buttons(self) -> None:
        selected = self.status_filter_var.get()
        for status, button in self.filter_buttons.items():
            if status == selected:
                button.config(bg="#23456f", fg="#ffffff", activebackground="#315985", activeforeground="#ffffff")
            else:
                button.config(bg="#ffffff", fg="#222222", activebackground="#e8e8e8", activeforeground="#222222")

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
            self.selected_file_name = None
            self.selected_label.config(text="No device selected")
            return
        self.selected_file_name = selected[0]
        if len(selected) == 1:
            self.selected_label.config(text=self.selected_file_name)
        else:
            self.selected_label.config(text=f"{len(selected)} devices selected")

    def _selected_file_names(self) -> list[str]:
        return [str(file_name) for file_name in self.table.selection()]

    def _selected_device_rows(self) -> list[dict[str, str | float]]:
        selected_files = set(self._selected_file_names())
        if not selected_files:
            return []
        return [row for row in self.visible_device_rows if str(row["file"]) in selected_files]

class PhotoPreviewWindow(tk.Toplevel):
    def __init__(self, parent: DeviceChecklistApp, image_paths: list[Path]):
        super().__init__(parent)
        self.image_paths = image_paths
        self.preview_image: tk.PhotoImage | None = None

        self.title("Photo Preview")
        self.geometry("840x620")
        self.minsize(700, 460)
        self.configure(bg="#ffffff")

        tk.Label(
            self,
            text="Device photos",
            bg="#ffffff",
            fg="#222222",
            font=("Segoe UI", 12, "bold"),
        ).pack(anchor="w", padx=14, pady=(14, 8))

        content = tk.Frame(self, bg="#ffffff")
        content.pack(fill="both", expand=True, padx=14, pady=(0, 10))

        list_frame = tk.Frame(content, bg="#ffffff")
        list_frame.pack(side="left", fill="y", padx=(0, 10))

        self.photo_list = tk.Listbox(list_frame, width=34, height=18)
        self.photo_list.pack(side="left", fill="y")
        scroll = ttk.Scrollbar(list_frame, orient="vertical", command=self.photo_list.yview)
        scroll.pack(side="right", fill="y")
        self.photo_list.configure(yscrollcommand=scroll.set)

        preview_panel = tk.Frame(content, bg="#f7f7f7", bd=1, relief="solid")
        preview_panel.pack(side="left", fill="both", expand=True)

        self.preview_label = tk.Label(
            preview_panel,
            text="Select a photo",
            bg="#f7f7f7",
            fg="#333333",
            anchor="center",
        )
        self.preview_label.pack(fill="both", expand=True, padx=8, pady=8)

        actions = tk.Frame(self, bg="#ffffff")
        actions.pack(fill="x", padx=14, pady=(0, 14))

        tk.Button(actions, text="Open Photo", command=self.open_selected_photo, height=1).pack(side="right")
        tk.Button(actions, text="Close", command=self.destroy, height=1).pack(side="right", padx=(0, 8))

        for path in image_paths:
            self.photo_list.insert("end", path.name)

        self.photo_list.bind("<<ListboxSelect>>", self._on_select)
        self.photo_list.bind("<Double-1>", lambda _event: self.open_selected_photo())
        self.photo_list.selection_set(0)
        self._show_photo(image_paths[0])

        self.transient(parent)
        self.grab_set()

    def _selected_path(self) -> Path | None:
        selected = self.photo_list.curselection()
        if not selected:
            return None
        return self.image_paths[selected[0]]

    def _on_select(self, _event=None) -> None:
        selected_path = self._selected_path()
        if selected_path:
            self._show_photo(selected_path)

    def _show_photo(self, image_path: Path) -> None:
        try:
            image = tk.PhotoImage(file=str(image_path))
        except tk.TclError:
            self.preview_image = None
            self.preview_label.config(
                image="",
                text=f"{image_path.name}\n\nPreview unavailable for this image type.\nUse Open Photo.",
            )
            return

        max_width = max(self.preview_label.winfo_width(), 420)
        max_height = max(self.preview_label.winfo_height(), 320)
        scale = max(1, int(max(image.width() / max_width, image.height() / max_height, 1)))
        if scale > 1:
            image = image.subsample(scale, scale)

        self.preview_image = image
        self.preview_label.config(image=self.preview_image, text="")

    def open_selected_photo(self) -> None:
        selected_path = self._selected_path()
        if not selected_path:
            messagebox.showinfo("Photo Preview", "Select a photo first.", parent=self)
            return
        opened = webbrowser.open(selected_path.as_uri())
        if not opened:
            messagebox.showinfo("Photo Preview", f"Photo path:\n{selected_path}", parent=self)


class ReportMenu(tk.Toplevel):
    def __init__(self, parent: DeviceChecklistApp):
        super().__init__(parent)
        self.parent = parent

        self.title("Reports")
        self.geometry("360x275")
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
            text="Selected device report(s)",
            command=self._run_device_report,
            bg="#23456f",
            fg="#ffffff",
            activebackground="#315985",
            activeforeground="#ffffff",
            height=1,
        ).pack(fill="x", padx=18, pady=5)

        tk.Button(
            self,
            text="Selected/visible table",
            command=self._run_all_devices_report,
            bg="#ffffff",
            fg="#222222",
            activebackground="#e8e8e8",
            height=1,
        ).pack(fill="x", padx=18, pady=5)

        tk.Button(
            self,
            text="Export visible table CSV",
            command=self._run_export_table,
            bg="#ffffff",
            fg="#222222",
            activebackground="#e8e8e8",
            height=1,
        ).pack(fill="x", padx=18, pady=5)

        tk.Button(
            self,
            text="Preview selected device photos",
            command=self._run_preview_photos,
            bg="#ffffff",
            fg="#222222",
            activebackground="#e8e8e8",
            height=1,
        ).pack(fill="x", padx=18, pady=5)

        tk.Button(self, text="Cancel", command=self.destroy, height=1).pack(fill="x", padx=18, pady=(10, 0))

        self.transient(parent)
        self.grab_set()

    def _run_device_report(self) -> None:
        self.destroy()
        self.parent.print_device_report()

    def _run_all_devices_report(self) -> None:
        self.destroy()
        self.parent.print_all_devices_report()

    def _run_export_table(self) -> None:
        self.destroy()
        self.parent.export_visible_devices()

    def _run_preview_photos(self) -> None:
        self.destroy()
        self.parent.preview_photos()


class DeviceTitleEditor(tk.Toplevel):
    def __init__(self, parent: DeviceChecklistApp, backend: DeviceChecklistBackend, file_name: str):
        super().__init__(parent)
        self.parent_app = parent
        self.backend = backend
        self.file_name = file_name

        self.title("Edit Device")
        self.geometry("400x410")
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
            height=1,
        ).pack(fill="x", padx=18, pady=(16, 8))

        tk.Button(
            self,
            text="Mark Not Fixable",
            command=self.mark_not_fixable,
            bg="#ffffff",
            fg="#222222",
            activebackground="#e8e8e8",
            height=1,
        ).pack(fill="x", padx=18, pady=4)

        tk.Button(
            self,
            text="Delete Device",
            command=self.delete_device,
            bg="#ffffff",
            fg="#222222",
            activebackground="#e8e8e8",
            height=1,
        ).pack(fill="x", padx=18, pady=4)

        self.transient(parent)
        self.grab_set()

    def _field(self, label: str, variable: tk.StringVar) -> None:
        tk.Label(self, text=label, bg="#ffffff", font=("Segoe UI", 10, "bold")).pack(
            anchor="w", padx=18, pady=(12, 4)
        )
        tk.Entry(self, textvariable=variable).pack(fill="x", padx=18)

    def save(self) -> None:
        try:
            self._save_title(self.status_var.get().strip())
            self.destroy()
        except Exception as exc:
            messagebox.showerror("Edit Device", str(exc), parent=self)

    def mark_not_fixable(self) -> None:
        try:
            new_path = self._save_title("notFixable")
            self.file_name = new_path.name
            self.status_var.set("notFixable")
            self.parent_app.refresh_table()
            self.parent_app._select_device(self.file_name)
            messagebox.showinfo("Edit Device", "Device marked not fixable.", parent=self)
        except Exception as exc:
            messagebox.showerror("Edit Device", str(exc), parent=self)

    def delete_device(self) -> None:
        confirmed = messagebox.askyesno(
            "Delete Device",
            f"Delete {self.file_name}?",
            parent=self,
        )
        if not confirmed:
            return

        try:
            self.backend.delete_device(self.file_name)
            self.parent_app.refresh_table()
            self.destroy()
        except Exception as exc:
            messagebox.showerror("Delete Device", str(exc), parent=self)

    def _save_title(self, status: str) -> Path:
        return self.backend.ChangeTitle(
            self.file_name,
            sn=self.sn_var.get().strip(),
            device_date=self.date_var.get().strip(),
            status=status,
            comment=self.comment_var.get().strip(),
        )


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
        self.category_index = self._starting_category_index()
        self.row_widgets: list[tuple[str, tk.BooleanVar, tk.StringVar]] = []
        self.checklist_font = ("Segoe UI", 12)
        self.checklist_heading_font = ("Segoe UI", 12, "bold")
        self.checklist_entry_font = ("Segoe UI", 12)

        self.title("Device Checklist")
        self.geometry("1120x720")
        self.minsize(980, 580)
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

        tk.Button(actions, text="Back", command=self.previous_category, width=12, height=1).pack(side="left")
        tk.Button(actions, text="Save", command=self.save_current, width=12, height=1).pack(side="left", padx=6)
        tk.Button(actions, text="Take Picture", command=self.take_picture, width=14, height=1).pack(side="left")
        tk.Button(actions, text="Reset Checks", command=self.reset_current_checks, width=14, height=1).pack(side="left", padx=6)
        tk.Button(
            actions,
            text="Complete And Continue",
            command=self.complete_current_category,
            bg="#23456f",
            fg="#ffffff",
            width=22,
            height=1,
        ).pack(side="right")

        self.render_category()
        self.protocol("WM_DELETE_WINDOW", self.close)
        self.transient(parent)
        self.grab_set()

    def _update_scroll_region(self, _event=None) -> None:
        self.content_canvas.configure(scrollregion=self.content_canvas.bbox("all"))

    def _resize_scroll_content(self, event) -> None:
        content_width = min(max(event.width - 36, 760), 1240)
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

    def reset_current_checks(self) -> None:
        category = self.category_names[self.category_index]
        confirmed = messagebox.askyesno(
            "Reset Checks",
            f"Reset check marks for {category}?",
            parent=self,
        )
        if not confirmed:
            return

        for item, checked_var, comment_var in self.row_widgets:
            checked_var.set(False)
            self.backend.update_item(
                self.file_name,
                category,
                item,
                status="no check",
                comment=comment_var.get(),
            )
        messagebox.showinfo("Reset Checks", "Current checklist check marks were reset.", parent=self)

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
        return copy_photo(source_path, output_path)

    def _next_photo_path(self, suffix: str) -> Path:
        category = self.category_names[self.category_index]
        return next_photo_path(self.photos_location, self.backend, self.file_name, category, suffix)

    def close(self) -> None:
        try:
            self.save_current(show_message=False)
        except Exception as exc:
            messagebox.showerror("Checklist", f"Could not save before closing: {exc}", parent=self)
            return
        self.on_saved(self.file_name)
        self.destroy()

    def _starting_category_index(self) -> int:
        try:
            _sn, _device_date, status, _comment = self.backend._parse_device_file_name(self.file_name)
        except ValueError:
            return self._first_incomplete_category_index()

        target_category = CHECKLIST_START_BY_STATUS.get(normalize_device_status(status))
        if target_category in self.category_names:
            return self.category_names.index(target_category)
        return self._first_incomplete_category_index()

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
        self.geometry("900x680")
        self.minsize(700, 520)
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
            height=1,
        ).pack(side="right")
        tk.Button(actions, text="Cancel", command=self.close, width=14, height=1).pack(side="right", padx=(0, 8))

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
