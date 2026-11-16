// Prefer the UTF-8 filename supplied by Flask for non-ASCII download names.
function responseFilename(response, fallback) {
    const header = response.headers.get('Content-Disposition') || '';
    const utf8 = header.match(/filename\*=UTF-8''([^;]+)/i);
    if (utf8) {
        try { return decodeURIComponent(utf8[1]); } catch (error) { /* use plain filename */ }
    }
    const plain = header.match(/\bfilename=(?:"([^"]+)"|([^;]+))/i);
    return plain ? (plain[1] || plain[2].trim()) : fallback;
}
