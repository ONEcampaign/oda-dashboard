import * as d3 from "npm:d3";
import { formatValue, getCurrencyLabel } from "./utils.js";
import { Mutable } from "observablehq:stdlib";
import {paletteTreemap} from "./colors.js";


const tooltip = d3.select("body")
    .append("div")
    .attr("class", "observable-tooltip")
    .style("visibility", "hidden");

// Declare an observable variable to hold the selected sector
export const selectedSector = Mutable("Health"); // Default selected sector

export function treemapPlot(data, width, { currency = null } = {}) {


    const period = data[0].period
    const indicator = data[0].indicator

    // Aggregate data by sector and calculate total values
    const aggregated = d3.rollups(
        data,
        (v) => d3.sum(v, (d) => d.value),
        (d) => d.sector
    );

    const formattedData = [
        { id: "root", parentId: null, value: null },
        ...aggregated.map(([sector, value]) => ({
            id: sector,
            parentId: "root",
            value: value,
        })),
    ];

    // Function to handle clicks and update the selectedSector observable
    const handleClick = (id) => {
        selectedSector.value = id; // Update the selected sector
    };

    // Return the Treemap visualization with the updated color scale
    return Treemap(formattedData, {
        parentId: (d) => d.parentId,
        value: (d) => d.value,
        group: (d) => d.id,
        currency: currency,
        period: period,
        indicator: indicator,
        width: width,
        height: 400,
        padding: 1,
        fillOpacity: (d) => d.id === selectedSector.value ? 0.6 : 0.8,
        strokeOpacity: 1,
        onClick: handleClick, // Pass the click handler to the Treemap
    });
}

// This will reactively handle the selected sector value
// selectedSector; // The observable will be updated automatically when a sector is clicked



