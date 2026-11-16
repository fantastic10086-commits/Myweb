"""Spreadsheet export of the same permission-scoped receipt rows as the page."""
from io import BytesIO
from datetime import timedelta
from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill, Alignment
from openpyxl.utils import get_column_letter


def export_receipts(details, date_from='', date_to='', salespeople=(), actual_ids=()):
    wb=Workbook();ws=wb.active;ws.title='实际到账明细'
    headers=['PI编号','客户','业务员','统计到账日期','日期依据','回款流水号','币种','订单总金额','本笔实收金额','手续费','本笔折合USD','业绩换算因子','汇率参考日期','汇率来源','到账账户','登记时间 北京时间','备注','回款状态']
    ws.append(headers)
    for r in details:
        pi,p=r.pi,r.payment
        # Do not infer actual arrival dates from registration timestamps.
        values=[pi.pi_number,pi.customer.name if pi.customer else '',pi.salesperson or '',r.received_on,
                '实际到账日期' if p.id in actual_ids else '登记日期',p.order_no or '',pi.currency or 'USD',
                pi.grand_total,p.amount,p.fee or 0,r.amount_usd,p.performance_usd_rate,
                p.performance_reference_date or '',p.performance_source or '历史汇率',p.receiving_account_name or '',
                p.created_at+timedelta(hours=8) if p.created_at else None,p.note or '',
                '已付清' if pi.paid else '部分回款' if pi.received_amount else '未回款']
        ws.append(values)
        for cell in ws[ws.max_row]:
            if isinstance(cell.value,str):cell.data_type='s'
        ws.cell(ws.max_row,4).number_format='yyyy-mm-dd'
        ws.cell(ws.max_row,16).number_format='yyyy-mm-dd hh:mm'
        for col in (8,9,10,11):ws.cell(ws.max_row,col).number_format='#,##0.00'
        ws.cell(ws.max_row,12).number_format='0.00000000'
    ws.auto_filter.ref=f'A1:R{ws.max_row}';ws.freeze_panes='A2'
    ws.append(['合计 折合USD']+[None]*9+[sum(r.amount_usd for r in details)])
    ws.cell(ws.max_row,11).number_format='#,##0.00'
    for cell in ws[1]:cell.font=Font(bold=True,color='FFFFFF');cell.fill=PatternFill('solid',fgColor='1D3F62')
    widths=[23,32,18,18,18,36,10,20,20,16,20,20,18,23,30,24,40,16]
    for i,width in enumerate(widths,1):ws.column_dimensions[get_column_letter(i)].width=width
    for row in ws:
        for c in row:c.alignment=Alignment(vertical='top',wrap_text=True)
    info=wb.create_sheet('筛选说明')
    for row in [('到账开始日期',date_from or '不限'),('到账结束日期',date_to or '不限'),('业务员','、'.join(salespeople) or '当前权限下全部'),('明细笔数',len(details)),('说明','按笔导出，手续费独立列示。不同币种原币不相加；合计为本笔实收折合USD。登记日期仅用于未填写实际到账日期的历史记录。')]:
        info.append(row)
        for c in info[info.max_row]:
            if isinstance(c.value,str):c.data_type='s'
    info.column_dimensions['A'].width=22;info.column_dimensions['B'].width=95
    for row in info:
        for c in row:c.alignment=Alignment(wrap_text=True,vertical='top')
    output=BytesIO();wb.save(output);output.seek(0);return output
