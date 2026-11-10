// Measure the rendered topic map: no label may touch another label or any
// node, and at the default zoom every node must sit inside the frame.
//   node scripts/check_map.mjs http://127.0.0.1:8765
import { launch } from "./cdp.mjs";

const base = process.argv[2] ?? "http://127.0.0.1:8765";
const VIEWPORTS = [[1917, 603], [1400, 900], [941, 508]];
const ZOOMS = [1, 2, 4];

const MEASURE = `(() => {
  const frame = document.querySelector('.map svg').getBoundingClientRect();
  const box = (el) => { const r = el.getBoundingClientRect(); return { id: el.dataset.label ?? el.dataset.node, x: r.x, y: r.y, w: r.width, h: r.height }; };
  return { frame: { x: frame.x, y: frame.y, w: frame.width, h: frame.height },
           labels: [...document.querySelectorAll('[data-label]')].map(box),
           nodes: [...document.querySelectorAll('[data-node]')].map(box) };
})()`;

const overlap = (a, b) => a.x < b.x + b.w && b.x < a.x + a.w && a.y < b.y + b.h && b.y < a.y + a.h;
function touchesCircle(label, node) {
  const cx = node.x + node.w / 2, cy = node.y + node.h / 2, r = node.w / 2;
  const dx = cx - Math.max(label.x, Math.min(cx, label.x + label.w));
  const dy = cy - Math.max(label.y, Math.min(cy, label.y + label.h));
  return dx * dx + dy * dy < r * r;
}

const page = await launch();
let failed = false;
try {
  for (const [w, h] of VIEWPORTS) {
    await page.viewport(w, h);
    for (const zoom of ZOOMS) {
      await page.goto(`${base}/?tab=map&zoom=${zoom}`, "document.querySelector('[data-node]')");
      const { frame, labels, nodes } = await page.evaluate(MEASURE);
      let labelLabel = 0, labelNode = 0, clipped = 0, outside = 0;
      labels.forEach((a, i) => {
        labels.slice(i + 1).forEach((b) => { if (overlap(a, b)) labelLabel += 1; });
        nodes.forEach((n) => { if (touchesCircle(a, n)) labelNode += 1; });
        if (a.x < frame.x || a.y < frame.y || a.x + a.w > frame.x + frame.w || a.y + a.h > frame.y + frame.h) outside += 1;
      });
      if (zoom === 1) {
        nodes.forEach((n) => {
          if (n.x < frame.x || n.y < frame.y || n.x + n.w > frame.x + frame.w || n.y + n.h > frame.y + frame.h) clipped += 1;
        });
      }
      const ok = labelLabel + labelNode + clipped + outside === 0 && (zoom > 1 || labels.length > 0);
      failed ||= !ok;
      console.log(`${ok ? "ok  " : "FAIL"} ${w}x${h} zoom ${zoom}: ${nodes.length} nodes, ${labels.length} labels, ` +
        `label-label ${labelLabel}, label-node ${labelNode}, labels outside frame ${outside}` +
        (zoom === 1 ? `, nodes clipped ${clipped}` : ""));
    }
  }
} finally {
  await page.close();
}
process.exit(failed ? 1 : 0);
