"""
Supplier Statement PDF Generator — 供应商对账单
"""
import os
from datetime import datetime
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.colors import HexColor, black, grey
from reportlab.lib.enums import TA_LEFT, TA_CENTER, TA_RIGHT
from reportlab.platypus import (
    SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer, HRFlowable
)

from pdf_generator import _CJK_FONT_NAME, _FONT, _FONT_BOLD, COMPANY_INFO


def generate_supplier_statement(supplier, procs, total_proc, output_path):
    """Generate a supplier statement PDF (对账单)."""
    doc = SimpleDocTemplate(
        output_path, pagesize=A4,
        leftMargin=20*mm, rightMargin=20*mm,
        topMargin=15*mm, bottomMargin=20*mm,
        title=f'Supplier Statement — {supplier.name}'
    )

    story = []
    c = '#1a5276'

    # ── Helper Styles ──
    s_title = ParagraphStyle('title', fontName=_FONT, fontSize=18, leading=22, textColor=HexColor(c), alignment=TA_CENTER, spaceAfter=2*mm)
    s_sub = ParagraphStyle('sub', fontName=_FONT, fontSize=10, leading=14, textColor=grey, alignment=TA_CENTER, spaceAfter=6*mm)
    s_hdr = ParagraphStyle('hdr', fontName=_FONT, fontSize=9, leading=12, textColor=black)
    s_cell = ParagraphStyle('cell', fontName=_FONT, fontSize=8, leading=11)
    s_rt = ParagraphStyle('rt', fontName=_FONT, fontSize=8, leading=11, alignment=TA_RIGHT)

    # ── Title ──
    story.append(Paragraph(f'Supplier Statement (对账单)', s_title))
    story.append(Paragraph(f'{COMPANY_INFO["name"]}', s_sub))

    # ── Supplier Info ──
    info_data = [
        [Paragraph('<b>Supplier:</b>', s_hdr), Paragraph(f'{supplier.name}', s_hdr),
         Paragraph('<b>Date:</b>', s_hdr), Paragraph(f'{datetime.now().strftime("%Y-%m-%d")}', s_hdr)],
        [Paragraph('<b>Contact:</b>', s_hdr), Paragraph(f'{supplier.contact_person or "-"}', s_hdr),
         Paragraph('<b>Phone:</b>', s_hdr), Paragraph(f'{supplier.phone or "-"}', s_hdr)],
        [Paragraph('<b>Address:</b>', s_hdr), Paragraph(f'{supplier.address or "-"}', s_hdr),
         Paragraph('<b>Email:</b>', s_hdr), Paragraph(f'{supplier.email or "-"}', s_hdr)],
    ]
    info_table = Table(info_data, colWidths=[50, 120, 40, 120])
    info_table.setStyle(TableStyle([
        ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
        ('TOPPADDING', (0,0), (-1,-1), 2),
        ('BOTTOMPADDING', (0,0), (-1,-1), 2),
        ('LINEBELOW', (0,0), (-1, -1), 0.5, HexColor('#dee2e6')),
    ]))
    story.append(info_table)
    story.append(Spacer(1, 6*mm))

    # ── Summary Cards ──
    story.append(HRFlowable(width="100%", thickness=1, color=HexColor(c)))
    summary_data = [[
        Paragraph(f'<b>Total Procurement Amount</b><br/>¥{total_proc:,.2f}', ParagraphStyle('sm', fontName=_FONT, fontSize=10, leading=14, alignment=TA_CENTER, textColor=HexColor('#0d6efd'))),
        Paragraph(f'<b>Outstanding Balance</b><br/>¥{total_proc:,.2f}', ParagraphStyle('sm2', fontName=_FONT, fontSize=10, leading=14, alignment=TA_CENTER, textColor=HexColor('#dc3545'))),
        Paragraph(f'<b>Total Items</b><br/>{len(procs)}', ParagraphStyle('sm3', fontName=_FONT, fontSize=10, leading=14, alignment=TA_CENTER, textColor=grey)),
    ]]
    sum_table = Table(summary_data, colWidths=[doc.width/3]*3)
    sum_table.setStyle(TableStyle([
        ('ALIGN', (0,0), (-1,-1), 'CENTER'),
        ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
        ('TOPPADDING', (0,0), (-1,-1), 6),
        ('BOTTOMPADDING', (0,0), (-1,-1), 6),
        ('BACKGROUND', (0,0), (-1,-1), HexColor('#f8f9fa')),
    ]))
    story.append(sum_table)
    story.append(Spacer(1, 6*mm))

    # ── Procurement Table ──
    header = [
        Paragraph('<b>PI#</b>', s_hdr),
        Paragraph('<b>Product</b>', s_hdr),
        Paragraph('<b>Date</b>', s_hdr),
        Paragraph('<b>Qty</b>', s_rt),
        Paragraph('<b>Unit Price</b>', s_rt),
        Paragraph('<b>Total</b>', s_rt),
    ]
    rows = [header]
    for p in procs:
        pi_num = p.pi.pi_number if p.pi else f'PI#{p.pi_id}'
        pname = p.pi_item.product.name if p.pi_item and p.pi_item.product else f'Item#{p.pi_item_id}'
        cn = p.pi_item.product.chinese_name if p.pi_item and p.pi_item.product else ''
        name_display = f'{pname}<br/><font color="#888">{cn}</font>' if cn else pname
        date_str = p.procurement_date or '-'
        rows.append([
            Paragraph(pi_num, s_cell),
            Paragraph(name_display, s_cell),
            Paragraph(date_str, s_cell),
            Paragraph(str(p.quantity), s_rt),
            Paragraph(f'¥{p.unit_price:,.2f}', s_rt),
            Paragraph(f'<b>¥{p.total:,.2f}</b>', s_rt),
        ])
    # Total row
    rows.append([
        Paragraph('', s_cell), Paragraph('', s_cell), Paragraph('', s_cell),
        Paragraph('', s_rt), Paragraph('<b>Total:</b>', s_rt),
        Paragraph(f'<b>¥{total_proc:,.2f}</b>', s_rt),
    ])

    tbl = Table(rows, colWidths=[80, 200, 60, 40, 70, 70])
    tbl_style = [
        ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
        ('TOPPADDING', (0,0), (-1,-1), 4),
        ('BOTTOMPADDING', (0,0), (-1,-1), 4),
        ('LEFTPADDING', (0,0), (-1,-1), 4),
        ('RIGHTPADDING', (0,0), (-1,-1), 4),
        ('BACKGROUND', (0,0), (-1,0), HexColor(c)),
        ('TEXTCOLOR', (0,0), (-1,0), HexColor('#ffffff')),
        ('LINEBELOW', (0,0), (-1,-1), 0.5, HexColor('#dee2e6')),
        ('BACKGROUND', (0,-1), (-1,-1), HexColor('#f8f9fa')),
    ]
    # Alternating row colors
    for i in range(1, len(rows)-1):
        if i % 2 == 0:
            tbl_style.append(('BACKGROUND', (0,i), (-1,i), HexColor('#f8f9fa')))
    tbl.setStyle(TableStyle(tbl_style))
    story.append(tbl)

    # ── Footer ──
    story.append(Spacer(1, 10*mm))
    story.append(HRFlowable(width="100%", thickness=1, color=HexColor('#dee2e6')))
    story.append(Paragraph(f'Generated on {datetime.now().strftime("%Y-%m-%d %H:%M")} — {COMPANY_INFO["name"]}',
                           ParagraphStyle('ft', fontName=_FONT, fontSize=7, textColor=grey, alignment=TA_RIGHT)))

    doc.build(story)
    return output_path
