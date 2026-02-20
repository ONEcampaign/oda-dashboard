import { ONEColors } from "@one-data/observable-themes/use-colors";

export const customPalette = {
    ge: ONEColors.teal0,
    flow: ONEColors.teal4,
    bilateral: ONEColors.teal1,
    multilateral: ONEColors.orange1,
    total: ONEColors.purple2,
    intlCommitment: ONEColors.burgundy1,
    genderMain: ONEColors.navy1,
    genderSecondary: ONEColors.navy6,
    genderNotTargeted: ONEColors.grey1,
    genderNotScreened: ONEColors.grey3,
    darkGrey: "#333333",
    midGrey: "#646464",
    neutralGrey: "#C2C2C4",
    lightGrey: "#E8E8E8",
}

export const paletteFinancing = {
    domain: [
        "Grant equivalents",
        "Flows"
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
        "Bilateral + imputed multilateral ODA"
    ],
    range: [
        customPalette.bilateral,
        customPalette.multilateral,
        customPalette.total
    ],
}

export const colorSector = ONEColors.teal1

export const paletteSubsectors = [
    ONEColors.navy1,
    ONEColors.orange1,
    ONEColors.purple1,
    ONEColors.blue0,
    ONEColors.yellow1,
    ONEColors.navy4,
    ONEColors.orange4,
    ONEColors.purple4,
    ONEColors.blue3,
    ONEColors.yellow4

]

export const paletteTreemap = [
    colorSector,
    customPalette.neutralGrey
]

export const paletteGender = {
    domain: [
        "Main target",
        "Secondary target",
        'Not targeted',
        'Not screened'
    ],
    range: [
        customPalette.genderMain,
        customPalette.genderSecondary,
        customPalette.genderNotTargeted,
        customPalette.genderNotScreened
    ]
}