import fs from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";
import JSZip from "jszip";
import sharp from "sharp";
import { FileBlob, SpreadsheetFile } from "@oai/artifact-tool";

const projectRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const sourcePath = process.argv[2]
  ? path.resolve(process.argv[2])
  : "/Users/fantastic/Desktop/e9d60a6780b06d49cfbf8efa3fbb177db2b06be364aeaf3981b5a0ab3efc03a2.xlsx";
const assetPath = process.argv[3]
  ? path.resolve(process.argv[3])
  : path.join(projectRoot, "assets", "qisuo_legacy_pi_template.xlsx");
const deliverablePath = process.argv[4]
  ? path.resolve(process.argv[4])
  : path.join(projectRoot, "outputs", "qisuo_legacy_template", "qisuo_legacy_pi_template.xlsx");
const previewDir = process.argv[5]
  ? path.resolve(process.argv[5])
  : path.join(projectRoot, "outputs", "qisuo_legacy_template", "preview");

const sourceBytes = await fs.readFile(sourcePath);
const sourceZip = await JSZip.loadAsync(sourceBytes);

// The workbook was saved by WPS with an orphaned sheet2 relationship and
// formatting that extends to XFD.  Repair those two package issues before the
// artifact editor opens it; the visible invoice itself only uses A:H.
const workbookRelsEntry = sourceZip.file("xl/_rels/workbook.xml.rels");
const worksheetEntry = sourceZip.file("xl/worksheets/sheet1.xml");
if (!workbookRelsEntry || !worksheetEntry) {
  throw new Error("The source workbook package is missing required XML parts.");
}

let workbookRelsXml = await workbookRelsEntry.async("string");
workbookRelsXml = workbookRelsXml.replace(
  /<Relationship\b(?=[^>]*\bId="rId2")(?=[^>]*\bTarget="worksheets\/sheet2\.xml")[^>]*\/>/,
  "",
);
sourceZip.file("xl/_rels/workbook.xml.rels", workbookRelsXml);

const columnNumber = (letters) => {
  let value = 0;
  for (const letter of letters) {
    value = value * 26 + letter.charCodeAt(0) - 64;
  }
  return value;
};

const stripCellsOutsideInvoice = (xml) => {
  const keepInvoiceCell = (cellXml, letters) => (
    columnNumber(letters) <= 8 ? cellXml : ""
  );

  // Treat self-closing and value-bearing cells separately.  WPS writes tens
  // of thousands of styled, empty cells after column H; keeping them makes
  // the template look like it uses the entire Excel sheet and is rejected by
  // the export safety check.
  return xml
    .replace(
      /<c\b(?=[^>]*\br="([A-Z]+)\d+")[^>]*\/>/g,
      keepInvoiceCell,
    )
    .replace(
      /<c\b(?=[^>]*\br="([A-Z]+)\d+")[^>]*>[\s\S]*?<\/c>/g,
      keepInvoiceCell,
    );
};

const enforceSinglePagePrintLayout = (worksheetXml) => {
  let xml = worksheetXml;
  if (/<pageSetup\b[^>]*\/>/.test(xml)) {
    xml = xml.replace(
      /<pageSetup\b[^>]*\/>/,
      '<pageSetup paperSize="9" fitToWidth="1" fitToHeight="0" orientation="portrait"/>',
    );
  } else {
    xml = xml.replace(
      /<headerFooter\b/,
      '<pageSetup paperSize="9" fitToWidth="1" fitToHeight="0" orientation="portrait"/><headerFooter',
    );
  }
  return xml;
};

const enforcePrintArea = (workbookXml, lastRow) => {
  const printArea = `<definedNames><definedName name="_xlnm.Print_Area" localSheetId="0">'Sheet1'!$A$1:$H$${lastRow}</definedName></definedNames>`;
  if (/<definedNames>[\s\S]*?<\/definedNames>/.test(workbookXml)) {
    return workbookXml.replace(/<definedNames>[\s\S]*?<\/definedNames>/, printArea);
  }
  return workbookXml.replace(/<calcPr\b/, `${printArea}<calcPr`);
};

let worksheetXml = await worksheetEntry.async("string");
worksheetXml = worksheetXml.replace(/<dimension\b[^>]*\bref="[^"]*"[^>]*\/>/, '<dimension ref="A1:H39"/>');
worksheetXml = worksheetXml.replace(/\s+spans="[^"]*"/g, "");
worksheetXml = worksheetXml.replace(/<cols>[\s\S]*?<\/cols>/, (colsXml) => {
  const kept = [...colsXml.matchAll(/<col\b[^>]*\/>/g)]
    .map((match) => match[0])
    .filter((colXml) => {
      const min = Number(colXml.match(/\bmin="(\d+)"/)?.[1] || 0);
      return min > 0 && min <= 8;
    })
    .map((colXml) => {
      const capped = colXml.replace(/\bmax="\d+"/, (maxAttr) => {
        const max = Number(maxAttr.match(/\d+/)?.[0] || 8);
        return `max="${Math.min(max, 8)}"`;
      });
      // WPS hid the CODE column in the original workbook.  The legacy
      // template must show both CODE (product code) and SKU (specification).
      return capped.replace(/\s+hidden="1"/g, "");
    });
  return kept.length ? `<cols>${kept.join("")}</cols>` : "";
});
worksheetXml = stripCellsOutsideInvoice(worksheetXml);
worksheetXml = enforceSinglePagePrintLayout(worksheetXml);
sourceZip.file("xl/worksheets/sheet1.xml", worksheetXml);

