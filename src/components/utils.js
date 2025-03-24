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

export function getCurrencyLabel(unit, {
    long = true,
    value = "",
    preffixOnly = false,
    suffixOnly = false,
})
{

    let prefix, suffix;

    if (long) {
        suffix = "Million"
    }
    else (
        suffix = "M"
    )

    if (unit === "US Dollars") {
        prefix = "US$"
    }
    else if (unit === "Euros") {
        prefix = "€"
    }
    else if (unit === "Canadian Dollars") {
        prefix =  "CA$"
    }
    else if (unit === "British Pounds") {
        prefix = "£"
    }

    if (preffixOnly) {
        return `${prefix}`
    }
    if (suffixOnly) {
        return `${suffix}`
    }
    if (value === "") {
        return `${prefix} ${suffix}`
    }
    else {
        return `${prefix}${value} ${suffix}`
    }

}

export function name2CodeMap(jsonData) {
    const map = new Map();

    for (const [code, { name, groups }] of Object.entries(jsonData)) {
        if (!map.has(name)) map.set(name, []);
        map.get(name).push(code);

        for (const group of groups) {
            if (!map.has(group)) map.set(group, []);
            map.get(group).push(code);
        }
    }

    return map;
}

export function getKeysByValue(map, targetCodes) {
    const result = [];
    const target = [...targetCodes].sort().join(",");

    for (const [key, value] of map.entries()) {
        if ([...value].sort().join(",") === target) {
            result.push(key);
        }
    }

    return result;
}