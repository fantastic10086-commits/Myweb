"""
PI (Proforma Invoice) PDF Generator.
Reference format: company header, PI title, customer info, product table,
total in words, payment terms, bank info, signatures.
"""

import os
from datetime import datetime
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.colors import HexColor, black, white, grey
from reportlab.lib.enums import TA_LEFT, TA_CENTER, TA_RIGHT
from reportlab.platypus import (
    SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer, HRFlowable, Image
)
from reportlab.platypus.doctemplate import PageTemplate, BaseDocTemplate, Frame
from reportlab.pdfgen import canvas

COMPANY_INFO = {
    'name': 'CHANGZHOU KLISTA INTERNATIONAL TRADE CO., LTD.',
    'address': 'No. 158 Jinchuang Road, Yaoguan Town, Changzhou City, China',
    'phone': '+86 17712333882',
    'email': 'fantastic10086@gmail.com',
}

BRANDS = {
    'klista': 'CHANGZHOU KLISTA INTERNATIONAL TRADE CO., LTD.',
    'qisuo':  'Changzhou QISUO Welding and Cutting Equipment Co., Ltd.',
}

PAGE_W, PAGE_H = A4


def _num_to_words(n):
    """Convert a number to English words (US DOLLARS ... ONLY)."""
    ones = ['', 'ONE', 'TWO', 'THREE', 'FOUR', 'FIVE', 'SIX', 'SEVEN', 'EIGHT', 'NINE']
    teens = ['TEN', 'ELEVEN', 'TWELVE', 'THIRTEEN', 'FOURTEEN', 'FIFTEEN', 'SIXTEEN', 'SEVENTEEN', 'EIGHTEEN', 'NINETEEN']
    tens = ['', '', 'TWENTY', 'THIRTY', 'FORTY', 'FIFTY', 'SIXTY', 'SEVENTY', 'EIGHTY', 'NINETY']

    def _h(n):
        if n < 10: return ones[n]
        if n < 20: return teens[n-10]
        if n < 100: return tens[n//10] + (' ' + ones[n%10] if n%10 else '')
        if n < 1000: return ones[n//100] + ' HUNDRED' + (' ' + _h(n%100) if n%100 else '')
        return ''

    dollars = int(n)
    cents = int(round((n - dollars) * 100))
    if dollars == 0:
        words = 'ZERO'
    elif dollars < 1000:
        words = _h(dollars)
    else:
        words = _h(dollars//1000) + ' THOUSAND'
        r = dollars % 1000
        if r: words += ' ' + _h(r)

    result = f'US DOLLARS {words} ONLY'
    if cents > 0:
        result += f' AND CENTS {cents}'
    return result


def currency_symbol(cur): return '¥' if cur == 'RMB' else '$'
def currency_label(cur): return 'RMB' if cur == 'RMB' else 'USD'


def _draw_page_template(canvas, doc):
    canvas.saveState()
    # Header bar
    canvas.setFillColor(HexColor('#1a3a5c'))
    canvas.rect(20*mm, PAGE_H-30*mm, PAGE_W-40*mm, 16*mm, fill=1, stroke=0)
    canvas.setFillColor(white)
    canvas.setFont('Helvetica-Bold', 15)
    company_name = getattr(doc, 'company_name', COMPANY_INFO['name'])
    canvas.drawString(25*mm, PAGE_H-20*mm, company_name)
    canvas.setFont('Helvetica', 7)
    canvas.setFillColor(HexColor('#cccccc'))
    canvas.drawCentredString(PAGE_W/2, PAGE_H-27*mm, COMPANY_INFO['address'])
    # Footer
    canvas.setFillColor(grey)
    canvas.setFont('Helvetica', 7)
    page_num = getattr(canvas, '_pageNumber', 1)
    canvas.drawCentredString(PAGE_W/2, 15*mm, f"Page {page_num}")
    canvas.setStrokeColor(HexColor('#1a3a5c'))
    canvas.setLineWidth(0.5)
    canvas.line(20*mm, 22*mm, PAGE_W-20*mm, 22*mm)
    canvas.restoreState()


def generate_pi_pdf(pi, output_dir, salesperson_info=None):
    if salesperson_info is None: salesperson_info = {}
    cur = getattr(pi, 'currency', 'USD') or 'USD'
    sym = currency_symbol(cur)
    cur_label = currency_label(cur)
    brand = getattr(pi, 'company', 'klista') or 'klista'
    company_name = BRANDS.get(brand, BRANDS['klista'])

    filename = f"{pi.pi_number}.pdf"
    filepath = os.path.join(output_dir, filename)

    doc = SimpleDocTemplate(filepath, pagesize=A4,
        leftMargin=20*mm, rightMargin=20*mm, topMargin=32*mm, bottomMargin=30*mm,
        title=f'PI {pi.pi_number}', author=company_name)
    # Attach company name for header callback
    doc.company_name = company_name

    styles = getSampleStyleSheet()
    title_style = ParagraphStyle('T', parent=styles['Title'], fontSize=20, fontName='Helvetica-Bold', textColor=HexColor('#1a3a5c'), spaceAfter=3*mm, alignment=TA_CENTER)
    label_style = ParagraphStyle('L', parent=styles['Normal'], fontSize=9, fontName='Helvetica-Bold', spaceAfter=1*mm, spaceBefore=2*mm)
    val_style = ParagraphStyle('V', parent=styles['Normal'], fontSize=9, fontName='Helvetica', spaceAfter=1*mm)
    th_style = ParagraphStyle('TH', parent=styles['Normal'], fontSize=8, fontName='Helvetica-Bold', textColor=white, alignment=TA_CENTER)
    td_style = ParagraphStyle('TD', parent=styles['Normal'], fontSize=8, fontName='Helvetica', alignment=TA_CENTER)
    td_left = ParagraphStyle('TDL', parent=td_style, alignment=TA_LEFT)
    td_right = ParagraphStyle('TDR', parent=td_style, alignment=TA_RIGHT)
    base_color = HexColor('#1a3a5c')

    story = []

    # Title
    story.append(Paragraph('PROFORMA INVOICE', title_style))
    story.append(HRFlowable(width="100%", thickness=1.5, color=base_color, spaceAfter=4*mm))

    # PI Info
    pi_rows = [
        ['PI Number:', pi.pi_number, 'Date:', pi.issue_date.strftime('%Y-%m-%d') if pi.issue_date else ''],
    ]
    if pi.salesperson:
        pi_rows.append(['Salesperson:', pi.salesperson, '', ''])
    if salesperson_info.get('phone'):
        pi_rows.append(['Tel:', salesperson_info['phone'], 'Email:', salesperson_info.get('email', '')])
    pi_table = Table(pi_rows, colWidths=[55, 140, 45, 120])
    pi_table.setStyle(TableStyle([
        ('FONT', (0,0), (0,-1), 'Helvetica-Bold'),
        ('FONT', (2,0), (2,-1), 'Helvetica-Bold'),
        ('FONTSIZE', (0,0), (-1,-1), 9),
        ('VALIGN', (0,0), (-1,-1), 'TOP'),
        ('TOPPADDING', (0,0), (-1,-1), 1),
        ('BOTTOMPADDING', (0,0), (-1,-1), 1),
        ('LEFTPADDING', (0,0), (-1,-1), 0),
    ]))
    story.append(pi_table)
    story.append(Spacer(1, 3*mm))

    # Customer (To / ATTN)
    customer = pi.customer
    story.append(Paragraph('To / ATTN:', label_style))
    cust_rows = []
    if customer:
        cust_rows.append([Paragraph('<b>Company:</b>', val_style), Paragraph(customer.name or '', val_style)])
        if customer.contact_person:
            cust_rows.append([Paragraph('<b>Contact:</b>', val_style), Paragraph(customer.contact_person, val_style)])
        if customer.country:
            cust_rows.append([Paragraph('<b>Country:</b>', val_style), Paragraph(customer.country, val_style)])
        if customer.address:
            cust_rows.append([Paragraph('<b>Address:</b>', val_style), Paragraph(customer.address, val_style)])
    if cust_rows:
        ct = Table(cust_rows, colWidths=[55, 300])
        ct.setStyle(TableStyle([('VALIGN',(0,0),(-1,-1),'TOP'),('TOPPADDING',(0,0),(-1,-1),1),('BOTTOMPADDING',(0,0),(-1,-1),1),('LEFTPADDING',(0,0),(-1,-1),0)]))
        story.append(ct)
    story.append(Spacer(1, 4*mm))

    # Product Table
    story.append(HRFlowable(width="100%", thickness=0.5, color=HexColor('#cccccc'), spaceAfter=2*mm))
    header = [
        Paragraph('No.', th_style),
        Paragraph('Description / Item', th_style),
        Paragraph('QTY<br/>(pcs)', th_style),
        Paragraph(f'Unit Price<br/>({cur_label})', th_style),
        Paragraph(f'Amount<br/>({cur_label})', th_style),
    ]
    col_w = [22, 260, 55, 75, 75]
    table_data = [header]
    upload_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'static', 'uploads')
    for i, item in enumerate(pi.items, 1):
        desc = item.product.name if item.product else ''
        if item.product and item.product.specification:
            desc += f'<br/><font size="7" color="#888888">{item.product.specification}</font>'
        img_cell = Paragraph('', td_style)
        if item.product and item.product.image:
            img_path = os.path.join(upload_dir, item.product.image)
            if os.path.exists(img_path):
                try: img_cell = Image(img_path, width=10*mm, height=10*mm)
                except: pass
        row = [
            Paragraph(str(i), td_style),
            Paragraph(desc, td_left),
            Paragraph(str(item.quantity), td_style),
            Paragraph(f'{sym}{item.unit_price:,.2f}', td_right),
            Paragraph(f'{sym}{item.amount:,.2f}', td_right),
        ]
        table_data.append(row)

    prod_table = Table(table_data, colWidths=col_w, repeatRows=1)
    light_bg = HexColor('#f4f6f9')
    style_cmds = [
        ('BACKGROUND',(0,0),(-1,0), base_color), ('TEXTCOLOR',(0,0),(-1,0), white),
        ('GRID',(0,0),(-1,-1), 0.5, HexColor('#cccccc')),
        ('LINEBELOW',(0,0),(-1,0), 1, base_color),
        ('VALIGN',(0,0),(-1,-1),'MIDDLE'),
        ('TOPPADDING',(0,0),(-1,-1),5), ('BOTTOMPADDING',(0,0),(-1,-1),5),
        ('LEFTPADDING',(0,0),(-1,-1),4), ('RIGHTPADDING',(0,0),(-1,-1),4),
    ]
    for ri in range(1, len(table_data)):
        if ri % 2 == 0: style_cmds.append(('BACKGROUND',(0,ri),(-1,ri), light_bg))
    prod_table.setStyle(TableStyle(style_cmds))
    story.append(prod_table)
    story.append(Spacer(1, 4*mm))

    # Total
    total = pi.total_amount
    total_words = _num_to_words(total)
    total_rows = [
        [Paragraph(f'<b>TOTAL:</b>', ParagraphStyle('TL', parent=val_style, fontSize=11, fontName='Helvetica-Bold', alignment=TA_RIGHT)),
         Paragraph(f'<b>{sym}{total:,.2f}</b>', ParagraphStyle('TV', parent=val_style, fontSize=11, fontName='Helvetica-Bold', alignment=TA_RIGHT))],
    ]
    if cur == 'USD':
        total_rows.append([Paragraph('', val_style), Paragraph(f'<i>{total_words}</i>', ParagraphStyle('TW', parent=val_style, fontSize=8, fontName='Helvetica-Oblique', alignment=TA_RIGHT))])
    total_table = Table(total_rows, colWidths=[390, 97])
    total_table.setStyle(TableStyle([
        ('ALIGN',(0,0),(-1,-1),'RIGHT'), ('TOPPADDING',(0,0),(-1,-1),4), ('BOTTOMPADDING',(0,0),(-1,-1),4),
        ('LINEABOVE',(0,0),(-1,0), 1.5, base_color), ('LINEBELOW',(0,0),(-1,0), 1.5, base_color),
    ]))
    story.append(total_table)
    story.append(Spacer(1, 6*mm))

    # Payment & Bank
    story.append(Paragraph('Payment Terms:', label_style))
    story.append(Paragraph(pi.payment_terms or '100% T/T in advance', val_style))
    story.append(Spacer(1, 2*mm))
    if pi.bank_info:
        story.append(Paragraph('Bank Information:', label_style))
        story.append(Paragraph(pi.bank_info.replace('\n', '<br/>'), val_style))
        story.append(Spacer(1, 2*mm))

    # Country of Origin
    story.append(Paragraph('<b>Country of Origin: China</b>', label_style))
    story.append(Spacer(1, 6*mm))

    # Signature
    sig_style = ParagraphStyle('Sig', parent=val_style, fontSize=9, alignment=TA_LEFT)
    sig_data = [
        [Paragraph(f'<b>{company_name}</b><br/><br/><br/>_________________________<br/>Date: {datetime.now().strftime("%Y-%m-%d")}', sig_style),
         Paragraph('<b>BUYER:</b><br/><br/><br/>_________________________<br/>', sig_style)],
    ]
    sig_table = Table(sig_data, colWidths=[230, 230])
    sig_table.setStyle(TableStyle([('VALIGN',(0,0),(-1,-1),'TOP'),('LEFTPADDING',(0,0),(-1,-1),0)]))
    story.append(sig_table)

    story.append(Spacer(1, 3*mm))
    story.append(HRFlowable(width="100%", thickness=0.5, color=HexColor('#cccccc'), spaceAfter=2*mm))
    story.append(Paragraph(f'<i>This is a computer-generated Proforma Invoice. For questions, contact {COMPANY_INFO["email"]}.</i>',
        ParagraphStyle('Disc', parent=val_style, fontSize=7, textColor=grey, alignment=TA_CENTER)))

    doc.build(story, onFirstPage=_draw_page_template, onLaterPages=_draw_page_template)
    return filename
