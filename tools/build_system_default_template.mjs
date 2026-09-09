import fs from "node:fs/promises";
import path from "node:path";
import { SpreadsheetFile, Workbook } from "@oai/artifact-tool";

const projectRoot = path.resolve(path.dirname(new URL(import.meta.url).pathname), "..");
const outputPath = process.argv[2]
  ? path.resolve(process.argv[2])
  : path.join(projectRoot, "assets", "system_default_pi_template.xlsx");
const previewPath = process.argv[3]
  ? path.resolve(process.argv[3])
  : "/tmp/pi-default-template-build/system_default_preview.png";

const navy = "#1A3A5C";
const lightBlue = "#EAF0F6";
const borderColor = "#B9C3CC";
const muted = "#5E6B78";

const workbook = Workbook.create();
const sheet = workbook.worksheets.add("PI Template");
sheet.showGridLines = false;

const widths = {
  A: 12,
  B: 8,
  C: 13,
  D: 23,
  E: 16,
  F: 7,
  G: 14,
  H: 14,
};
for (const [column, width] of Object.entries(widths)) {
  sheet.getRange(`${column}:${column}`).format.columnWidth = width;
}

sheet.getRange("A1:H38").format = {
  font: { size: 10, color: "#111111" },
  verticalAlignment: "center",
};

sheet.getRange("A1:H1").merge();
sheet.getRange("A1").values = [["{{company_name}}"]];
sheet.getRange("A1:H1").format = {
  fill: navy,
  font: { bold: true, color: "#FFFFFF", size: 18 },
  horizontalAlignment: "center",
  verticalAlignment: "center",
};
sheet.getRange("A1:H1").format.rowHeight = 32;

sheet.getRange("A2:H2").merge();
sheet.getRange("A2").values = [["{{company_address}}"]];
sheet.getRange("A2:H2").format = {
  fill: navy,
  font: { color: "#FFFFFF", size: 8 },
  horizontalAlignment: "center",
  verticalAlignment: "center",
};
sheet.getRange("A2:H2").format.rowHeight = 19;

sheet.getRange("A4:H4").merge();
sheet.getRange("A4").values = [["PROFORMA INVOICE"]];
sheet.getRange("A4:H4").format = {
  font: { bold: true, color: navy, size: 22 },
  horizontalAlignment: "center",
  verticalAlignment: "center",
};
sheet.getRange("A4:H4").format.rowHeight = 34;
sheet.getRange("A5:H5").format.borders = {
  bottom: { style: "medium", color: navy },
};

const infoRows = [
  ["PI Number:", "{{pi_number}}", "To / Buyer:", "{{customer_name}}"],
  ["Date:", "{{issue_date}}", "Contact:", "{{customer_contact}}"],
  ["Salesperson:", "{{salesperson}}", "Country:", "{{customer_country}}"],
  ["Tel:", "{{salesperson_phone}}", "Email:", "{{customer_email}}"],
  ["Email:", "{{salesperson_email}}", "Phone:", "{{customer_phone}}"],
  ["Customer Notes:", "{{customer_notes}}", "Address:", "{{customer_address}}"],
];
for (let i = 0; i < infoRows.length; i += 1) {
  const row = 7 + i;
  const [leftLabel, leftValue, rightLabel, rightValue] = infoRows[i];
  sheet.getRange(`A${row}`).values = [[leftLabel]];
  sheet.getRange(`B${row}:D${row}`).merge();
  sheet.getRange(`B${row}`).values = [[leftValue]];
  sheet.getRange(`E${row}`).values = [[rightLabel]];
  sheet.getRange(`F${row}:H${row}`).merge();
  sheet.getRange(`F${row}`).values = [[rightValue]];
  sheet.getRange(`A${row}`).format.font = { bold: true, size: 9 };
  sheet.getRange(`E${row}`).format.font = { bold: true, size: 9 };
  sheet.getRange(`B${row}:D${row}`).format = {
    font: { size: 9 }, horizontalAlignment: "left", wrapText: true,
  };
  sheet.getRange(`F${row}:H${row}`).format = {
    font: { size: 9 }, horizontalAlignment: "left", wrapText: true,
  };
  sheet.getRange(`A${row}:H${row}`).format.rowHeight = row === 12 ? 28 : 19;
}
sheet.getRange("B8").format.numberFormat = "yyyy-mm-dd";

