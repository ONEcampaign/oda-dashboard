export function formatString(str, options = {fileMode: false}) {
    let result = str.replace(/, Total/g, '');

    if (options.fileMode) {
        result = result.toLowerCase().replace(/\s+/g, "_");
    }

    return result;
}
