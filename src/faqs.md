```js
import * as React from "npm:react"
import {NavMenu} from "./components/NavMenu.js"
import {generateList} from "./js/utils.js"
import "./js/embed.js"

const donorMapping = await FileAttachment("./data/analysis_tools/donors.json").json()
const recipientMapping = await FileAttachment("./data/analysis_tools/recipients.json").json()
const sectorMapping = await FileAttachment("./data/analysis_tools/sectors.json").json()
```

```jsx
function GeneratedList({data, mode}) {
  const ref = React.useRef(null)
  React.useEffect(() => {
    if (!ref.current) return
    const el = generateList(data, mode)
    ref.current.innerHTML = ""
    ref.current.appendChild(el)
  }, [data, mode])
  return <div ref={ref} />
}

function App() {
  return (
      <div className="mx-auto w-full max-w-6xl space-y-6 px-0 py-14 sm:space-y-12 sm:px-6 sm:py-10">
        <NavMenu currentPage="faqs" />
          <div
              className="space-y-4 px-4 py-2 text-md sm:px-6 lg:px-25 lg:py-10 [&_a]:text-indigo-500 [&_a]:underline [&_a:hover]:underline [&_a:focus]:underline [&_a:visited]:text-indigo-500"
              style={{ fontFamily: "Colfax, Helvetica, sans-serif" }}
          >
              <h2 className="font-bold text-xl mt-8 mb-2">What is the ODA Dashboard?</h2>
              <p>
                ONE's ODA Dashboard presents Official Development Assistance (ODA) in an accessible format, allowing users to
                explore trends and gain insights, regardless of their ODA knowledge. It is built using ONE's methodology and
                custom Python tools for processing the data. For an introduction to ODA and a detailed explanation of our
                approach, visit the <a className="underline" href="https://one-campaign.observablehq.cloud/oda-cookbook/">ODA Cookbook</a>.
              </p>
              <p>The dashboard is divided into four tabs:</p>
              <p>
                <strong>Financing</strong> offers data on various ODA indicators from the perspective of provider
                countries and country groups. Use this tab to answer questions like:
              </p>
              <ul className="list-disc pl-6 text-base text-slate-700 space-y-1">
                <li>How much aid does <em>Country X</em> provide?</li>
                <li>Is <em>Country X</em> meeting the 0.7% GNI target for its ODA contributions?</li>
              </ul>
              <p>
                <strong>Recipients</strong> shows ODA flows from providers to recipient countries and groups. This tab
                is useful if you're interested in:
              </p>
              <ul className="list-disc pl-6 text-base text-slate-700 space-y-1">
                <li>How much ODA does <em>Country X</em> give directly to <em>Country Y</em>?</li>
                <li>How much ODA does <em>Country X</em> channel to <em>Country Y</em> via multilateral organisations?</li>
              </ul>
              <p>
                <strong>Sectors</strong> breaks down ODA data by economic sectors, which can be broken down into
                sub-sectors. Use this tab to explore questions like:
              </p>
              <ul className="list-disc pl-6 text-base text-slate-700 space-y-1">
                <li>How much ODA does <em>Country X</em> allocate to humanitarian aid?</li>
                <li>How much ODA does <em>Country Y</em> receive for health?</li>
                <li>How much ODA does <em>Country X</em> direct to <em>Country Y</em>'s education sector?</li>
              </ul>
              <p>
                <strong>Gender</strong> categorises ODA by whether it targets gender equality as a policy objective.
                This tab helps you explore questions such as:
              </p>
              <ul className="list-disc pl-6 text-base text-slate-700 space-y-1">
                <li>How much ODA from <em>Country X</em> targets gender as a principal or secondary goal?</li>
                <li>What share of ODA received by <em>Country Y</em> focuses on gender equality?</li>
              </ul>
              <h2 className="font-bold text-xl mt-8 mb-2">Where does the data come from?</h2>
              <p>
                ODA data is retrieved from the OECD Data Explorer API via the{" "}
                <a className="underline" href="https://docs.one.org/tools/oda-data/">oda-data</a> python package.
              </p>
              <h2 className="font-bold text-xl mt-8 mb-2">How is the data transformed?</h2>
              <p>
                ODA figures are first obtained in current US Dollars and converted into other currencies and constant prices via{" "}
                <a className="underline" href="https://github.com/jm-rivera/pydeflate">pydeflate</a>.
              </p>
              <p>
                The data preparation scripts are located in the{" "}
                <span style={{ fontFamily: "monospace" }}>src/data</span> directory of the project's{" "}
                <a className="underline" href="https://github.com/ONEcampaign/oda-dashboard">GitHub repository</a>.
              </p>
              <h2 className="font-bold text-xl mt-8 mb-2">How are sectors and sub-sectors defined?</h2>
              <p>
                The groupings are based on the <em>purpose</em> field from the Creditor Reporting System (CRS) database.
              </p>
              <h2 className="font-bold text-xl mt-8 mb-2">Who should I contact for questions and suggestions?</h2>
              <p>
                Please refer your comments to miguel.haroruiz[at]one[dot]org or jorge.rivera[at]one[dot]org.
              </p>
          </div>
    </div>
  )
}

display(<App />)
```
