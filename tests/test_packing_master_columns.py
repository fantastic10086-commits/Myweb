import unittest
from io import BytesIO
from pathlib import Path

from openpyxl import Workbook, load_workbook
from openpyxl.styles import Font

from packing_list_export import apply_packing_template_style


class PackingMasterColumnTests(unittest.TestCase):
    def test_legacy_master_keeps_custom_style_and_new_quantity_columns(self):
        master = Workbook()
        source = master.active
        source['E10'] = '数量'
        source['F10'] = 'Custom net weight'
        source['N10'] = 'Custom item notes'
        source['F11'].font = Font(name='Arial', italic=True, color='9900FF')
        source.column_dimensions['N'].width = 19
        source['B8'] = 'Example shipping requirement'
        legacy = BytesIO()
        master.save(legacy)
        legacy.seek(0)
        master.close()

        sample = Path(__file__).resolve().parents[1] / 'assets' / 'packing_a4.xlsx'
        result = load_workbook(BytesIO(apply_packing_template_style(sample.read_bytes(), legacy)))
        sheet = result.active
        self.assertEqual([sheet[f'{col}10'].value for col in 'BFG'],
                         ['箱数\nCartons', '每箱数量\nQty/Carton', '总数量\nTotal Qty'])
        self.assertEqual([sheet[f'{col}11'].value for col in 'BFG'], [2, 10, 20])
        self.assertEqual(sheet['H10'].value, 'Custom net weight')
        self.assertTrue(sheet['H11'].font.italic)
        self.assertEqual(sheet['P10'].value, 'Custom item notes')
        self.assertEqual(sheet.column_dimensions['P'].width, 19)
        self.assertNotEqual(sheet['B8'].value, 'Example shipping requirement')
        result.close()
