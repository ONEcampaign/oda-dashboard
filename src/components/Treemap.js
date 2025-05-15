import * as d3 from "npm:d3";
import { formatValue, getCurrencyLabel } from "./utils.js";
import { Mutable } from "observablehq:stdlib";
import { paletteTreemap } from "./colors.js";

// Tooltip setup
const tooltip = d3.select("body")
    .append("div")
    .attr("class", "observable-tooltip")
    .style("visibility", "hidden");

// Shared state for selected sector
export const selectedSector = Mutable("Health");

export function treemapPlot(data, width, { currency = null } = {}) {

    const uniqueSectors = [...new Set(data.map(d => d.sector))];
    if (!uniqueSectors.includes(selectedSector.value)) {
        selectedSector.value = uniqueSectors[0];
    }

    // Layout config
    const height = 400;
    const strokeWidth = 17.5;
    const padding = 1;

    const period = data[0].period;

    // Aggregate data by sector
    const aggregated = d3.rollups(
        data,
        v => d3.sum(v, d => d.value),
        d => d.sector
    );

    // Convert to hierarchy-friendly format
    const formattedData = [
        { id: "root", parentId: null, value: null },
        ...aggregated.map(([sector, value]) => ({
            id: sector,
            parentId: "root",
            value
        }))
    ];

    // Create hierarchy root
    const root = d3
        .stratify()
        .id(d => d.id)
        .parentId(d => d.parentId)(formattedData)
        .sum(d => d.value);

    // Sort sectors descending by value
    root.sort((a, b) => d3.descending(a.value, b.value));

    // Generate treemap layout
    d3.treemap()
        .tile(d3.treemapBinary)
        .size([width, height])
        .paddingInner(padding)
        .paddingTop(padding)
        .paddingRight(padding)
        .paddingBottom(padding)
        .paddingLeft(padding)
        .round(true)(root);

    const leaves = root.leaves();
    const uid = `O-${Math.random().toString(16).slice(2)}`;

    // Create SVG container
    const svg = d3
        .create("svg")
        .attr("viewBox", [0, 0, width, height])
        .attr("width", width)
        .attr("height", height)
        .attr("style", "max-width: 100%; height: auto; height: intrinsic;")
        .attr("font-family", "sans-serif")
        .attr("font-size", 10);

    // Create a group for each node
    const node = svg
        .selectAll("g")
        .data(leaves)
        .join("g")
        .attr("transform", d => `translate(${d.x0},${d.y0})`);

    // Draw rects with color and stroke
    node.append("rect")
        .attr("id", d => `rect-${d.id.replace(/\s+/g, '-').replace(/[&/,]/g, '')}`)
        .attr("fill", d => d.id === selectedSector.value ? paletteTreemap[0] : paletteTreemap[1])
        .attr("fill-opacity", d => d.id === selectedSector.value ? 0.6 : 0.8)
        .attr("stroke", d => {
            const w = d.x1 - d.x0;
            const h = d.y1 - d.y0;
            return (w < strokeWidth || h < strokeWidth) ? "none" : (d.id === selectedSector.value ? paletteTreemap[0] : paletteTreemap[1]);
        })
        .attr("stroke-width", d => {
            const w = d.x1 - d.x0;
            const h = d.y1 - d.y0;
            return (w < strokeWidth || h < strokeWidth) ? 0 : strokeWidth;
        })
        .attr("x", d => ((d.x1 - d.x0 < strokeWidth || d.y1 - d.y0 < strokeWidth) ? 0 : strokeWidth / 2))
        .attr("y", d => ((d.x1 - d.x0 < strokeWidth || d.y1 - d.y0 < strokeWidth) ? 0 : strokeWidth / 2))
        .attr("width", d => Math.max(0, d.x1 - d.x0 - ((d.x1 - d.x0 < strokeWidth || d.y1 - d.y0 < strokeWidth) ? 0 : strokeWidth)))
        .attr("height", d => Math.max(0, d.y1 - d.y0 - ((d.x1 - d.x0 < strokeWidth || d.y1 - d.y0 < strokeWidth) ? 0 : strokeWidth)));

    node.append("text")
        .attr("x", 5)
        .attr("y", strokeWidth / 1.5)
        .attr("vertical-align", "middle")
        .attr("font-size", ".65rem")
        .attr("font-weight", d => d.id === selectedSector.value ? "700" : "500")
        .attr("fill", d => d.id === selectedSector.value ? "white" : "black")
        .text(d => {
            const w = d.x1 - d.x0;
            if (w < 10) return "";

            const estimatedCharLimit = Math.floor(w / 7); // crude estimate
            const sliceLength = Math.max(0, estimatedCharLimit - 5);

            return d.id.length > estimatedCharLimit
                ? d.id.toUpperCase().slice(0, sliceLength) + "…"
                : d.id.toUpperCase();
        });

    // Sector value label (centered)
    node.append("text")
        .attr("clip-path", (d, i) => `url(${new URL(`#${uid}-clip-${i}`, location)})`)
        .attr("x", d => (d.x1 - d.x0) / 2)
        .attr("y", d => (d.y1 - d.y0) / 1.8)
        .attr("text-anchor", "middle")
        .text(d => {
            const w = d.x1 - d.x0 - strokeWidth;
            const h = d.y1 - d.y0 - strokeWidth;
            if (h > 25 && w > 55) return formatValue(d.value).label;
            return "";
        })
        .attr("font-size", d => {
            const w = d.x1 - d.x0 - strokeWidth;
            const h = d.y1 - d.y0 - strokeWidth;
            const area = w * h;
            if (h < 25 || w < 55) return "0px";
            const size = Math.sqrt(area) / 10;
            return `${Math.max(8, Math.min(size, 20))}px`;
        })
        .attr("font-weight", "500")
        .attr("fill", d => d.id === selectedSector.value ? "white" : "black");

    // Interactive overlay for hover/click
    node.append("rect")
        .attr("id", d => d.id)
        .attr("fill", "transparent")
        .attr("width", d => d.x1 - d.x0)
        .attr("height", d => d.y1 - d.y0)
        .attr("cursor", "pointer")
        .on("click", function (event, d) {
            selectedSector.value = d.id;

            node.selectAll("rect")
                .filter(function () {
                    return d3.select(this).attr("id")?.startsWith("rect-");
                })
                .transition()
                .attr("fill", rectD => rectD.id === d.id ? paletteTreemap[0] : paletteTreemap[1])
                .attr("stroke", rectD => rectD.id === d.id ? paletteTreemap[0] : paletteTreemap[1]);
        })
        .on("mouseenter", function (event, d) {
            const id = d.id.replace(/\s+/g, '-').replace(/[&/,]/g, '');

            d3.select(`#rect-${id}`).transition().style("fill-opacity", 0.6);

            d3.select(this.parentNode)
                .append("rect")
                .attr("class", "hover-outline")
                .attr("x", 0)
                .attr("y", 0)
                .attr("width", d.x1 - d.x0)
                .attr("height", d.y1 - d.y0)
                .attr("stroke", "black")
                .attr("stroke-width", 1.25)
                .attr("fill", "none")
                .attr("pointer-events", "none");

            const valueLabel = formatValue(d.value).label;
            const label = `
                <span style="font-size: calc(var(--table-base-font-size) * 1.15)">
                    <span style="line-height: 1.25"><b>Sector</b> ${d.id}</span><br>
                    <span style="line-height: 1.25"><b>Period</b> ${period}</span><br>
                    <span style="line-height: 1.25"><b>${getCurrencyLabel(currency, { currencyLong: false })}</b> ${valueLabel}</span>
                </span>
            `;

            tooltip.html(label).style("visibility", "visible");
        })
        .on("mousemove", function (event) {
            tooltip
                .style("top", `${event.pageY + 12}px`)
                .style("left", `${event.pageX + 12}px`);
        })
        .on("mouseleave", function (event, d) {
            const id = d.id.replace(/\s+/g, '-').replace(/[&/,]/g, '');
            d3.select(`#rect-${id}`).transition().style("fill-opacity", 0.8);
            d3.select(this.parentNode).select(".hover-outline").remove();
            tooltip.style("visibility", "hidden");
        });

    return svg.node();
}
