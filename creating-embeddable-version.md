# Creating an Embeddable Version of an Observable Framework Dashboard

This guide explains how to enable embedding for an Observable Framework dashboard. When embedded, the header, footer, and navigation are hidden, and the dashboard communicates its height to the parent window for responsive iframe sizing.

## How It Works

The embed feature uses runtime detection to determine if the page is:
1. Accessed with `?embed=true` URL parameter, OR
2. Loaded inside an iframe

When either condition is met, it:
- Adds an `embedded` class to the `<html>` element
- Uses CSS to hide chrome (header, footer, nav)
- Uses ResizeObserver to send height updates to the parent window via `postMessage`

## Implementation Steps

### 1. Create the Embed Detection Module

Create `src/components/embed.js`:

```javascript
// Detect if embedded via URL parameter or iframe
const isEmbedded =
  new URLSearchParams(window.location.search).get('embed') === 'true' ||
  window.self !== window.top;

if (isEmbedded) {
  // Add class to hide header/footer via CSS
  document.documentElement.classList.add('embedded');

  // Communicate height to parent for responsive iframe
  const observer = new ResizeObserver(([entry]) => {
    parent.postMessage({height: entry.target.offsetHeight}, "*");
  });
  observer.observe(document.documentElement);
}

export {isEmbedded};
```

### 2. Add Embed CSS Styles

Append the following to your `src/style.css` (or create a dedicated `src/embed.css` and import it):

```css
/* === Embed Mode Styles === */
.embedded #observablehq-header,
.embedded #observablehq-footer,
.embedded header,
.embedded footer,
.embedded nav {
  display: none !important;
}

.embedded #observablehq-main,
.embedded main,
.embedded #observablehq-center {
  padding: 0 !important;
  margin: 0 !important;
  max-width: none !important;
}
```

**Optional: Disable scrolling in embedded mode**

If you want the parent page to control scrolling (common for seamless embeds), add:

```css
.embedded body {
  overflow: hidden;
}
```

> **Note:** This prevents scrolling when testing with `?embed=true` directly in a browser. Only add this if your embed container will handle scrolling.

### 3. Import the Embed Module in Each Page

Add this import to the first JavaScript code block of each markdown page you want to be embeddable:

```js
import "./components/embed.js";
```

**Example for a typical page:**

```markdown
```js
import "./components/embed.js";
import {setCustomColors} from "@one-data/observable-themes/use-colors";
// ... rest of your imports
```
```

### Files to Modify

For a typical Observable Framework dashboard, add the import to:
- `src/index.md`
- Any other page files (`src/page-name.md`)

## Usage

### Standalone (Normal View)
```
https://your-dashboard-url.com/
```

### Embedded (No Chrome)
```
https://your-dashboard-url.com/?embed=true
```

### In an iframe (Auto-Detected)
```html
<iframe src="https://your-dashboard-url.com/" width="100%" height="600"></iframe>
```

The `?embed=true` parameter is optional when using iframes - the script auto-detects iframe context.

## Responsive Iframe Example

To create a responsive iframe that adjusts to content height, use this HTML/JS on your parent page:

```html
<iframe
  id="dashboard-embed"
  src="https://your-dashboard-url.com/?embed=true"
  width="100%"
  frameborder="0"
  style="border: none; min-height: 400px;">
</iframe>

<script>
  window.addEventListener('message', function(e) {
    if (e.data && e.data.height) {
      document.getElementById('dashboard-embed').style.height = e.data.height + 'px';
    }
  });
</script>
```

## Testing

1. Start the dev server:
   ```bash
   npm run dev
   ```

2. Test normal view:
   ```
   http://localhost:3000/
   ```
   Should show header, footer, and navigation.

3. Test embed view:
   ```
   http://localhost:3000/?embed=true
   ```
   Should hide header, footer, and navigation.

4. Test iframe embedding:
   Create a test HTML file:
   ```html
   <!DOCTYPE html>
   <html>
   <head><title>Embed Test</title></head>
   <body>
     <h1>Embedded Dashboard Test</h1>
     <iframe
       id="dashboard"
       src="http://localhost:3000/"
       width="100%"
       height="600"
       style="border: 1px solid #ccc;">
     </iframe>
     <script>
       window.addEventListener('message', function(e) {
         if (e.data && e.data.height) {
           document.getElementById('dashboard').style.height = e.data.height + 'px';
           console.log('Resized to:', e.data.height);
         }
       });
     </script>
   </body>
   </html>
   ```

## Customization

### Hiding Additional Elements

If your dashboard has custom elements that should be hidden when embedded, add them to the CSS:

```css
.embedded .your-custom-element {
  display: none !important;
}
```

### Using isEmbedded in JavaScript

You can import `isEmbedded` to conditionally render content:

```js
import {isEmbedded} from "./components/embed.js";

if (!isEmbedded) {
  // Show something only in standalone mode
}
```

### Restricting postMessage Origin

For security, you can restrict which origins receive height updates. Modify `embed.js`:

```javascript
// Instead of "*", specify allowed origins
const ALLOWED_ORIGINS = [
  'https://your-parent-site.com',
  'https://another-allowed-site.com'
];

if (isEmbedded) {
  document.documentElement.classList.add('embedded');

  const observer = new ResizeObserver(([entry]) => {
    ALLOWED_ORIGINS.forEach(origin => {
      parent.postMessage({height: entry.target.offsetHeight}, origin);
    });
  });
  observer.observe(document.documentElement);
}
```

## Troubleshooting

### Header/Footer Still Visible
- Verify the import is in the first code block of your markdown file
- Check browser dev tools for the `embedded` class on `<html>`
- Inspect the CSS selectors - your theme may use different IDs/classes

### Cannot Scroll in Embed Mode
- Remove `overflow: hidden` from the CSS if you want embedded pages to scroll independently
- Or ensure your parent iframe container handles scrolling

### Height Not Updating
- Check browser console for errors
- Verify the parent page has the `message` event listener
- Test with `console.log` in the ResizeObserver callback

### Cross-Origin Issues
- If embedding from a different domain, ensure CORS headers allow it
- The `postMessage` with `"*"` should work cross-origin, but the parent must listen correctly
