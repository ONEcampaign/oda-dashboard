export function hex2rgb(hex, alpha = 1) {
    // Remove the hash if present
    hex = hex.replace(/^#/, "");

    // Parse the hex into RGB components
    let r,
        g,
        b,
        a = 1; // Default alpha is 1

    if (hex.length === 6) {
        // If hex is #RRGGBB
        r = parseInt(hex.slice(0, 2), 16);
        g = parseInt(hex.slice(2, 4), 16);
        b = parseInt(hex.slice(4, 6), 16);
    } else if (hex.length === 8) {
        // If hex is #RRGGBBAA
        r = parseInt(hex.slice(0, 2), 16);
        g = parseInt(hex.slice(2, 4), 16);
        b = parseInt(hex.slice(4, 6), 16);
        a = parseInt(hex.slice(6, 8), 16) / 255; // Alpha is in [0, 255]
    } else {
        throw new Error("Invalid hex format. Use #RRGGBB or #RRGGBBAA.");
    }

    // Combine the RGBA components into a CSS string
    return `rgba(${r}, ${g}, ${b}, ${a * alpha})`;
}