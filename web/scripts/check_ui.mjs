// Exercise the page in headless Chromium and report each behaviour.
//   node scripts/check_ui.mjs http://127.0.0.1:8765
import { launch } from "./cdp.mjs";

const base = process.argv[2] ?? "http://127.0.0.1:8765";
const page = await launch();
const results = [];
const check = (name, ok, detail = "") => {
  results.push(ok);
  console.log(`${ok ? "ok  " : "FAIL"} ${name}${detail ? `: ${detail}` : ""}`);
};
const js = (expression) => page.evaluate(expression);
const click = (selector, text) => js(`(() => {
  const el = [...document.querySelectorAll(${JSON.stringify(selector)})]
    .find((e) => ${text ? `new RegExp(${JSON.stringify(text)}).test(e.textContent.trim())` : "true"});
  if (!el) return false;
  el.click();
  return true;
})()`);
const choose = (selector, index, value) => js(`(() => {
  const select = document.querySelectorAll(${JSON.stringify(selector)})[${index}];
  const v = ${value === null ? "select.options[1].value" : JSON.stringify(value)};
  Object.getOwnPropertyDescriptor(HTMLSelectElement.prototype, 'value').set.call(select, v);
  select.dispatchEvent(new Event('change', { bubbles: true }));
})()`);
const count = (selector) => js(`document.querySelectorAll(${JSON.stringify(selector)}).length`);
const theme = () => js("document.documentElement.dataset.theme");
const TOTAL = "Number(document.querySelector('.filters-head span').textContent.replace(/\\D/g, ''))";

try {
  await page.viewport(1400, 900);
  const status = await (await fetch(`${base}/api/status`)).json();

  await page.colorScheme("dark");
  await page.goto(base);
  check("default follows prefers-color-scheme: dark", await theme() === status.theme_dark, await theme());
  await page.colorScheme("light");
  await page.reload();
  check("default follows prefers-color-scheme: light", await theme() === status.theme_light, await theme());

  await choose(".theme-pick select", 0, "blueprint");
  await page.until("document.documentElement.dataset.theme === 'blueprint'");
  await page.reload();
  check("theme switch persists across reload", await theme() === "blueprint", await theme());
  await js("localStorage.clear()");
  await page.reload();

  const before = await js(TOTAL);
  await click(".facet-values input");
  await page.until(`${TOTAL} < ${before}`);
  check("filter narrows the corpus", (await js(TOTAL)) < before, `${before} -> ${await js(TOTAL)}`);
  await click(".filters-head button", "^Clear$");
  await page.until(`${TOTAL} === ${before}`);

  await click(".searchbar button", "^Random$");
  await page.until("document.querySelector('.hit')");
  check("Random lists texts", (await count(".hit")) > 0, `${await count(".hit")} cards`);

  await click(".searchbar button", "^Browse$");
  await page.until("document.querySelectorAll('.hit').length >= 50");
  const first = await count(".hit");
  await click(".list > button", "^More$");
  await page.until(`document.querySelectorAll('.hit').length > ${first}`);
  check("Browse lists texts and More adds a page", (await count(".hit")) > first,
    `${first} -> ${await count(".hit")} cards`);

  const same = await js(`(() => {
    const b = [...document.querySelectorAll('.hit-foot button')].find((e) => /\\(\\d+\\)$/.test(e.textContent.trim()));
    if (!b) return 0;
    b.click();
    return Number(b.textContent.match(/\\((\\d+)\\)$/)[1]);
  })()`);
  if (same) {
    await page.until(`document.querySelectorAll('.hit').length === ${same}`);
    check("same-id view lists every text of the id", (await count(".hit")) === same, `${same} cards`);
  } else {
    check("same-id view", false, "no id with more than one text on the first pages");
  }

  await click(".hit-foot button", "^Similar$");
  await page.until("document.querySelector('.source .hit')");
  check("Similar shows the source and its neighbours", (await count(".hit")) > 1,
    `${(await count(".hit")) - 1} neighbours`);

  await click(".tab", "^Map$");
  await page.until("document.querySelector('[data-node]')");
  const node = () => js(`(() => { const r = document.querySelector('[data-node]').getBoundingClientRect(); return [r.x, r.y]; })()`);
  const unlabelled = await js(`(() => {
    const labelled = new Set([...document.querySelectorAll('[data-label]')].map((e) => e.dataset.label));
    const el = [...document.querySelectorAll('[data-node]')].reverse().find((e) => !labelled.has(e.dataset.node));
    if (!el) return null;
    const r = el.getBoundingClientRect();
    return [r.x + r.width / 2, r.y + r.height / 2];
  })()`);
  if (unlabelled) {
    await page.mouse("mouseMoved", unlabelled[0], unlabelled[1]);
    await page.until("document.querySelector('[data-hover] text')");
    check("hover shows the label of an unlabelled node", true, await js("document.querySelector('[data-hover] text').textContent"));
    await page.mouse("mouseMoved", 5, 5);
  } else {
    check("hover label", true, "every node already has a label at this size");
  }
  await click(".map-tools button", "^\\+$");
  await page.until("Number(document.querySelector('.map svg').dataset.zoom) > 1");
  check("map zoom", true, `zoom ${await js("document.querySelector('.map svg').dataset.zoom")}`);
  await click(".map-tools button", "^Reset$");
  await page.sleep(200);

  const start = await node();
  const mid = await js(`(() => { const r = document.querySelector('.map svg').getBoundingClientRect(); return [r.x + 30, r.y + 30]; })()`);
  await page.mouse("mousePressed", mid[0], mid[1]);
  await page.mouse("mouseMoved", mid[0] + 60, mid[1] + 40, { buttons: 1 });
  await page.mouse("mouseReleased", mid[0] + 60, mid[1] + 40);
  await page.sleep(200);
  const end = await node();
  check("map pan", Math.abs(end[0] - start[0] - 60) < 2 && Math.abs(end[1] - start[1] - 40) < 2,
    `node moved by ${Math.round(end[0] - start[0])}, ${Math.round(end[1] - start[1])} px`);

  const centre = await js(`(() => { const r = document.querySelector('[data-node]').getBoundingClientRect(); return [r.x + r.width / 2, r.y + r.height / 2]; })()`);
  await page.mouse("mousePressed", centre[0], centre[1]);
  await page.mouse("mouseReleased", centre[0], centre[1]);
  await page.until("document.querySelector('.panel .hit')");
  check("clicking a node opens its topic", true, await js("document.querySelector('.panel h2').textContent"));

  await click(".tab", "^Contrast$");
  await page.until("document.querySelector('.contrast select')");
  await choose(".contrast select", 1, null);
  await page.sleep(200);
  await click(".contrast button", "^Contrast$");
  await page.until("document.querySelector('.contrast-words tbody tr')");
  check("Contrast lists words for both sides", (await count(".contrast-words")) === 2,
    `${await count(".contrast-words tbody tr")} rows`);

  check("no page errors or blocked resources", page.problems.length === 0, page.problems.slice(0, 3).join(" | "));
} catch (e) {
  check("run completed", false, String(e));
} finally {
  await page.close();
}
process.exit(results.every(Boolean) ? 0 : 1);
