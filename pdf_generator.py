"""
PI (Proforma Invoice) PDF Generator using ReportLab.
Generates A4-sized professional foreign trade PI documents.
"""

import os
import glob
from datetime import datetime
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm, cm
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.colors import HexColor, black, white, grey
from reportlab.lib.enums import TA_LEFT, TA_CENTER, TA_RIGHT
from reportlab.platypus import (
    SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer,
    HRFlowable, Image
)
from reportlab.platypus.doctemplate import PageTemplate, BaseDocTemplate, Frame
from reportlab.pdfgen import canvas
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont


# ── Chinese Font Detection ──────────────────────────────────────────
_CJK_FONT_NAME = 'Helvetica'  # fallback

def _find_cjk_font():
    """Find a CJK-capable font on the system and register it."""
    candidates = [
        # macOS
        '/System/Library/Fonts/STHeiti Light.ttc',
        '/System/Library/Fonts/STHeiti Medium.ttc',
        '/System/Library/Fonts/Hiragino Sans GB.ttc',
        '/System/Library/Fonts/Supplemental/Songti.ttc',
        '/Library/Fonts/Arial Unicode.ttf',
        '/System/Library/Fonts/Supplemental/Arial Unicode.ttf',
        # Linux (NAS)
        '/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc',
        '/usr/share/fonts/truetype/wqy/wqy-microhei.ttc',
        '/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc',
        '/usr/share/fonts/truetype/noto/NotoSansCJK-Regular.ttc',
        '/usr/share/fonts/truetype/droid/DroidSansFallbackFull.ttf',
        '/usr/share/fonts/truetype/arphic/uming.ttc',
        # Windows
        'C:/Windows/Fonts/msyh.ttc',
        'C:/Windows/Fonts/simsun.ttc',
    ]
    for path in candidates:
        if os.path.exists(path):
            try:
                # Try subfont index 0 for .ttc files
                pdfmetrics.registerFont(TTFont('CJK', path, subfontIndex=0))
                return 'CJK'
            except:
                try:
                    pdfmetrics.registerFont(TTFont('CJK', path))
                    return 'CJK'
                except:
                    continue
    # Try glob for any .ttc/.ttf with CJK in name
    for d in ['/usr/share/fonts', '/System/Library/Fonts', '/Library/Fonts']:
        for f in glob.glob(os.path.join(d, '**', '*.tt*'), recursive=True):
            name = os.path.basename(f).lower()
            if any(k in name for k in ['wqy', 'noto', 'cjk', 'chinese', 'hei', 'song', 'ming', 'kai', 'unicode', 'arialuni']):
                try:
                    pdfmetrics.registerFont(TTFont('CJK', f))
                    return 'CJK'
                except:
                    pass
    return 'Helvetica'

_CJK_FONT_NAME = _find_cjk_font()
_FONT = _CJK_FONT_NAME if _CJK_FONT_NAME != 'Helvetica' else 'Helvetica'
_FONT_BOLD = 'Helvetica-Bold' if _FONT == 'Helvetica' else _FONT  # CJK fonts use same name for bold


# ── Company Info (editable) ──────────────────────────────────────────
COMPANY_INFO = {
    'name': 'CHANGZHOU KLISTA INTERNATIONAL TRADE CO., LTD.',
    'address': 'No. 158 Jinchuang Road, Yaoguan Town, Changzhou City, China',
    'phone': '+86 17712333882',
    'email': 'fantastic10086@gmail.com',
    'website': '',
}

BRANDS = {
    'klista':  'CHANGZHOU KLISTA INTERNATIONAL TRADE CO., LTD.',
    'qisuo':   'Changzhou QISUO Welding and Cutting Equipment Co., Ltd.',
}

# A4 dimensions
PAGE_W, PAGE_H = A4  # (595.27, 841.89) points


