const FONT_REGULAR_URL =
  "https://cdn.jsdelivr.net/npm/@one-data/observable-themes@latest/assets/fonts/ItalianPlateNo2-Regular.woff2"
const FONT_BOLD_URL =
  "https://cdn.jsdelivr.net/npm/@one-data/observable-themes@latest/assets/fonts/ItalianPlateNo2-Bold.woff2"

const COLORS = {
  title: "#0f172a",    // slate-900
  subtitle: "#64748b", // slate-500
  source: "#64748b",
  note: "#64748b",
  bg: "#ffffff"
}

const FONT_FAMILY = "'Italian Plate', Helvetica, sans-serif"
const PADDING = 32
const SCALE = 2

/**
 * Fetch a URL as a base64 data URI. Returns null on failure.
 */
async function fetchAsDataURI(url, mime) {
  try {
    const res = await fetch(url)
    if (!res.ok) return null
    const buf = await res.arrayBuffer()
    const b64 = btoa(String.fromCharCode(...new Uint8Array(buf)))
    return `data:${mime};base64,${b64}`
  } catch {
    return null
  }
}

/**
 * Convert an image src (URL or data URI) to a base64 data URI suitable for
 * embedding in an SVG <image> element.  If the src is already a data URI it is
 * returned as-is.  Otherwise the raw bytes are fetched to preserve full
 * resolution (avoids canvas re-encoding which degrades quality).
 */
async function toEmbeddableDataURI(src) {
  if (!src) return null
  if (src.startsWith("data:")) return src
  try {
    const res = await fetch(src)
    if (!res.ok) return null
    const blob = await res.blob()
    const buf = await blob.arrayBuffer()
    const b64 = btoa(String.fromCharCode(...new Uint8Array(buf)))
    return `data:${blob.type || "image/png"};base64,${b64}`
  } catch {
    return null
  }
}

/**
 * Strip HTML tags from a string, returning plain text.
 */
function stripHTML(html) {
  const tmp = document.createElement("div")
  tmp.innerHTML = html
  return tmp.textContent || tmp.innerText || ""
}

/**
 * Parse an HTML string into an array of {text, color, fontWeight} segments
 * by walking the DOM tree and inheriting inline styles from parent elements.
 */
function parseHTMLSegments(html) {
  const div = document.createElement("div")
  div.innerHTML = html
  const segments = []

  function walk(node, inheritedColor, inheritedWeight) {
    if (node.nodeType === 3 /* TEXT_NODE */) {
      if (node.textContent) {
        segments.push({ text: node.textContent, color: inheritedColor, fontWeight: inheritedWeight })
      }
    } else if (node.nodeType === 1 /* ELEMENT_NODE */) {
      const color = node.style.color || inheritedColor
      const fontWeight = node.style.fontWeight || inheritedWeight
      for (const child of node.childNodes) {
        walk(child, color, fontWeight)
      }
    }
  }

  for (const child of div.childNodes) {
    walk(child, null, null)
  }
  return segments.filter(s => s.text)
}

/**
 * Resolve the source prop to plain text suitable for SVG.
 */
function resolveSourceText(source) {
  if (!source) return ""
  if (typeof source === "string") return stripHTML(source)
  const { href, label, publisher } = source
  const parts = []
  if (href && label) parts.push(`${label}.`)
  if (publisher) parts.push(`${publisher}.`)
  return parts.join(" ")
}

/**
 * Inline axis/tick styles onto matching SVG elements so they render
 * correctly when the SVG is serialised outside the document.
 */
function inlineAxisStyles(svg) {
  const axisSelectors = [
    '[aria-label="x-axis tick label"]',
    '[aria-label="y-axis label"] text',
    '[aria-label="y-axis tick label"]'
  ]
  const axisStyle = {
    "font-size": "12px",
    "font-family": FONT_FAMILY,
    fill: "black"
  }
  for (const sel of axisSelectors) {
    for (const el of svg.querySelectorAll(sel)) {
      for (const [k, v] of Object.entries(axisStyle)) {
        el.style.setProperty(k, v)
      }
      // Also apply to child <text> elements
      for (const t of el.querySelectorAll("text")) {
        for (const [k, v] of Object.entries(axisStyle)) {
          t.style.setProperty(k, v)
        }
      }
    }
  }
  // Grid color
  for (const el of svg.querySelectorAll('[aria-label="y-grid"]')) {
    el.style.setProperty("color", "black")
  }
}

