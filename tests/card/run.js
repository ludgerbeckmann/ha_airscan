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
    window.boxed = (w) => { const d = document.createElement("div"); d.style.width = w + "px"; document.body.appendChild(d); return d; };
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
    out.link = root(d).querySelector(".status a.act").href;

    const f = mount({ status: "idle", fail: "Scanner is busy" }, document.body);
    click(f, '[data-act="scan"]'); await new Promise((r2) => setTimeout(r2, 20));
    out.toast = root(f).querySelector(".toast")?.textContent;

    localStorage.clear();   // the card remembers source/duplex per entity
    const e = mount({ status: "idle", lang: "en" }, document.body);
    out.en = root(e).querySelector(".primary").textContent;

    const q = mount({ status: "queued", queue: { count: 2, next: 240000, rejected: 1, items: [{ last_error: "boom" }] } }, document.body);
    click(q, '[data-act="retry"]');
    out.queue = q._hass.calls.slice();
    out.queueText = root(q).querySelector(".status.warn").textContent;
    out.queueChip = root(q).querySelector(".status .chip").textContent;
    const q0 = mount({ status: "idle" }, document.body);
    out.noQueueBanner = root(q0).querySelector(".status.warn") === null;

    const off = mount({ status: "idle", attrs: { printer_online: false } }, document.body);
    out.offChip = root(off).querySelector(".status .chip").textContent;
    out.offBanner = root(off).querySelector(".status.err")?.textContent || "";
    out.offScanEnabled = !root(off).querySelector('[data-act="scan"]').disabled;     // a scan is still attempted (printer may wake up)
    const offRun = mount({ status: "running", attrs: { printer_online: false } }, document.body);
    out.offRunBanner = root(offRun).querySelector(".status.err") === null;           // no false alarm while scanning
    out.offRunChip = root(offRun).querySelector(".status .chip").textContent;
    const fault = mount({ status: "idle", attrs: { printer_state: "Stopped" } }, document.body);
    out.fault = root(fault).querySelector(".status.err")?.textContent || "";
    const okc = mount({ status: "idle" }, document.body);
    out.okNoBanner = root(okc).querySelector(".status.err") === null;

    localStorage.clear();
    const fc = mount({ status: "idle", feeder: "loaded" }, boxed(360));
    out.feederChip = root(fc).querySelector(".chip.feeder")?.textContent;
    out.chipOrder = [root(fc).querySelector(".head .chip.feeder").textContent, root(fc).querySelector(".status .chip").textContent];
    out.noDots = root(fc).querySelector(".dot") === null && root(fc).querySelector(".feeder-hint") === null;
    out.scanLabel = root(fc).querySelector('[data-act="scan"]').textContent;
    out.gearSize = parseFloat(getComputedStyle(root(fc).querySelector(".gear")).fontSize);
    const nm = root(fc).querySelector(".name"); out.nameWhole = nm.textContent === "EPSON ET-3950 Series" && nm.scrollHeight <= nm.clientHeight + 1;
    out.headHeight = Math.round(root(fc).querySelector(".head").getBoundingClientRect().height);
    const fe = mount({ status: "idle", feeder: "empty" }, document.body);
    out.feederEmpty = [root(fe).querySelector(".chip.feeder").textContent, root(fe).querySelector(".dot") === null];
    const fu = mount({ status: "idle", feeder: "unavailable" }, document.body);
    out.noFeederChipOffline = root(fu).querySelector(".chip.feeder") === null;
    const ferr = mount({ status: "error", ui: { source: "adf" } }, document.body);
    out.retryLabel = root(ferr).querySelector('[data-act="scan"]').textContent;

    // --- the card must not change its size from state to state ---
    localStorage.clear();
    const long = "Scan fehlgeschlagen: " + "sehr lange Fehlermeldung des Scanners ".repeat(6);
    const cases = {
      idle: { status: "idle", ui: { source: "adf", duplex: true } },
      running0: { status: "running", ui: { source: "adf", duplex: true } },
      running: { status: "running", ui: { source: "adf", duplex: true }, attrs: { pages: 12, detail: "Seite 12 gescannt" } },
      done: { status: "done", ui: { source: "adf", duplex: true }, attrs: { pages: 6, destination: "paperless", document_id: 123, blank_removed: 2 } },
      error: { status: "error", ui: { source: "adf", duplex: true }, attrs: { detail: long } },
      queued: { status: "queued", ui: { source: "adf", duplex: true }, queue: { count: 2, next: 240000, rejected: 1, items: [{ last_error: "ClientConnectorError: Cannot connect to host paperless:8000" }] } },
      offline: { status: "idle", feeder: "unavailable", ui: { source: "adf", duplex: true }, attrs: { printer_online: false } },
      fault: { status: "idle", ui: { source: "adf", duplex: true }, attrs: { printer_state: "Stopped" } },
      batch: { status: "batch", attrs: { batch_pages: 3, batch_expires_at: iso(24 * 60000), batch_auto_send: true } },
      flat: { status: "idle", ui: { source: "platen" } },
    };
    out.heights = {}; out.headline = {};
    for (const width of [360, 320]) {
      for (const [k, o] of Object.entries(cases)) {
        const c2 = mount(o, boxed(width));
        out.heights[`${k}@${width}`] = Math.round(root(c2).querySelector(".body").getBoundingClientRect().height);
        const hl = root(c2).querySelector(".headline");
        if (width === 360) out.headline[k] = [hl.textContent, hl.scrollWidth <= hl.clientWidth];   // headline must not be cut at 360 px
      }
    }
    const bt = mount({ status: "batch", attrs: { batch_pages: 3 } }, document.body);
    out.batchButtons = [...root(bt).querySelectorAll(".actions button")].map((b) => b.textContent);
    const bTops = [...root(bt).querySelectorAll(".actions button")].map((b) => Math.round(b.getBoundingClientRect().top));
    out.batchOneRow = new Set(bTops).size === 1;
    const runC = mount({ status: "running", ui: { source: "adf", duplex: true }, attrs: { pages: 3, detail: "Seite 3 gescannt" } }, boxed(360));
    out.runDetail = root(runC).querySelector(".detail").textContent;
    const runC2 = mount({ status: "running", ui: { source: "adf", duplex: true }, attrs: { pages: 3, detail: "Prüfe auf Leerseiten…" } }, boxed(360));
    out.runDetail2 = root(runC2).querySelector(".detail").textContent;
    out.statusAreas = root(bt).querySelectorAll(".status").length;
    out.oldBanners = root(bt).querySelectorAll(".banner, .live, .stack, .link").length;
    out.statusHeight = Math.round(root(bt).querySelector(".status").getBoundingClientRect().height);

    // --- blank pages on the flatbed ---
    localStorage.clear();
    const bn = mount({ status: "idle", ui: { source: "platen" }, attrs: { notice: "blank_skipped", notice_at: iso(-60000) } }, boxed(360));
    out.notice = [root(bn).querySelector(".status .chip").textContent, root(bn).querySelector(".headline").textContent, root(bn).querySelector(".detail").textContent];
    const bn2 = mount({ status: "batch", attrs: { batch_pages: 2, notice: "blank_skipped", notice_at: iso(-60000) } }, boxed(360));
    out.noticeWithBatch = root(bn2).querySelector(".detail").textContent;
    const bn3 = mount({ status: "idle", ui: { source: "platen" }, attrs: { notice: "blank_skipped", notice_at: iso(-11 * 60000) } }, boxed(360));
    out.noticeStale = root(bn3).querySelector(".status .chip").textContent;          // after 10 minutes the hint is gone
    out.heights.notice = Math.round(root(bn).querySelector(".body").getBoundingClientRect().height);
    out.heights.flat = out.heights.flat || out.heights["flat@360"];
    const pf = mount({ status: "idle", ui: { source: "platen", blank: "off" } }, boxed(360));
    out.pillFlatbedOff = [...root(pf).querySelectorAll(".pill")].some((p2) => /Leerseiten/.test(p2.textContent));
    click(pf, '[data-act="scan"]');
    out.flatbedBlankOff = pf._hass.calls.slice();
    const pf2 = mount({ status: "idle", ui: { source: "platen" } }, boxed(360));        // default: detection on (harness settings)
    out.pillFlatbedOn = [...root(pf2).querySelectorAll(".pill")].some((p2) => /Leerseiten/.test(p2.textContent));
    click(pf2, '[data-act="gear"]'); await tick();
    out.blankSelectOnFlatbed = root(pf2).querySelector('[data-set="blank"]') !== null;

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
  assert.strictEqual(result.en, "Scan");
  assert.ok(/nicht gefunden/.test(result.missing));
  assert.strictEqual(result.nameWhole, true, "the device name must not be cut off (360 px)");
  assert.ok(result.headHeight <= 46, "header height " + result.headHeight);
  assert.strictEqual(result.feederChip, "Einzug: Geladen");
  assert.deepStrictEqual(result.chipOrder, ["Einzug: Geladen", "Bereit"]);
  assert.strictEqual(result.noDots, true, "no coloured dots, no hint text");
  assert.strictEqual(result.scanLabel, "Scannen");
  assert.ok(result.gearSize >= 26, "gear size " + result.gearSize);
  assert.deepStrictEqual(result.feederEmpty, ["Einzug: Leer", true]);
  assert.strictEqual(result.noFeederChipOffline, true);
  assert.strictEqual(result.retryLabel, "Erneut versuchen");
  for (const width of [360, 320]) {
    const hs = Object.entries(result.heights).filter(([k]) => k.endsWith("@" + width)).map(([, v]) => v);
    assert.ok(Math.max(...hs) - Math.min(...hs) <= 1, `card height changes between states at ${width} px: ` + JSON.stringify(result.heights));
  }
  for (const [k, [text, whole]] of Object.entries(result.headline)) assert.ok(whole, `headline of "${k}" is cut off: ${text}`);
  assert.deepStrictEqual(result.batchButtons, ["+ Seite", "Senden", "Verwerfen"]);
  assert.strictEqual(result.batchOneRow, true, "the three batch buttons share one row");
  assert.strictEqual(result.statusAreas, 1, "exactly one status area");
  assert.strictEqual(result.oldBanners, 0, "no separate banners any more");
  assert.strictEqual(result.statusHeight, 88);
  assert.deepStrictEqual(result.notice, ["Hinweis", "Leere Seite erkannt", "Nicht zum Stapel hinzugefügt."]);
  assert.strictEqual(result.noticeWithBatch, "Nicht zum Stapel hinzugefügt. 2 Seiten im Stapel");
  assert.strictEqual(result.noticeStale, "Bereit", "the hint disappears after ten minutes");
  assert.ok(Math.abs(result.heights.notice - result.heights["flat@360"]) <= 1, "the hint does not change the card height");
  assert.strictEqual(result.pillFlatbedOff, false);
  assert.strictEqual(result.pillFlatbedOn, true, "blank-page pill is shown for the flatbed too");
  assert.strictEqual(result.blankSelectOnFlatbed, true, "per-scan setting is offered for the flatbed too");
  assert.deepStrictEqual(result.flatbedBlankOff, [["ha_airscan", "batch_add", { skip_blank: false }]]);
  assert.strictEqual(result.runDetail, "Einzug beidseitig", "no repeat of the counter");
  assert.strictEqual(result.runDetail2, "Prüfe auf Leerseiten…", "special steps are shown");
  assert.strictEqual(result.offChip, "Offline");
  assert.ok(/Drucker nicht erreichbar/.test(result.offBanner) && /Scan wird trotzdem versucht/.test(result.offBanner), result.offBanner);
  assert.strictEqual(result.offScanEnabled, true);
  assert.strictEqual(result.offRunBanner, true);
  assert.strictEqual(result.offRunChip, "Läuft");
  assert.ok(/Drucker-Fehler: Stopped/.test(result.fault) && /Bitte am Gerät nachsehen/.test(result.fault), result.fault);
  assert.strictEqual(result.okNoBanner, true);
  assert.deepStrictEqual(result.queue, [["ha_airscan", "retry_queue", {}]]);
  assert.ok(/2 Scans warten/.test(result.queueText) && /Für Paperless gespeichert/.test(result.queueText) && /Nächster Versuch in 4 min/.test(result.queueText) && /1 von Paperless abgelehnt/.test(result.queueText), result.queueText);
  assert.strictEqual(result.queueChip, "Wartet");
  assert.strictEqual(result.noQueueBanner, true);
  assert.deepStrictEqual(errors, [], "console errors: " + errors.join("; "));
  console.log("card checks passed");
  await browser.close();
})().catch((e) => { console.error(e); process.exit(1); });