def _draw_page_template(canvas: canvas.Canvas, doc):
    """Draw header/footer on every page."""
    canvas.saveState()

    # ── Header background bar ──
    canvas.setFillColor(HexColor('#1a3a5c'))
    canvas.rect(20 * mm, PAGE_H - 30 * mm, PAGE_W - 40 * mm, 18 * mm, fill=1, stroke=0)

    # Company name in header (use CJK font for Chinese support)
    canvas.setFillColor(white)
    canvas.setFont(_FONT_BOLD, 16)
    canvas.drawString(27 * mm, PAGE_H - 19 * mm, getattr(doc, 'company_name', COMPANY_INFO['name']))

    # Company address in header (centered)
    canvas.setFont(_FONT, 7)
    canvas.setFillColor(HexColor('#cccccc'))
    canvas.drawCentredString(PAGE_W / 2, PAGE_H - 26 * mm, COMPANY_INFO['address'])

    # ── Footer ──
    canvas.setFillColor(grey)
    canvas.setFont(_FONT, 7)
    canvas.drawCentredString(PAGE_W / 2, 15 * mm, f"Page {doc.page}")

    # Footer line
    canvas.setStrokeColor(HexColor('#1a3a5c'))
    canvas.setLineWidth(0.5)
    canvas.line(20 * mm, 22 * mm, PAGE_W - 20 * mm, 22 * mm)

    canvas.restoreState()


def currency_symbol(cur):
    return '¥' if cur == 'RMB' else '$'

def currency_label(cur):
    return 'RMB' if cur == 'RMB' else 'USD'

