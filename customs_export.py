"""Create the five-sheet customs package and its immutable data snapshot."""

from collections import OrderedDict
from copy import copy
from io import BytesIO
from pathlib import Path

from openpyxl import load_workbook
from openpyxl.styles import Alignment
from openpyxl.worksheet.page import PageMargins


NAVY = '1F4E78'
CUSTOMS_TEMPLATE_PATH = (
    Path(__file__).resolve().parent / 'assets' / 'customs_declaration_template.xlsx'
)


def _text(value):
    if value is None:
        return ''
    if hasattr(value, 'isoformat'):
        return value.isoformat()
    return str(value)


def _unique(values):
    return '；'.join(dict.fromkeys(
        _text(value).strip() for value in values if _text(value).strip()
    ))


def build_customs_snapshot(pi, form_data):
    """Capture every value used by the export so confirmed files stay stable."""
    groups = OrderedDict()
    for item in pi.items:
        product = item.product
        key = (
            product.customs_hs_code,
            product.customs_name_cn,
            product.customs_name_en,
            product.customs_unit,
        )
        group = groups.setdefault(key, {
            'hs_code': product.customs_hs_code,
            'name_cn': product.customs_name_cn,
            'name_en': product.customs_name_en,
            'unit': product.customs_unit,
            'quantity': 0,
            'amount': 0.0,
            'product_details': [],
            'brand_type': [],
            'preferential': [],
            'purpose': [],
            'brand': [],
            'origin_country': [],
            'domestic_source': [],
            'tax_exemption': [],
            'elements': [],
        })
        group['quantity'] += int(item.quantity or 0)
        group['amount'] += float(item.amount or 0)
        detail = ' / '.join(
            value for value in (
                product.name, product.product_code, product.specification,
            ) if value
        )
        if detail:
            group['product_details'].append(detail)
        for key_name, field_name in (
            ('brand_type', 'customs_brand_type'),
            ('preferential', 'customs_preferential'),
            ('purpose', 'customs_purpose'),
            ('brand', 'customs_brand'),
            ('origin_country', 'customs_origin_country'),
            ('domestic_source', 'customs_domestic_source'),
            ('tax_exemption', 'customs_tax_exemption'),
            ('elements', 'customs_elements'),
        ):
            group[key_name].append(getattr(product, field_name, '') or '')

    normalized_groups = []
    for group in groups.values():
        for key_name in (
            'product_details', 'brand_type', 'preferential', 'purpose',
            'brand', 'origin_country', 'domestic_source', 'tax_exemption',
            'elements',
        ):
            group[key_name] = _unique(group[key_name])
        group['amount'] = round(group['amount'], 2)
        group['unit_price'] = round(
            group['amount'] / group['quantity'], 6
        ) if group['quantity'] else 0
        normalized_groups.append(group)

    packing_list = pi.packing_list
    boxes = []
    for box in packing_list.boxes if packing_list else []:
        boxes.append({
            'box_no': box.box_no,
            'net_weight': float(box.net_weight or 0),
            'gross_weight': float(box.gross_weight or 0),
            'length_cm': float(box.length_cm or 0),
            'width_cm': float(box.width_cm or 0),
            'height_cm': float(box.height_cm or 0),
            'volume_cbm': float(box.volume_cbm or 0),
            'shipping_mark': box.shipping_mark or '',
            'note': box.note or '',
            'items': [
                {
                    'product_name': item.product_name,
                    'product_code': item.product_code or '',
                    'specification': item.specification or '',
                    'quantity': int(item.quantity or 0),
                    'unit': (
                        item.pi_item.product.customs_unit
                        if item.pi_item and item.pi_item.product
                        else '件'
                    ) or '件',
                    'note': item.note or '',
                }
                for item in box.items
            ],
        })

    company_name = (
        'Changzhou Qisuo Welding And Cutting Equipment Co., Ltd.'
        if (pi.company or '').lower() == 'qisuo'
        else 'CHANGZHOU KLISTA INTERNATIONAL TRADE CO., LTD.'
    )
    company_name_cn = (
        company_name
        if (pi.company or '').lower() == 'qisuo'
        else '常州市克利斯达国际贸易有限公司'
    )
    return {
        'pi_number': pi.pi_number,
        'issue_date': _text(pi.issue_date),
        'currency': (pi.currency or 'USD').upper(),
        'salesperson': pi.salesperson or '',
        'payment_terms': pi.payment_terms or '',
        'price_terms': pi.price_terms or '',
        'delivery_time': pi.delivery_time or '',
        'bank_info': pi.bank_info or '',
        'company_name': company_name,
        'company_name_cn': company_name_cn,
        'customer': {
            'name': pi.customer.name,
            'contact_person': pi.customer.contact_person or '',
            'country': pi.customer.country or '',
            'address': pi.customer.address or '',
            'email': pi.customer.email or '',
            'phone': pi.customer.phone or '',
        },
        'product_total': round(sum(
            group['amount'] for group in normalized_groups
        ), 2),
        'other_charges': round(float(pi.other_charges or 0), 2),
        'other_charges_treatment': 'exclude',
        'customs': {
            key: _text(value) for key, value in form_data.items()
            if not key.startswith('_')
        },
        'groups': normalized_groups,
        'boxes': boxes,
    }


