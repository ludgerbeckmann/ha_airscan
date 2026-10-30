// Visual + behaviour check of the card without Home Assistant:  node tests/card/run.js [out.png]
const { chromium } = require("playwright");
const path = require("path");
const assert = require("assert");

(async () => {
  const browser = await chromium.launch();
  const page = await browser.newPage({ viewport: { width: 1240, height: 900 }, deviceScaleFactor: 2 });
  const errors = [];
  page.on("pageerror", (e) => errors.push(e.message));
  page.on("console", (m) => { if (m.type() === "error") errors.push(m.text()); });
  await page.goto("file://" + path.join(__dirname, "harness.html"));

  await page.evaluate(() => {
    mount({ cap: "1 · Bereit", status: "idle", ui: { source: "adf", duplex: true }, attrs: { pages: 6 } });
    mount({ cap: "2 · Läuft", status: "running", ui: { source: "adf", duplex: true }, feeder: "processing", attrs: { pages: 3, detail: "Seite 3 gescannt" } });
    mount({ cap: "3 · Stapel offen", status: "batch", attrs: { batch_pages: 3, batch_expires_at: iso(24 * 60000), detail: "Stapel: 3 Seite(n)" } });
    mount({ cap: "4 · Fertig", status: "done", ui: { source: "adf", duplex: true }, attrs: { pages: 6, destination: "paperless", document_id: 123, blank_removed: 2 }, last: iso(-2 * 60000) });
    mount({ cap: "5 · Fehler", status: "error", ui: { source: "adf" }, feeder: "empty", attrs: { detail: "Scan fehlgeschlagen: Scanner refused the job (ADF empty or cover open?)" } });
    mount({ cap: "6 · Wartet auf Paperless", status: "queued", ui: { source: "adf", duplex: true }, attrs: { pages: 6, detail: "6 Seite(n) gescannt – Paperless nicht erreichbar" },
      queue: { count: 2, next: 4 * 60000, items: [{ title: "Scan 2026-10-29 21:10", last_error: "ClientConnectorError: Cannot connect to host paperless:8000" }] } });
    mount({ cap: "7 · Drucker offline", status: "idle", feeder: "unavailable", attrs: { printer_online: false, printer_state: null } });
    mount({ cap: "8 · Dunkel (Stapel)", status: "batch", dark: true, attrs: { batch_pages: 3, batch_expires_at: iso(24 * 60000) } });
  });
  await page.screenshot({ path: process.argv[2] || "card.png", fullPage: true });

  // --- behaviour: every click must call the right service with the right data ---
  const result = await page.evaluate(async () => {
    const out = {};
    const root = (c) => c.shadowRoot;
    const click = (c, sel) => root(c).querySelector(sel).click();
    const tick = () => new Promise((r) => setTimeout(r, 0));

    const c = mount({ status: "idle" }, document.body);      // default source = feeder
    out.defaultFeeder = root(c).querySelector('[data-act="mode"][data-v="adf1"]').classList.contains("on");
    out.modes = [...root(c).querySelectorAll('.seg button')].map((b) => b.dataset.v);
    const rowTops = (card) => [...new Set([...root(card).querySelectorAll('.opts > *')].map((e) => { const b = e.getBoundingClientRect(); return Math.round((b.top + b.height / 2) / 4); }))].length;   // vertical centres, 4px tolerance
    out.optsRows = rowTops(c);
    out.simplex = c._hass.calls.length === 0 && (click(c, '[data-act="scan"]'), c._hass.calls.slice());
    c._hass.calls.length = 0;
    click(c, '[data-act="mode"][data-v="platen"]'); await tick();
    click(c, '[data-act="scan"]'); out.glass = c._hass.calls.slice();
    click(c, '[data-act="mode"][data-v="adf2"]'); await tick();
    out.duplexOn = root(c).querySelector('[data-act="mode"][data-v="adf2"]').classList.contains("on");
    click(c, '[data-act="scan"]'); out.adfDuplex = c._hass.calls.slice();
    click(c, '[data-act="gear"]'); await tick();
    const sel = root(c).querySelector('[data-set="resolution"]'); sel.value = "600"; sel.dispatchEvent(new Event("change", { bubbles: true })); await tick();
    const bl = root(c).querySelector('[data-set="blank"]'); bl.value = "off"; bl.dispatchEvent(new Event("change", { bubbles: true })); await tick();
    click(c, '[data-act="scan"]'); out.adfOverrides = c._hass.calls.slice();
    out.pills = [...root(c).querySelectorAll(".pill")].map((p) => p.textContent);

    const b = mount({ status: "batch", attrs: { batch_pages: 2 } }, document.body);
    click(b, '[data-act="add"]'); click(b, '[data-act="send"]'); click(b, '[data-act="discard"]');
    out.batch = b._hass.calls.slice();
    out.batchAdfDisabled = root(b).querySelector('[data-act="mode"][data-v="adf1"]').disabled && root(b).querySelector('[data-act="mode"][data-v="adf2"]').disabled;

    const r = mount({ status: "running" }, document.body);
    out.runningDisabled = root(r).querySelector(".primary").disabled;

    const d = mount({ status: "done", attrs: { pages: 6, destination: "paperless", document_id: 123 } }, document.body);
    out.link = root(d).querySelector(".banner a").href;

    const f = mount({ status: "idle", fail: "Scanner is busy" }, document.body);
    click(f, '[data-act="scan"]'); await new Promise((r2) => setTimeout(r2, 20));
    out.toast = root(f).querySelector(".toast")?.textContent;

    localStorage.clear();   // the card remembers source/duplex per entity
    const e = mount({ status: "idle", lang: "en" }, document.body);
    out.en = root(e).querySelector(".primary").textContent;

    const q = mount({ status: "queued", queue: { count: 2, next: 240000, rejected: 1, items: [{ last_error: "boom" }] } }, document.body);
    click(q, '[data-act="retry"]');
    out.queue = q._hass.calls.slice();
    out.queueText = root(q).querySelector(".banner.warn").textContent;
    out.queueChip = root(q).querySelector(".chip").textContent;
    const q0 = mount({ status: "idle" }, document.body);
    out.noQueueBanner = root(q0).querySelector(".banner.warn") === null;

    const off = mount({ status: "idle", attrs: { printer_online: false } }, document.body);
    out.offChip = root(off).querySelector(".chip").textContent;
    out.offBanner = root(off).querySelector(".banner.err")?.textContent || "";
    out.offScanEnabled = !root(off).querySelector('[data-act="scan"]').disabled;     // a scan is still attempted (printer may wake up)
    const offRun = mount({ status: "running", attrs: { printer_online: false } }, document.body);
    out.offRunBanner = root(offRun).querySelector(".banner.err") === null;           // no false alarm while scanning
    out.offRunChip = root(offRun).querySelector(".chip").textContent;
    const fault = mount({ status: "idle", attrs: { printer_state: "Stopped" } }, document.body);
    out.fault = root(fault).querySelector(".banner.err")?.textContent || "";
    const okc = mount({ status: "idle" }, document.body);
    out.okNoBanner = root(okc).querySelector(".banner.err") === null;

    const x = document.createElement("ha-airscan-card"); x.setConfig({ entity: "sensor.nope" });
    x.hass = { language: "de", states: {}, entities: {} }; document.body.appendChild(x);
    out.missing = x.shadowRoot.querySelector(".missing")?.textContent;
    return out;
  });

  assert.strictEqual(result.defaultFeeder, true, "feeder must be the default");
  assert.deepStrictEqual(result.modes, ["adf1", "adf2", "platen"], "feeder one-sided, feeder two-sided, flatbed");
  assert.strictEqual(result.optsRows, 1, "the options must fit in one row");
  assert.strictEqual(result.duplexOn, true);
  assert.deepStrictEqual(result.simplex, [["ha_airscan", "scan", { source: "adf", duplex: false }]]);
  assert.deepStrictEqual(result.glass, [["ha_airscan", "batch_add", {}]]);
  assert.deepStrictEqual(result.adfDuplex[1], ["ha_airscan", "scan", { source: "adf", duplex: true }]);
  assert.deepStrictEqual(result.adfOverrides[2], ["ha_airscan", "scan", { source: "adf", duplex: true, resolution: 600, skip_blank: false }]);
  assert.ok(result.pills.includes("600 dpi"), JSON.stringify(result.pills));
  assert.deepStrictEqual(result.batch.map((x) => x[1]), ["batch_add", "batch_send", "batch_discard"]);
  assert.strictEqual(result.batchAdfDisabled, true);
  assert.strictEqual(result.runningDisabled, true);
  assert.strictEqual(result.link, "http://paperless.local:8000/documents/123/details");
  assert.strictEqual(result.toast, "Scanner is busy");
  assert.strictEqual(result.en, "Scan feeder");
  assert.ok(/nicht gefunden/.test(result.missing));
  assert.strictEqual(result.offChip, "Offline");
  assert.ok(/Drucker nicht erreichbar/.test(result.offBanner) && /Scan wird trotzdem versucht/.test(result.offBanner), result.offBanner);
  assert.strictEqual(result.offScanEnabled, true);
  assert.strictEqual(result.offRunBanner, true);
  assert.strictEqual(result.offRunChip, "Läuft");
  assert.ok(/Drucker meldet einen Fehler \(Stopped\)/.test(result.fault), result.fault);
  assert.strictEqual(result.okNoBanner, true);
  assert.deepStrictEqual(result.queue, [["ha_airscan", "retry_queue", {}]]);
  assert.ok(/2 Scans warten auf Paperless/.test(result.queueText) && /Nächster Versuch in 4 min/.test(result.queueText) && /1 von Paperless abgelehnt/.test(result.queueText), result.queueText);
  assert.strictEqual(result.queueChip, "Wartet");
  assert.strictEqual(result.noQueueBanner, true);
  assert.deepStrictEqual(errors, [], "console errors: " + errors.join("; "));
  console.log("card checks passed");
  await browser.close();
})().catch((e) => { console.error(e); process.exit(1); });
