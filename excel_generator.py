"""
PI Excel Generator using openpyxl.
"""

import os
from openpyxl import Workbook
from openpyxl.styles import Font, Alignment, Border, Side, PatternFill, numbers
from openpyxl.utils import get_column_letter

CUR_SYMBOL = {'USD': '$', 'RMB': '¥'}


def generate_pi_excel(pi, output_dir):
    cur = getattr(pi, 'currency', 'USD') or 'USD'
    sym = CUR_SYMBOL.get(cur, '$')
    filename = f"{pi.pi_number}.xlsx"
    filepath = os.path.join(output_dir, filename)

    wb = Workbook()
    ws = wb.active
    ws.title = pi.pi_number

    # Styles
    hdr_fill = PatternFill(start_color='1a3a5c', end_color='1a3a5c', fill_type='solid')
    hdr_font = Font(name='Arial', bold=True, color='FFFFFF', size=10)
    bold = Font(name='Arial', bold=True, size=10)
    normal = Font(name='Arial', size=10)
    thin_border = Border(
        left=Side(style='thin'), right=Side(style='thin'),
        top=Side(style='thin'), bottom=Side(style='thin')
    )
    center = Alignment(horizontal='center', vertical='center')
    right = Alignment(horizontal='right', vertical='center')
    left = Alignment(horizontal='left', vertical='center', wrap_text=True)
    cur_fmt = f'{sym}#,##0.00'

    # Column widths
    ws.column_dimensions['A'].width = 45
    ws.column_dimensions['B'].width = 22
    ws.column_dimensions['C'].width = 22
    ws.column_dimensions['D'].width = 22
    ws.column_dimensions['E'].width = 18
    ws.column_dimensions['F'].width = 18
    ws.column_dimensions['G'].width = 18

    row = 1

    # Title
    ws.merge_cells('A1:G1')
    c = ws['A1']
    c.value = 'PROFORMA INVOICE'
    c.font = Font(name='Arial', bold=True, size=18, color='1a3a5c')
    c.alignment = Alignment(horizontal='center')
    row += 1

    ws.merge_cells('A2:G2')
    ws['A2'].value = pi.pi_number
    ws['A2'].font = Font(name='Arial', size=12, color='1a3a5c')
    ws['A2'].alignment = Alignment(horizontal='center')
    row += 2

    # Info section
    info = [
        ('PI Number:', pi.pi_number),
        ('Date:', pi.issue_date.strftime('%Y-%m-%d') if pi.issue_date else ''),
        ('Salesperson:', pi.salesperson or ''),
        ('Currency:', cur),
    ]
    customer = pi.customer
    cust_info = [
        ('Customer:', customer.name if customer else ''),
        ('Contact:', customer.contact_person if customer else ''),
        ('Country:', customer.country if customer else ''),
    ]
    for label, val in info:
        ws[f'A{row}'] = label; ws[f'A{row}'].font = bold
        ws[f'B{row}'] = val; ws[f'B{row}'].font = normal
        row += 1
    row += 1
    for label, val in cust_info:
        ws[f'A{row}'] = label; ws[f'A{row}'].font = bold
        ws[f'B{row}'] = val; ws[f'B{row}'].font = normal
        row += 1
    row += 1

    # Product table header
    headers = ['No.', 'Product Code', 'Description', 'Specification', 'Quantity', f'Unit Price ({cur})', f'Amount ({cur})']
    for i, h in enumerate(headers):
        cell = ws.cell(row=row, column=i+1, value=h)
        cell.font = hdr_font; cell.fill = hdr_fill; cell.alignment = center; cell.border = thin_border
    row += 1

    # Product rows
    for i, item in enumerate(pi.items, 1):
        vals = [i,
                item.product.product_code if item.product else '',
                item.product.name if item.product else '',
                item.product.specification if item.product else '',
                item.quantity,
                item.unit_price,
                item.amount]
        for j, v in enumerate(vals):
            cell = ws.cell(row=row, column=j+1, value=v)
            cell.font = normal; cell.border = thin_border
            if j >= 4: cell.alignment = right; cell.number_format = '#,##0.00' if j > 4 else '#,##0'
            else: cell.alignment = center if j == 0 else left
        row += 1

    # Total
    ws.merge_cells(start_row=row, start_column=1, end_row=row, end_column=6)
    c = ws.cell(row=row, column=1, value=f'TOTAL AMOUNT ({cur}):')
    c.font = Font(name='Arial', bold=True, size=12); c.alignment = right
    c = ws.cell(row=row, column=7, value=pi.total_amount)
    c.font = Font(name='Arial', bold=True, size=12); c.alignment = right; c.number_format = cur_fmt
    row += 2

    # Payment & Bank
    ws[f'A{row}'] = 'Payment Terms:'; ws[f'A{row}'].font = bold
    ws[f'B{row}'] = pi.payment_terms or ''; ws[f'B{row}'].font = normal
    row += 1
    ws[f'A{row}'] = 'Bank Info:'; ws[f'A{row}'].font = bold
    ws[f'B{row}'] = pi.bank_info or ''; ws[f'B{row}'].font = normal; ws[f'B{row}'].alignment = left
    row += 2

    # Signature
    ws[f'A{row}'] = 'Issued By:'; ws[f'A{row}'].font = bold
    row += 3
    ws[f'A{row}'] = '_________________________'
    row += 1
    ws[f'A{row}'] = 'CHANGZHOU KLISTA INTERNATIONAL TRADE CO., LTD.'

    wb.save(filepath)
    return filename
