import {
    wrapTextWithAnsi,
} from "@earendil-works/pi-tui";

export function splitTextbyWidth(text) {
    const availableWidth = Math.max(20, (process.stdout.columns || 80) - 6);
    return wrapTextWithAnsi(text, availableWidth);
}

export function summarizeArgs(args) {
    return Object.entries(args || {}).map(([k, v]) => {
        let text = typeof v == "string" ? v : JSON.stringify(v);
        text = text.replace(/\s+/g, " ").trim(); // flatten newlines and extra spaces

        if (text.length > 60) {
            text = `${text.slice(0, 60)}...`;
        }

        return `${k}: ${text}`
    }).join(", ");
}