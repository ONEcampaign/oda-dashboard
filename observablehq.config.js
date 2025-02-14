// See https://observablehq.com/framework/config for documentation.
export default {
  title: "ODA Dashboard",

  head: '<link rel="icon" href="ONE-logo-favicon.png" type="image/png" sizes="32x32">' +
      '<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Material+Symbols+Outlined" />',

  root: "src",
  theme: ["light", "wide", "alt"],
  toc: false,
  sidebar: false,
  pager: false,
  style: "style.css"

  // Some additional configuration options and their defaults:
  // theme: "default", // try "light", "dark", "slate", etc.
  // header: "", // what to show in the header (HTML)
  // footer: "Built with Observable.", // what to show in the footer (HTML)
  // sidebar: true, // whether to show the sidebar
  // pager: true, // whether to show previous & next links in the footer
  // output: "dist", // path to the output root for build
  // search: true, // activate search
  // linkify: true, // convert URLs in Markdown to links
  // typographer: false, // smart quotes and other typographic improvements
  // preserveExtension: false, // drop .html from URLs
  // preserveIndex: false, // drop /index from URLs
};