def _copy_row_layout(source_ws, source_row, target_ws, target_row, max_column):
    """Copy a template row's style without carrying its sample values."""
    target_ws.row_dimensions[target_row].height = (
        source_ws.row_dimensions[source_row].height
    )
    for column in range(1, max_column + 1):
        source = source_ws.cell(source_row, column)
        target = target_ws.cell(target_row, column)
        target._style = copy(source._style)
        target.alignment = copy(source.alignment)
        target.protection = copy(source.protection)


def _clear_row(ws, row, max_column):
    for column in range(1, max_column + 1):
        ws.cell(row, column).value = None


def _unmerge_from(ws, first_row):
    for merged in list(ws.merged_cells.ranges):
        if merged.min_row >= first_row:
            ws.unmerge_cells(str(merged))


def _setup_print(ws, last_column, last_row, landscape=False):
    ws.sheet_view.showGridLines = False
    ws.sheet_properties.pageSetUpPr.fitToPage = True
    ws.page_setup.paperSize = ws.PAPERSIZE_A4
    ws.page_setup.orientation = (
        ws.ORIENTATION_LANDSCAPE if landscape else ws.ORIENTATION_PORTRAIT
    )
    ws.page_setup.fitToWidth = 1
    ws.page_setup.fitToHeight = 0
    ws.print_area = f'A1:{last_column}{last_row}'
    ws.page_margins = PageMargins(
        left=0.25, right=0.25, top=0.35, bottom=0.35,
        header=0.15, footer=0.15,
    )


def _move_stamp(ws, anchor, width=120, height=108):
    """Keep the supplied company chop, but prevent it creating extra pages."""
    for image in ws._images:
        image.width = width
        image.height = height
        image.anchor = anchor


def _customer_block(customer):
    parts = []
    for value in (
        customer.get('name', ''), customer.get('contact_person', ''),
        customer.get('address', ''),
    ):
        value = _text(value).strip()
        if value and value not in parts:
            parts.append(value)
    return '\n'.join(parts)


def _location(port, country):
    values = []
    for value in (port, country):
        value = _text(value).strip()
        if value and value not in values:
            values.append(value)
    return ', '.join(values)


def _chinese_number(number):
    labels = '一二三四五六七八九十'
    return labels[number - 1] if 1 <= number <= len(labels) else str(number)


