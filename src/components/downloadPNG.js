import {toPng} from 'npm:html-to-image';

export function downloadPNG(elementId, filename) {
    const element = document.getElementById(elementId);
    if (!element) {
        console.error(`Element with ID "${elementId}" not found.`);
        return;
    }

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