sheet.getRange("A14:H14").merge();
sheet.getRange("A14").values = [["ITEM DETAILS"]];
sheet.getRange("A14:H14").format = {
  font: { bold: true, color: navy, size: 11 },
  verticalAlignment: "center",
};
sheet.getRange("A14:H14").format.rowHeight = 22;

sheet.getRange("A15:H15").values = [[
  "No.",
  "Image",
  "Product\nCode",
  "Description",
  "Specification",
  "Qty",
  "Unit Price\n({{currency}})",
  "Amount\n({{currency}})",
]];
sheet.getRange("A15:H15").format = {
  fill: navy,
  font: { bold: true, color: "#FFFFFF", size: 9 },
  horizontalAlignment: "center",
  verticalAlignment: "center",
  wrapText: true,
  borders: { preset: "all", style: "thin", color: borderColor },
};
sheet.getRange("A15:H15").format.rowHeight = 34;

sheet.getRange("A16:H16").values = [[
  "{{item.no}}",
  "{{item.image}}",
  "{{item.code}}",
  "{{item.name}}",
  "{{item.specification}}",
  "{{item.quantity}}",
  "{{item.unit_price}}",
  "{{item.amount}}",
]];
sheet.getRange("A16:H16").format = {
  font: { size: 9 },
  horizontalAlignment: "center",
  verticalAlignment: "center",
  wrapText: true,
  borders: { preset: "all", style: "thin", color: borderColor },
};
sheet.getRange("D16:E16").format.horizontalAlignment = "left";
sheet.getRange("A16:H16").format.rowHeight = 42;
sheet.getRange("G16:H16").format.numberFormat = "#,##0.00";
sheet.getRange("F16").format.numberFormat = "0";

sheet.getRange("E18:G18").merge();
sheet.getRange("E18").values = [["Product Subtotal ({{currency}}):"]];
sheet.getRange("H18").values = [["{{product_subtotal}}"]];
sheet.getRange("E19:G19").merge();
sheet.getRange("E19").values = [["Other Charges / Discount ({{currency}}):"]];
sheet.getRange("H19").values = [["{{other_charges}}"]];
sheet.getRange("E20:G20").merge();
sheet.getRange("E20").values = [["{{shipping_note}}"]];
sheet.getRange("H20").values = [[""]];
sheet.getRange("E21:G21").merge();
sheet.getRange("E21").values = [["TOTAL AMOUNT ({{currency}}):"]];
sheet.getRange("H21").values = [["{{grand_total}}"]];
sheet.getRange("E18:H21").format = {
  horizontalAlignment: "right",
  verticalAlignment: "center",
  font: { size: 9 },
};
sheet.getRange("E20:G20").format.font = { italic: true, color: muted, size: 8 };
sheet.getRange("E21:H21").format = {
  font: { bold: true, color: navy, size: 12 },
  horizontalAlignment: "right",
  borders: { top: { style: "medium", color: navy } },
};
sheet.getRange("H18:H21").format.numberFormat = "#,##0.00";
sheet.getRange("E18:H21").format.rowHeight = 20;

sheet.getRange("A23:H23").merge();
sheet.getRange("A23").values = [["PAYMENT & BANK DETAILS"]];
sheet.getRange("A23:H23").format = {
  font: { bold: true, color: navy, size: 11 },
  verticalAlignment: "center",
};
sheet.getRange("A23:H23").format.rowHeight = 23;