// Copyright 2021-2023 Observable, Inc.
// Released under the ISC license.
// https://observablehq.com/@d3/treemap
function Treemap(data, { // data is either tabular (array of objects) or hierarchy (nested objects)
    path,
    id = Array.isArray(data) ? d => d.id : null,
    parentId = Array.isArray(data) ? d => d.parentId : null,
    children,
    value,
    sort = (a, b) => d3.descending(a.value, b.value),
    label,
    group,
    currency,
    period,
    indicator,
    title,
    link,
    linkTarget = "_blank",
    tile = d3.treemapBinary,
    width = 640,
    height = 400,
    margin = 0,
    marginTop = margin,
    marginRight = margin,
    marginBottom = margin,
    marginLeft = margin,
    padding = 1,
    paddingInner = padding,
    paddingOuter = padding,
    paddingTop = paddingOuter,
    paddingRight = paddingOuter,
    paddingBottom = paddingOuter,
    paddingLeft = paddingOuter,
    round = true,
    colors,
    zDomain,
    fill = "#ccc",
    fillOpacity = group == null ? null : 0.6,
    stroke,
    strokeWidth = 20,
    strokeOpacity = group == null ? null : 0.6,
    strokeLinejoin,
    onClick = null
} = {}) {

    // If id and parentId options are specified, or the path option, use d3.stratify
    const stratify = data => (d3.stratify().path(path)(data)).each(node => {
        if (node.children?.length && node.data != null) {
            const child = new d3.Node(node.data);
            node.data = null;
            child.depth = node.depth + 1;
            child.height = 0;
            child.parent = node;
            child.id = node.id + "/";
            node.children.unshift(child);
        }
    });

    const root = path != null ? stratify(data)
        : id != null || parentId != null ? d3.stratify().id(id).parentId(parentId)(data)
            : d3.hierarchy(data, children);

    value == null ? root.count() : root.sum(d => Math.max(0, d ? value(d) : null));

    const leaves = root.leaves();

    // Color scale setup
    if (zDomain === undefined && group != null) {
        const groupValues = d3.rollups(
            root.leaves(),
            (v) => d3.sum(v, (d) => value(d.data)),
            (d) => group(d.data)
        );
        groupValues.sort((a, b) => d3.descending(a[1], b[1]));
        zDomain = groupValues.map(([key]) => key);
    }

    // zDomain = new d3.InternSet(zDomain);
    // const color = group == null ? null : d3.scaleOrdinal(zDomain, colors);

    const L = label == null ? null : leaves.map(d => label(d.data, d));
    const T = title === undefined ? L : title == null ? null : leaves.map(d => title(d.data, d));

    if (sort != null) {
        root.sort((a, b) => d3.descending(a.value, b.value));
    }

    d3.treemap()
        .tile(tile)
        .size([width - marginLeft - marginRight, height - marginTop - marginBottom])
        .paddingInner(paddingInner)
        .paddingTop(paddingTop)
        .paddingRight(paddingRight)
        .paddingBottom(paddingBottom)
        .paddingLeft(paddingLeft)
        .round(round)
        (root);

    const svg = d3.create("svg")
        .attr("viewBox", [-marginLeft, -marginTop, width, height])
        .attr("width", width)
        .attr("height", height)
        .attr("style", "max-width: 100%; height: auto; height: intrinsic;")
        .attr("font-family", "sans-serif")
        .attr("font-size", 10);

    const node = svg.selectAll("a")
        .data(leaves)
        .join("a")
        .attr("xlink:href", link == null ? null : (d, i) => link(d.data, d))
        .attr("target", link == null ? null : linkTarget)
        .attr("transform", d => `translate(${d.x0},${d.y0})`)

    node.append("rect")
        .attr("id", (d) => `rect-${d.id ? d.id.replace(/\s+/g, '-').replace(/[&/,]/g, '') : d.id}`)
        .attr("fill", (d) => d.id === selectedSector.value ? paletteTreemap[0] : paletteTreemap[1])
        .attr("fill-opacity", fillOpacity)
        .attr("stroke", (d) => d.id === selectedSector.value ? paletteTreemap[0] : paletteTreemap[1])
        .attr("stroke-width", strokeWidth)
        .attr("stroke-opacity", strokeOpacity)
        .attr("stroke-linejoin", strokeLinejoin)
        .attr("x", strokeWidth / 2) // Adjust x position
        .attr("y", strokeWidth / 2) // Adjust y position
        .attr("width", d => d.x1 - d.x0 - strokeWidth) // Adjust width
        .attr("height", d => d.y1 - d.y0 - strokeWidth); // Adjust height

    const uid = `O-${Math.random().toString(16).slice(2)}`;

    node.append("clipPath")
        .attr("id", (d, i) => `${uid}-clip-${i}`)
        .append("rect")
        .attr("width", d => d.x1 - d.x0 - 5)
        .attr("height", d => d.y1 - d.y0)

    node.append("text")
        .attr("filter", "url(#text-shadow)")
        .attr("clip-path", (d, i) => `url(${new URL(`#${uid}-clip-${i}`, location)})`)
        .attr("x", 5)
        .attr("y", strokeWidth / 1.75)
        .attr("text-anchor", "start")
        .attr("dominant-baseline", "middle")
        .text(d => String(d.id).toUpperCase())
        .attr("font-size", "12px")
        .attr("font-family", "var(--sans-serif)")
        .attr("font-weight", "500")
        .attr("fill", (d) => d.id === selectedSector.value ? "white" : "black")

    node.append("text")
        .attr("filter", "url(#text-shadow)")
        .attr("clip-path", (d, i) => `url(${new URL(`#${uid}-clip-${i}`, location)})`)
        .attr("x", (d) => (d.x1 - d.x0) / 2)
        .attr("y", (d) => (d.y1 - d.y0) / 2)
        .attr("text-anchor", "middle")
        .text(
            (d) => (d.x1 - d.x0) > 150
                ? getCurrencyLabel(currency, {value: formatValue(d.value).label, long: false})
                : (d.x1 - d.x0) > 50
                    ? "..."
                    : ""

        )
        .attr("font-size", "10px")
        .attr("font-family", "var(--sans-serif)")
        .attr("font-weight", "500")
        .attr("fill", (d) => d.id === selectedSector.value ? "white" : "black")

    node.append("rect")
        .attr("id", (d) => d.id)
        .attr("fill", "transparent")
        .attr("width", d => d.x1 - d.x0)
        .attr("height", d => d.y1 - d.y0)
        .attr("cursor", "pointer")
        .on("click", function (event, d) {
            if (onClick) {
                onClick(d.id);
            }

            node.selectAll("rect")
                .filter(function () {
                    return d3.select(this).attr("id")?.startsWith("rect-");
                })
                .transition()
                .attr("fill", (rectD) => rectD.id === d.id ? paletteTreemap[0] : paletteTreemap[1])
                .attr("stroke", (rectD) => rectD.id === d.id ? paletteTreemap[0] : paletteTreemap[1]);
        })
        .on("mouseenter", function (event, d) {
            const id = d.id.replace(/\s+/g, '-').replace(/[&/,]/g, '');

            d3.select(`#rect-${id}`)
                .transition()
                .style("fill-opacity", 0.6);

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
                    <b>${getCurrencyLabel(currency, {currencyLong: false})}</b> ${valueLabel}
            `;

            tooltip
                .html(label)
                .style("visibility", "visible");

        })
        .on("mousemove", function (event) {
            tooltip
                .style("top", `${event.pageY + 12}px`)
                .style("left", `${event.pageX + 12}px`);
        })
        .on("mouseleave", function (event, d) {
            const id = d.id.replace(/\s+/g, '-').replace(/[&/,]/g, '');

            d3.select(`#rect-${id}`)
                .transition()
                .style("fill-opacity", fillOpacity);

            d3.select(this.parentNode).select(".hover-outline").remove();

            tooltip.style("visibility", "hidden");
        });



    return Object.assign(svg.node(), {});
}
