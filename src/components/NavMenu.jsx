const NAV_ITEMS = [
  { id: "financing", label: "FINANCING", href: "./" },
  { id: "recipients", label: "RECIPIENTS", href: "./recipients.html" },
  { id: "sectors", label: "SECTORS", href: "./sectors.html" },
  { id: "gender", label: "GENDER", href: "./gender.html" },
  { id: "faqs", label: "FAQs", href: "./faqs.html" }
]

export function NavMenu({ currentPage }) {
  return (
    <div
      className="mt-0 mb-6 flex flex-wrap justify-end gap-4 text-lg font-semibold sm:mb-16 sm:gap-10 sm:text-xl"
      style={{ fontFamily: "Colfax, Helvetica, sans-serif" }}
      aria-label="Primary"
    >
      {NAV_ITEMS.map((item) => {
        const isActive = item.id === currentPage
        return (
          <a
            key={item.id}
            href={item.href}
            className={`group flex flex-col items-center gap-.5 tracking-wide transition-colors ${
              isActive ? "text-slate-900" : "text-slate-400 hover:text-slate-700"
            }`}
            aria-current={isActive ? "page" : undefined}
          >
            <span>{item.label}</span>
            <span
              aria-hidden
              className={`h-0.5 rounded-full transition-all duration-150 ${
                isActive
                  ? "w-full bg-slate-900"
                  : "w-1 ml-0 bg-slate-300 group-hover:w-full group-hover:bg-slate-500"
              }`}
            />
          </a>
        )
      })}
    </div>
  )
}
