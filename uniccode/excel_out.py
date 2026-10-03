"""Natija Excel fayli: Датабаза formatidagi kodlar + xulosa."""
from io import BytesIO

from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter

from uniccode.generator import BatchResult

HF = Font(name="Arial", bold=True)
BF = Font(name="Arial")
FILL = PatternFill("solid", fgColor="DDEBF7")


def _sheet(ws, header, rows, widths):
    ws.append(header)
    for c in ws[1]:
        c.font, c.fill, c.alignment = HF, FILL, Alignment(horizontal="center")
    for r in rows:
        ws.append(r)
    for row in ws.iter_rows(min_row=2):
        for c in row:
            c.font = BF
    for i, w in enumerate(widths, 1):
        ws.column_dimensions[get_column_letter(i)].width = w
    ws.freeze_panes = "A2"


def build_excel(result: BatchResult, title: str = "") -> bytes:
    wb = Workbook()
    ws = wb.active
    ws.title = "Kodlar"
    created = result.created_at.replace(tzinfo=None)
    rows = []
    for ir in result.items:
        it = ir.item
        for i, code in enumerate(ir.codes):
            rows.append([created, int(it.article), ir.first_seq + i, code, it.note or it.address or it.series,
                         it.address, it.name, it.series])
    _sheet(ws, ["Дата", "Артикул", "Уникальный код", "Уникальный код", "Izoh", "Адрес", "Наименование", "Seria"],
           rows, [20, 10, 16, 24, 16, 15, 55, 16])
    for row in ws.iter_rows(min_row=2, max_col=1):
        row[0].number_format = "DD/MM/YYYY HH:MM:SS"

    ws2 = wb.create_sheet("Xulosa")
    srows = [[ir.item.address, int(ir.item.article), ir.item.name, ir.item.series, len(ir.codes),
              ir.codes[0] if ir.codes else None, ir.codes[-1] if ir.codes else None] for ir in result.items]
    srows.append(["JAMI", None, None, None, result.total, None, None])
    _sheet(ws2, ["Адрес", "Артикул", "Наименование", "Seria", "Kod soni", "Birinchi kod", "Oxirgi kod"],
           srows, [15, 10, 55, 16, 10, 24, 24])
    ws2.cell(ws2.max_row, 1).font = HF
    ws2.cell(ws2.max_row, 5).font = HF
    if title:
        ws3 = wb.create_sheet("Izoh")
        ws3.column_dimensions["A"].width = 120
        for line in title.split("\n"):
            ws3.append([line])
    buf = BytesIO()
    wb.save(buf)
    return buf.getvalue()