/**
 * Wrap text into multiple lines given a max width (approximate character-based).
 * Returns an array of strings.
 */
function wrapText(text, maxCharsPerLine) {
  if (!text) return []
  const words = text.split(/\s+/)
  const lines = []
  let current = ""
  for (const word of words) {
    if (current && (current.length + 1 + word.length) > maxCharsPerLine) {
      lines.push(current)
      current = word
    } else {
      current = current ? current + " " + word : word
    }
  }
  if (current) lines.push(current)
  return lines
}

/**
 * Create SVG <text> element with optional tspan lines.
 */
function svgTextBlock(lines, { x, y, fontSize, fontWeight, fill, lineHeight }) {
  if (!lines.length) return { el: null, height: 0 }
  const textEl = document.createElementNS("http://www.w3.org/2000/svg", "text")
  textEl.setAttribute("x", x)
  textEl.setAttribute("y", y)
  textEl.setAttribute("font-family", FONT_FAMILY)
  textEl.setAttribute("font-size", fontSize)
  if (fontWeight) textEl.setAttribute("font-weight", fontWeight)
  textEl.setAttribute("fill", fill)

  lines.forEach((line, i) => {
    const tspan = document.createElementNS("http://www.w3.org/2000/svg", "tspan")
    tspan.setAttribute("x", x)
    tspan.setAttribute("dy", i === 0 ? "0" : lineHeight)
    tspan.textContent = line
    textEl.appendChild(tspan)
  })

  const totalHeight = fontSize * 1.2 + (lines.length - 1) * parseFloat(lineHeight)
  return { el: textEl, height: totalHeight }
}

/**
 * Create a single-line SVG <text> element from an array of {text, color, fontWeight} segments.
 */
function svgRichTextLine(segments, { x, y, fontSize, defaultFill }) {
  const textEl = document.createElementNS("http://www.w3.org/2000/svg", "text")
  textEl.setAttribute("x", x)
  textEl.setAttribute("y", y)
  textEl.setAttribute("font-family", FONT_FAMILY)
  textEl.setAttribute("font-size", fontSize)
  textEl.setAttribute("fill", defaultFill)

  for (const segment of segments) {
    const tspan = document.createElementNS("http://www.w3.org/2000/svg", "tspan")
    tspan.textContent = segment.text
    if (segment.color) tspan.setAttribute("fill", segment.color)
    if (segment.fontWeight) tspan.setAttribute("font-weight", segment.fontWeight)
    textEl.appendChild(tspan)
  }
  return textEl
}

/**
 * Captures a plot container as a PNG via pure SVG composition.
 *
 * @param {HTMLElement} plotContainer - DOM element containing the Observable Plot SVG
 * @param {Object} opts
 * @param {string} opts.title
 * @param {string} opts.subtitle
 * @param {string|Object} opts.source
 * @param {string} opts.note
 * @param {string} opts.filename
 * @param {string} [opts.logoSrc] - Pre-loaded logo src (URL or data URI) to embed in the PNG
 */
