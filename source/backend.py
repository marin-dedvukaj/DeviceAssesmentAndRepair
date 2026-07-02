from __future__ import annotations

import csv
import re
import shutil
from datetime import date, datetime
from pathlib import Path
from typing import Iterable


class DeviceChecklistBackend:
    """
    Backend helper for device checklist CSV files.

    File names use this title format:
        SN_date_status.csv
        SN_date_status_comment.csv

    CSV rows use this header:
        Category,Item,Status,Comment
    """

    HEADERS = ["Category", "Item", "Status", "Comment"]
    VALID_STATUSES = {"", "check", "no check"}

    def __init__(self, storage_location: str | Path, template_csv: str | Path | None = None):
        self.storage_location = Path(storage_location)
        self.storage_location.mkdir(parents=True, exist_ok=True)
        self.template_csv = Path(template_csv) if template_csv else None

    def AddNewDevice(
        self,
        sn: str,
        status: str,
        device_date: str | None = None,
        comment: str = "",
    ) -> Path:
        """
        Create a new device CSV in the storage location.

        If template_csv was provided to the class, the template is copied.
        Otherwise, a new empty checklist CSV is created with the correct header.
        """
        self._require_value(sn, "sn")
        self._require_value(status, "status")

        device_date = device_date or date.today().isoformat()
        file_path = self.storage_location / self._build_file_name(sn, device_date, status, comment)

        if file_path.exists():
            raise FileExistsError(f"Device CSV already exists: {file_path}")

        if self.template_csv:
            if not self.template_csv.exists():
                raise FileNotFoundError(f"Template CSV not found: {self.template_csv}")
            shutil.copy2(self.template_csv, file_path)
            self._ensure_headers(file_path)
        else:
            self._write_rows(file_path, [])

        return file_path

    def ChangeTitle(
        self,
        csv_name_or_sn: str,
        sn: str | None = None,
        device_date: str | None = None,
        status: str | None = None,
        comment: str | None = None,
    ) -> Path:
        """
        Rename a CSV using SN_date_status.csv or SN_date_status_comment.csv.

        Empty or None values keep the existing value unchanged.
        csv_name_or_sn can be a full CSV filename, a path, or just the current SN.
        """
        current_path = self._find_device_file(csv_name_or_sn)
        current_sn, current_date, current_status, current_comment = self._parse_device_file_name(current_path.name)

        new_sn = sn or current_sn
        new_date = device_date or current_date
        new_status = status or current_status
        new_comment = current_comment if comment is None else comment.strip()
        new_path = current_path.with_name(self._build_file_name(new_sn, new_date, new_status, new_comment))

        if new_path != current_path and new_path.exists():
            raise FileExistsError(f"Target CSV already exists: {new_path}")

        current_path.rename(new_path)
        new_path.touch()
        return new_path

    def add_item(
        self,
        csv_name_or_sn: str,
        category: str,
        item: str,
        status: str = "no check",
        comment: str = "",
    ) -> dict[str, str]:
        """Add one checklist item to a device CSV."""
        self._require_value(category, "category")
        self._require_value(item, "item")
        self._validate_status(status)

        path = self._find_device_file(csv_name_or_sn)
        rows = self._read_rows(path)

        if self._find_row_index(rows, category, item) is not None:
            raise ValueError(f"Checklist item already exists: {category} / {item}")

        row = {
            "Category": category,
            "Item": item,
            "Status": status,
            "Comment": comment,
        }
        rows.append(row)
        self._write_rows(path, rows)
        return row

    def update_item(
        self,
        csv_name_or_sn: str,
        category: str,
        item: str,
        new_category: str | None = None,
        new_item: str | None = None,
        status: str | None = None,
        comment: str | None = None,
    ) -> dict[str, str]:
        """
        Edit a checklist item.

        Empty or None fields are ignored and left unchanged.
        """
        path = self._find_device_file(csv_name_or_sn)
        rows = self._read_rows(path)
        row_index = self._find_row_index(rows, category, item)

        if row_index is None:
            raise ValueError(f"Checklist item not found: {category} / {item}")

        if status is not None:
            self._validate_status(status)

        row = rows[row_index]
        row["Category"] = new_category or row["Category"]
        row["Item"] = new_item or row["Item"]
        row["Status"] = status if status is not None else row["Status"]
        row["Comment"] = comment if comment is not None else row["Comment"]

        self._write_rows(path, rows)
        return row

    def delete_item(self, csv_name_or_sn: str, category: str, item: str) -> dict[str, str]:
        """Delete one checklist item from a device CSV."""
        path = self._find_device_file(csv_name_or_sn)
        rows = self._read_rows(path)
        row_index = self._find_row_index(rows, category, item)

        if row_index is None:
            raise ValueError(f"Checklist item not found: {category} / {item}")

        deleted_row = rows.pop(row_index)
        self._write_rows(path, rows)
        return deleted_row

    def delete_device(self, csv_name_or_sn: str) -> Path:
        """Delete an entire device CSV."""
        path = self._find_device_file(csv_name_or_sn)
        path.unlink()
        return path

    def list_items(self, csv_name_or_sn: str) -> list[dict[str, str]]:
        """Return all checklist rows for a device CSV."""
        return self._read_rows(self._find_device_file(csv_name_or_sn))

    def display_items(self, csv_name_or_sn: str) -> str:
        """Return a simple text table for displaying checklist rows."""
        rows = self.list_items(csv_name_or_sn)
        if not rows:
            return "No checklist items found."

        widths = {
            header: max(len(header), *(len(row.get(header, "")) for row in rows))
            for header in self.HEADERS
        }
        header_line = " | ".join(header.ljust(widths[header]) for header in self.HEADERS)
        separator = "-+-".join("-" * widths[header] for header in self.HEADERS)
        row_lines = [
            " | ".join(row.get(header, "").ljust(widths[header]) for header in self.HEADERS)
            for row in rows
        ]

        return "\n".join([header_line, separator, *row_lines])

    def get_item(self, csv_name_or_sn: str, category: str, item: str) -> dict[str, str]:
        """Return one checklist item."""
        rows = self._read_rows(self._find_device_file(csv_name_or_sn))
        row_index = self._find_row_index(rows, category, item)

        if row_index is None:
            raise ValueError(f"Checklist item not found: {category} / {item}")

        return rows[row_index]

    def list_devices(self) -> list[Path]:
        """Return all device CSV files in the storage location."""
        return sorted(self.storage_location.glob("*.csv"))

    def list_device_summaries(self) -> list[dict[str, str | float]]:
        """Return parsed device metadata for table and report views."""
        rows: list[dict[str, str | float]] = []
        for path in self.list_devices():
            try:
                sn, device_date, status, comment = self._parse_device_file_name(path.name)
            except ValueError:
                continue

            updated_ts = path.stat().st_mtime
            rows.append(
                {
                    "sn": sn,
                    "date": device_date,
                    "status": status,
                    "comment": comment,
                    "updated": datetime.fromtimestamp(updated_ts).strftime("%Y-%m-%d %H:%M"),
                    "updated_ts": updated_ts,
                    "file": path.name,
                }
            )
        return rows

    def _find_device_file(self, csv_name_or_sn: str) -> Path:
        value = Path(csv_name_or_sn)

        if value.exists():
            return value

        if value.suffix.lower() == ".csv":
            path = self.storage_location / value.name
            if path.exists():
                return path
            raise FileNotFoundError(f"CSV not found: {path}")

        matches = [
            path
            for path in self.storage_location.glob("*.csv")
            if self._parse_device_file_name(path.name)[0] == csv_name_or_sn
        ]

        if not matches:
            raise FileNotFoundError(f"No device CSV found for SN: {csv_name_or_sn}")
        if len(matches) > 1:
            names = ", ".join(path.name for path in matches)
            raise ValueError(f"Multiple CSV files found for SN {csv_name_or_sn}: {names}")

        return matches[0]

    def _ensure_headers(self, path: Path) -> None:
        rows = self._read_rows(path)
        self._write_rows(path, rows)

    def _read_rows(self, path: Path) -> list[dict[str, str]]:
        with path.open("r", newline="", encoding="utf-8") as csv_file:
            reader = csv.DictReader(csv_file)
            if reader.fieldnames != self.HEADERS:
                raise ValueError(f"{path.name} must have headers: {', '.join(self.HEADERS)}")
            return [
                {header: row.get(header, "") or "" for header in self.HEADERS}
                for row in reader
            ]

    def _write_rows(self, path: Path, rows: Iterable[dict[str, str]]) -> None:
        with path.open("w", newline="", encoding="utf-8") as csv_file:
            writer = csv.DictWriter(csv_file, fieldnames=self.HEADERS)
            writer.writeheader()
            writer.writerows(rows)

    def _build_file_name(self, sn: str, device_date: str, status: str, comment: str = "") -> str:
        parts = [self._safe_title_part(sn), self._safe_title_part(device_date), self._safe_title_part(status)]
        if comment.strip():
            parts.append(self._safe_title_part(comment))
        return "_".join(parts) + ".csv"

    def _parse_file_name(self, file_name: str) -> tuple[str, str, str]:
        sn, device_date, status, _comment = self._parse_device_file_name(file_name)
        return sn, device_date, status

    def _parse_device_file_name(self, file_name: str) -> tuple[str, str, str, str]:
        stem = Path(file_name).stem
        parts = stem.split("_", 3)
        if len(parts) not in {3, 4}:
            raise ValueError("CSV name must use SN_date_status.csv or SN_date_status_comment.csv format")
        comment = parts[3] if len(parts) == 4 else ""
        return parts[0], parts[1], parts[2], comment

    def _find_row_index(
        self,
        rows: list[dict[str, str]],
        category: str,
        item: str,
    ) -> int | None:
        for index, row in enumerate(rows):
            if row["Category"] == category and row["Item"] == item:
                return index
        return None

    def _validate_status(self, status: str) -> None:
        if status not in self.VALID_STATUSES:
            allowed = ", ".join(sorted(self.VALID_STATUSES))
            raise ValueError(f"Status must be one of: {allowed}")

    def _safe_title_part(self, value: str) -> str:
        self._require_value(value, "title part")
        return re.sub(r"[^A-Za-z0-9.-]+", "-", value.strip())

    def _require_value(self, value: str, field_name: str) -> None:
        if not value or not value.strip():
            raise ValueError(f"{field_name} cannot be empty")


if __name__ == "__main__":
    backend = DeviceChecklistBackend(Path(__file__).resolve().parent.parent / "data" / "devices")
    csv_path = backend.AddNewDevice("SN12345", "active")
    backend.add_item("SN12345", "Battery", "Voltage test")
    backend.update_item("SN12345", "Battery", "Voltage test", status="check", comment="Passed")
    print(f"Created: {csv_path}")
    print(backend.display_items("SN12345"))