const cleanedSourcePath = path.join("/private/tmp", "qisuo-legacy-source-clean.xlsx");
await fs.writeFile(cleanedSourcePath, await sourceZip.generateAsync({ type: "nodebuffer" }));

const input = await FileBlob.load(cleanedSourcePath);
const workbook = await SpreadsheetFile.importXlsx(input);
const sheet = workbook.worksheets.getItemAt(0);

await fs.mkdir(previewDir, { recursive: true });
const sourcePreview = await workbook.render({
  sheetName: sheet.name,
  range: "A1:H39",
  scale: 1,
  format: "png",
});
await fs.writeFile(
  path.join(previewDir, "source-before-edit.png"),
  new Uint8Array(await sourcePreview.arrayBuffer()),
);

sheet.getRange("A39:H39").clear({ applyTo: "all" });
sheet.deleteAllDrawings();

const logoEntry = sourceZip.file("xl/media/image2.png")
  || sourceZip.file(/^xl\/media\/.*\.(png|jpe?g)$/i)[0];
if (!logoEntry) {
  throw new Error("The QISUO logo image is missing from the source workbook.");
}
const logoBytes = await logoEntry.async("nodebuffer");
// The source logo is placed in the middle of a large white square.  Trim the
// whitespace before inserting it so that the wordmark stays visible.
const trimmedLogo = await sharp(logoBytes)
  .trim({ background: "#ffffff", threshold: 12 })
  .resize({
    width: 330,
    height: 74,
    fit: "contain",
    background: { r: 255, g: 255, b: 255, alpha: 0 },
  })
  .png()
  .toBuffer();
const logoBase64 = trimmedLogo.toString("base64");
sheet.images.add({
  dataUrl: `data:image/png;base64,${logoBase64}`,
  anchor: {
    from: { row: 2, col: 5 },
    extent: { widthPx: 330, heightPx: 74 },
  },
});

// Keep all eight invoice columns visible and readable in Excel and PDF.
const columnWidths = {
  A: 12,
  B: 15,
  C: 30,
  D: 20,
  E: 15,
  F: 17,
  G: 13,
  H: 17,
};
for (const [column, width] of Object.entries(columnWidths)) {
  sheet.getRange(`${column}:${column}`).format.columnWidth = width;
}
sheet.getRange("A19:H20").format.wrapText = true;
sheet.getRange("A19:H20").format.verticalAlignment = "center";
sheet.getRange("A19:H19").format.rowHeight = 42;
sheet.getRange("A20:H20").format.rowHeight = 58;

const setValue = (address, value) => {
  sheet.getRange(address).values = [[value]];
};

setValue("A1", "PROFORMA INVOICE");
setValue("A3", "Exporter:");
setValue("C3", "{{company_name}}");
setValue("C4", "Address: {{company_address}}");
setValue("C5", "ZIP CODE: 213102");
setValue("D5", "E-mail: {{salesperson_email}}");
setValue("C6", "From: {{salesperson}}");
setValue("D6", "Phone Number: {{salesperson_phone}}");
setValue("C7", "Wechat: {{salesperson_wechat}}");
setValue("D7", "Whatsapp: {{salesperson_whatsapp}}");

setValue("A9", "Importer:");
setValue("C9", "{{customer_name}} ({{customer_country}})");
setValue("F9", "Date:");
setValue("G9", "{{issue_date}}");
sheet.getRange("G9").format.numberFormat = "yyyy-mm-dd";
setValue("C10", "{{customer_contact}}  {{customer_phone}}");
setValue("F10", "INVOICE NO:");
setValue("G10", "{{pi_number}}");
setValue("C11", "{{customer_address}}\nCustomer Notes: {{customer_notes}}");
setValue("C12", "");
setValue("F11", "Place of Loading:");
setValue("G11", "{{place_of_loading}}");
setValue("F12", "Origin:");
setValue("G12", "{{origin}}");

setValue("A14", "Price Term: {{price_terms}}");
setValue("A15", "Payment Term: {{payment_terms}}");
setValue("A18", "Settlement in {{currency}}");

setValue("A19", "ITEM");
setValue("B19", "CODE");
setValue("C19", "NAME");
setValue("D19", "SKU");
setValue("E19", "PICTURE");
setValue("F19", "Unit Price\n({{currency}})");
setValue("G19", "QUANTITY");
setValue("H19", "Amount\n({{currency}})");

setValue("A20", "{{item.no}}");
setValue("B20", "{{item.code}}");
setValue("C20", "{{item.name}}");
setValue("D20", "{{item.specification}}");
setValue("E20", "{{item.image}}");
setValue("F20", "{{item.unit_price}}");
setValue("G20", "{{item.quantity}}");
setValue("H20", "{{item.amount}}");

