# Embedding a dashboard page

Every page in this dashboard can be embedded in an iframe. Embed mode comes entirely from the `@one-data/observable-themes` package.

## How it works

Importing anything from `npm:@one-data/observable-themes/utils` runs the package's embed module (`utils/embed.js`) as a side effect. Each page in `src/` already imports from it (`isEmbedded`, `formatString` and so on), so each page is embeddable.

The module treats a page as embedded when it is loaded inside an iframe or with `?embed=true` in its URL. An embedded page:

- has the `embedded` class on `<html>`;
- posts `{height}` to the parent window from a `ResizeObserver` whenever its height changes (the `<html>` border-box height, rounded up to a whole pixel);
- hides its own overflow when it is both framed and loaded with `?embed=true`, so the parent page shows one scrollbar.

`isEmbedded` is exported as a boolean for pages that want to render differently when embedded. No page reads it today.

Observable's own header, footer, sidebar and pager are off for the whole site in `observablehq.config.js`. The repository defines no styles for the `embedded` class, so the theme's `Header` component shows on an embedded page. To hide it or anything else, add rules to `src/style.css`:

```css
.embedded .your-element {
  display: none;
}
```

## Making a new page embeddable

Import from the theme's utils in the page's first `js` block. Importing a helper the page uses is enough:

```js
import {formatString} from "npm:@one-data/observable-themes/utils"
```

## Embedding a page

A parent that sizes the iframe to the posted height should load the page with `?embed=true` and check that each message comes from its own iframe:

```html
<iframe id="dashboard" src="https://<host>/oda-dashboard/sectors.html?embed=true"></iframe>
<script>
  const iframe = document.getElementById("dashboard")
  window.addEventListener("message", (event) => {
    if (event.source === iframe.contentWindow && typeof event.data?.height === "number") {
      iframe.style.height = `${event.data.height}px`
    }
  })
</script>
```

A parent that embeds the page at a fixed height can leave out `?embed=true`. The framed page then keeps its own scrollbar.

Framed content must not size itself in `vh` units. Inside an iframe `vh` is the iframe height, so an element with `min-height: 100vh` grows with every posted height and the iframe grows without end.

## Checking embed mode locally

1. Run `npm run dev`.
2. Open the Sectors page in the local preview with `?embed=true` added to its URL, and check in the browser's dev tools that `<html>` has the `embedded` class.
3. To check the height messages, load the page in an iframe on a local test page with the listener above and log `event.data.height`.
