const ONEPalette = {
    teal0 : "#17858C",
    teal1: "#1A9BA3",
    teal2: "#4DAEB4",
    teal3: "#80C0C4",
    teal4: "#9ACACD",
    orange0: "#FF5E1F",
    orange1: "#FF7F4C",
    orange2: "#FF9970",
    orange3: "#FFA785",
    orange4: "#FFB699",
    yellow0: "#F5BE29",
    yellow1: "#F7CE5B",
    yellow2: "#F9D677",
    yellow3: "#F9DC8A",
    yellow4: "#FAE29E",
    burgundy0: "#7A0018",
    burgundy1: "#A20021",
    burgundy2: "#CC0029",
    burgundy3: "#F50031",
    burgundy4: "#FF1F4B",
    purple0: "#661450",
    purple1: "#73175A",
    purple2: "#991E79",
    purple3: "#BB2593",
    purple4: "#D733AB",
    navy0: "#081248",
    navy1: "#0C1B6E",
    navy2: "#102493",
    navy3: "#142DB8",
    navy4: "#1836DC",
    blue0: "#7ECBF1",
    blue1: "#A3DAF5",
    red0: "#ED8282",
};

export const customPalette = {
    ge: ONEPalette.teal0,
    flow: ONEPalette.teal4,
    bilateral: ONEPalette.teal1,
    multilateral: ONEPalette.orange1,
    total: ONEPalette.purple2,
    intlCommitment: ONEPalette.burgundy1,
    genderMain: ONEPalette.orange1,
    genderSecondary: ONEPalette.navy0,
    genderNot: ONEPalette.purple1,
    darkGrey: "#333333",
    midGrey: "#646464",
    lightGrey: "#E8E8E8",
    neutralGrey: "#c2c2c4",
}

export const paletteFinancing = {
    domain: [
        "Grant Equivalent",
        "Flow"
    ],
    range: [
        customPalette.ge,
        customPalette.flow
    ]
}

export const paletteRecipients = {
    domain: [
        "Bilateral",
        "Imputed multilateral",
        "Total"
    ],
    range: [
        customPalette.bilateral,
        customPalette.multilateral,
        customPalette.total
    ],
}

export const paletteSectors = [
    ONEPalette.teal1,
    ONEPalette.orange1,
    ONEPalette.navy0,
    ONEPalette.purple1,
    ONEPalette.blue0,
]

export const paletteGender = {
    domain: [
        "Gender total",
        "Main focus",
        "Secondary focus",
        'Not targeted'
    ],
    range: [
        customPalette.total,
        customPalette.genderMain,
        customPalette.genderSecondary,
        customPalette.genderNot
    ]
}

export function setCustomColors() {
    const root = document.documentElement;

    // Set CSS variables for each color in the palette
    Object.entries(customPalette).forEach(([key, value]) => {
        root.style.setProperty(`--${key}`, value);
    });
}
