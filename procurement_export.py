"""Generate supplier-facing purchase orders as editable Excel workbooks."""

import os
from io import BytesIO

from openpyxl import Workbook
from openpyxl.drawing.image import Image as ExcelImage
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.worksheet.page import PageMargins
from PIL import Image, ImageOps


NAVY = "1F4E78"
LIGHT_BLUE = "D9EAF7"
LIGHT_GRAY = "F3F5F7"
GREEN = "198754"


def _safe_product_image(filename, upload_dir, image_buffers):
    """Return an Excel image without allowing a stored filename to escape uploads."""
    filename = str(filename or "")
    if not filename or os.path.basename(filename) != filename:
        return None
    source_path = os.path.join(upload_dir, filename)
    if not os.path.isfile(source_path):
        return None
    try:
        with Image.open(source_path) as source:
            rendered = ImageOps.exif_transpose(source)
            if rendered.mode not in ("RGB", "RGBA"):
                rendered = rendered.convert("RGBA" if "transparency" in rendered.info else "RGB")
            rendered.thumbnail((360, 360), Image.Resampling.LANCZOS)
            buffer = BytesIO()
            rendered.save(buffer, format="PNG")
        buffer.seek(0)
        image_buffers.append(buffer)
        image = ExcelImage(buffer)
        image.width = 48
        image.height = 48
        return image
    except Exception:
        return None


