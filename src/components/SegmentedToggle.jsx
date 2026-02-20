import React from "npm:react"

export function SegmentedToggle({
  label,
  options = [],
  value,
  onChange,
  disabled = false,
  disabledReason = "",
  className = ""
}) {
  const normalized = React.useMemo(() => {
    if (!Array.isArray(options) || options.length === 0) {
      return []
    }
    return options
      .filter((option) => option && typeof option === "object")
      .map((option) => ({
        label: option.label ?? String(option.value ?? ""),
        value: option.value
      }))
  }, [options])

  const fallbackValue = normalized[0]?.value
  const activeValue = normalized.some((option) => option.value === value)
    ? value
    : fallbackValue

  React.useEffect(() => {
    if (value === undefined && fallbackValue !== undefined) {
      onChange?.(fallbackValue)
    }
  }, [value, fallbackValue, onChange])

  const handleSelect = (nextValue) => {
    if (disabled || nextValue === undefined) return
    if (nextValue === activeValue) return
    onChange?.(nextValue)
  }

  const renderToggle = () => (
    <div className={`${
      disabled ? "cursor-not-allowed opacity-15" : ""
    }`}>
      {label && (
        <label
          className="mb-2 block text-sm tracking-wide text-slate-black"
          style={{ fontFamily: "Colfax, Helvetica, sans-serif" }}
        >
          {label}
        </label>
      )}
      <div
        className="flex w-full items-stretch justify-between gap-1 rounded-full border border-slate-900 bg-white p-1"
      >
        {normalized.map((option, index) => {
          const isActive = option.value === activeValue
          const first = index === 0
          const last = index === normalized.length - 1
          return (
            <button
              type="button"
              key={option.value}
              disabled={disabled}
              aria-disabled={disabled}
              onClick={() => handleSelect(option.value)}
              className={`flex-1 min-w-0 rounded-full px-2 py-2 text-xs font-semibold uppercase tracking-wide transition lg:px-4 lg:text-sm ${
                disabled ? "cursor-not-allowed" : "hover:cursor-pointer"
              } focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-slate-900 ${
                isActive
                  ? "bg-slate-900 text-white shadow"
                  : "text-slate-900 hover:bg-slate-100"
              } ${first ? "ml-0" : ""} ${last ? "mr-0" : ""}`}
            >
              {option.label}
            </button>
          )
        })}
      </div>
    </div>
  )

  if (disabled && disabledReason) {
    return (
      <div className={`${className} relative group`}>
        {renderToggle()}
            <div className="pointer-events-none absolute -top-2 left-1/2 z-10 hidden -translate-x-1/2 whitespace-nowrap rounded-md bg-slate-900 px-3 py-1 text-xs text-white opacity-0 shadow group-hover:block group-hover:opacity-100">
          {disabledReason}
          <div className="absolute left-1/2 top-full -translate-x-1/2 border-4 border-transparent border-t-slate-900" />
        </div>
      </div>
    )
  }

  return <div className={className}>{renderToggle()}</div>
}