def _populate_declaration(workbook, donor, snapshot):
    ws = workbook['报关单']
    source = donor['报关单']
    groups = snapshot['groups']
    boxes = snapshot['boxes']
    customs = snapshot['customs']
    customer = snapshot['customer']

    values = {
        'A4': snapshot['company_name_cn'],
        'H4': customs.get('export_customs', ''),
        'J4': customs.get('export_date', ''),
        'L4': customs.get('declaration_date', ''),
        'A6': customer['name'],
        'H6': customs.get('transport_mode', ''),
        'J6': customs.get('vehicle_voyage', ''),
        'L6': customs.get('bill_no', ''),
        'A8': snapshot['company_name_cn'],
        'H8': customs.get('supervision_mode', ''),
        'J8': customs.get('exemption_nature', ''),
        'L8': customs.get('license_no', ''),
        'A10': snapshot['pi_number'],
        'D10': customs.get('trade_country', ''),
        'H10': customs.get('destination_country', ''),
        'L10': customs.get('destination_port', ''),
        'M10': customs.get('departure_port', ''),
        'A12': customs.get('packing_type', ''),
        'D12': len(boxes),
        'E12': round(sum(box['gross_weight'] for box in boxes), 3),
        'H12': round(sum(box['net_weight'] for box in boxes), 3),
        'I12': snapshot['price_terms'],
        'J12': 0,
        'L12': 0,
        'N12': 0,
        'A14': customs.get('accompanying_documents', ''),
        'A16': customs.get('marks_notes', ''),
    }
    for coordinate, value in values.items():
        ws[coordinate] = value

    _unmerge_from(ws, 17)
    ws.delete_rows(18, 3)
    detail_count = max(1, len(groups))
    ws.insert_rows(18, detail_count)
    for offset in range(detail_count):
        row = 18 + offset
        _copy_row_layout(source, 18, ws, row, 14)
        _clear_row(ws, row, 14)
    for number, group in enumerate(groups, 1):
        row = 17 + number
        row_values = [
            number, group['hs_code'], group['name_cn'],
            group['product_details'], group['quantity'], '', group['unit'],
            group['unit_price'], group['amount'], snapshot['currency'],
            group['origin_country'], customs.get('destination_country', ''),
            group['domestic_source'], group['tax_exemption'],
        ]
        for column, value in enumerate(row_values, 1):
            ws.cell(row, column, value)
        ws.cell(row, 5).number_format = '#,##0'
        ws.cell(row, 8).number_format = '#,##0.000000'
        ws.cell(row, 9).number_format = '#,##0.00'

    total_row = 18 + detail_count
    footer_row = total_row + 1
    declaration_row = total_row + 2
    for source_row, target_row in (
        (21, total_row), (22, footer_row), (23, declaration_row),
    ):
        _copy_row_layout(source, source_row, ws, target_row, 14)
        _clear_row(ws, target_row, 14)
    ws.cell(total_row, 3, '合计')
    ws.cell(total_row, 5, sum(group['quantity'] for group in groups))
    ws.cell(total_row, 6, round(sum(box['net_weight'] for box in boxes), 3))
    ws.cell(total_row, 9, snapshot['product_total'])
    ws.cell(total_row, 9).number_format = '#,##0.00'
    for column, value in (
        (1, '特殊关系确认：'), (4, '价格影响确认：'),
        (8, '支付特许权使用费确认：'), (12, '自报自缴：'),
    ):
        ws.cell(footer_row, column, value)
    for column, value in (
        (1, '申报人员'),
        (2, customs.get('declaration_agent', '')),
        (3, '申报人员证号'), (4, '电话'),
        (8, '兹申明对以上内容承担如实申报、依法纳税之法律责任'),
        (11, '海关批注及签章'),
    ):
        ws.cell(declaration_row, column, value)
    _move_stamp(ws, f'K{max(total_row, declaration_row - 1)}', 105, 94)
    _setup_print(ws, 'N', declaration_row + 2, landscape=True)


def _prepare_five_column_detail_sheet(ws, source, detail_count):
    _unmerge_from(ws, 16)
    ws.delete_rows(17, 7)
    rows_to_add = detail_count + 4
    ws.insert_rows(17, rows_to_add)
    for offset in range(detail_count):
        _copy_row_layout(source, 17, ws, 17 + offset, 5)
        _clear_row(ws, 17 + offset, 5)
    total_row = 18 + detail_count
    footer_row = 20 + detail_count
    _copy_row_layout(source, 21, ws, total_row, 5)
    _copy_row_layout(source, 23, ws, footer_row, 5)
    _clear_row(ws, total_row, 5)
    _clear_row(ws, footer_row, 5)
    return total_row, footer_row


