import {
    wrapTextWithAnsi,
} from "@earendil-works/pi-tui";

export function splitTextbyWidth(text: string, padding: number = 6): string[] {
    const columns = process.stdout.columns || 80;
    const availableWidth = Math.max(20, columns - padding);
    return wrapTextWithAnsi(text, availableWidth);
}

export function summarizeArgs(args: Record<string, unknown> | null | undefined): string {
    if (!args) return "";

    return Object.entries(args).map(([k, v]) => {
        let text = typeof v == "string" ? v : JSON.stringify(v);
        text = text.replace(/\s+/g, " ").trim(); // flatten newlines and extra spaces

        if (text.length > 60) {
            text = `${text.slice(0, 60)}...`;
        }

        return `${k}: ${text}`
    }).join(", ");
}