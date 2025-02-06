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