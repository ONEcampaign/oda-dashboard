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
  const [searchQuery, setSearchQuery] = React.useState("")
  const [highlightedIndex, setHighlightedIndex] = React.useState(-1)
  const containerRef = React.useRef(null)
  const buttonRef = React.useRef(null)
  const listRef = React.useRef(null)
  const searchInputRef = React.useRef(null)
  const searchRef = React.useRef({ term: "", timeout: null })

  const selectedIndex = normalized.findIndex((option) => option.value === value)
  const selected = selectedIndex >= 0 ? normalized[selectedIndex] : undefined

  const filteredOptions = React.useMemo(
    () => searchQuery
      ? normalized.filter(o => o.label.toLowerCase().includes(searchQuery.toLowerCase()))
      : normalized,
    [normalized, searchQuery]
  )

  const toggleOpen = () => {
    if (disabled) return
    setOpen((prev) => !prev)
  }

  const close = () => {
    setOpen(false)
    setHighlightedIndex(-1)
    setSearchQuery("")
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

  // When the dropdown opens, focus the search input and set the initial highlighted index
  React.useEffect(() => {
    if (!open) return
    searchInputRef.current?.focus()
    if (filteredOptions.length === 0) {
      setHighlightedIndex(-1)
      return
    }
    setHighlightedIndex(() => {
      const filteredSelectedIndex = filteredOptions.findIndex(o => o.value === value)
      return filteredSelectedIndex >= 0 ? filteredSelectedIndex : 0
    })
  }, [open])

  // When the search query changes, reset highlight to the first result
  React.useEffect(() => {
    if (!open) return
    setHighlightedIndex(filteredOptions.length > 0 ? 0 : -1)
  }, [searchQuery])

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
    const total = filteredOptions.length
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

    const matchIndex = filteredOptions.findIndex((option) =>
      option.label.toLowerCase().startsWith(nextTerm)
    )
    if (matchIndex >= 0) {
      if (!open) setOpen(true)
      setHighlightedIndex(matchIndex)
    }
  }

  // Keyboard handler for the trigger button
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
        if (open && highlightedIndex >= 0 && filteredOptions[highlightedIndex]) {
          handleSelect(filteredOptions[highlightedIndex])
        } else {
          setOpen(true)
        }
        break
      case "Escape":
        close()
        break
      case "Home":
        event.preventDefault()
        if (filteredOptions.length) {
          if (!open) setOpen(true)
          setHighlightedIndex(0)
        }
        break
      case "End":
        event.preventDefault()
        if (filteredOptions.length) {
          if (!open) setOpen(true)
          setHighlightedIndex(filteredOptions.length - 1)
        }
        break
      default:
        handleTypeAhead(event.key)
    }
  }

  // Keyboard handler for the search input — arrow keys and Enter navigate/select,
  // all other keys are handled natively by the input (typing to filter)
  const handleSearchKeyDown = (event) => {
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
        if (highlightedIndex >= 0 && filteredOptions[highlightedIndex]) {
          handleSelect(filteredOptions[highlightedIndex])
        }
        break
      case "Escape":
        close()
        buttonRef.current?.focus()
        break
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
          <div className="absolute z-10 mt-2 w-full rounded-md border border-slate-200 bg-white shadow-lg">
            <div className="border-b border-slate-100 p-2">
              <input
                ref={searchInputRef}
                type="text"
                value={searchQuery}
                onChange={e => setSearchQuery(e.target.value)}
                onKeyDown={handleSearchKeyDown}
                placeholder="Search..."
                className="w-full rounded border border-slate-200 px-3 py-1.5 text-sm text-slate-700 uppercase outline-none focus:border-slate-400"
                style={{ fontFamily: "Colfax, Helvetica, sans-serif" }}
              />
            </div>
            <ul
              ref={listRef}
              className="max-h-56 overflow-y-auto"
              role="listbox"
              tabIndex={-1}
            >
              {filteredOptions.map((option, index) => {
                const isSelected = option.value === value
                const isHighlighted = index === highlightedIndex
                return (
                  <li key={option.value}>
                    <button
                      type="button"
                      data-index={index}
                      style={{ fontFamily: "Colfax, Helvetica, sans-serif" }}
                      className={`flex w-full justify-start px-4 py-2 text-md uppercase transition-colors hover:cursor-pointer
                      ${isSelected ? "font-bold" : ""}
                      ${isHighlighted
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
              {filteredOptions.length === 0 && (
                <li className="px-4 py-2 text-sm text-slate-500">No results</li>
              )}
            </ul>
          </div>
        )}
      </div>
    </div>
  )
}