export async function downloadPlotAsPng(plotContainer, { title, subtitle, source, note, filename = "plot", logoSrc }) {
  if (!plotContainer) return

  // --- 1. Clone the plot SVG ---
  const origSvg = plotContainer.querySelector("svg")
  if (!origSvg) return

  const plotSvg = origSvg.cloneNode(true)

  // Remove tooltip elements
  for (const tip of plotSvg.querySelectorAll('[aria-label="tip"]')) {
    tip.remove()
  }

  // Inline axis styles
  inlineAxisStyles(plotSvg)

  // Get plot dimensions from the original SVG
  const plotRect = origSvg.getBoundingClientRect()
  const plotW = parseFloat(plotSvg.getAttribute("width")) || plotRect.width
  const plotH = parseFloat(plotSvg.getAttribute("height")) || plotRect.height

  // Ensure the cloned SVG has a viewBox
  if (!plotSvg.getAttribute("viewBox")) {
    plotSvg.setAttribute("viewBox", `0 0 ${plotW} ${plotH}`)
  }

  // --- 2. Prepare text content ---
  // Font sizes are halved relative to on-screen CSS sizes so that when
  // rendered at SCALE=2 the output PNG matches the visual appearance.
  const titleFontSize = 24
  const subtitleFontSize = 18
  const footerFontSize = 12
  const lineHeightPx = 1.25

  const sourceText = resolveSourceText(source)
  const contentWidth = plotW + PADDING * 2
  const maxChars = Math.floor(contentWidth / (footerFontSize * 0.5))

  const titleLines = wrapText(title || "", Math.floor(contentWidth / (titleFontSize * 0.7)))
  const subtitleHasHTML = subtitle && /<[a-z]/i.test(subtitle)
  const subtitleSegments = subtitleHasHTML ? parseHTMLSegments(subtitle) : []
  const subtitleLines = subtitleHasHTML ? [] : wrapText(subtitle ? stripHTML(subtitle) : "", maxChars)
  const hasSubtitle = subtitleHasHTML ? subtitleSegments.length > 0 : subtitleLines.length > 0
  const sourceLines = wrapText(sourceText ? `Source: ${sourceText}` : "", maxChars)
  const noteLines = wrapText(note || "", maxChars)

  // --- 3. Fetch logo & fonts in parallel ---
  const [logoDataURI, fontRegularURI, fontBoldURI] = await Promise.all([
    toEmbeddableDataURI(logoSrc),
    fetchAsDataURI(FONT_REGULAR_URL, "font/woff2"),
    fetchAsDataURI(FONT_BOLD_URL, "font/woff2")
  ])

  // --- 4. Calculate layout ---
  let cursorY = PADDING

  const titleBlockH = titleLines.length
    ? titleFontSize * lineHeightPx * titleLines.length
    : 0
  cursorY += titleBlockH

  if (hasSubtitle) {
    cursorY += 4 // gap
  }
  const subtitleBlockH = hasSubtitle
    ? subtitleFontSize * lineHeightPx * (subtitleHasHTML ? 1 : subtitleLines.length)
    : 0
  cursorY += subtitleBlockH

  cursorY += 16 // gap before plot
  const plotY = cursorY
  cursorY += plotH

  cursorY += 20 // gap after plot
  const footerY = cursorY
  const sourceBlockH = sourceLines.length
    ? footerFontSize * lineHeightPx * sourceLines.length
    : 0
  cursorY += sourceBlockH
  if (noteLines.length && sourceLines.length) cursorY += 4
  const noteBlockH = noteLines.length
    ? footerFontSize * lineHeightPx * noteLines.length
    : 0
  cursorY += noteBlockH

  cursorY += PADDING // bottom padding
  const totalW = contentWidth
  const totalH = cursorY

  // --- 5. Build wrapper SVG ---
  const ns = "http://www.w3.org/2000/svg"
  const wrapper = document.createElementNS(ns, "svg")
  wrapper.setAttribute("xmlns", ns)
  wrapper.setAttribute("xmlns:xlink", "http://www.w3.org/1999/xlink")
  wrapper.setAttribute("width", totalW)
  wrapper.setAttribute("height", totalH)
  wrapper.setAttribute("viewBox", `0 0 ${totalW} ${totalH}`)

  // Font-face style block
  let fontFaceCSS = ""
  if (fontRegularURI) {
    fontFaceCSS += `
      @font-face {
        font-family: 'Italian Plate';
        font-weight: 400;
        src: url('${fontRegularURI}') format('woff2');
      }
    `
  }
  if (fontBoldURI) {
    fontFaceCSS += `
      @font-face {
        font-family: 'Italian Plate';
        font-weight: 700;
        src: url('${fontBoldURI}') format('woff2');
      }
    `
  }
  if (fontFaceCSS) {
    const styleEl = document.createElementNS(ns, "style")
    styleEl.textContent = fontFaceCSS
    wrapper.appendChild(styleEl)
  }

  // White background
  const bg = document.createElementNS(ns, "rect")
  bg.setAttribute("width", totalW)
  bg.setAttribute("height", totalH)
  bg.setAttribute("fill", COLORS.bg)
  wrapper.appendChild(bg)

  // Title
  let textY = PADDING + titleFontSize
  if (titleLines.length) {
    const { el } = svgTextBlock(titleLines, {
      x: PADDING,
      y: textY,
      fontSize: titleFontSize,
      fontWeight: "700",
      fill: COLORS.title,
      lineHeight: `${titleFontSize * lineHeightPx}px`
    })
    if (el) wrapper.appendChild(el)
    textY += titleBlockH
  }

  // Subtitle
  if (hasSubtitle) {
    textY += 4
    if (subtitleHasHTML && subtitleSegments.length) {
      const el = svgRichTextLine(subtitleSegments, {
        x: PADDING,
        y: textY,
        fontSize: subtitleFontSize,
        defaultFill: COLORS.subtitle
      })
      wrapper.appendChild(el)
    } else if (subtitleLines.length) {
      const { el } = svgTextBlock(subtitleLines, {
        x: PADDING,
        y: textY,
        fontSize: subtitleFontSize,
        fontWeight: "400",
        fill: COLORS.subtitle,
        lineHeight: `${subtitleFontSize * lineHeightPx}px`
      })
      if (el) wrapper.appendChild(el)
    }
  }

  // Plot SVG (nested via <g> with transform)
  plotSvg.removeAttribute("width")
  plotSvg.removeAttribute("height")
  plotSvg.setAttribute("x", PADDING)
  plotSvg.setAttribute("y", plotY)
  plotSvg.setAttribute("width", plotW)
  plotSvg.setAttribute("height", plotH)
  wrapper.appendChild(plotSvg)

  // Footer: source + note (left) and logo (right)
  let footerCursorY = footerY + footerFontSize
  if (sourceLines.length) {
    const { el } = svgTextBlock(sourceLines, {
      x: PADDING,
      y: footerCursorY,
      fontSize: footerFontSize,
      fontWeight: "400",
      fill: COLORS.source,
      lineHeight: `${footerFontSize * lineHeightPx}px`
    })
    if (el) wrapper.appendChild(el)
    footerCursorY += sourceBlockH
  }

  if (noteLines.length) {
    if (sourceLines.length) footerCursorY += 4
    const { el } = svgTextBlock(noteLines, {
      x: PADDING,
      y: footerCursorY,
      fontSize: footerFontSize,
      fontWeight: "400",
      fill: COLORS.note,
      lineHeight: `${footerFontSize * lineHeightPx}px`
    })
    if (el) wrapper.appendChild(el)
  }

  // Logo position (drawn directly on canvas later for full resolution)
  const logoSize = 20
  const logoX = totalW - PADDING - logoSize
  const logoY = footerY

  // --- 6. Render pipeline: SVG → Image → Canvas → PNG → download ---
  const serializer = new XMLSerializer()
  const svgString = serializer.serializeToString(wrapper)
  const svgBlob = new Blob([svgString], { type: "image/svg+xml;charset=utf-8" })
  const svgUrl = URL.createObjectURL(svgBlob)

  return new Promise((resolve) => {
    const img = new Image()
    img.onload = () => {
      const canvas = document.createElement("canvas")
      canvas.width = totalW * SCALE
      canvas.height = totalH * SCALE
      const ctx = canvas.getContext("2d")
      ctx.scale(SCALE, SCALE)
      ctx.drawImage(img, 0, 0, totalW, totalH)
      URL.revokeObjectURL(svgUrl)

      // Draw logo directly on canvas at full resolution (bypasses SVG rasterization)
      if (logoDataURI) {
        const logoImg = new Image()
        logoImg.onload = () => {
          ctx.drawImage(logoImg, logoX, logoY, logoSize, logoSize)
          finalize()
        }
        logoImg.onerror = () => finalize()
        logoImg.src = logoDataURI
        return
      }

      finalize()

      function finalize() {

        canvas.toBlob((blob) => {
          if (!blob) { resolve(); return }
          const a = document.createElement("a")
          a.href = URL.createObjectURL(blob)
          a.download = `${filename}.png`
          a.click()
          URL.revokeObjectURL(a.href)
          resolve()
        }, "image/png")
      }
    }
    img.onerror = () => {
      URL.revokeObjectURL(svgUrl)
      console.error("SVG → PNG export: failed to load SVG as image")
      resolve()
    }
    img.src = svgUrl
  })
}
