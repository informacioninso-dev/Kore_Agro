import { copyFile, mkdir } from "node:fs/promises";

await mkdir("static/vendor", { recursive: true });
await copyFile("node_modules/htmx.org/dist/htmx.min.js", "static/vendor/htmx.min.js");
await copyFile("node_modules/chart.js/dist/chart.umd.js", "static/vendor/chart.umd.js");
