export const ONEPalette = {
    teal0 : "#17858C",
    teal1: "#1A9BA3",
    teal4: "#9ACACD",
    orange0: "#FF5E1F",
    orange1: "#FF7F4C",
    orange4: "#FFB699",
    yellow0: "#F5BE29",
    yellow1: "#F7CE5B",
    yellow4: "#FAE29E",
    navy0: "#081248",
    navy1: "#0C1B6E",
    blue0: "#7ECBF1",
    blue1: "#A3DAF5",
    burgundy0: "#7A0018",
    burgundy1: "#A20021",
    burgundy4: "#FF1F4B",
    purple0: "#661450",
    purple1: "#73175A",
    purple2: "#991E79",
    purple4: "#D733AB",
};

export const customPalette = {
    ge: ONEPalette.teal0,
    flow: ONEPalette.teal4,
    bilateral: ONEPalette.teal1,
    multilateral: ONEPalette.orange1,
    total: ONEPalette.purple2,
    intlCommitment: ONEPalette.burgundy1,
    darkGrey: "#333333",
    midGrey: "#646464",
    lightGrey: "#E8E8E8",
    neutralGrey: "#c2c2c4",
}

export const paletteFinancing = {
    domain: ["Grant Equivalent", "Flow"],
    range: [customPalette.ge, customPalette.flow]
}

export const paletteRecipients = {
    domain: ["Bilateral", "Imputed multilateral", "Total"],
    range: [customPalette.bilateral, customPalette.multilateral, customPalette.total],
}

export const paletteSectors = [
    ONEPalette.teal1,
    ONEPalette.orange1,
    ONEPalette.navy1,
    ONEPalette.blue1
]

export function setCustomColors() {
    const root = document.documentElement;

    // Set CSS variables for each color in the palette
    Object.entries(customPalette).forEach(([key, value]) => {
        root.style.setProperty(`--${key}`, value);
    });
}
