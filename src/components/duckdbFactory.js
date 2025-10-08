import {DuckDBClient} from "npm:@observablehq/duckdb";

// Cache for DuckDB instances by configuration
const dbCache = new Map();

/**
 * Creates a DuckDB client instance with the specified table configuration.
 * Instances are cached to avoid duplicate initialization.
 *
 * Observable Framework requires FileAttachment to be called with literal strings,
 * so the caller must construct the tableConfig object with FileAttachment calls.
 *
 * @param {Object} tableConfig - Table configuration object for DuckDBClient.of()
 * @param {string} cacheKey - Unique key for caching this configuration
 * @returns {Promise<DuckDBClient>} Promise that resolves to a DuckDB client instance
 */
export function createDuckDBClient(tableConfig, cacheKey) {
    if (!dbCache.has(cacheKey)) {
        dbCache.set(cacheKey, DuckDBClient.of(tableConfig));
    }

    return dbCache.get(cacheKey);
}
