export const ONEPalette = {
    teal0 : "#17858C",
    teal1: "#1A9BA3",
    teal4: "#9ACACD",
    orange0: "#FF5E1F",
    orange1: "#FF7F4C",
    orange4: "#FFB699",
    navy0: "#081248",
    navy1: "#0C1B6E",
    blue0: "#7ECBF1",
    blue1: "#A3DAF5",
    burgundy2: "#991E79",
    darkGrey: "#333333",
    midGrey: "#646464",
    lightGrey: "#E8E8E8",
    neutralGrey: "#c2c2c4",
};

export const paletteFinancing = {
    domain: ["Grant Equivalent", "Flow"],
    range: [ONEPalette.teal0, ONEPalette.teal4]
}

export const paletteRecipients = {
    domain: ["Bilateral", "Imputed multilateral", "Total"],
    range: [ONEPalette.teal1, ONEPalette.orange1, ONEPalette.burgundy2],
}

export const paletteSectors = [
    ONEPalette.teal1,
    ONEPalette.orange1,
    ONEPalette.navy1,
    ONEPalette.blue1
]
