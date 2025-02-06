import {html} from "npm:htl"
import {hex2rgb} from "./hex2rgb.js"
import {ONEPalette} from "./ONEPalette.js"
import {formatValue} from "./formatValue.js";

export function sparkbar(fillColor, alignment, globalMax) {
    const range = globalMax ;

    // Ensure the range is not zero to avoid division by zero
    const safeRange = range === 0 ? 1 : range;

    return (x) => {
        // Calculate bar width as a percentage of the total range
        const barWidth = (100 * Math.abs(x - 0)) / safeRange;

        const barStyle =
            alignment === "center"
                ? `
                  position: absolute;
                  height: 80%;
                  top: 10%;
                  background: ${hex2rgb(fillColor, 0.4)};
                  width: ${barWidth}%;
                  ${
                    x >= 0
                        ? `left: 0%;`
                        : `left: ${(0 - barWidth / 100) * 100}%;`
                }
                  box-sizing: border-box;
                  overflow: hidden;
                `
                : `
                  position: absolute;
                  height: 80%;
                  top: 10%;
                  background: ${hex2rgb(fillColor, 0.4)};
                  width: ${barWidth}%;
                  ${alignment === "right" ? "right: 0;" : "left: 0;"};
                  box-sizing: border-box;
                  overflow: hidden;
                `;

        // Zero line style with full height
        const zeroLineStyle =
            alignment === "center"
                ? `
                  position: absolute;
                  height: 100%;
                  width: 1px;
                  background: ${hex2rgb(ONEPalette.midGrey, 0.5)};
                  left: 0%;
                  box-sizing: border-box;
                `
                : alignment === "right"
                    ? `
                      position: absolute;
                      height: 100%;
                      width: 1px;
                      background: ${hex2rgb(ONEPalette.midGrey, 0.5)};
                      right: 0;
                      box-sizing: border-box;
                    `
                    : `
                      position: absolute;
                      height: 100%;
                      width: 1px;
                      background: ${hex2rgb(ONEPalette.midGrey, 0.5)};
                      left: 0;
                      box-sizing: border-box;
                    `;

        // Text alignment based on alignment type
        const textAlignment =
            alignment === "center"
                ? "center"
                : alignment === "right"
                    ? "end" // Right-align text
                    : "start"; // Left-align text

        return html`
            <div style="
                position: relative;
                width: 100%; /* Constrain to table cell width */
                height: var(--size-l);
                background: none;
                display: flex;
                z-index: 0;
                align-items: center;
                justify-content: ${textAlignment};
                box-sizing: border-box;
                overflow: hidden;"> <!-- Prevent overflow -->
                <div style="${barStyle}"></div>
                <div style="${zeroLineStyle}"></div> <!-- Zero line -->
                <span style="
                    position: relative;
                    z-index: 1;
                    font-size: var(--size-m);
                    color: black;
                    text-shadow: .5px .5px 0 ${ONEPalette.lightGrey};
                    padding: 0 3px;">
                    ${formatValue(x).label}
                </span>
            </div>`;
    };
}

