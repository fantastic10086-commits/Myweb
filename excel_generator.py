"""
PI Excel Generator — matching PI PDF format.
"""

import os
from openpyxl import Workbook
from openpyxl.styles import Font, Alignment, Border, Side, PatternFill

CUR_SYMBOL = {'USD': '$', 'RMB': '¥'}

BRANDS = {
    'klista': 'CHANGZHOU KLISTA INTERNATIONAL TRADE CO., LTD.',
    'qisuo':  'Changzhou QISUO Welding and Cutting Equipment Co., Ltd.',
}

def _num_to_words(n):
    ones = ['', 'ONE', 'TWO', 'THREE', 'FOUR', 'FIVE', 'SIX', 'SEVEN', 'EIGHT', 'NINE']
    teens = ['TEN', 'ELEVEN', 'TWELVE', 'THIRTEEN', 'FOURTEEN', 'FIFTEEN', 'SIXTEEN', 'SEVENTEEN', 'EIGHTEEN', 'NINETEEN']
    tens = ['', '', 'TWENTY', 'THIRTY', 'FORTY', 'FIFTY', 'SIXTY', 'SEVENTY', 'EIGHTY', 'NINETY']
    def _h(n):
        if n < 10: return ones[n]
        if n < 20: return teens[n-10]
        if n < 100: return tens[n//10] + (' ' + ones[n%10] if n%10 else '')
        if n < 1000: return ones[n//100] + ' HUNDRED' + (' ' + _h(n%100) if n%100 else '')
        return ''
    dollars = int(n); cents = int(round((n-dollars)*100))
    if dollars == 0: words = 'ZERO'
    elif dollars < 1000: words = _h(dollars)
    else:
        words = _h(dollars//1000) + ' THOUSAND'
        r = dollars % 1000
        if r: words += ' ' + _h(r)
    return f'US DOLLARS {words} ONLY' + (f' AND CENTS {cents}' if cents else '')


def generate_pi_excel(pi, output_dir):
    cur = getattr(pi, 'currency', 'USD') or 'USD'
    sym = CUR_SYMBOL.get(cur, '$')
    brand = getattr(pi, 'company', 'klista') or 'klista'
    company_name = BRANDS.get(brand, BRANDS['klista'])
    filename = f"{pi.pi_number}.xlsx"
    filepath = os.path.join(output_dir, filename)

    wb = Workbook(); ws = wb.active; ws.title = pi.pi_number

    hf = PatternFill(start_color='1a3a5c', end_color='1a3a5c', fill_type='solid')
    hfont = Font(name='Arial', bold=True, color='FFFFFF', size=10)
    bold = Font(name='Arial', bold=True, size=10)
    nrm = Font(name='Arial', size=10)
    thin = Border(left=Side('thin'), right=Side('thin'), top=Side('thin'), bottom=Side('thin'))
    ctr = Alignment(horizontal='center', vertical='center')
    rgt = Alignment(horizontal='right', vertical='center')
    lft = Alignment(horizontal='left', vertical='center', wrap_text=True)

    ws.column_dimensions['A'].width = 6
    ws.column_dimensions['B'].width = 50
    ws.column_dimensions['C'].width = 12
    ws.column_dimensions['D'].width = 18
    ws.column_dimensions['E'].width = 18

    r = 1
    # Company name
    ws.merge_cells('A1:E1'); c=ws['A1']; c.value=company_name; c.font=Font(name='Arial',bold=True,size=14,color='1a3a5c'); c.alignment=Alignment(horizontal='center')
    r+=1
    ws.merge_cells(f'A{r}:E{r}'); ws[f'A{r}'].value='No. 158 Jinchuang Road, Yaoguan Town, Changzhou City, China'; ws[f'A{r}'].font=Font(name='Arial',size=8,color='888888'); ws[f'A{r}'].alignment=Alignment(horizontal='center')
    r+=2

    # Title
    ws.merge_cells(f'A{r}:E{r}'); c=ws[f'A{r}']; c.value='PROFORMA INVOICE'; c.font=Font(name='Arial',bold=True,size=18,color='1a3a5c'); c.alignment=Alignment(horizontal='center')
    r+=2

    # PI Info
    info = [('PI Number:', pi.pi_number), ('Date:', pi.issue_date.strftime('%Y-%m-%d') if pi.issue_date else '')]
    if pi.salesperson: info.append(('Salesperson:', pi.salesperson))
    for lb, vl in info:
        ws[f'A{r}']=lb; ws[f'A{r}'].font=bold; ws[f'B{r}']=vl; ws[f'B{r}'].font=nrm; r+=1
    r+=1

    # Customer
    customer = pi.customer
    ws[f'A{r}']='To / ATTN:'; ws[f'A{r}'].font=Font(name='Arial',bold=True,size=11)
    r+=1
    if customer:
        for lb, vl in [('Company:', customer.name), ('Contact:', customer.contact_person), ('Country:', customer.country), ('Address:', customer.address)]:
            if vl:
                ws[f'A{r}']=lb; ws[f'A{r}'].font=bold; ws[f'B{r}']=vl; ws[f'B{r}'].font=nrm; r+=1
    r+=1

    # Product table
    headers = ['No.', 'Description / Item', 'QTY (pcs)', f'Unit Price ({cur})', f'Amount ({cur})']
    for i, h in enumerate(headers):
        c=ws.cell(row=r,column=i+1,value=h); c.font=hfont; c.fill=hf; c.alignment=ctr; c.border=thin
    r+=1
    for i, item in enumerate(pi.items, 1):
        desc = item.product.name if item.product else ''
        if item.product and item.product.specification: desc += f'\n{item.product.specification}'
        vals = [i, desc, item.quantity, item.unit_price, item.amount]
        for j, v in enumerate(vals):
            c=ws.cell(row=r,column=j+1,value=v); c.font=nrm; c.border=thin
            if j>=2: c.alignment=rgt; c.number_format='#,##0.00' if j>2 else '#,##0'
            elif j==0: c.alignment=ctr
            else: c.alignment=lft
        r+=1
    r+=1

    # Total
    total = pi.total_amount
    ws.merge_cells(start_row=r, start_column=1, end_row=r, end_column=4)
    ws.cell(row=r, column=1, value='TOTAL:').font=Font(name='Arial',bold=True,size=12); ws.cell(row=r, column=1).alignment=rgt
    c=ws.cell(row=r, column=5, value=total); c.font=Font(name='Arial',bold=True,size=12); c.alignment=rgt; c.number_format=f'{sym}#,##0.00'
    r+=1
    if cur == 'USD':
        ws.merge_cells(start_row=r, start_column=1, end_row=r, end_column=5)
        ws.cell(row=r, column=1, value=_num_to_words(total)).font=Font(name='Arial',italic=True,size=9,color='666666'); ws.cell(row=r, column=1).alignment=rgt
        r+=1
    r+=1

    # Payment & Bank
    ws[f'A{r}']='Payment Terms:'; ws[f'A{r}'].font=bold
    ws[f'B{r}']=pi.payment_terms or '100% T/T in advance'; ws[f'B{r}'].font=nrm; r+=1
    if pi.bank_info:
        ws[f'A{r}']='Bank Information:'; ws[f'A{r}'].font=bold
        ws[f'B{r}']=pi.bank_info; ws[f'B{r}'].font=nrm; ws[f'B{r}'].alignment=lft; r+=1

    ws[f'A{r}']='Country of Origin:'; ws[f'A{r}'].font=bold
    ws[f'B{r}']='China'; ws[f'B{r}'].font=nrm; r+=2

    # Signatures
    ws[f'A{r}']=company_name; ws[f'A{r}'].font=bold
    ws[f'D{r}']='BUYER:'; ws[f'D{r}'].font=bold; r+=3
    ws[f'A{r}']='_________________________'; ws[f'D{r}']='_________________________'; r+=1
    ws[f'A{r}']=f'Date: {__import__("datetime").datetime.now().strftime("%Y-%m-%d")}'

    wb.save(filepath)
    return filename
