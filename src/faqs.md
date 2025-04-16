```js
import {generateList} from "./components/utils.js"

const donorMapping = await FileAttachment("./data/analysis_tools/donors.json").json()
const recipientMapping = await FileAttachment("./data/analysis_tools/recipients.json").json()
const sectorMapping = await FileAttachment("./data/analysis_tools/sectors.json").json()
```

<div class="header card">
    <a class="view-button" href="./">
        Financing
    </a>
    <a class="view-button" href="./recipients">
        Recipients
    </a>
    <a class="view-button" href="./sectors">
        Sectors
    </a>
    <a class="view-button" href="./gender">
        Gender
    </a>
    <a class="view-button active" href="./faqs">
        FAQs
    </a>
</div>

<div class="card methodology">
    <h2 class="section-header">
        What is the ODA Dashboard?
    </h2>
    <p class="base-text">
        ONE's ODA Dashboard presents Official Development Assistance (ODA) in an accessible format, allowing users to 
        explore trends and gain insights, regardless of their ODA knowledge. It is built using ONE’s methodology and 
        custom Python tools for processing the data. For an introduction to ODA and a detailed explanation of our 
        approach, visit the <a href="https://one-campaign.observablehq.cloud/oda-cookbook/">ODA Cookbook</a>.
    </p>
    <p class="base-text">
        The dashboard is divided into four tabs:
    </p> 
    <p class="base-text">
        <strong>Financing</strong> offers data on various ODA indicators from the perspective of provider 
        countries and country groups. Use this tab to answer questions like:
    </p> 
    <ul class="group-list">
        <li>How much aid does <i>Country X</i> provide?</li>
        <li>Is <i>Country X</i> meeting the 0.7% GNI target for its ODA contributions?</li>
    </ul>
    <p class="base-text">
        <strong>Recipients</strong> shows ODA flows from providers to recipient countries and groups. This tab 
        is useful if you're interested in:
    </p>
    <ul class="group-list">
        <li>How much ODA does <i>Country X</i> give directly to <i>Country Y</i>?</li>
        <li>How much ODA does <i>Country X</i> channel to <i>Country Y</i> via multilateral organisations?</li>
    </ul>
    <p class="base-text">
        <strong>Sectors</strong> breaks down ODA data by economic sectors, which can be broken down into
        sub-sectors. Use this tab to explore questions like:
    </p>
    <ul class="group-list">
        <li>How much ODA does <i>Country X</i> allocate to humanitarian aid?</li>
        <li>How much ODA does <i>Country Y</i> receive for health?</li>
        <li>How much ODA does <i>Country X</i> direct to <i>Country Y</i>’s education sector?</li>
    </ul>
    <p class="base-text">
        <strong>Gender</strong> categorises ODA by whether it targets gender equality as a policy objective. 
        This tab helps you explore questions such as:
    </p>
    <ul class="group-list">
        <li>How much ODA from <i>Country X</i> targets gender as a principal or secondary goal?</li>
        <li>What share of ODA received by <i>Country Y</i> focuses on gender equality?</li>
    </ul>
    <h2 class="section-header">
        Where does the data come from?
    </h2>
    <p class="base-text">
        ODA data is retrieved from the OECD Data Explorer API via the 
        <a href="https://github.com/ONEcampaign/oda_data_package">oda-data</a> python package.
    </p>
    <h2 class="section-header">
        How is the data transformed?
    </h2>
    <p class="base-text">
        ODA figures are first obtained in current US Dollars and converted into other currencies and constant prices via
        <a href="https://github.com/jm-rivera/pydeflate">pydeflate</a>.
    </p>
    <p class="base-text">
        The data preparation scripts are located in the <span style="font-family: monospace">src/data</span>
        directory of the project's <a href="https://github.com/ONEcampaign/oda-dashboard"> GitHub
        repository</a>.
    </p>
    <h2 class="section-header">
        What countries are included in donor country groups?
    </h2>
    ${generateList(donorMapping, "countries")}
    <h2 class="section-header">
        What countries are included in recipient country groups?
    </h2>
    ${generateList(recipientMapping, "countries")}
    <h2 class="section-header">
        How are sectors and sub-sectors defined?
    </h2>
    <p class="base-text">
        The groupings are based on the <i>purpose</i> fields from the Creditor Reporting System (CRS) database. Below is a list
        of all sectors currently present in the data. If a sector has sub-sectors, they’re listed after the sector name.
    </p>
    ${generateList(sectorMapping, "sectors")}
    <h2 class="section-header">
        Who should I contact for questions and suggestions?
    </h2>
    <p class="base-text">
        Please refer your comments to miguel.haroruiz[at]one[dot]org or jorge.rivera[at]one[dot]org.
    </p>
</div>