def generate_supplier_purchase_order(
    pi,
    supplier,
    entries,
    purchase_date,
    buyer_company,
    buyer_address,
    upload_dir,
):
    """Return one supplier-specific purchase order as XLSX bytes.

    ``entries`` contains trusted, server-normalized dictionaries with
    ``pi_item``, ``unit_price``, ``quantity`` and ``note`` keys.
    Customer information, sales prices, exchange rates and profit figures are
    deliberately excluded from this supplier-facing document.
    """
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "采购订单"
    sheet.sheet_view.showGridLines = False
    sheet.freeze_panes = "A10"
    sheet.page_setup.paperSize = sheet.PAPERSIZE_A4
    sheet.page_setup.orientation = "landscape"
    sheet.page_setup.fitToWidth = 1
    sheet.page_setup.fitToHeight = 0
    sheet.sheet_properties.pageSetUpPr.fitToPage = True
    sheet.page_margins = PageMargins(
        left=0.3, right=0.3, top=0.45, bottom=0.45, header=0.2, footer=0.2
    )

    thin_gray = Side(style="thin", color="B8C2CC")
    border = Border(left=thin_gray, right=thin_gray, top=thin_gray, bottom=thin_gray)
    title_font = Font(name="Microsoft YaHei", size=18, bold=True, color="FFFFFF")
    label_font = Font(name="Microsoft YaHei", size=10, bold=True, color="4A5568")
    normal_font = Font(name="Microsoft YaHei", size=10, color="1F2937")
    header_font = Font(name="Microsoft YaHei", size=10, bold=True, color="FFFFFF")
    total_font = Font(name="Microsoft YaHei", size=12, bold=True, color=GREEN)
    centered = Alignment(horizontal="center", vertical="center", wrap_text=True)
    left = Alignment(horizontal="left", vertical="center", wrap_text=True)
    right = Alignment(horizontal="right", vertical="center")

    widths = {
        "A": 6,
        "B": 11,
        "C": 31,
        "D": 16,
        "E": 22,
        "F": 12,
        "G": 10,
        "H": 14,
        "I": 24,
    }
    for column, width in widths.items():
        sheet.column_dimensions[column].width = width

    sheet.merge_cells("A1:I2")
    title = sheet["A1"]
    title.value = "采购订单"
    title.font = title_font
    title.fill = PatternFill("solid", fgColor=NAVY)
    title.alignment = centered
    for row in sheet["A1:I2"]:
        for cell in row:
            cell.fill = PatternFill("solid", fgColor=NAVY)

    details = [
        (4, "采购单号", f"{pi.pi_number}-{supplier.id}", "采购日期", purchase_date),
        (5, "采购方", buyer_company, "供应商", supplier.name),
        (6, "采购方地址", buyer_address or "—", "联系人", supplier.contact_person or "—"),
        (7, "联系电话", "—", "电话", supplier.phone or "—"),
        (8, "电子邮箱", "—", "邮箱", supplier.email or "—"),
    ]
    for row_number, left_label, left_value, right_label, right_value in details:
        sheet.cell(row=row_number, column=1, value=left_label).font = label_font
        sheet.merge_cells(start_row=row_number, start_column=2, end_row=row_number, end_column=4)
        sheet.cell(row=row_number, column=2, value=left_value).font = normal_font
        sheet.cell(row=row_number, column=5, value=right_label).font = label_font
        sheet.merge_cells(start_row=row_number, start_column=6, end_row=row_number, end_column=9)
        sheet.cell(row=row_number, column=6, value=right_value).font = normal_font
        for column in range(1, 10):
            sheet.cell(row=row_number, column=column).alignment = left

    headers = ["序号", "图片", "产品名称", "产品编码", "规格", "数量", "采购单价", "金额", "备注"]
    header_row = 10
    for column, text in enumerate(headers, 1):
        cell = sheet.cell(row=header_row, column=column, value=text)
        cell.font = header_font
        cell.fill = PatternFill("solid", fgColor=NAVY)
        cell.alignment = centered
        cell.border = border
    sheet.row_dimensions[header_row].height = 25

    image_buffers = []
    first_item_row = header_row + 1
    total = 0.0
    for index, entry in enumerate(entries, 1):
        row_number = header_row + index
        pi_item = entry["pi_item"]
        unit_price = float(entry["unit_price"])
        quantity = int(entry["quantity"])
        line_total = round(unit_price * quantity, 2)
        total += line_total
        values = [
            index,
            "",
            entry.get("product_name", "") or "未知产品",
            entry.get("product_code", "") or "",
            entry.get("specification", "") or "",
            quantity,
            unit_price,
            line_total,
            entry.get("note", "") or "",
        ]
        for column, value in enumerate(values, 1):
            cell = sheet.cell(row=row_number, column=column, value=value)
            cell.font = normal_font
            cell.border = border
            cell.alignment = centered if column in (1, 2, 6) else left
            if column in (7, 8):
                cell.alignment = right
                cell.number_format = '¥#,##0.00'
            if index % 2 == 0:
                cell.fill = PatternFill("solid", fgColor=LIGHT_GRAY)
        chinese_name = entry.get("chinese_name", "") or ""
        if chinese_name:
            sheet.cell(row=row_number, column=3).value += f"\n{chinese_name}"
        image = _safe_product_image(entry.get("image", ""), upload_dir, image_buffers)
        if image:
            sheet.add_image(image, f"B{row_number}")
        sheet.row_dimensions[row_number].height = 44

    total_row = header_row + len(entries) + 1
    sheet.merge_cells(start_row=total_row, start_column=1, end_row=total_row, end_column=7)
    total_label = sheet.cell(row=total_row, column=1, value="采购产品合计（人民币）")
    total_label.font = Font(name="Microsoft YaHei", size=11, bold=True)
    total_label.alignment = right
    total_value = sheet.cell(row=total_row, column=8, value=round(total, 2))
    total_value.font = total_font
    total_value.number_format = '¥#,##0.00'
    total_value.alignment = right
    sheet.cell(row=total_row, column=9, value="")
    for column in range(1, 10):
        cell = sheet.cell(row=total_row, column=column)
        cell.fill = PatternFill("solid", fgColor=LIGHT_BLUE)
        cell.border = border
    sheet.row_dimensions[total_row].height = 28

    note_row = total_row + 2
    sheet.merge_cells(start_row=note_row, start_column=1, end_row=note_row + 1, end_column=9)
    note = sheet.cell(
        row=note_row,
        column=1,
        value="请核对以上产品、规格、数量及价格。如有差异，请在安排生产或发货前联系我们确认。",
    )
    note.font = Font(name="Microsoft YaHei", size=9, color="4A5568")
    note.alignment = left
    note.fill = PatternFill("solid", fgColor="FFF8E1")

    sheet.auto_filter.ref = f"A{header_row}:I{header_row + len(entries)}"
    sheet.print_title_rows = f"1:{header_row}"
    sheet.print_area = f"A1:I{note_row + 1}"
    sheet.oddFooter.center.text = "第 &P 页 / 共 &N 页"
    sheet.oddFooter.center.size = 8

    output = BytesIO()
    workbook.save(output)
    output.seek(0)
    return output.getvalue()
