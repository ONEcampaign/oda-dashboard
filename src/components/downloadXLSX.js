// https://observablehq.observablehq.cloud/pangea/party/xlsx-downloads
import * as XLSX from "npm:xlsx";

export function downloadXLSX(data, filename) {

    const worksheet = XLSX.utils.json_to_sheet(data);
    const workbook = XLSX.utils.book_new();
    XLSX.utils.book_append_sheet(workbook, worksheet);
    XLSX.writeFile(workbook, `${filename}.xlsx`);
}