setValue("A21", "Gross commodity price (HS Code {{hs_code}}):");
setValue("G21", "{{total_quantity}}");
setValue("H21", "{{product_subtotal}}");
setValue("A22", "Customer Charges / Discount ({{shipping_note_en}})");
setValue("G22", "");
setValue("H22", "{{other_charges}}");
setValue("A23", "TOTAL");
setValue("G23", "{{currency}}");
setValue("H23", "{{grand_total}}");
setValue("A24", "Packing: {{packing}}");
setValue("A25", "Delivery Time: {{delivery_time}}");
setValue("A26", "Payment: {{payment_terms}}");

setValue("A27", "BANK ACCOUNT");
setValue("A28", "Beneficiary Name: {{bank_beneficiary_name}}");
setValue("A29", "Beneficiary Account Number: {{bank_account_no}}");
setValue("A30", "Country/Region: {{bank_country_region}}");
setValue("A31", "Beneficiary Address: {{bank_beneficiary_address}}");
setValue("A32", "Beneficiary Bank: {{bank_name}}");
setValue("A33", "Beneficiary Bank Address: {{bank_address}}");
setValue("A34", "SWIFT Code: {{bank_swift_code}}");
setValue("A35", "Bank Code: {{bank_code}}");
setValue("A36", "Branch Code: {{bank_branch_code}}");
setValue("A37", "Currency: {{bank_currency}}");
setValue("A38", "");

sheet.getRange("A28:H37").format.wrapText = true;
sheet.getRange("A28:H37").format.verticalAlignment = "center";
sheet.getRange("F20:H23").format.numberFormat = "#,##0.00";
sheet.getRange("G20:G21").format.numberFormat = "0";

await fs.mkdir(path.dirname(assetPath), { recursive: true });
await fs.mkdir(path.dirname(deliverablePath), { recursive: true });

const authoredDraftPath = path.join("/private/tmp", "qisuo-legacy-artifact-draft.xlsx");
await workbook.recalculate();
const authored = await SpreadsheetFile.exportXlsx(workbook);
await authored.save(authoredDraftPath);

// Artifact Tool preserves the repaired invoice but can re-emit styled empty
// cells from the imported WPS package.  Apply the same package-level repair to
// the authored workbook so the final selectable template is compact and safe.
const authoredZip = await JSZip.loadAsync(await fs.readFile(authoredDraftPath));
const authoredWorksheetEntry = authoredZip.file("xl/worksheets/sheet1.xml");
if (!authoredWorksheetEntry) {
  throw new Error("The authored workbook is missing sheet1.xml.");
}
let authoredWorksheetXml = await authoredWorksheetEntry.async("string");
authoredWorksheetXml = authoredWorksheetXml.replace(
  /<dimension\b[^>]*\bref="[^"]*"[^>]*\/>/,
  '<dimension ref="A1:H38"/>',
);
authoredWorksheetXml = authoredWorksheetXml.replace(/\s+spans="[^"]*"/g, "");
authoredWorksheetXml = stripCellsOutsideInvoice(authoredWorksheetXml);
authoredWorksheetXml = enforceSinglePagePrintLayout(authoredWorksheetXml);
authoredZip.file("xl/worksheets/sheet1.xml", authoredWorksheetXml);
const authoredWorkbookEntry = authoredZip.file("xl/workbook.xml");
if (!authoredWorkbookEntry) {
  throw new Error("The authored workbook is missing workbook.xml.");
}
const authoredWorkbookXml = enforcePrintArea(
  await authoredWorkbookEntry.async("string"),
  38,
);
authoredZip.file("xl/workbook.xml", authoredWorkbookXml);
await fs.writeFile(assetPath, await authoredZip.generateAsync({ type: "nodebuffer" }));
await fs.copyFile(assetPath, deliverablePath);

const finalWorkbook = await SpreadsheetFile.importXlsx(await FileBlob.load(assetPath));
await finalWorkbook.recalculate();
const finalSheet = finalWorkbook.worksheets.getItemAt(0);
const inspection = await finalWorkbook.inspect({
  kind: "region",
  sheetId: finalSheet.name,
  range: "A1:H38",
  maxChars: 14000,
});
console.log(inspection.ndjson);

const errorInspection = await finalWorkbook.inspect({
  kind: "match",
  searchTerm: "#REF!|#DIV/0!|#VALUE!|#NAME\\?|#N/A",
  options: { useRegex: true, maxResults: 100 },
  summary: "final formula error scan",
});
console.log(errorInspection.ndjson);

const finalPreview = await finalWorkbook.render({
  sheetName: finalSheet.name,
  range: "A1:H38",
  scale: 1,
  format: "png",
});
const finalPreviewPath = path.join(previewDir, "qisuo-legacy-final.png");
await fs.writeFile(
  finalPreviewPath,
  new Uint8Array(await finalPreview.arrayBuffer()),
);

console.log(JSON.stringify({
  sourcePath,
  assetPath,
  deliverablePath,
  finalPreviewPath,
}));
