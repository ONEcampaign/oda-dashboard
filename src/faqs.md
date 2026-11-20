```js
import * as React from "npm:react"
import { Header } from "npm:@one-data/observable-themes/ui"
import {
    generateList,
    isEmbedded
} from "npm:@one-data/observable-themes/utils"
import {APP_TITLE, APP_DESCRIPTION, NAV_ITEMS} from "./js/config.js"

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
      <div className="mx-auto space-y-12 px-4 py-10 sm:px-8 sm:py-16 lg:px-12 lg:py-20">

          <Header appTitle={APP_TITLE} navItems={NAV_ITEMS} currentPage="faqs" />

          
          <div
              className="max-w-4xl mx-auto space-y-4 text-md [&_a]:text-indigo-500 [&_a]:underline [&_a:hover]:underline [&_a:focus]:underline [&_a:visited]:text-indigo-500"
              style={{ fontFamily: "Colfax, Helvetica, sans-serif" }}
          >
              <h2 className="font-bold text-xl mt-8 mb-2">What is the ODA Dashboard?</h2>
              <p>
                ONE's ODA Dashboard presents Official Development Assistance (ODA) in an accessible format, allowing users to
                explore trends and gain insights, regardless of their ODA knowledge. It is built using ONE's methodology and
                custom Python tools for processing the data.
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
                <a target="_blank" className="underline" href="https://docs.one.org/tools/oda-data/">oda-data</a> python package.
              </p>
              <h2 className="font-bold text-xl mt-8 mb-2">How is the data transformed?</h2>
              <p>
                ODA figures are first obtained in current US Dollars and converted into other currencies and constant prices via{" "}
                <a target="_blank" className="underline" href="https://github.com/jm-rivera/pydeflate">pydeflate</a>.
              </p>
              <p>
                The data preparation scripts are located in the{" "}
                <span style={{ fontFamily: "monospace" }}>src/data</span> directory of the project's{" "}
                <a target="_blank" className="underline" href="https://github.com/ONEcampaign/oda-dashboard">GitHub repository</a>.
              </p>
              <h2 className="font-bold text-xl mt-8 mb-2">Which measure does each tab use?</h2>
              <ul className="list-disc pl-6 text-base text-slate-700 space-y-1">
                <li><strong>Financing</strong>: net flows up to 2017 and grant equivalents from 2018, the OECD's headline measure. In-donor costs are in net flows throughout, which for these grants equal their grant equivalents, and private sector instruments are in net flows until 2022, as explained below. The charts colour each year by its measure.</li>
                <li><strong>Recipients</strong>: net disbursements, from the OECD's DAC2A table.</li>
                <li><strong>Sectors</strong> and <strong>Gender</strong>: gross disbursements, from the Creditor Reporting System (CRS).</li>
              </ul>
              <p>
                Totals for the same donor and year therefore differ between tabs. All four tabs cover ODA only. From
                2023 that includes private sector instruments, which the CRS reports in a category of their own from that
                year, so Sectors figures rise in 2023 partly for that reason. The gender marker data the Gender tab uses
                leave that category out, so Gender figures from 2023 do not include private sector instruments. Other
                official flows, which are not ODA, are left out.
              </p>
              <h2 className="font-bold text-xl mt-8 mb-2">How are donor groups defined?</h2>
              <p>
                Every group is the sum of its members, built the same way in all four tabs. DAC countries, Non-DAC
                countries, G7 countries and EU27 countries add up their member countries. EU Institutions is shown on
                its own and belongs to none of them. Because the groups add up individual countries, Non-DAC countries
                can be smaller than the OECD's own Non-DAC total, which includes amounts the OECD does not publish
                country by country.
              </p>
              <p>
                <strong>All bilateral donors</strong> is DAC countries plus Non-DAC countries. It does not include
                EU Institutions, following the OECD's headline totals: much of EU Institutions' spending is funded by
                contributions from EU member states and other donors, which their own totals already include, so adding
                it would count the same money twice. The OECD's own "DAC Members" total does add EU Institutions in full,
                so it is larger than All bilateral donors.
              </p>
              <p>
                <strong>EU27 & EU Institutions</strong> combines EU member states and EU Institutions without counting
                members' contributions to the institutions twice. The Financing and Recipients tabs keep only the share of
                EU Institutions' spending not funded by EU members. The Sectors tab removes members' multilateral spending
                that passes through EU institutions. The Gender tab adds the two together, because members'
                contributions to the institutions are not part of that data. The Financing tab shows this group up to
                2024, the last year for which members' contributions are reported.
              </p>
              <h2 className="font-bold text-xl mt-8 mb-2">How are recipient groups defined?</h2>
              <p>
                The Recipients tab uses the groups the OECD publishes in its DAC2A table. The Sectors and Gender tabs
                build regions from the region the CRS records for each recipient.
              </p>
              <p>
                "Africa, unspecified" and similar entries are aid to more than one country in an area that cannot be
                split between them, which some OECD tables call "regional". "Africa" is the full total for the area,
                including its unspecified aid. Aid to developing countries that cannot be attributed to any country or
                region is "ODA eligible countries, unspecified", part of "ODA eligible countries". Country names follow
                each source, so a few are spelled slightly differently between tabs.
              </p>
              <p>
                Income groups follow the World Bank classification in every tab. The Sectors and Gender tabs use the July
                2026 classification (fiscal year 2027) and apply it to every year, as the OECD's own groups in the
                Recipients tab do. Least Developed Countries follow the UN list and overlap with the income groups.
                Territories the World Bank does not classify appear as "Countries not classified by the World Bank",
                and aid to regions or unspecified recipients as "Unallocated by income".
              </p>
              <h2 className="font-bold text-xl mt-8 mb-2">How is imputed multilateral aid calculated?</h2>
              <p>
                A donor's core contribution to a multilateral organisation is spread across sectors and recipients in
                the same proportions as that organisation's own spending over a three-year period. Those proportions
                cover both its ODA and its other official flows, as in the OECD's former method, since some
                organisations, such as the World Bank's IBRD, report mostly non-concessional lending.
              </p>
              <p>
                Contributions that cannot be traced to a recipient are shown under "ODA eligible countries, unspecified",
                where the OECD's DAC2A table also records them, so the total matches the contributions made.
              </p>
              <h2 className="font-bold text-xl mt-8 mb-2">How is double counting with multilateral contributions avoided?</h2>
              <p>
                Since the April 2026 release, the CRS includes donors' core contributions to multilateral organisations
                as separate records. The dashboard leaves them out of bilateral figures, because the same money appears
                under <em>imputed multilateral</em>, which shows how multilateral organisations spend it.
              </p>
              <p>
                For the same reason, the Recipients tab does not offer the "All recipients" and "All multilateral
                recipients" groups. Bilateral flows to those groups include core contributions to multilateral
                organisations.
              </p>
              <h2 className="font-bold text-xl mt-8 mb-2">Why are some figures missing for the latest year?</h2>
              <p>
                The OECD's preliminary data for the latest year are incomplete. The split of Total ODA into grants and
                non-grants is left out for a group in any year where members that do not report it account for more than
                1% of the group's Total ODA. Countries that report the split keep their own figures. EU27 & EU
                Institutions is shown up to 2024, as explained above.
              </p>
              <p>
                From 2018 to 2022 private sector instruments were reported under provisional methods, as net flows, and
                the dashboard shows them as net flows. The DAC adopted revised methods in 2023, with a transition of up
                to two years. In 2023 and 2024 a donor can report some instruments under the provisional methods, as net
                flows, and others under the revised methods, as grant equivalents. The dashboard's total for private
                sector instruments adds the two, as the OECD does, and shows the total as grant equivalents, following
                the OECD's headline figures. The charts note this for those years. The split into the institutional and
                instrument approaches only ever covers instruments reported under the provisional methods, so it is in
                net flows throughout. From 2025 all private sector instruments are reported as grant equivalents.
              </p>
              <h2 className="font-bold text-xl mt-8 mb-2">How is the gender marker used?</h2>
              <p>
                Donors score each activity 2 if gender equality is its main objective, 1 if it is a significant one, and
                0 if it was screened and does not target gender equality. Activities that were not screened are left
                blank, and the dashboard shows them as "Not screened". The gender marker data the dashboard uses start in
                2010, so the Gender tab starts in that year.
              </p>
              <p>
                Shares are calculated over a donor's bilateral allocable aid, which the four categories add up to. The
                OECD's own figures use screened aid only, and commitments rather than disbursements, so its shares differ
                from the dashboard's and are usually higher.
              </p>
              <h2 className="font-bold text-xl mt-8 mb-2">How are sectors and sub-sectors defined?</h2>
              <p>
                The groupings are based on the <em>purpose</em> field from the Creditor Reporting System (CRS) database.
              </p>
              <h2 className="font-bold text-xl mt-8 mb-2">Who should I contact for questions and suggestions?</h2>
              <p>
                Please refer your comments to <a href="mailto:miguel.haroruiz@one.org">Miguel Haro Ruiz</a> or <a href="mailto:jorge.rivera@one.org">Jorge Rivera</a>.
              </p>
          </div>
    </div>
  )
}

display(<App />)
```