def _populate_invoice(workbook, donor, snapshot):
    ws = workbook['发票１']
    source = donor['发票１']
    groups = snapshot['groups']
    boxes = snapshot['boxes']
    customs = snapshot['customs']
    customer = snapshot['customer']
    detail_count = max(1, len(groups))
    total_row, footer_row = _prepare_five_column_detail_sheet(
        ws, source, detail_count
    )
    ws.title = '发票'
    ws['A1'] = snapshot['company_name_cn']
    ws['A2'] = snapshot['company_name']
    ws['A6'] = _customer_block(customer)
    ws['D6'] = snapshot['pi_number']
    ws['D7'] = snapshot['issue_date']
    ws['D8'] = snapshot['price_terms']
    ws['B11'] = _location(customs.get('departure_port', ''), 'China')
    ws['D11'] = _location(
        customs.get('destination_port', ''),
        customs.get('destination_country', ''),
    )
    ws['B14'] = 'China'
    ws['D14'] = snapshot['currency']
    ws['D16'] = f"单价\nUnit Price ({snapshot['currency']})"
    ws['E16'] = f"总金额\nAmount ({snapshot['currency']})"
    for number, group in enumerate(groups, 1):
        row = 16 + number
        description = '\n'.join(filter(None, (
            group['name_en'], group['product_details'],
        )))
        for column, value in enumerate((
            number, description, group['quantity'],
            group['unit_price'], group['amount'],
        ), 1):
            ws.cell(row, column, value)
        ws.cell(row, 3).number_format = '#,##0'
        ws.cell(row, 4).number_format = '#,##0.000000'
        ws.cell(row, 5).number_format = '#,##0.00'
    ws.merge_cells(start_row=total_row, start_column=1, end_row=total_row, end_column=3)
    ws.cell(total_row, 1, 'TOTAL:')
    ws.cell(total_row, 4, snapshot['currency'])
    ws.cell(total_row, 5, snapshot['product_total'])
    ws.cell(total_row, 5).number_format = '#,##0.00'
    ws.merge_cells(start_row=footer_row, start_column=1, end_row=footer_row, end_column=5)
    ws.cell(footer_row, 1, (
        f"Packing: {len(boxes)} CARTONS    "
        f"Gross Weight: {sum(box['gross_weight'] for box in boxes):g} KGS    "
        f"Net Weight: {sum(box['net_weight'] for box in boxes):g} KGS"
    ))
    _move_stamp(ws, f'D{footer_row + 1}', 105, 94)
    _setup_print(ws, 'E', footer_row + 6)


def _packing_lines(snapshot):
    lines = []
    for box_index, box in enumerate(snapshot['boxes'], 1):
        items = box['items'] or [{
            'product_name': '—', 'quantity': 0, 'unit': '件',
        }]
        start = len(lines)
        for item_index, item in enumerate(items):
            description_parts = [item.get('product_name', '')]
            identity = ' / '.join(filter(None, (
                item.get('product_code', ''), item.get('specification', ''),
            )))
            if identity:
                description_parts.append(identity)
            if item_index == 0:
                description_parts.append(
                    f"Packing Size: {box['length_cm']:g} × "
                    f"{box['width_cm']:g} × {box['height_cm']:g} cm"
                )
            lines.append({
                'box_index': box_index,
                'box': box,
                'description': '\n'.join(filter(None, description_parts)),
                'quantity': item.get('quantity', 0),
                'unit': item.get('unit', '件'),
                'first': item_index == 0,
            })
        end = len(lines) - 1
        for index in range(start, end + 1):
            lines[index]['span_start'] = start
            lines[index]['span_end'] = end
    return lines


