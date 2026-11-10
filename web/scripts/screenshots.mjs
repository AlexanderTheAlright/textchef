// Retake docs/screenshots.   node scripts/screenshots.mjs http://127.0.0.1:8765 [QUERY]
import { mkdirSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { launch } from "./cdp.mjs";

const base = process.argv[2] ?? "http://127.0.0.1:8765";
const query = encodeURIComponent(process.argv[3] ?? "manager");
const out = join(dirname(fileURLToPath(import.meta.url)), "..", "..", "docs", "screenshots");
mkdirSync(out, { recursive: true });

const graph = await (await fetch(`${base}/api/graph`)).json();
const facets = await (await fetch(`${base}/api/facets`, { method: "POST", headers: { "content-type": "application/json" }, body: "{}" })).json();
const topic = [...graph.topics].sort((a, b) => b.count - a.count)[0].id;
const group = encodeURIComponent(facets.facets.group.values[0].v);

const SHOTS = [
  ["search-cafe", `/?q=${query}&theme=cafe`, 1917, 603, ".hit"],
  ["map-dark", "/?tab=map&theme=dark", 1400, 900, "[data-label]"],
  ["topic-blueprint", `/?topic=${topic}&theme=blueprint`, 1917, 603, ".panel .hit"],
  ["contrast-light", `/?tab=contrast&contrast=group:${group}&theme=light`, 1400, 900, ".contrast-words tbody tr"],
  ["search-light-small", `/?q=${query}&theme=light`, 941, 508, ".hit"],
];

const page = await launch();
try {
  for (const [name, path, w, h, ready] of SHOTS) {
    await page.viewport(w, h);
    await page.goto(base + path, `document.querySelector(${JSON.stringify(ready)})`);
    await page.screenshot(join(out, `${name}.png`));
    console.log(name);
  }
} finally {
  await page.close();
}
