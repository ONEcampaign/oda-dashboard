// Lazy-load download libraries only when needed
export async function downloadPNG(elementId, filename) {
    const element = document.getElementById(elementId);
    if (!element) {
        console.error(`Element with ID "${elementId}" not found.`);
        return;
    }

    // Dynamic import - only loads when user clicks download button
    const {toPng} = await import('npm:html-to-image');

    toPng(element, { pixelRatio: 2, backgroundColor: "white" })
        .then((dataUrl) => {
            const link = document.createElement('a');
            link.href = dataUrl;
            link.download = `${filename}.png`;
            link.click();
        })
        .catch((error) => {
            console.error('Error capturing the element as an image:', error);
        });
}

// https://observablehq.observablehq.cloud/pangea/party/xlsx-downloads
export async function downloadXLSX(data, filename) {
    // Dynamic import - only loads when user clicks download button
    const {utils, writeFile} = await import('npm:xlsx');

    const worksheet = utils.json_to_sheet(data);
    const workbook = utils.book_new();
    utils.book_append_sheet(workbook, worksheet);
    writeFile(workbook, `${filename}.xlsx`);
}