def _populate_packing(workbook, donor, snapshot):
    ws = workbook['装箱单１']
    source = donor['装箱单１']
    customs = snapshot['customs']
    customer = snapshot['customer']
    lines = _packing_lines(snapshot)
    detail_count = max(1, len(lines))
    _unmerge_from(ws, 16)
    ws.delete_rows(17, 13)
    ws.insert_rows(17, detail_count + 3)
    for offset in range(detail_count):
        _copy_row_layout(source, 17, ws, 17 + offset, 7)
        _clear_row(ws, 17 + offset, 7)
    total_row = 17 + detail_count
    note_row = total_row + 2
    _copy_row_layout(source, 27, ws, total_row, 7)
    _copy_row_layout(source, 29, ws, note_row, 7)
    _clear_row(ws, total_row, 7)
    _clear_row(ws, note_row, 7)

    ws.title = '装箱单'
    ws['A1'] = snapshot['company_name_cn']
    ws['A2'] = snapshot['company_name']
    ws['A6'] = _customer_block(customer)
    ws['F6'] = snapshot['pi_number']
    ws['F7'] = snapshot['issue_date']
    ws['F8'] = snapshot['price_terms']
    ws['B11'] = _location(customs.get('departure_port', ''), 'China')
    ws['F11'] = _location(
        customs.get('destination_port', ''),
        customs.get('destination_country', ''),
    )
    ws['B14'] = customs.get('packing_type', '') or 'CARTONS'
    ws['F14'] = len(snapshot['boxes'])

    for offset, line in enumerate(lines):
        row = 17 + offset
        box = line['box']
        mark = box.get('shipping_mark') or f"CTN {box.get('box_no') or line['box_index']}"
        first = line['first']
        values = (
            mark if first else '', line['description'],
            f"{line['quantity']} {line['unit']}", 1 if first else '',
            box['gross_weight'] if first else '',
            box['net_weight'] if first else '',
            box['volume_cbm'] if first else '',
        )
        for column, value in enumerate(values, 1):
            ws.cell(row, column, value)
        for column in (5, 6, 7):
            ws.cell(row, column).number_format = '0.000'
    if not lines:
        ws.cell(17, 2, 'No packing data / 暂无装箱数据')

    for line in lines:
        if not line['first'] or line['span_end'] <= line['span_start']:
            continue
        start = 17 + line['span_start']
        end = 17 + line['span_end']
        for column in (1, 4, 5, 6, 7):
            ws.merge_cells(
                start_row=start, start_column=column,
                end_row=end, end_column=column,
            )

    ws.cell(total_row, 2, 'TOTAL:')
    ws.cell(total_row, 4, len(snapshot['boxes']))
    ws.cell(total_row, 5, round(sum(
        box['gross_weight'] for box in snapshot['boxes']
    ), 3))
    ws.cell(total_row, 6, round(sum(
        box['net_weight'] for box in snapshot['boxes']
    ), 3))
    ws.cell(total_row, 7, round(sum(
        box['volume_cbm'] for box in snapshot['boxes']
    ), 6))
    ws.merge_cells(start_row=note_row, start_column=1, end_row=note_row, end_column=7)
    ws.cell(note_row, 1, customs.get('marks_notes', ''))
    _move_stamp(ws, f'E{note_row + 1}', 105, 94)
    _setup_print(ws, 'G', note_row + 6)


def _populate_elements(workbook, donor, snapshot):
    ws = workbook['申报要素']
    source = donor['申报要素']
    groups = snapshot['groups']
    ws._images = list(ws._images)
    _unmerge_from(ws, 2)
    ws.delete_rows(2, max(ws.max_row - 1, 1))
    ws['A1'] = f"申报要素（按{len(groups)}个报关品名整理）"
    row = 2
    for number, group in enumerate(groups, 1):
        _copy_row_layout(source, 2, ws, row, 2)
        _clear_row(ws, row, 2)
        ws.cell(row, 1, f'{_chinese_number(number)}、{group["hs_code"]}')
        ws.cell(row, 2, group['name_cn'])
        row += 1
        elements = [
            ('商品编码', group['hs_code']),
            ('品名', group['name_cn']),
            ('品牌类型', group['brand_type']),
            ('出口享惠情况', group['preferential']),
            ('用途', group['purpose']),
            ('品牌（中文或外文名称）', group['brand']),
            ('型号/规格', group['product_details']),
            ('原产国', group['origin_country']),
            ('境内货源地', group['domestic_source']),
            ('征免', group['tax_exemption']),
            ('申报数量', f"{group['quantity']} {group['unit']}"),
            ('申报金额', f"{snapshot['currency']} {group['amount']:,.2f}"),
            ('其他申报要素', group['elements']),
        ]
        for label, value in elements:
            _copy_row_layout(source, 3, ws, row, 2)
            _clear_row(ws, row, 2)
            ws.cell(row, 1, label)
            ws.cell(row, 2, value)
            row += 1
        row += 1
    if not groups:
        _copy_row_layout(source, 3, ws, row, 2)
        ws.cell(row, 1, '暂无报关产品')
        row += 1
    _move_stamp(ws, f'B{row}', 105, 94)
    _setup_print(ws, 'B', row + 5)