def generate_pi_pdf(pi, output_dir, salesperson_info=None):
    """
    Generate a PI PDF for the given PI object.

    Args:
        pi: PI model instance with items and customer loaded.
        output_dir: Absolute path to the pdf/ directory.
        salesperson_info: Optional dict with 'phone' and 'email' keys.
    """
    if salesperson_info is None:
        salesperson_info = {}
    cur = getattr(pi, 'currency', 'USD') or 'USD'
    sym = currency_symbol(cur)
    cur_label = currency_label(cur)
    filename = f"{pi.pi_number}.pdf"
    filepath = os.path.join(output_dir, filename)

    # ── Document setup ──
    doc = BaseDocTemplate(
        filepath,
        pagesize=A4,
        leftMargin=20 * mm,
        rightMargin=20 * mm,
        topMargin=32 * mm,
        bottomMargin=30 * mm,
        title=f'Proforma Invoice {pi.pi_number}',
        author=COMPANY_INFO['name'],
    )

    # Add page template with header/footer
    frame = Frame(
        doc.leftMargin, doc.bottomMargin,
        doc.width, doc.height,
        id='normal'
    )
    doc.addPageTemplates([PageTemplate(id='main', frames=frame, onPage=_draw_page_template)])
    doc._pageTemplates = doc.pageTemplates  # compatibility

    # Set company name based on brand (allow override from export_pdf)
    override_name = getattr(pi, '_company_name_override', None)
    override_addr = getattr(pi, '_company_addr_override', None)
    if override_name:
        company_name = override_name
        COMPANY_INFO['address'] = override_addr or COMPANY_INFO['address']
    else:
        brand = getattr(pi, 'company', 'klista') or 'klista'
        company_name = BRANDS.get(brand, BRANDS['klista'])
    doc.company_name = company_name

    # ── Styles ──
    styles = getSampleStyleSheet()
    title_style = ParagraphStyle(
        'PITitle', parent=styles['Title'],
        fontSize=22, fontName=_FONT_BOLD, textColor=HexColor('#1a3a5c'),
        spaceAfter=4 * mm, alignment=TA_CENTER,
    )
    section_style = ParagraphStyle(
        'SectionLabel', parent=styles['Normal'],
        fontSize=10, fontName=_FONT_BOLD, textColor=HexColor('#1a3a5c'),
        spaceAfter=1 * mm, spaceBefore=4 * mm,
    )
    info_style = ParagraphStyle(
        'InfoValue', parent=styles['Normal'],
        fontSize=10, fontName=_FONT, spaceAfter=1 * mm,
    )
    table_header_style = ParagraphStyle(
        'TblHeader', parent=styles['Normal'],
        fontSize=10, fontName=_FONT_BOLD, textColor=white, alignment=TA_CENTER,
    )
    table_cell_style = ParagraphStyle(
        'TblCell', parent=styles['Normal'],
        fontSize=10, fontName=_FONT, alignment=TA_CENTER,
    )
    table_cell_left = ParagraphStyle(
        'TblCellLeft', parent=table_cell_style,
        alignment=TA_LEFT,
    )
    amount_style = ParagraphStyle(
        'AmountRight', parent=table_cell_style,
        alignment=TA_RIGHT,
    )

    # ── Build story ──
    story = []

    # Title
    story.append(Paragraph('PROFORMA INVOICE', title_style))
    story.append(Spacer(1, 3 * mm))

    # Separator line
    story.append(HRFlowable(width="100%", thickness=1.5, color=HexColor('#1a3a5c'), spaceAfter=4 * mm))

    # ── PI Info & Customer Info (side-by-side table) ──
    pi_info_data = [
        [Paragraph('<b>PI Number:</b>', info_style), Paragraph(pi.pi_number, info_style)],
        [Paragraph('<b>Date:</b>', info_style),
         Paragraph(pi.issue_date.strftime('%Y-%m-%d') if pi.issue_date else '', info_style)],
    ]
    # Append salesperson rows to PI info column
    if pi.salesperson:
        pi_info_data.append([Paragraph('<b>Salesperson:</b>', info_style), Paragraph(pi.salesperson, info_style)])
        if salesperson_info.get('phone'):
            pi_info_data.append([Paragraph('<b>Tel:</b>', info_style), Paragraph(salesperson_info['phone'], info_style)])
        if salesperson_info.get('email'):
            pi_info_data.append([Paragraph('<b>Email:</b>', info_style), Paragraph(salesperson_info['email'], info_style)])
    pi_info_table = Table(pi_info_data, colWidths=[70, 140])
    pi_info_table.setStyle(TableStyle([
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('LEFTPADDING', (0, 0), (-1, -1), 0),
        ('RIGHTPADDING', (0, 0), (-1, -1), 0),
        ('TOPPADDING', (0, 0), (-1, -1), 0),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 2),
    ]))

    customer = pi.customer
    customer_info_data = [
        [Paragraph('<b>To / Buyer:</b>', info_style), Paragraph(customer.name or '', info_style)],
        [Paragraph('<b>Contact:</b>', info_style), Paragraph(customer.contact_person or '', info_style)],
        [Paragraph('<b>Country:</b>', info_style), Paragraph(customer.country or '', info_style)],
        [Paragraph('<b>Email:</b>', info_style), Paragraph(customer.email or '', info_style)],
        [Paragraph('<b>Phone:</b>', info_style), Paragraph(customer.phone or '', info_style)],
        [Paragraph('<b>Address:</b>', info_style), Paragraph(customer.address or '', info_style)],
    ]
    customer_info_table = Table(customer_info_data, colWidths=[70, 250])
    customer_info_table.setStyle(TableStyle([
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('LEFTPADDING', (0, 0), (-1, -1), 0),
        ('RIGHTPADDING', (0, 0), (-1, -1), 0),
        ('TOPPADDING', (0, 0), (-1, -1), 0),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 2),
    ]))

    # Two blocks side by side — indent left block to align with header company name (27mm)
    top_table = Table([
        [pi_info_table, customer_info_table]
    ], colWidths=[210, 340])
    top_table.setStyle(TableStyle([
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('LEFTPADDING', (0, 0), (0, 0), 10 * mm),
        ('LEFTPADDING', (1, 0), (1, 0), 4 * mm),
        ('RIGHTPADDING', (0, 0), (-1, -1), 0),
    ]))

    story.append(top_table)

    story.append(Spacer(1, 5 * mm))

    # ── Product Table ──
    story.append(Paragraph('ITEM DETAILS', section_style))
    story.append(Spacer(1, 2 * mm))

    # Table header
    upload_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'static', 'uploads')
    header = [
        Paragraph('No.', table_header_style),
        Paragraph('Image', table_header_style),
        Paragraph('Product Code', table_header_style),
        Paragraph('Description', table_header_style),
        Paragraph('Specification', table_header_style),
        Paragraph('Qty', table_header_style),
        Paragraph(f'Unit Price ({cur_label})', table_header_style),
        Paragraph(f'Amount ({cur_label})', table_header_style),
    ]
    col_widths = [22, 35, 58, 120, 65, 40, 66, 66]

    table_data = [header]
    for i, item in enumerate(pi.items, 1):
        # Product image
        img_cell = Paragraph('', table_cell_style)
        if item.product and item.product.image:
            img_path = os.path.join(upload_dir, item.product.image)
            if os.path.exists(img_path):
                try:
                    img_cell = Image(img_path, width=10*mm, height=10*mm)
                except:
                    pass
        row = [
            Paragraph(str(i), table_cell_style),
            img_cell,
            Paragraph(item.product.product_code if item.product else '', table_cell_style),
            Paragraph(item.product.name if item.product else '', table_cell_left),
            Paragraph(item.product.specification if item.product else '', table_cell_style),
            Paragraph(str(item.quantity), amount_style),
            Paragraph(f'{sym}{item.unit_price:,.2f}', amount_style),
            Paragraph(f'{sym}{item.amount:,.2f}', amount_style),
        ]
        table_data.append(row)

    prod_table = Table(table_data, colWidths=col_widths, repeatRows=1)
    base_color = HexColor('#1a3a5c')
    light_bg = HexColor('#f0f4f8')

    table_style_cmds = [
        # Header
        ('BACKGROUND', (0, 0), (-1, 0), base_color),
        ('TEXTCOLOR', (0, 0), (-1, 0), white),
        ('FONTNAME', (0, 0), (-1, 0), _FONT_BOLD),
        ('FONTSIZE', (0, 0), (-1, 0), 10),
        # Grid
        ('GRID', (0, 0), (-1, -1), 0.5, HexColor('#cccccc')),
        ('LINEBELOW', (0, 0), (-1, 0), 1, base_color),
        # Alignment
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('TOPPADDING', (0, 0), (-1, -1), 5),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 5),
        ('LEFTPADDING', (0, 0), (-1, -1), 6),
        ('RIGHTPADDING', (0, 0), (-1, -1), 6),
    ]
    # Alternate row colors
    for row_idx in range(1, len(table_data)):
        if row_idx % 2 == 0:
            table_style_cmds.append(('BACKGROUND', (0, row_idx), (-1, row_idx), light_bg))

    prod_table.setStyle(TableStyle(table_style_cmds))
    story.append(prod_table)

    story.append(Spacer(1, 5 * mm))

    # ── Total Section ──
    # Align with product table: the Amount column spans col 5-7 in the footer
    # Table full width = sum(col_widths) = 472; Amount col at offset 406, width 66
    total = pi.total_amount
    shipping_cost = getattr(pi, 'shipping_cost', 0.0) or 0.0
    tbl_w = sum(col_widths)  # 472

    right_label_style = ParagraphStyle('RLabel', parent=info_style, fontSize=10,
                                        fontName=_FONT, textColor=base_color, alignment=TA_RIGHT)
    right_value_style = ParagraphStyle('RValue', parent=info_style, fontSize=10,
                                        fontName=_FONT, textColor=base_color, alignment=TA_RIGHT)
    right_total_label = ParagraphStyle('RTLabel', parent=info_style, fontSize=13,
                                        fontName=_FONT_BOLD, textColor=base_color, alignment=TA_RIGHT)
    right_total_value = ParagraphStyle('RTValue', parent=info_style, fontSize=13,
                                        fontName=_FONT_BOLD, textColor=base_color, alignment=TA_RIGHT)

    # Adjustment row (if non-zero)
    if abs(shipping_cost) > 0.001:
        # Use a table that matches the product table width, with the value in the rightmost columns
        spacer_w = tbl_w - 140 - 66  # space + label + value columns
        shipping_data = [
            ['', Paragraph(f'Subtotal ({cur_label}):', right_label_style),
             Paragraph(f'{sym}{total:,.2f}', right_value_style)],
            ['', Paragraph(f'Adj. / Cost:', right_label_style),
             Paragraph(f'{sym}{shipping_cost:,.2f}', right_value_style)],
        ]
        # Add shipping note as a separate row if present
        shipping_note = getattr(pi, 'shipping_note', '') or ''
        if shipping_note:
            shipping_data.append(['', Paragraph(f'({shipping_note})', ParagraphStyle(
                'ShipNote', parent=info_style, fontSize=9, fontName=_FONT,
                textColor=grey, alignment=TA_RIGHT,
            )), ''])
        ship_table = Table(shipping_data, colWidths=[spacer_w, 140, 66])
        ship_table.setStyle(TableStyle([
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ('TOPPADDING', (0, 0), (-1, -1), 2),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 2),
        ]))
        story.append(ship_table)

    spacer_w2 = tbl_w - 140 - 66
    total_data = [
        ['', Paragraph(f'<b>TOTAL AMOUNT ({cur_label}):</b>', right_total_label),
         Paragraph(f'<b>{sym}{total + shipping_cost:,.2f}</b>', right_total_value)],
    ]
    total_table = Table(total_data, colWidths=[spacer_w2, 140, 66])
    total_table.setStyle(TableStyle([
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('TOPPADDING', (0, 0), (-1, -1), 4),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
        ('LINEABOVE', (0, 0), (-1, 0), 1, base_color),
    ]))
    story.append(total_table)

    story.append(Spacer(1, 5 * mm))

    # ── Payment & Bank Info ──
    story.append(Paragraph('PAYMENT &amp; BANK DETAILS', section_style))
    story.append(Spacer(1, 2 * mm))

    bank_info = pi.bank_info or 'Please contact us for bank details.'
    payment_terms = pi.payment_terms or 'T/T 30% deposit, 70% before shipment'

    payment_data = [
        [Paragraph('<b>Payment Terms:</b>', info_style), Paragraph(payment_terms, info_style)],
        [Paragraph('<b>Bank Info:</b>', info_style), Paragraph(bank_info.replace('\n', '<br/>'), info_style)],
    ]
    pay_table = Table(payment_data, colWidths=[110, 430])
    pay_table.setStyle(TableStyle([
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('LEFTPADDING', (0, 0), (-1, -1), 0),
        ('TOPPADDING', (0, 0), (-1, -1), 2),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 2),
    ]))
    story.append(pay_table)

    # ── Notes ──
    if pi.notes and pi.notes.strip():
        story.append(Spacer(1, 6 * mm))
        story.append(Paragraph('NOTES', section_style))
        story.append(Spacer(1, 2 * mm))
        story.append(Paragraph(pi.notes.strip().replace('\n', '<br/>'), info_style))

    story.append(Spacer(1, 12 * mm))

    # ── Signature Area ──
    sig_data = [
        [
            Paragraph('<b>Issued By:</b><br/><br/><br/>_________________________<br/>'
                      f'{COMPANY_INFO["name"]}<br/>'
                      f'Date: {datetime.now().strftime("%Y-%m-%d")}',
                      ParagraphStyle('SigLeft', parent=info_style, fontSize=10)),
            Paragraph('<b>Authorized Signature &amp; Stamp:</b><br/><br/><br/>'
                      '_________________________<br/>'
                      '<i>(Company Chop / Signature)</i>',
                      ParagraphStyle('SigRight', parent=info_style, fontSize=10, alignment=TA_RIGHT)),
        ]
    ]
    sig_table = Table(sig_data, colWidths=[250, 250])
    sig_table.setStyle(TableStyle([
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('LEFTPADDING', (0, 0), (-1, -1), 0),
        ('RIGHTPADDING', (0, 0), (-1, -1), 0),
    ]))
    story.append(sig_table)

    story.append(Spacer(1, 6 * mm))
    story.append(HRFlowable(width="100%", thickness=0.5, color=HexColor('#cccccc'), spaceAfter=2 * mm))
    story.append(Paragraph(
        '<i>This is a computer-generated Proforma Invoice. For any questions, '
        f'please contact {COMPANY_INFO["email"]}.</i>',
        ParagraphStyle('Disclaimer', parent=info_style, fontSize=7, textColor=grey, alignment=TA_CENTER)
    ))

    # ── Build PDF ──
    doc.build(story)

    return filename
