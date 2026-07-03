# Device Assessment And Repair

Desktop checklist logger for device assessment, disassembly, assembly, final testing, photos, and PDF reports.

The application stores each device as a CSV file, tracks checklist status by repair stage, saves optional photos, and generates a PDF report with problems found, final test results, and device images.

## Features

- Create, edit, and delete device records.
- Add a device comment to make records easier to identify.
- Search and sort the device table.
- View dashboard counters by device status.
- Filter the device table by status.
- Show each device's last updated time.
- Export the visible device table to CSV.
- Preview or open saved photos for the selected device from Reports.
- Track device status: `received`, `tested`, `dismantled`, `notFixable`, and `fixed`.
- Load checklist sections from `source/checklist_config.json`.
- Checklist boxes are unchecked by default.
- Checklist forms open on the expected stage from the device status.
- Reset check marks for the current checklist section only.
- Add comments for each checklist item.
- Capture a photo from a connected camera when OpenCV is installed.
- Attach an existing image when camera capture is unavailable.
- Generate selected-device and all-devices PDF reports, then open them in the browser or system PDF viewer.
- Store device CSV files and photos under the `data` folder.

## Requirements

- Python 3.10 or newer
- Tkinter
- pip

Tkinter is included with most Windows Python installers. If the app fails with a missing `tkinter` error, reinstall Python from [python.org](https://www.python.org/downloads/) and make sure Tcl/Tk support is selected.

## Install

From the project folder:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install reportlab opencv-python
```

`opencv-python` is used for the **Take Picture** camera workflow. If you do not need camera capture, install only the required PDF dependency:

```powershell
python -m pip install reportlab
```

Without OpenCV, **Take Picture** falls back to selecting an existing image file.

## Run

```powershell
python source\app.py
```

## Project Structure

```text
DeviceAssesmentAndRepair/
  source/
    app.py
    backend.py
    config.py
    frontend.py
    photos.py
    reports.py
    checklist_config.json
  data/
    devices/
    photos/
  Logo.jpeg
  Logo.ico
  README.md
```

`data` is created automatically when the app runs. PDF reports are generated in the system temporary folder when opened.

## Checklist Configuration

Checklist sections and items are configured in:

```text
source/checklist_config.json
```

The `checklists` object controls the checklist categories and rows. The `status_after_checklist` object controls which device status is applied after each checklist category is completed.

When opening a form, the device status chooses the starting checklist stage:

```text
received   -> assessment
tested     -> disassembly
dismantled -> assembly
fixed      -> Final test
```

Example:

```json
{
  "status_after_checklist": {
    "assessment": "tested",
    "disassembly": "dismantled",
    "assembly": "tested",
    "Final test": "fixed"
  }
}
```

## Data Storage

Device files are saved as CSV files in:

```text
data/devices/
```

The filename format is:

```text
SerialNumber_Date_Status.csv
```

When a device comment is added, the filename format is:

```text
SerialNumber_Date_Status_Comment.csv
```

Photos are saved in:

```text
data/photos/
```

PDF reports are generated in the system temporary folder and opened automatically.

## PDF Reports

Use **Reports** to create reports for selected devices, create a table report for selected or visible devices, export selected or visible rows to CSV, or preview selected-device photos. Reports open automatically in the browser or system PDF viewer.

Selected-device reports include:

- Device serial number and date.
- Device comment.
- Problems found.
- Final test checklist results.
- Saved photos for the device.
- The project logo when a supported logo file is present.

Table reports include the selected rows when devices are selected, or the current visible table when nothing is selected.

## Table Workflow

The main device table includes dashboard counters, status filters, search, sortable columns, and a last-updated column based on each device CSV file's modified time.

Use **Reports** > **Export visible table CSV** to export selected rows, or the currently visible table when nothing is selected.

Use **Reports** > **Preview selected device photos** after selecting a device to browse saved photos. If an image type cannot be previewed inside the app, use **Open Photo** from the preview window.

Use **Edit Device** for device title edits, marking a device not fixable, or deleting the selected device.

Supported logo filenames include `Logo.jpeg`, `Logo.jpg`, and `Logo.png`.

## Optional EXE Build

To package the app as a Windows executable:

```powershell
python -m pip install pyinstaller
pyinstaller --onefile --windowed --icon Logo.ico --add-data "source\checklist_config.json;source" --add-data "Logo.jpeg;." source\app.py
```

The built executable will be created in the `dist` folder.

When using auto-py-to-exe, add `Logo.jpeg` as an additional file with destination `.` so it is bundled at the application root. The app also checks the executable folder, so a loose `Logo.jpeg` beside the `.exe` still works as a fallback.

## Notes

- Existing blank checklist statuses are treated as unchecked by default.
- Manually unchecked boxes are saved as `no check`.
- Checked boxes are saved as `check`.
- New checklist items are created as unchecked.