def _populate_contract(workbook, donor, snapshot):
    source = donor['发票１']
    ws = workbook['合同']
    groups = snapshot['groups']
    customer = snapshot['customer']
    detail_count = max(1, len(groups))
    total_row, footer_row = _prepare_five_column_detail_sheet(
        ws, source, detail_count
    )
    ws['A1'] = snapshot['company_name_cn']
    ws['A2'] = snapshot['company_name']
    ws['A3'] = '销售合同'
    ws['A4'] = 'S A L E S   C O N T R A C T'
    ws['A5'] = 'SELLER:'
    ws['A6'] = snapshot['company_name']
    ws['C5'] = '合同号码'
    ws['C6'] = 'Contract No.'
    ws['D6'] = snapshot['pi_number']
    ws['C7'] = '合同日期'
    ws['D7'] = snapshot['issue_date']
    ws['C8'] = 'Price Term'
    ws['D8'] = snapshot['price_terms']
    ws['A10'] = 'BUYER:'
    ws['A11'] = 'Buyer:'
    ws['B11'] = customer['name']
    ws['C10'] = '付款条款'
    ws['C11'] = 'Payment:'
    ws.merge_cells('D11:E11')
    ws['D11'] = snapshot['payment_terms']
    ws['D11'].alignment = Alignment(
        horizontal='left', vertical='center', wrap_text=True
    )
    ws.row_dimensions[11].height = 34
    ws['A13'] = '交货期'
    ws['A14'] = 'Delivery:'
    ws['B14'] = snapshot['delivery_time']
    ws['C13'] = '币制'
    ws['C14'] = 'Currency:'
    ws['D14'] = snapshot['currency']
    headers = (
        'No.', '货物描述\nDescriptions', '数量\nQuantities',
        f"单价\nUnit Price ({snapshot['currency']})",
        f"总金额\nAmount ({snapshot['currency']})",
    )
    for column, value in enumerate(headers, 1):
        ws.cell(16, column, value)
    for number, group in enumerate(groups, 1):
        row = 16 + number
        for column, value in enumerate((
            number,
            '\n'.join(filter(None, (group['name_en'], group['product_details']))),
            group['quantity'], group['unit_price'], group['amount'],
        ), 1):
            ws.cell(row, column, value)
        ws.cell(row, 3).number_format = '#,##0'
        ws.cell(row, 4).number_format = '#,##0.000000'
        ws.cell(row, 5).number_format = '#,##0.00'
    ws.merge_cells(start_row=total_row, start_column=1, end_row=total_row, end_column=3)
    ws.cell(total_row, 1, 'TOTAL:')
    ws.cell(total_row, 4, snapshot['currency'])
    ws.cell(total_row, 5, snapshot['product_total'])
    ws.cell(total_row, 5).number_format = '#,##0.00'
    ws.merge_cells(start_row=footer_row, start_column=1, end_row=footer_row, end_column=5)
    ws.cell(footer_row, 1, (
        f"Seller: {snapshot['company_name']}    Buyer: {customer['name']}\n"
        f"Contract No.: {snapshot['pi_number']}    "
        f"Payment: {snapshot['payment_terms']}    Delivery: {snapshot['delivery_time']}"
    ))
    ws.cell(footer_row, 1).alignment = Alignment(
        horizontal='left', vertical='center', wrap_text=True
    )
    ws.row_dimensions[footer_row].height = 42
    _setup_print(ws, 'E', footer_row + 2)


def generate_customs_workbook(pi, document, data):
    """Fill the approved customs template without rebuilding its layout."""
    snapshot = data.get('_confirmed_snapshot') or build_customs_snapshot(pi, data)
    if not snapshot.get('company_name_cn'):
        snapshot['company_name_cn'] = (
            snapshot.get('company_name', '')
            if 'Qisuo' in snapshot.get('company_name', '')
            else '常州市克利斯达国际贸易有限公司'
        )
    workbook = load_workbook(CUSTOMS_TEMPLATE_PATH)
    donor = load_workbook(CUSTOMS_TEMPLATE_PATH)
    contract = workbook.copy_worksheet(workbook['发票１'])
    contract.title = '合同'
    contract._images = []

    _populate_declaration(workbook, donor, snapshot)
    _populate_invoice(workbook, donor, snapshot)
    _populate_packing(workbook, donor, snapshot)
    _populate_elements(workbook, donor, snapshot)
    _populate_contract(workbook, donor, snapshot)

    workbook.calculation.fullCalcOnLoad = True
    workbook.calculation.forceFullCalc = True
    output = BytesIO()
    workbook.save(output)
    workbook.close()
    donor.close()
    return output.getvalue()
