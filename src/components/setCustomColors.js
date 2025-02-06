import {ONEPalette} from "./ONEPalette.js"

export function setCustomColors() {
    const root = document.documentElement;

    // Set CSS variables for each color in the palette
    Object.entries(ONEPalette).forEach(([key, value]) => {
        root.style.setProperty(`--${key}`, value);
    });
}
