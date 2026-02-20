import {icon} from "@one-data/observable-themes/use-images";

export default {
  title: "ODA Dashboard",
  head: `<link rel="icon" href=${icon} type="image/png" sizes="32x32"><script src="https://cdn.jsdelivr.net/npm/@tailwindcss/browser@4"></script>`,

  base: "/oda-dashboard",
  preserveExtension: true,

  root: "src",
  style: "style.css",

  toc: false,
  pager: false,
  sidebar: false,
  header: false,
  footer: false,
};
