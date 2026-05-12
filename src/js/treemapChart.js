import * as d3 from "npm:d3";
import { getCurrencyLabel, resolveScale } from "npm:@one-data/observable-themes/utils";
import { paletteTreemap } from "./colors.js";

// Tooltip setup
const tooltip = d3.select("body")
    .append("div")
    .attr("class", "treemap-tooltip")
    .style("visibility", "hidden");

// Module-level tracking of the active sector for coloring across redraws
let _activeSector = "All sectors";

export function treemapChart(data, width, { currency = null, onSectorChange = null } = {}) {

    const uniqueSectors = [...new Set(data.map(d => d.sector))];

    // If active sector is set but no longer in data, reset to "All sectors"
    if (_activeSector !== "All sectors" && !uniqueSectors.includes(_activeSector)) {
        _activeSector = "All sectors";
        if (onSectorChange) setTimeout(() => onSectorChange("All sectors"), 0);
    }

    // Layout config
    const height = 400;
    const strokeWidth = 17.5;
    const padding = 1;

    const year = data[0].period;

    // Aggregate data by sector
    const aggregated = d3.rollups(
        data,
        v => d3.sum(v, d => d.value),
        d => d.sector
    );

    const scale = resolveScale(aggregated.map(([, v]) => v), 6);
    const SHORT_SUFFIX = { million: "M", billion: "B", thousand: "K", trillion: "T" };

    function formatCellValue(value) {
        const scaled = (value / scale.divisor).toFixed(1);
        const suffix = SHORT_SUFFIX[scale.suffix] ?? scale.suffix;
        return suffix ? `${scaled} ${suffix}` : scaled;
    }

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
        .attr("font-family", "'Italian Plate', sans-serif")
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
        .attr("fill", d => (_activeSector === "All sectors" || d.id === _activeSector) ? paletteTreemap.active : paletteTreemap.inactive)
        .attr("fill-opacity", d => (_activeSector === "All sectors" || d.id === _activeSector) ? 0.6 : 0.8)
        .attr("stroke", d => {
            const w = d.x1 - d.x0;
            const h = d.y1 - d.y0;
            const isActive = _activeSector === "All sectors" || d.id === _activeSector;
            return (w < strokeWidth || h < strokeWidth) ? "none" : (isActive ? paletteTreemap.active : paletteTreemap.inactive);
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

    // Sector titles
    node.append("text")
        .attr("x", 5)
        .attr("y", strokeWidth / 1.5)
        .attr("vertical-align", "middle")
        .attr("font-size", ".75rem")
        .attr("font-weight", d => (_activeSector === "All sectors" || d.id === _activeSector) ? "700" : "500")
        .style("fill", d => (_activeSector === "All sectors" || d.id === _activeSector) ? "white" : "black")
        .text(d => {
            const w = d.x1 - d.x0;
            if (w < 10) return "";

            const estimatedCharLimit = Math.floor(w / 5); // crude estimate
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
            if (h > 15 && w > 35) return formatCellValue(d.value);
            return "";
        })
        .attr("font-size", d => {
            const w = d.x1 - d.x0 - strokeWidth;
            const h = d.y1 - d.y0 - strokeWidth;
            if (w <= 0 || h <= 0) return "0px";

            const label = formatCellValue(d.value);

            const areaSize = Math.sqrt(w * h) / 6;
            const widthMax = w / (label.length * 0.58);
            const heightMax = h / 1.5;

            const size = Math.min(areaSize, widthMax, heightMax);

            if (size < 8) return "0px";
            return `${Math.min(size, 18)}px`;
        })
        .attr("font-weight", "500")
        .style("fill", d => (_activeSector === "All sectors" || d.id === _activeSector) ? "white" : "black");

    // Interactive overlay for hover/click
    node.append("rect")
        .attr("id", d => d.id)
        .attr("fill", "transparent")
        .attr("width", d => d.x1 - d.x0)
        .attr("height", d => d.y1 - d.y0)
        .attr("cursor", "pointer")
        .on("click", function (event, d) {
            _activeSector = d.id;

            // Update rect fill/stroke
            node.selectAll("rect")
                .filter(function () {
                    return d3.select(this).attr("id")?.startsWith("rect-");
                })
                .transition()
                .attr("fill", rectD => rectD.id === d.id ? paletteTreemap.active : paletteTreemap.inactive)
                .attr("stroke", rectD => rectD.id === d.id ? paletteTreemap.active : paletteTreemap.inactive);

            // Update text fill and font-weight for all tiles
            node.each(function(nodeData) {
                const isSelected = nodeData.id === d.id;
                const g = d3.select(this);
                g.selectAll("text").transition()
                    .style("fill", isSelected ? "white" : "black");
                g.select("text")
                    .attr("font-weight", isSelected ? "700" : "500");
            });

            onSectorChange?.(d.id);
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

            const scaledValue = (d.value / scale.divisor).toFixed(1);
            const currencyUnitLabel = getCurrencyLabel(currency, { suffix: scale.suffix });
            const label = `
                <span style="font-size: calc(var(--table-base-font-size) * 1.15)">
                    <span style="line-height: 1.25"><b>Year</b> ${year}</span><br>
                    <span style="line-height: 1.25"><b>${currencyUnitLabel}</b> ${scaledValue}</span><br>
                    <span style="line-height: 1.25"><b>Sector</b> ${d.id}</span>
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
            const isActive = _activeSector === "All sectors" || d.id === _activeSector;
            d3.select(`#rect-${id}`).transition().style("fill-opacity", isActive ? 0.6 : 0.8);
            d3.select(this.parentNode).select(".hover-outline").remove();
            tooltip.style("visibility", "hidden");
        });

    return svg.node();
}

export function selectSector(container, sectorId) {
    _activeSector = sectorId
    const svg = d3.select(container).select("svg")
    if (svg.empty()) return

    svg.selectAll("rect")
        .filter(function() { return d3.select(this).attr("id")?.startsWith("rect-") })
        .transition()
        .attr("fill", d => (sectorId === "All sectors" || d.id === sectorId) ? paletteTreemap.active : paletteTreemap.inactive)
        .attr("fill-opacity", d => (sectorId === "All sectors" || d.id === sectorId) ? 0.6 : 0.8)
        .attr("stroke", d => (sectorId === "All sectors" || d.id === sectorId) ? paletteTreemap.active : paletteTreemap.inactive)

    svg.selectAll("g").each(function(nodeData) {
        if (!nodeData) return
        const isSelected = sectorId === "All sectors" || nodeData.id === sectorId
        const g = d3.select(this)
        g.selectAll("text").transition()
            .style("fill", isSelected ? "white" : "black")
        g.select("text:first-of-type")
            .attr("font-weight", isSelected ? "700" : "500")
    })
}