sheet.getRange("A24:B24").merge();
sheet.getRange("A24").values = [["Payment Terms:"]];
sheet.getRange("C24:H24").merge();
sheet.getRange("C24").values = [["{{payment_terms}}"]];
sheet.getRange("A25:B25").merge();
sheet.getRange("A25").values = [["Bank Info:"]];
sheet.getRange("C25:H26").merge();
sheet.getRange("C25").values = [["{{bank_info}}"]];
sheet.getRange("A24:B25").format.font = { bold: true, size: 9 };
sheet.getRange("C24:H26").format = { font: { size: 9 }, wrapText: true, verticalAlignment: "top" };
sheet.getRange("A24:H24").format.rowHeight = 20;
sheet.getRange("A25:H26").format.rowHeight = 29;

sheet.getRange("A28:H28").merge();
sheet.getRange("A28").values = [["NOTES"]];
sheet.getRange("A28:H28").format = {
  font: { bold: true, color: navy, size: 11 },
  verticalAlignment: "center",
};
sheet.getRange("A29:H30").merge();
sheet.getRange("A29").values = [["{{notes}}"]];
sheet.getRange("A29:H30").format = {
  fill: lightBlue,
  font: { size: 9 },
  wrapText: true,
  verticalAlignment: "top",
  borders: { preset: "outside", style: "thin", color: borderColor },
};
sheet.getRange("A29:H30").format.rowHeight = 24;

sheet.getRange("A32:D32").merge();
sheet.getRange("A32").values = [["Issued By:"]];
sheet.getRange("E32:H32").merge();
sheet.getRange("E32").values = [["Authorized Signature & Stamp:"]];
sheet.getRange("A32:H32").format = {
  font: { bold: true, size: 9 },
  verticalAlignment: "center",
};
sheet.getRange("A33:D34").merge();
sheet.getRange("A33").values = [["{{company_name}}\nDate: {{issue_date}}"]];
sheet.getRange("E33:H34").merge();
sheet.getRange("E33").values = [["\n________________________________\n(Company Chop / Signature)"]];
sheet.getRange("A33:H34").format = {
  font: { size: 9 },
  wrapText: true,
  verticalAlignment: "bottom",
};
sheet.getRange("E33:H34").format.horizontalAlignment = "center";
sheet.getRange("A33:H34").format.rowHeight = 28;

sheet.getRange("A36:H36").merge();
sheet.getRange("A36").values = [[
  "This Proforma Invoice is for order confirmation only and is not a tax or customs invoice.",
]];
sheet.getRange("A36:H36").format = {
  font: { italic: true, color: muted, size: 8 },
  horizontalAlignment: "center",
  verticalAlignment: "center",
  borders: { top: { style: "thin", color: borderColor } },
};
sheet.getRange("A36:H36").format.rowHeight = 20;

await fs.mkdir(path.dirname(outputPath), { recursive: true });
await fs.mkdir(path.dirname(previewPath), { recursive: true });

await workbook.recalculate();

const inspection = await workbook.inspect({
  kind: "region",
  sheetId: "PI Template",
  range: "A1:H38",
  maxChars: 8000,
});
console.log(inspection.ndjson);

const errorInspection = await workbook.inspect({
  kind: "match",
  searchTerm: "#REF!|#DIV/0!|#VALUE!|#NAME\\?|#N/A",
  options: { useRegex: true, maxResults: 100 },
  summary: "final formula error scan",
});
console.log(errorInspection.ndjson);

const preview = await workbook.render({
  sheetName: "PI Template",
  range: "A1:H38",
  scale: 1,
  format: "png",
});
await fs.writeFile(previewPath, new Uint8Array(await preview.arrayBuffer()));

const output = await SpreadsheetFile.exportXlsx(workbook);
await output.save(outputPath);
await fs.rm(`${outputPath}.inspect.ndjson`, { force: true });
console.log(JSON.stringify({ outputPath, previewPath }));
