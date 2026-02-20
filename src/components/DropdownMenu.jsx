import React from "npm:react"

const normalizeOptions = (options) => {
  if (!options) return []
  if (options instanceof Map) {
    return Array.from(options.entries()).map(([label, value]) => ({ label, value }))
  }
  return options.map((option) =>
    typeof option === "string"
      ? { label: option, value: option }
      : { label: option.label, value: option.value }
  )
}

export function DropdownMenu({
  label,
  options = [],
  value,
  placeholder = "Select",
  onChange,
  disabled = false,
  className = "",
}) {
  const normalized = React.useMemo(() => normalizeOptions(options), [options])
  const [open, setOpen] = React.useState(false)
  const [highlightedIndex, setHighlightedIndex] = React.useState(-1)
  const containerRef = React.useRef(null)
  const buttonRef = React.useRef(null)
  const listRef = React.useRef(null)
  const searchRef = React.useRef({ term: "", timeout: null })

  const selectedIndex = normalized.findIndex((option) => option.value === value)
  const selected = selectedIndex >= 0 ? normalized[selectedIndex] : undefined

  const toggleOpen = () => {
    if (disabled) return
    setOpen((prev) => !prev)
  }

  const close = () => {
    setOpen(false)
    setHighlightedIndex(-1)
    if (searchRef.current.timeout) {
      clearTimeout(searchRef.current.timeout)
    }
    searchRef.current.term = ""
  }

  React.useEffect(() => {
    function handleClickOutside(event) {
      if (!containerRef.current) return
      if (!containerRef.current.contains(event.target)) {
        close()
      }
    }

    function handleEscape(event) {
      if (event.key === "Escape") {
        close()
        buttonRef.current?.focus()
      }
    }

    document.addEventListener("mousedown", handleClickOutside)
    document.addEventListener("keydown", handleEscape)
    return () => {
      document.removeEventListener("mousedown", handleClickOutside)
      document.removeEventListener("keydown", handleEscape)
      if (searchRef.current.timeout) {
        clearTimeout(searchRef.current.timeout)
      }
    }
  }, [])

  React.useEffect(() => {
    if (!open) return
    if (normalized.length === 0) {
      setHighlightedIndex(-1)
      return
    }
    setHighlightedIndex((prev) => {
      if (prev >= 0 && prev < normalized.length) return prev
      return selectedIndex >= 0 ? selectedIndex : 0
    })
  }, [open, selectedIndex, normalized.length])

  React.useEffect(() => {
    if (!open || highlightedIndex < 0) return
    const optionNode = listRef.current?.querySelector(
      `[data-index="${highlightedIndex}"]`
    )
    optionNode?.scrollIntoView({ block: "nearest" })
  }, [open, highlightedIndex])

  const handleSelect = (option) => {
    onChange?.(option.value)
    close()
    buttonRef.current?.focus()
  }

  const handleArrowNavigation = (direction) => {
    if (!open) {
      setOpen(true)
      return
    }
    const total = normalized.length
    if (total === 0) return
    setHighlightedIndex((prev) => {
      const next = prev < 0 ? 0 : (prev + direction + total) % total
      return next
    })
  }

  const handleTypeAhead = (char) => {
    const isValidChar = char.length === 1 && /[\w\s]/i.test(char)
    if (!isValidChar) return
    const lower = char.toLowerCase()
    const nextTerm = searchRef.current.term + lower
    searchRef.current.term = nextTerm
    if (searchRef.current.timeout) clearTimeout(searchRef.current.timeout)
    searchRef.current.timeout = setTimeout(() => {
      searchRef.current.term = ""
    }, 600)

    const matchIndex = normalized.findIndex((option) =>
      option.label.toLowerCase().startsWith(nextTerm)
    )
    if (matchIndex >= 0) {
      if (!open) setOpen(true)
      setHighlightedIndex(matchIndex)
    }
  }

  const handleKeyDown = (event) => {
    switch (event.key) {
      case "ArrowDown":
        event.preventDefault()
        handleArrowNavigation(1)
        break
      case "ArrowUp":
        event.preventDefault()
        handleArrowNavigation(-1)
        break
      case "Enter":
        event.preventDefault()
        if (open && highlightedIndex >= 0 && normalized[highlightedIndex]) {
          handleSelect(normalized[highlightedIndex])
        } else {
          setOpen(true)
        }
        break
      case "Escape":
        close()
        break
      case "Home":
        event.preventDefault()
        if (normalized.length) {
          if (!open) setOpen(true)
          setHighlightedIndex(0)
        }
        break
      case "End":
        event.preventDefault()
        if (normalized.length) {
          if (!open) setOpen(true)
          setHighlightedIndex(normalized.length - 1)
        }
        break
      default:
        handleTypeAhead(event.key)
    }
  }

  const labelStyle = {
    display: "-webkit-box",
    WebkitLineClamp: 2,
    WebkitBoxOrient: "vertical",
    overflow: "hidden"
  }

  const baseButtonClasses = "flex w-full items-start justify-between gap-2 rounded-md border px-4 py-2 text-left hover:cursor-pointer"
  const stateClasses = disabled
    ? "cursor-not-allowed border-slate-200 bg-slate-50 text-slate-400"
    : "border-slate-300 bg-white text-slate-900 hover:border-slate-400"

  return (
    <div className={`dropdown ${className} max-w-75 min-w-60`} ref={containerRef}>
      {label && (
        <label
            className="mb-1 block text-sm tracking-wide text-slate-black"
            style={{ fontFamily: "Colfax, Helvetica, sans-serif" }}
        >
          {label}
        </label>
      )}
      <div className="relative">
        <button
          type="button"
          ref={buttonRef}
          className={`${baseButtonClasses} ${stateClasses}`}
          onClick={toggleOpen}
          onKeyDown={handleKeyDown}
          aria-haspopup="listbox"
          aria-expanded={open}
          disabled={disabled}
        >
          <span
              className="text-md uppercase font-semibold flex-1 text-left"
              style={{ fontFamily: "Colfax, Helvetica, sans-serif", ...labelStyle }}
          >
              {selected?.label ?? placeholder}
          </span>
          <svg
            className={`h-4 w-4 transition-transform ${open ? "rotate-180" : "rotate-0"}`}
            viewBox="0 0 20 20"
            fill="none"
            xmlns="http://www.w3.org/2000/svg"
          >
            <path
              d="M5 7.5L10 12.5L15 7.5"
              stroke="currentColor"
              strokeWidth="1.5"
              strokeLinecap="round"
              strokeLinejoin="round"
            />
          </svg>
        </button>
        {open && (
          <ul
            ref={listRef}
            className="absolute z-10 mt-2 max-h-64 w-full overflow-y-auto rounded-md border border-slate-200 bg-white shadow-lg"
            role="listbox"
            tabIndex={-1}
            onKeyDown={handleKeyDown}
          >
            {normalized.map((option, index) => {
              const isSelected = option.value === value
              const isHighlighted = index === highlightedIndex
              return (
                <li key={option.value}>
                  <button
                    type="button"
                    data-index={index}
                    style={{ fontFamily: "Colfax, Helvetica, sans-serif" }}
                    className={`flex w-full justify-start px-4 py-2 text-md uppercase transition-colors hover:cursor-pointer
                    ${
                      isSelected
                          ? "font-bold"
                          : ""
                    }
                    ${
                      isHighlighted
                          ? "bg-slate-100 text-slate-900"
                          : "text-slate-600 hover:bg-slate-50 hover:text-slate-900"
                    }`}
                    onClick={() => handleSelect(option)}
                    onMouseEnter={() => setHighlightedIndex(index)}
                    role="option"
                    aria-selected={isSelected}
                    >
                    <span className="flex-1 text-left" style={labelStyle}>{option.label}</span>
                  </button>
                </li>
              )
            })}
            {normalized.length === 0 && (
              <li className="px-4 py-2 text-sm text-slate-500">No options</li>
            )}
          </ul>
        )}
      </div>
    </div>
  )
}
