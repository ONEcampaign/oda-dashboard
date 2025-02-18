import * as d3 from "npm:d3";
import {getCurrencyLabel} from "./getCurrencyLabel.js";
import {formatValue} from "./formatValue.js";

// Copyright 2021-2023 Observable, Inc.
// Released under the ISC license.
// https://observablehq.com/@d3/treemap
export function Treemap(data, { // data is either tabular (array of objects) or hierarchy (nested objects)
    path,
    id = Array.isArray(data) ? d => d.id : null,
    parentId = Array.isArray(data) ? d => d.parentId : null,
    children,
    value,
    sort = (a, b) => d3.descending(a.value, b.value),
    label,
    group,
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
    colors = d3.schemeObservable10,
    zDomain,
    fill = "#ccc",
    fillOpacity = group == null ? null : 0.6,
    stroke = d3.schemeObservable10,
    strokeWidth = 15,
    strokeOpacity = 1,
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

    console.log(leaves);

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

    zDomain = new d3.InternSet(zDomain);
    const color = group == null ? null : d3.scaleOrdinal(zDomain, colors);

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
        .attr("fill", color ? (d, i) => color(group(d.data, d)) : fill)
        .attr("fill-opacity", fillOpacity)
        .attr("stroke", stroke ? (d, i) => color(group(d.data, d)) : stroke)
        .attr("stroke-width", strokeWidth)
        .attr("stroke-opacity", strokeOpacity)
        .attr("stroke-linejoin", strokeLinejoin)
        .attr("x", strokeWidth / 2) // Adjust x position
        .attr("y", strokeWidth / 2) // Adjust y position
        .attr("width", d => d.x1 - d.x0 - strokeWidth) // Adjust width
        .attr("height", d => d.y1 - d.y0 - strokeWidth); // Adjust height


    // if (T) {
    //     node.append("title").text((d, i) => T[i]);
    // }

    console.log(leaves)

    const darkColors = ["#4269d0", "#a463f2", "#9c6b4e"]

    const uid = `O-${Math.random().toString(16).slice(2)}`;

    node.append("clipPath")
        .attr("id", (d, i) => `${uid}-clip-${i}`)
        .append("rect")
        .attr("width", d => d.x1 - d.x0 - 5)
        .attr("height", d => d.y1 - d.y0)

    node.append("text")
        .attr("filter", "url(#text-shadow)")
        .attr("clip-path", (d, i) => `url(${new URL(`#${uid}-clip-${i}`, location)})`)
        .attr("x", 2.5)
        .attr("y", strokeWidth / 2)
        .attr("text-anchor", "start")
        .attr("dominant-baseline", "middle")
        .text(d => String(d.id).toUpperCase())
        .attr("font-size", "12px")
        .attr("font-family", "var(--sans-serif)")
        .attr("font-weight", "500")
        .attr("fill", (d) => darkColors.includes(color(group(d.data, d))) ? "white" : "black")

    node.append("text")
        .attr("filter", "url(#text-shadow)")
        .attr("clip-path", (d, i) => `url(${new URL(`#${uid}-clip-${i}`, location)})`)
        .attr("x", (d) => (d.x1 - d.x0) / 2)
        .attr("y", (d) => (d.y1 - d.y0) / 2)
        .attr("text-anchor", "middle")
        .text(
            (d) => (d.x1 - d.x0) > 100
                ? getCurrencyLabel("US Dollars", {value: formatValue(d.value).label, long: false})
                : "..."
        )
        .attr("font-size", "12px")
        .attr("font-family", "var(--sans-serif)")
        .attr("font-weight", "500")
        .attr("fill", (d) => darkColors.includes(color(group(d.data, d))) ? "white" : "black")

    node.append("rect")
        .attr("id", (d) => d.id)
        .attr("fill", "transparent")
        .attr("width", d => d.x1 - d.x0)
        .attr("height", d => d.y1 - d.y0)
        .attr("cursor", "pointer")
        .on("click", function (event, d) {
            if (onClick) {
                onClick(d.id); // Pass the ID of the clicked rect
            }
        })
        // Add hover effects: change opacity on hover
        .on("mouseenter", function (event, d) {
            d3.select(`#rect-${d.id.replace(/\s+/g, '-').replace(/[&/,]/g, '')}`)
                .transition()
                .duration(200)
                .style("fill-opacity", 0.6);  // Increase opacity on hover
        })
        .on("mouseleave", function (event, d) {
            d3.select(`#rect-${d.id.replace(/\s+/g, '-').replace(/[&/,]/g, '')}`)
                .transition()
                .duration(200)
                .style("fill-opacity", fillOpacity); // Reset opacity when mouse leaves
        });

    return Object.assign(svg.node(), {scales: {color}});
}
