# Device Assessment And Repair

Desktop checklist logger for device assessment, disassembly, assembly, final testing, photos, and PDF reports.

The application stores each device as a CSV file, tracks checklist status by repair stage, saves optional photos, and generates a PDF report with unchecked items, final test results, and device images.

## Features

- Create, edit, and delete device records.
- Track device status: `received`, `tested`, `dismantled`, `notFixable`, and `fixed`.
- Load checklist sections from `source/checklist_config.json`.
- Checklist boxes are unchecked by default.
- Add comments for each checklist item.
- Capture a photo from a connected camera when OpenCV is installed.
- Attach an existing image when camera capture is unavailable.
- Generate PDF reports and open them in the browser or system PDF viewer.
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
python source\frontend.py
```

## Project Structure

```text
DeviceAssesmentAndRepair/
  source/
    backend.py
    frontend.py
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

Photos are saved in:

```text
data/photos/
```

PDF reports are generated in the system temporary folder and opened automatically.

## PDF Reports

Use **Print report** after selecting a device. The report opens automatically in the browser or system PDF viewer. Reports include:

- Device serial number and date.
- Any unchecked checklist items.
- Final test checklist results.
- Saved photos for the device.
- The project logo when a supported logo file is present.

Supported logo filenames include `Logo.jpeg`, `Logo.jpg`, and `Logo.png`.

## Optional EXE Build

To package the app as a Windows executable:

```powershell
python -m pip install pyinstaller
pyinstaller --onefile --windowed --icon Logo.ico --add-data "source\checklist_config.json;source" --add-data "Logo.jpeg;." source\frontend.py
```

The built executable will be created in the `dist` folder.

## Notes

- Existing blank checklist statuses are treated as unchecked by default.
- Manually unchecked boxes are saved as `no check`.
- Checked boxes are saved as `check`.
- New checklist items are created as unchecked.
