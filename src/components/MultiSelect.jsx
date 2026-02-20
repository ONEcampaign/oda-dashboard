import React from "npm:react"

function normalizeOption(option) {
  if (option == null) return null
  if (typeof option === "string") {
    return {label: option, value: option, disabled: false}
  }
  if (typeof option === "object" && option.value != null) {
    return {
      label: option.label ?? String(option.value),
      value: option.value,
      disabled: Boolean(option.disabled)
    }
  }
  return null
}

export function MultiSelect({
  label,
  options = [],
  value = [],
  onChange,
  maxSelected = 5,
  disabledValues = [],
  placeholder = "Search..."
}) {
  const normalizedOptions = React.useMemo(() => {
    return options
      .map(normalizeOption)
      .filter((option) => option && option.label && option.value != null)
  }, [options])

  const optionLabelMap = React.useMemo(() => {
    const map = new Map()
    for (const option of normalizedOptions) {
      map.set(option.value, option.label)
    }
    return map
  }, [normalizedOptions])

  const selectedSet = React.useMemo(() => new Set(value ?? []), [value])
  const disabledSet = React.useMemo(
    () => new Set(disabledValues ?? []),
    [disabledValues]
  )

  const [query, setQuery] = React.useState("")

  const filteredOptions = React.useMemo(() => {
    const normalizedQuery = query.trim().toLowerCase()
    return normalizedOptions.filter((option) => {
      if (selectedSet.has(option.value)) return false
      if (disabledSet.has(option.value)) return false
      if (!normalizedQuery) return true
      return option.label.toLowerCase().includes(normalizedQuery)
    })
  }, [normalizedOptions, selectedSet, disabledSet, query])

  const limitReached = value.length >= maxSelected

  const commit = (next) => {
    if (!onChange) return
    onChange(next)
  }

  const addValue = (nextValue) => {
    if (nextValue == null) return
    if (disabledSet.has(nextValue)) return
    if (selectedSet.has(nextValue)) return
    if (limitReached) return
    const optionMeta = normalizedOptions.find((option) => option.value === nextValue)
    if (optionMeta?.disabled) return
    commit([...value, nextValue])
    setQuery("")
  }

  const removeValue = (targetValue) => {
    commit(value.filter((item) => item !== targetValue))
  }

  const handleKeyDown = (event) => {
    if (event.key === "Enter" && filteredOptions[0]) {
      event.preventDefault()
      addValue(filteredOptions[0].value)
    } else if (event.key === "Backspace" && !query && value.length) {
      event.preventDefault()
      removeValue(value[value.length - 1])
    }
  }

  return (
    <div className>
      {label && (
        <label
          className="mb-1 block text-sm tracking-wide text-slate-black"
          style={{ fontFamily: "Colfax, Helvetica, sans-serif" }}
        >
          {label}
        </label>
      )}
      <div className="rounded-md border border-slate-300 bg-white p-3">
        <div className="flex flex-wrap gap-2">
          {value.map((item) => (
            <span
              key={item}
              className="inline-flex items-center gap-2 rounded-full bg-slate-900 px-3 py-1 text-sm font-semibold text-white"
            >
              {optionLabelMap.get(item) ?? item}
              <button
                type="button"
                className="text-xs text-white/70 transition hover:text-white"
                onClick={() => removeValue(item)}
              >
                ×
              </button>
            </span>
          ))}
          { placeholder ?
              <input
                  type="text"
                  value={query}
                  onChange={(event) => setQuery(event.target.value)}
                  onKeyDown={handleKeyDown}
                  placeholder={limitReached ? null : placeholder}
                  disabled={limitReached}
                  className={limitReached ? "hidden" : "flex-1 border-none bg-transparent text-sm text-slate-900 placeholder:text-slate-400 focus:outline-none"}
              />
              : null
          }
        </div>
        {filteredOptions.length > 0 && (
          <ul className="mt-3 max-h-25 divide-y divide-slate-100 overflow-auto rounded-md border border-slate-200">
            {filteredOptions.map((option) => {
              const optionDisabled = limitReached || option.disabled
              return (
                <li key={option.value}>
                  <button
                    type="button"
                    onClick={() => addValue(option.value)}
                    disabled={optionDisabled}
                    aria-disabled={optionDisabled}
                    className={`flex w-full items-center justify-between px-3 py-2 text-left text-sm transition ${
                      optionDisabled
                        ? "cursor-not-allowed text-slate-200"
                        : "text-slate-700 hover:bg-slate-50 hover:cursor-pointer"
                    }`}
                  >
                    <span>{option.label}</span>
                  </button>
                </li>
              )
            })}
          </ul>
        )}
      </div>
    </div>
  )
}
