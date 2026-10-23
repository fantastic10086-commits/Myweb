import fs from 'node:fs/promises';
import { FileBlob, SpreadsheetFile } from '@oai/artifact-tool';

// Convert the supplied bilingual contract into the application's placeholder format.
const [source, destination, mode = 'build'] = process.argv.slice(2);
const book = await SpreadsheetFile.importXlsx(await FileBlob.load(source));
const sheet = book.worksheets.getItemAt(0);
if (mode === 'inspect') {
  const image = await book.render({sheetName: sheet.name, range: 'A1:E25', scale: 1.5});
  await fs.writeFile('/tmp/contract-template/source.png', new Uint8Array(await image.arrayBuffer()));
} else {
  const values = {
    E1: '{{pi_number}}', E2: '{{issue_date}}',
    B5: '{{company_name}}\nADD: {{company_address}}',
    B9: '{{customer_name}}\n{{customer_address}}\n{{customer_country}}', A11: '',
    A18: '{{item.name}}\n{{item.specification}}', C18: '{{item.quantity}}',
    D18: '{{item.unit_price}}', E18: '{{item.amount}}',
    A19: 'Charges / Discount: {{shipping_note_en}}', C19: '', D19: '', E19: '{{other_charges}}',
    C20: '{{total_quantity}}', D20: '{{price_terms}}', E20: '{{grand_total}}',
    E17: 'Amount\n({{currency}})', D17: 'Unit Price\n({{currency}})',
    A26: '4. 装运期限：', A27: 'Time Of Shipment: {{delivery_time}}',
    A29: 'Port Of Loading: {{contract_loading_port}}',
    A31: 'Port Of Destination: {{contract_destination_port}}',
    A34: '8. 付款条件：', A35: 'Terms Of Payment: {{payment_terms}}',
  };
  for (const [cell, value] of Object.entries(values)) sheet.getRange(cell).values = [[value]];
  for (const row of [62, 63, 67, 68, 69, 70, 74, 75]) sheet.getRange(`A${row}`).clear({applyTo: 'contents'});
  sheet.getRange('B9').format.font = {name: 'Arial', size: 11, color: '#000000', underline: 'none'};
  sheet.getRange('E1:E2').format.wrapText = true;
  sheet.getRange('A1:E1').format.rowHeight = 32;
  sheet.getRange('E2').setNumberFormat('yyyy-mm-dd');
  sheet.getRange('D18').setNumberFormat('0.000');
  sheet.getRange('E18:E20').setNumberFormat('0.00');
  sheet.getRange('A17:E20').format.wrapText = true;
  sheet.getRange('A17:E20').format.rowHeight = 42;
  sheet.getRange('A18:E18').format.rowHeight = 60;
  sheet.getRange('A27:E35').format.wrapText = true;
  sheet.getRange('A27:E27').format.rowHeight = 32;
  sheet.getRange('A29:E29').format.rowHeight = 32;
  sheet.getRange('A31:E31').format.rowHeight = 32;
  sheet.getRange('A35:E35').format.rowHeight = 32;
  book.recalculate();
  await (await SpreadsheetFile.exportXlsx(book)).save(destination);
  const image = await book.render({sheetName: sheet.name, range: 'A1:E35', scale: 1.5});
  await fs.writeFile('/tmp/contract-template/template.png', new Uint8Array(await image.arrayBuffer()));
  for (const [start, end] of [[36, 53], [54, 75]]) {
    const page = await book.render({sheetName: sheet.name, range: `A${start}:E${end}`, scale: 1});
    await fs.writeFile(`/tmp/contract-template/terms-${start}.png`, new Uint8Array(await page.arrayBuffer()));
  }
}
