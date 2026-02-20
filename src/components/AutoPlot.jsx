import * as React from "npm:react"

export function AutoPlot({data, plotFn}) {
  const ref = React.useRef(null)
  const [width, setWidth] = React.useState(0)

  React.useEffect(() => {
    if (!ref.current) return
    const observer = new ResizeObserver(entries => setWidth(entries[0].contentRect.width))
    observer.observe(ref.current)
    setWidth(ref.current.clientWidth)
    return () => observer.disconnect()
  }, [])

  React.useEffect(() => {
    const node = ref.current
    if (!node || !width || !data?.length) {
      if (node) node.innerHTML = ""
      return
    }
    const plotEl = plotFn(width)
    node.innerHTML = ""
    node.appendChild(plotEl)
    return () => { if (plotEl?.remove) plotEl.remove() }
  }, [data, width, plotFn])

  return <div ref={ref} className="h-full w-full" />
}
