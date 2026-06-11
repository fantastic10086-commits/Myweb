"""
PI Excel Generator — compact A4 portrait, all columns fit to page.
"""

import os
from openpyxl import Workbook
from openpyxl.styles import Font, Alignment, Border, Side, PatternFill
from openpyxl.worksheet.page import PageMargins

CUR_SYMBOL = {'USD': '$', 'RMB': '¥'}
BRANDS = {
    'klista': 'CHANGZHOU KLISTA INTERNATIONAL TRADE CO., LTD.',
    'qisuo':  'Changzhou QISUO Welding and Cutting Equipment Co., Ltd.',
}


def generate_pi_excel(pi, output_dir):
    cur = getattr(pi, 'currency', 'USD') or 'USD'
    sym = CUR_SYMBOL.get(cur, '$')
    brand = getattr(pi, 'company', 'klista') or 'klista'
    company_name = BRANDS.get(brand, BRANDS['klista'])
    filename = f"{pi.pi_number}.xlsx"
    filepath = os.path.join(output_dir, filename)

    wb = Workbook()
    ws = wb.active
    ws.title = pi.pi_number

    # ── Page setup A4 portrait ──
    ws.page_setup.paperSize = ws.PAPERSIZE_A4
    ws.page_setup.orientation = 'portrait'
    ws.page_margins = PageMargins(left=0.4, right=0.4, top=0.4, bottom=0.4, header=0.2, footer=0.2)
    ws.page_setup.fitToWidth = 1
    ws.page_setup.fitToHeight = 0

    # ── Styles ──
    hdr_fill = PatternFill(start_color='1a3a5c', end_color='1a3a5c', fill_type='solid')
    hdr_font = Font(name='Arial', bold=True, color='FFFFFF', size=9)
    bold8 = Font(name='Arial', bold=True, size=8)
    bold9 = Font(name='Arial', bold=True, size=9)
    nrm8 = Font(name='Arial', size=8)
    nrm9 = Font(name='Arial', size=9)
    thin = Border(left=Side('thin'), right=Side('thin'), top=Side('thin'), bottom=Side('thin'))
    ctr = Alignment(horizontal='center', vertical='center', wrap_text=True)
    rgt = Alignment(horizontal='right', vertical='center')
    lft = Alignment(horizontal='left', vertical='center', wrap_text=True)

    # Column widths — total ~200 units to fit A4
    ws.column_dimensions['A'].width = 4    # No.
    ws.column_dimensions['B'].width = 40   # Description
    ws.column_dimensions['C'].width = 10   # QTY
    ws.column_dimensions['D'].width = 14   # Unit Price
    ws.column_dimensions['E'].width = 14   # Amount

    r = 1

    # ── Company header ──
    ws.merge_cells(start_row=r, start_column=1, end_row=r, end_column=5)
    c = ws.cell(row=r, column=1, value=company_name)
    c.font = Font(name='Arial', bold=True, size=12, color='1a3a5c')
    c.alignment = Alignment(horizontal='center')
    r += 1
    ws.merge_cells(start_row=r, start_column=1, end_row=r, end_column=5)
    ws.cell(row=r, column=1, value='No. 158 Jinchuang Road, Yaoguan Town, Changzhou City, China').font = Font(name='Arial', size=6, color='888888')
    ws.cell(row=r, column=1).alignment = Alignment(horizontal='center')
    r += 1

    # ── Title ──
    ws.merge_cells(start_row=r, start_column=1, end_row=r, end_column=5)
    c = ws.cell(row=r, column=1, value='PROFORMA INVOICE')
    c.font = Font(name='Arial', bold=True, size=16, color='1a3a5c')
    c.alignment = Alignment(horizontal='center')
    r += 2

    # ── PI Info section ──
    info_rows = [
        ('PI Number:', pi.pi_number, 'Date:', pi.issue_date.strftime('%Y-%m-%d') if pi.issue_date else ''),
    ]
    if pi.salesperson:
        info_rows.append(('Salesperson:', pi.salesperson, '', ''))

    for left_lb, left_vl, right_lb, right_vl in info_rows:
        ws.cell(row=r, column=1, value=left_lb).font = bold9
        ws.merge_cells(start_row=r, start_column=2, end_row=r, end_column=2)
        ws.cell(row=r, column=2, value=left_vl).font = nrm9
        if right_lb:
            ws.cell(row=r, column=3, value=right_lb).font = bold9
            ws.merge_cells(start_row=r, start_column=4, end_row=r, end_column=5)
            ws.cell(row=r, column=4, value=right_vl).font = nrm9
        r += 1
    r += 1

    # ── Customer Info ──
    ws.cell(row=r, column=1, value='To / ATTN:').font = Font(name='Arial', bold=True, size=9)
    r += 1
    customer = pi.customer
    if customer:
        for lb, vl in [('Company:', customer.name), ('Contact:', customer.contact_person),
                       ('Country:', customer.country), ('Address:', customer.address)]:
            if vl:
                ws.cell(row=r, column=1, value=lb).font = bold8
                ws.merge_cells(start_row=r, start_column=2, end_row=r, end_column=5)
                ws.cell(row=r, column=2, value=vl).font = nrm8
                ws.cell(row=r, column=2).alignment = lft
                r += 1
    r += 1

    # ── Product Table ──
    headers = ['No.', 'Description / Item', 'QTY(pcs)', f'Unit Price({cur})', f'Amount({cur})']
    for i, h in enumerate(headers):
        c = ws.cell(row=r, column=i+1, value=h)
        c.font = hdr_font; c.fill = hdr_fill; c.alignment = ctr; c.border = thin
    r += 1

    light_bg = PatternFill(start_color='f4f6f9', end_color='f4f6f9', fill_type='solid')
    for idx, item in enumerate(pi.items, 1):
        desc = item.product.name if item.product else ''
        if item.product and item.product.specification:
            desc += f'\n{item.product.specification}'
        vals = [idx, desc, item.quantity, item.unit_price, item.amount]
        for j, v in enumerate(vals):
            c = ws.cell(row=r, column=j+1, value=v)
            c.font = nrm8; c.border = thin
            if j >= 2: c.alignment = rgt; c.number_format = '#,##0.00' if j > 2 else '#,##0'
            elif j == 0: c.alignment = ctr
            else: c.alignment = lft
            # alternate row
            if idx % 2 == 0: c.fill = light_bg
        r += 1
    r += 1

    # ── Total ──
    total = pi.total_amount
    ws.merge_cells(start_row=r, start_column=1, end_row=r, end_column=4)
    c = ws.cell(row=r, column=1, value='TOTAL:')
    c.font = Font(name='Arial', bold=True, size=11); c.alignment = rgt
    c = ws.cell(row=r, column=5, value=total)
    c.font = Font(name='Arial', bold=True, size=11); c.alignment = rgt
    c.number_format = f'{sym}#,##0.00'
    c.border = Border(bottom=Side('double'))
    r += 1

    # ── Payment / Bank / Origin ──
    ws.merge_cells(start_row=r, start_column=1, end_row=r, end_column=5)
    ws.cell(row=r, column=1, value=f'Payment Terms: {pi.payment_terms or "100% TT before shipment"}').font = nrm8
    r += 1
    if pi.bank_info:
        ws.merge_cells(start_row=r, start_column=1, end_row=r, end_column=5)
        ws.cell(row=r, column=1, value=f'Bank: {pi.bank_info}').font = nrm8
        ws.cell(row=r, column=1).alignment = lft
        r += 1
    ws.cell(row=r, column=1, value='Country of Origin: China').font = bold8
    r += 2

    # ── Signature ──
    ws.cell(row=r, column=1, value=company_name).font = bold9
    ws.cell(row=r, column=4, value='BUYER:').font = bold9
    r += 3
    ws.cell(row=r, column=1, value='_________________________')
    ws.cell(row=r, column=4, value='_________________________')
    r += 1
    ws.cell(row=r, column=1, value=f'Date: {__import__("datetime").datetime.now().strftime("%Y-%m-%d")}')

    # ── Print area ──
    ws.print_area = f'A1:E{r}'

    wb.save(filepath)
    return filename
