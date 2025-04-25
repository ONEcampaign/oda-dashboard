import {generateHeader} from "@one-data/observable-themes/header";
import {generateFooter} from "@one-data/observable-themes/footer";
import {icon} from "@one-data/observable-themes/use-images";

export default {
  title: "ODA Dashboard",
  head: `<link rel="icon" href=${icon} type="image/png" sizes="32x32">`,

  root: "src",

  style: "style.css",

  header: generateHeader({title: "ODA Dashboard"}),
  footer: generateFooter(),

  toc: false,
  sidebar: false,
  pager: false,
};