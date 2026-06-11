"""Write a vision-board state (systems + data flows) to an .xlsx that ExcelReader can read back."""
from __future__ import annotations

from pathlib import Path

from atlas.sedraw.vision_ai import FLOW_HEADERS, SYSTEM_HEADERS


def write_vision_state(systems: list, flows: list, out_path: Path) -> Path:
    import openpyxl

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Systems"
    ws.append(SYSTEM_HEADERS)
    for s in systems or []:
        ws.append([s.get(h, "") for h in SYSTEM_HEADERS])
    for col, w in {"A": 28, "B": 20, "C": 32, "D": 12, "E": 14,
                   "F": 12, "G": 30, "H": 50, "I": 50, "J": 50}.items():
        ws.column_dimensions[col].width = w

    ws2 = wb.create_sheet("Data Flows")
    ws2.append(FLOW_HEADERS)
    for f in flows or []:
        ws2.append([f.get(h, "") for h in FLOW_HEADERS])
    for col, w in {"A": 28, "B": 28, "C": 20, "D": 14, "E": 12}.items():
        ws2.column_dimensions[col].width = w

    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    wb.save(str(out_path))
    return out_path
