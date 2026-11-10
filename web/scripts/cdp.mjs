// A small driver for headless Chromium over the DevTools protocol, with no
// dependencies (Node 22+ for the built-in WebSocket). The GPU is always off.
import { spawn } from "node:child_process";
import { mkdtempSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";

const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

export async function launch() {
  const profile = mkdtempSync(join(tmpdir(), "textchef-browser-"));
  const proc = spawn(process.env.CHROMIUM ?? "chromium", [
    "--headless=new", "--disable-gpu", "--no-first-run", "--hide-scrollbars",
    `--user-data-dir=${profile}`, "--remote-debugging-port=0", "about:blank",
  ], { stdio: ["ignore", "ignore", "pipe"] });
  const port = await new Promise((resolve, reject) => {
    let err = "";
    proc.stderr.on("data", (d) => {
      err += d;
      const m = err.match(/DevTools listening on ws:\/\/127\.0\.0\.1:(\d+)\//);
      if (m) resolve(m[1]);
    });
    proc.on("exit", () => reject(new Error(`browser exited: ${err.slice(0, 400)}`)));
  });
  const targets = await (await fetch(`http://127.0.0.1:${port}/json`)).json();
  const ws = new WebSocket(targets.find((t) => t.type === "page").webSocketDebuggerUrl);
  await new Promise((r) => ws.addEventListener("open", r));

  let next = 0;
  const waiting = new Map();
  const problems = [];      // page errors and blocked resources, e.g. CSP violations
  ws.addEventListener("message", (e) => {
    const msg = JSON.parse(e.data);
    if (msg.id && waiting.has(msg.id)) {
      const { resolve, reject } = waiting.get(msg.id);
      waiting.delete(msg.id);
      msg.error ? reject(new Error(msg.error.message)) : resolve(msg.result);
    } else if (msg.method === "Runtime.exceptionThrown") {
      problems.push(msg.params.exceptionDetails.exception?.description ?? msg.params.exceptionDetails.text);
    } else if (msg.method === "Log.entryAdded" && msg.params.entry.level === "error") {
      problems.push(msg.params.entry.text);
    }
  });
  const send = (method, params = {}) => new Promise((resolve, reject) => {
    waiting.set(++next, { resolve, reject });
    ws.send(JSON.stringify({ id: next, method, params }));
  });
  for (const domain of ["Page", "Runtime", "Log"]) await send(`${domain}.enable`);

  const page = {
    problems,
    async viewport(width, height) {
      await send("Emulation.setDeviceMetricsOverride", { width, height, deviceScaleFactor: 1, mobile: false });
    },
    async colorScheme(value) {
      await send("Emulation.setEmulatedMedia", { features: [{ name: "prefers-color-scheme", value }] });
    },
    async evaluate(expression) {
      const r = await send("Runtime.evaluate", { expression, awaitPromise: true, returnByValue: true });
      if (r.exceptionDetails) throw new Error(r.exceptionDetails.exception?.description ?? "evaluate failed");
      return r.result.value;
    },
    /** Wait until an expression is truthy in the page. */
    async until(expression, ms = 15000) {
      for (let t = 0; t < ms; t += 100) {
        if (await page.evaluate(`Boolean(${expression})`).catch(() => false)) return;
        await sleep(100);
      }
      throw new Error(`timed out waiting for: ${expression}`);
    },
    async goto(url, ready = "document.querySelector('.app')") {
      await send("Page.navigate", { url });
      await page.until(`document.readyState === 'complete' && ${ready}`);
      await sleep(300);
    },
    async reload(ready = "document.querySelector('.app')") {
      await send("Page.reload");
      await sleep(200);
      await page.until(`document.readyState === 'complete' && ${ready}`);
      await sleep(300);
    },
    async mouse(type, x, y, extra = {}) {
      await send("Input.dispatchMouseEvent", { type, x, y, button: "left", clickCount: 1, ...extra });
    },
    async screenshot(path) {
      const r = await send("Page.captureScreenshot", { format: "png" });
      writeFileSync(path, Buffer.from(r.data, "base64"));
    },
    async close() {
      await send("Browser.close").catch(() => {});
      proc.kill();
    },
    sleep,
  };
  return page;
}
