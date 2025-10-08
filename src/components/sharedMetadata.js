import {FileAttachment} from "observablehq:stdlib";

// Load all metadata files in parallel (shared across all query modules)
// This avoids redundant loading of the same JSON files multiple times
const [
    donorOptions,
    recipientOptions,
    financingIndicators,
    sectorsIndicators,
    recipientsIndicators,
    genderIndicators,
    code2Subsector,
    subsector2Sector
] = await Promise.all([
    FileAttachment("../data/analysis_tools/donors.json").json(),
    FileAttachment("../data/analysis_tools/recipients.json").json(),
    FileAttachment("../data/analysis_tools/financing_indicators.json").json(),
    FileAttachment("../data/analysis_tools/sectors_indicators.json").json(),
    FileAttachment("../data/analysis_tools/recipients_indicators.json").json(),
    FileAttachment("../data/analysis_tools/gender_indicators.json").json(),
    FileAttachment("../data/analysis_tools/sub_sectors.json").json(),
    FileAttachment("../data/analysis_tools/sectors.json").json()
]);

export {
    donorOptions,
    recipientOptions,
    financingIndicators,
    sectorsIndicators,
    recipientsIndicators,
    genderIndicators,
    code2Subsector,
    subsector2Sector
};
