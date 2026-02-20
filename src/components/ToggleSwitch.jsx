import React from "npm:react"

const defaultOptions = [
  { label: "Off", value: false },
  { label: "On", value: true }
]

export function ToggleSwitch({
  label,
  value,
  options = defaultOptions,
  onChange,
  disabled = false,
  className = "",
}) {
  const normalizedOptions = options.length >= 2 ? options : defaultOptions
  const [leftOption, rightOption] = normalizedOptions
  const isRightSelected = value === rightOption.value
  const isLeftSelected = value === leftOption.value || !isRightSelected

  const commit = (nextValue) => {
    if (disabled) return
    onChange?.(nextValue)
  }

  const toggle = () => {
    commit(isLeftSelected ? rightOption.value : leftOption.value)
  }

  const handleKeyDown = (event) => {
    if (disabled) return
    if (event.key === "ArrowLeft") {
      event.preventDefault()
      commit(leftOption.value)
    } else if (event.key === "ArrowRight") {
      event.preventDefault()
      commit(rightOption.value)
    }
  }

  return (
    <div className={`toggle ${className}`}>
      {label && (
        <label
            className="mb-2 block text-sm tracking-wide text-slate-black"
            style={{ fontFamily: "Colfax, Helvetica, sans-serif" }}
        >
          {label}
        </label>
      )}
      <div className="flex items-center gap-3">
        <span
            className={`text-md uppercase text-slate-black ${isLeftSelected ? "font-bold" : "font-medium"}`}
            style={{ fontFamily: "Colfax, Helvetica, sans-serif" }}
        >
          {leftOption.label}
        </span>
        <button
          type="button"
          role="switch"
          aria-checked={isRightSelected}
          aria-label={label}
          disabled={disabled}
          onClick={toggle}
          onKeyDown={handleKeyDown}
          className={`relative h-6 w-12 rounded-full transition-colors hover:cursor-pointer ${
            disabled
              ? "cursor-not-allowed bg-slate-200"
              : "bg-slate-900"
          }`}
        >
          <span
            className={`absolute top-1 left-1 h-4 w-4 rounded-full bg-white shadow transition-transform ${
              isRightSelected ? "translate-x-6" : "translate-x-0"
            }`}
          />
        </button>
        <span
            className={`text-md uppercase text-slate-black ${isRightSelected ? "font-bold" : "font-medium"}`}
            style={{ fontFamily: "Colfax, Helvetica, sans-serif" }}
        >
          {rightOption.label}
        </span>
      </div>
    </div>
  )
}
