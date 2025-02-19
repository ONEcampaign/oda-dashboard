export function uint32ArrayToDecimal(uint32Array, scale = 2) {
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
