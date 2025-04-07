import * as d3 from "npm:d3";
import { formatValue, getCurrencyLabel } from "./utils.js";
import { Mutable } from "observablehq:stdlib";
import { paletteTreemap } from "./colors.js";

const tooltip = d3.select("body")
    .append("div")
    .attr("class", "observable-tooltip")
    .style("visibility", "hidden");

export const selectedSector = Mutable("Health");

export function treemapPlot(data, width, { currency = null } = {}) {
    const height = 400;
    const margin = 0;
    const strokeWidth = 17.5;
    const padding = 1;
    const marginTop = margin,
        marginRight = margin,
        marginBottom = margin,
        marginLeft = margin;

    const period = data[0].period;
    const indicator = data[0].indicator;

    const aggregated = d3.rollups(
        data,
        v => d3.sum(v, d => d.value),
        d => d.sector
    );

    const formattedData = [
        { id: "root", parentId: null, value: null },
        ...aggregated.map(([sector, value]) => ({
            id: sector,
            parentId: "root",
            value
        }))
    ];

    const root = d3
        .stratify()
        .id(d => d.id)
        .parentId(d => d.parentId)(formattedData)
        .sum(d => d.value);

    root.sort((a, b) => d3.descending(a.value, b.value));

    d3.treemap()
        .tile(d3.treemapBinary)
        .size([width - marginLeft - marginRight, height - marginTop - marginBottom])
        .paddingInner(padding)
        .paddingTop(padding)
        .paddingRight(padding)
        .paddingBottom(padding)
        .paddingLeft(padding)
        .round(true)(root);

    const leaves = root.leaves();
    const uid = `O-${Math.random().toString(16).slice(2)}`;

    const svg = d3
        .create("svg")
        .attr("viewBox", [-marginLeft, -marginTop, width, height])
        .attr("width", width)
        .attr("height", height)
        .attr("style", "max-width: 100%; height: auto; height: intrinsic;")
        .attr("font-family", "sans-serif")
        .attr("font-size", 10);

    const node = svg
        .selectAll("g")
        .data(leaves)
        .join("g")
        .attr("transform", d => `translate(${d.x0},${d.y0})`);

    node.append("rect")
        .attr("id", d => `rect-${d.id.replace(/\s+/g, '-').replace(/[&/,]/g, '')}`)
        .attr("fill", d => d.id === selectedSector.value ? paletteTreemap[0] : paletteTreemap[1])
        .attr("fill-opacity", d => d.id === selectedSector.value ? 0.6 : 0.8)
        .attr("stroke", d => d.id === selectedSector.value ? paletteTreemap[0] : paletteTreemap[1])
        .attr("stroke-width", strokeWidth)
        .attr("x", strokeWidth / 2)
        .attr("y", strokeWidth / 2)
        .attr("width", d => d.x1 - d.x0 - strokeWidth)
        .attr("height", d => d.y1 - d.y0 - strokeWidth);

    node.append("clipPath")
        .attr("id", (d, i) => `${uid}-clip-${i}`)
        .append("rect")
        .attr("width", d => d.x1 - d.x0 - 5)
        .attr("height", d => d.y1 - d.y0);

    node.append("text")
        .attr("clip-path", (d, i) => `url(${new URL(`#${uid}-clip-${i}`, location)})`)
        .attr("x", 5)
        .attr("y", strokeWidth / 1.5)
        .text(d => d.id.toUpperCase())
        .attr("vertical-align", "middle")
        .attr("font-size", "12px")
        .attr("font-family", "var(--sans-serif)")
        .attr("font-weight", "500")
        .attr("fill", d => d.id === selectedSector.value ? "white" : "black");

    node.append("text")
        .attr("clip-path", (d, i) => `url(${new URL(`#${uid}-clip-${i}`, location)})`)
        .attr("x", d => (d.x1 - d.x0) / 2)
        .attr("y", d => (d.y1 - d.y0) / 2)
        .attr("text-anchor", "middle")
        .text(d => {
            const w = d.x1 - d.x0;
            const h = d.y1 - d.y0;
            if (h > 40) {
                if (w > 75) return formatValue(d.value).label;
                if (w > 50) return "...";
            }
            return "";
        })
        .attr("font-size", d => {
            const w = d.x1 - d.x0;
            if (w > 100) return "14px";
            if (w > 75) return "10px";
            return "8px"
        })
        .attr("font-family", "var(--sans-serif)")
        .attr("font-weight", "500")
        .attr("fill", d => d.id === selectedSector.value ? "white" : "black");

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
        <b>Sector</b> ${d.id}<br>
        <b>Period</b> ${period}<br>
        <b>Indicator</b> ${indicator}<br>
        <b>${getCurrencyLabel(currency, { currencyLong: false })}</b> ${valueLabel}
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
