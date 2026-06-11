"""
PI Excel Generator — matches PDF side-by-side layout, A4 portrait.
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
    hf = Font(name='Arial', bold=True, color='FFFFFF', size=9)
    b8 = Font(name='Arial', bold=True, size=8)
    b9 = Font(name='Arial', bold=True, size=9)
    n8 = Font(name='Arial', size=8)
    n9 = Font(name='Arial', size=9)
    thin = Border(left=Side('thin'), right=Side('thin'), top=Side('thin'), bottom=Side('thin'))
    ctr = Alignment(horizontal='center', vertical='center', wrap_text=True)
    rgt = Alignment(horizontal='right', vertical='center')
    lft = Alignment(horizontal='left', vertical='center', wrap_text=True)
    light_fill = PatternFill(start_color='f4f6f9', end_color='f4f6f9', fill_type='solid')

    # Columns for side-by-side layout:
    # A:Label(12)  B:Value(30)  C:gap(2)  D:Label(12)  E:Value(35)
    ws.column_dimensions['A'].width = 14
    ws.column_dimensions['B'].width = 34
    ws.column_dimensions['C'].width = 3
    ws.column_dimensions['D'].width = 14
    ws.column_dimensions['E'].width = 38

    r = 1

    # ── Company + Title ──
    ws.merge_cells('A1:E1')
    c = ws['A1']; c.value = company_name
    c.font = Font(name='Arial', bold=True, size=13, color='1a3a5c'); c.alignment = Alignment(horizontal='center')
    r += 1
    ws.merge_cells(f'A{r}:E{r}')
    c = ws.cell(row=r, column=1, value='No. 158 Jinchuang Road, Yaoguan Town, Changzhou City, China')
    c.font = Font(name='Arial', size=6, color='888888'); c.alignment = Alignment(horizontal='center')
    r += 1
    ws.merge_cells(f'A{r}:E{r}')
    c = ws.cell(row=r, column=1, value='PROFORMA INVOICE')
    c.font = Font(name='Arial', bold=True, size=16, color='1a3a5c'); c.alignment = Alignment(horizontal='center')
    r += 2

    # ── PI Info (left) + Customer Info (right) ──
    pi_start = r

    # Left column: PI info
    ws.cell(row=r, column=1, value='PI Number:').font = b9
    ws.cell(row=r, column=2, value=pi.pi_number).font = n9; r += 1
    ws.cell(row=r, column=1, value='Date:').font = b9
    ws.cell(row=r, column=2, value=pi.issue_date.strftime('%Y-%m-%d') if pi.issue_date else '').font = n9; r += 1
    if pi.salesperson:
        ws.cell(row=r, column=1, value='Salesperson:').font = b9
        ws.cell(row=r, column=2, value=pi.salesperson).font = n9; r += 1
    r = pi_start  # reset for right side

    # Right column: Customer info
    customer = pi.customer
    ws.cell(row=r, column=4, value='To / Buyer:').font = b9
    ws.cell(row=r, column=5, value=customer.name if customer else '').font = n9; r += 1
    if customer:
        if customer.contact_person:
            ws.cell(row=r, column=4, value='Contact:').font = b9
            ws.cell(row=r, column=5, value=customer.contact_person).font = n9; r += 1
        if customer.country:
            ws.cell(row=r, column=4, value='Country:').font = b9
            ws.cell(row=r, column=5, value=customer.country).font = n9; r += 1
        if customer.email:
            ws.cell(row=r, column=4, value='Email:').font = b9
            ws.cell(row=r, column=5, value=customer.email).font = n9; r += 1
        if customer.phone:
            ws.cell(row=r, column=4, value='Phone:').font = b9
            ws.cell(row=r, column=5, value=customer.phone).font = n9; r += 1
        if customer.address:
            ws.cell(row=r, column=4, value='Address:').font = b9
            ws.cell(row=r, column=5, value=customer.address).font = n9; ws.cell(row=r, column=5).alignment = lft; r += 1

    r = max(r, pi_start + 3) + 2

    # ── Product table (full width) ──
    # Adjust columns for table
    ws.column_dimensions['A'].width = 5
    ws.column_dimensions['B'].width = 50
    ws.column_dimensions['C'].width = 12
    ws.column_dimensions['D'].width = 16
    ws.column_dimensions['E'].width = 16

    headers = ['No.', 'Description / Item', 'QTY(pcs)', f'U.Price({cur})', f'Amount({cur})']
    for i, h in enumerate(headers):
        c = ws.cell(row=r, column=i+1, value=h); c.font = hf; c.fill = hdr_fill; c.alignment = ctr; c.border = thin
    r += 1

    for idx, item in enumerate(pi.items, 1):
        desc = item.product.name if item.product else ''
        if item.product and item.product.specification:
            desc += f'\n{item.product.specification}'
        vals = [idx, desc, item.quantity, item.unit_price, item.amount]
        for j, v in enumerate(vals):
            c = ws.cell(row=r, column=j+1, value=v); c.font = n8; c.border = thin
            if j >= 2: c.alignment = rgt; c.number_format = '#,##0.00' if j > 2 else '#,##0'
            elif j == 0: c.alignment = ctr
            else: c.alignment = lft
            if idx % 2 == 0: c.fill = light_fill
        r += 1
    r += 1

    # ── Total ──
    total = pi.total_amount
    ws.merge_cells(start_row=r, start_column=1, end_row=r, end_column=4)
    ws.cell(row=r, column=1, value='TOTAL:').font = Font(name='Arial', bold=True, size=12); ws.cell(row=r, column=1).alignment = rgt
    c = ws.cell(row=r, column=5, value=total); c.font = Font(name='Arial', bold=True, size=12); c.alignment = rgt
    c.number_format = f'{sym}#,##0.00'; c.border = Border(bottom=Side('double'))
    r += 2

    # ── Payment / Bank / Origin ──
    ws.merge_cells(f'A{r}:E{r}')
    ws.cell(row=r, column=1, value=f'Payment Terms: {pi.payment_terms or "100% TT before shipment"}').font = n9; r += 1
    if pi.bank_info:
        ws.merge_cells(f'A{r}:E{r}')
        ws.cell(row=r, column=1, value=f'Bank: {pi.bank_info}').font = n9
        ws.cell(row=r, column=1).alignment = lft; r += 1
    ws.cell(row=r, column=1, value='Country of Origin: China').font = b9; r += 2

    # ── Signature ──
    ws.cell(row=r, column=1, value=company_name).font = b9
    ws.merge_cells(start_row=r, start_column=1, end_row=r, end_column=2)
    ws.cell(row=r, column=4, value='BUYER:').font = b9
    r += 3
    ws.cell(row=r, column=1, value='_________________________')
    ws.cell(row=r, column=4, value='_________________________')
    r += 1
    ws.cell(row=r, column=1, value=f'Date: {__import__("datetime").datetime.now().strftime("%Y-%m-%d")}')

    ws.print_area = f'A1:E{r}'
    wb.save(filepath)
    return filename
