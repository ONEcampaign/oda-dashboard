import React from "npm:react"

const clamp = (value, min, max) => Math.min(Math.max(value, min), max)

export function RangeInput({
  min = 0,
  max = 100,
  step = 1,
  value,
  label = "",
  onChange
}) {
  const initial = React.useMemo(() => value ?? [min, max], [value, min, max])
  const [range, setRange] = React.useState(initial)

  React.useEffect(() => {
    setRange(initial)
  }, [initial])

  const emit = React.useCallback(
    (next) => {
      setRange(next)
      onChange?.(next)
    },
    [onChange]
  )

  const updateMin = (next) => {
    const minValue = clamp(Number(next), min, max)
    emit([Math.min(minValue, range[1]), range[1]])
  }

  const updateMax = (next) => {
    const maxValue = clamp(Number(next), min, max)
    emit([range[0], Math.max(maxValue, range[0])])
  }

  const percent = (val) => ((val - min) / (max - min || 1)) * 100

  return (
    <div className="range-input flex w-full flex-col gap-3 bg-white max-w-2xl">
      {label && (
        <div
          className="flex items-center justify-between text-sm tracking-wide text-slate-black"
          style={{ fontFamily: "Colfax, Helvetica, sans-serif" }}
        >
          <span>
            {label}
          </span>
        </div>
      )}
      <div className="flex items-center gap-3">
        <input
          type="number"
          value={range[0]}
          min={min}
          max={range[1]}
          step={step}
          onChange={(event) => updateMin(event.target.value)}
          className="w-20 rounded-md border border-slate-200 px-2 py-1 text-md uppercase font-bold"
          style={{ fontFamily: "Colfax, Helvetica, sans-serif" }}
        />
        <div className="relative flex-1 h-6">
          <div className="absolute inset-x-0 top-1/2 -translate-y-1/2 rounded-full bg-slate-200" style={{ height: 4 }} />
          <div
            className="absolute top-1/2 -translate-y-1/2 rounded-full bg-slate-900"
            style={{ left: `${percent(range[0])}%`, right: `${100 - percent(range[1])}%`, height: 4 }}
          />
          <input
            type="range"
            min={min}
            max={max}
            step={step}
            value={range[0]}
            aria-label="Minimum value"
            onChange={(event) => updateMin(event.target.value)}
          />
          <input
            type="range"
            min={min}
            max={max}
            step={step}
            value={range[1]}
            aria-label="Maximum value"
            onChange={(event) => updateMax(event.target.value)}
          />
        </div>
        <input
          type="number"
          value={range[1]}
          min={range[0]}
          max={max}
          step={step}
          onChange={(event) => updateMax(event.target.value)}
          className="w-20 rounded-md border border-slate-200 px-2 py-1 text-md uppercase font-bold"
          style={{ fontFamily: "Colfax, Helvetica, sans-serif" }}
        />
      </div>
    </div>
  )
}
