import * as React from "npm:react"

export function AutoTable({data, tableFn}) {
  const ref = React.useRef(null)

  React.useEffect(() => {
    const node = ref.current
    if (!node || !data?.length) {
      if (node) node.innerHTML = ""
      return
    }
    const tableEl = tableFn()
    node.innerHTML = ""
    node.appendChild(tableEl)
    return () => { if (tableEl?.remove) tableEl.remove() }
  }, [data, tableFn])

  return <div ref={ref} className="w-full overflow-x-auto" />
}
