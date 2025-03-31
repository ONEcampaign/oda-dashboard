export function convertUint32Array(uint32Array, scale = 2) {
    // Handle missing or non-Uint32Array inputs
    if (!uint32Array || !(uint32Array instanceof Uint32Array) || uint32Array.length !== 4) {
        // console.warn("Skipping conversion: Invalid Uint32Array(4) format", uint32Array);
        return null; // Return null or original value instead of throwing an error
    }

    // Convert Uint32Array(4) to a BigInt (Apache Arrow stores it in little-endian order)
    let bigIntValue =
        (BigInt(uint32Array[3]) << BigInt(96)) +
        (BigInt(uint32Array[2]) << BigInt(64)) +
        (BigInt(uint32Array[1]) << BigInt(32)) +
        BigInt(uint32Array[0]);

    // Scale down by 10^scale to get the correct decimal value
    return Number(bigIntValue) / Math.pow(10, scale);
}

export function formatString(str, options = {fileMode: false}) {
    let result = str.replace(/, Total/g, '');

    if (options.fileMode) {
        result = result.toLowerCase().replace(/\s+/g, "_");
    }

    return result;
}

export function formatValue(value) {
    // Handle null values
    if (value == null) {
        return {value: 0, label: "0"};
    }

    // Round to two decimal places for the value
    const roundedValue = parseFloat(value.toFixed(2));

    // Determine the label
    let label;
    if (value === 0) {
        label = "0";
    } else if (value > -0.01 && value < 0.01) {
        if (value > -0.01) {
            label = "> -0.01";
        } else {
            label = "< 0.01";
        }
    } else {
        label = roundedValue.toLocaleString("en-US", {
            minimumFractionDigits: 1,
            maximumFractionDigits: 2
        });
    }

    // Return both rounded value and label
    return {value: roundedValue, label};
}


export function getCurrencyLabel(tag, {
    currencyOnly = false,
    currencyLong = false,
    unitsOnly = false,
    unitsLong = true,
    inSentence = false,
    value = "",
} = {}) {

    const currencyMap = {
        "usd": currencyLong ? "US Dollars" : "US$",
        "eur": currencyLong ? "Euros" : "€",
        "cad": currencyLong ? "Canada Dollars" : "CA$",
        "gbp": currencyLong ? "British Pounds" : "£",
    };

    const currency = currencyMap[tag] ?? tag;
    const units = unitsLong ? "Million" : "M";

    if (inSentence) {
        return `${currency} (millions)`;
    }

    if (currencyOnly) return currency;
    if (unitsOnly) return units;

    return value === "" ? `${currency} ${units}` : `${currency}${value} ${units}`;
}



export function name2CodeMap(obj) {
        const map = new Map();

        for (const [code, { name, groups }] of Object.entries(obj)) {
            // Add country name → code
            if (!map.has(name)) map.set(name, []);
            map.get(name).push(Number(code));

            // Add each group → code
            for (const group of groups) {
                if (!map.has(group)) map.set(group, []);
                map.get(group).push(Number(code));
            }
        }

        return map;
    }


export function getNameByCode(map, codes) {
    const codeArray = Array.isArray(codes) ? codes : [codes];
    const target = codeArray.map(String).sort().join(",");

    for (const [name, codeListRaw] of map.entries()) {
        const codeList = Array.isArray(codeListRaw) ? codeListRaw : [codeListRaw];
        const listKey = codeList.map(String).sort().join(",");

        if (listKey === target) {
            return name;
        }
    }

    return undefined;
}



export function generateIndicatorMap(data, page) {
    // Step 1: Filter entries by page and collect unique names
    const names = new Set();

    for (const key in data) {
        const entry = data[key];
        if (entry.page === page && typeof entry.name === "string") {
            names.add(entry.name);
        }
    }

    // Step 2: Sort names alphabetically and assign incremental IDs
    const sortedNames = [...names].sort();
    const nameToId = new Map();

    sortedNames.forEach((name, index) => {
        nameToId.set(name, index);
    });

    return nameToId;
}


