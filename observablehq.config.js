import { generateHeader } from "@one-data/observable-themes/header-template";

// See https://observablehq.com/framework/config for documentation.
export default {
  title: "ODA Dashboard",

  head: `<link rel="icon" href="ONE-logo-favicon.png" type="image/png" sizes="32x32">'
      <script src="npm:@one-data/observable-themes/header.js" defer></script>
      <script src="npm:@one-data/observable-themes/footer.js" defer></script>
      <link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Material+Symbols+Outlined" />`,

  root: "src",
  theme: ["light", "wide", "alt"],
  toc: false,
  sidebar: false,
  pager: false,
  style: "style.css",

  header: generateHeader({title: "ODA Dashboard"}),
   footer: "", // what to show in the footer (HTML)
  // sidebar: true, // whether to show the sidebar
  // pager: true, // whether to show previous & next links in the footer
  // output: "dist", // path to the output root for build
  // search: true, // activate search
  // linkify: true, // convert URLs in Markdown to links
  // typographer: false, // smart quotes and other typographic improvements
  // preserveExtension: false, // drop .html from URLs
  // preserveIndex: false, // drop /index from URLs
};
