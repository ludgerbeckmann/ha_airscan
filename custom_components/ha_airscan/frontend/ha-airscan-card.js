/* Scan to Paperless card for Home Assistant. Served and registered by the ha_airscan integration.
 *
 *   type: custom:ha-airscan-card
 *   entity: sensor.<scanner>_status      # the "Status" sensor of the scanner
 *   name: Optional title
 *
 * Buttons call the ha_airscan services; everything shown comes from the sensors of the
 * integration. No external libraries.
 */
const CARD_VERSION = "0.8.0";

const T = {
  de: {
    ready: "Bereit", notice: "Hinweis", running: "Läuft", batch: "Stapel", done: "Fertig", queued: "Wartet", error: "Fehler", unavailable: "Nicht verfügbar", offline: "Offline",
    platen: "Flachbett", adf: "Einzug", loaded: "Geladen", empty: "Leer", processing: "Arbeitet", jam: "Papierstau",
    cover_open: "Abdeckung offen", feeder_error: "Fehler",
    simplex: "einseitig", duplex_lc: "beidseitig", scan: "Scannen",
    scanning: "Scannt …", retry: "Erneut versuchen", add_page: "+ Seite", send: "Senden", discard: "Verwerfen",
    last_scan: "Letzter Scan", pages_n: (n) => `${n} ${n === 1 ? "Seite" : "Seiten"}`,
    pages_scanned: "Seiten gescannt", in_batch: (n) => `${n} ${n === 1 ? "Seite" : "Seiten"} im Stapel`,
    batch_hint: "Noch eine Seite? Auf das Flachbett legen.", auto_send: (m) => `Wird in ${m} min automatisch gesendet`,
    reminder: (m) => `Erinnerung in ${m} min`, auto_send_soon: "Wird gleich automatisch gesendet",
    to_paperless: (n) => `${n} → Paperless`, to_file: (n) => `${n} → Datei`, doc: (id) => `Dokument #${id}`,
    blank_removed: (n) => `${n} ${n === 1 ? "Leerseite" : "Leerseiten"} entfernt`, open_paperless: "In Paperless öffnen ↗",
    failed: "Scan fehlgeschlagen", settings: "Einstellungen für den nächsten Scan", resolution: "Auflösung", color: "Farbe",
    gray: "Graustufen", paper: "Format", blank: "Leerseiten", blank_default: "Standard", on: "An", off: "Aus",
    default: "Standard", max: "Volle Fläche", batch_lock: "Erst den Stapel senden oder verwerfen",
    queue_title: (n) => (n === 1 ? "1 Scan wartet" : `${n} Scans warten`), queue_hint: "Für Paperless gespeichert, wird automatisch erneut gesendet.",
    queue_retry: "Jetzt senden", queue_next: (m) => `Nächster Versuch in ${m} min`, queue_rejected: (n) => `${n} von Paperless abgelehnt (Datei bleibt im Ordner ha_airscan_outbox)`, refused_head: (n) => `${n} von Paperless abgelehnt`,
    printer_offline: "Drucker nicht erreichbar", printer_offline_hint: "Ist er eingeschaltet und im Netzwerk? Ein Scan wird trotzdem versucht.",
    printer_fault: (s) => `Drucker-Fehler: ${s}`, printer_fault_hint: "Der Drucker meldet einen Fehler. Bitte am Gerät nachsehen.",
    notice_blank_skipped: "Leere Seite erkannt", notice_blank_detail: "Nicht zum Stapel hinzugefügt.",
    scanned_n: (n) => `${n} ${n === 1 ? "Seite" : "Seiten"} gescannt`, no_scan_yet: "Noch kein Scan", open_short: "Paperless ↗",
    missing: "Entität nicht gefunden – bitte den Status-Sensor des Scanners angeben.",
  },
  en: {
    ready: "Ready", notice: "Notice", running: "Running", batch: "Batch", done: "Done", queued: "Waiting", error: "Error", unavailable: "Unavailable", offline: "Offline",
    platen: "Flatbed", adf: "Feeder", loaded: "Loaded", empty: "Empty", processing: "Busy", jam: "Jam",
    cover_open: "Cover open", feeder_error: "Error",
    simplex: "one-sided", duplex_lc: "two-sided", scan: "Scan",
    scanning: "Scanning …", retry: "Try again", add_page: "+ Page", send: "Send", discard: "Discard",
    last_scan: "Last scan", pages_n: (n) => `${n} ${n === 1 ? "page" : "pages"}`,
    pages_scanned: "pages scanned", in_batch: (n) => `${n} ${n === 1 ? "page" : "pages"} in the batch`,
    batch_hint: "Another page? Put it on the flatbed.", auto_send: (m) => `Sent automatically in ${m} min`,
    reminder: (m) => `Reminder in ${m} min`, auto_send_soon: "Will be sent automatically soon",
    to_paperless: (n) => `${n} → Paperless`, to_file: (n) => `${n} → file`, doc: (id) => `Document #${id}`,
    blank_removed: (n) => `${n} blank ${n === 1 ? "page" : "pages"} removed`, open_paperless: "Open in Paperless ↗",
    failed: "Scan failed", settings: "Settings for the next scan", resolution: "Resolution", color: "Color",
    gray: "Grayscale", paper: "Format", blank: "Blank pages", blank_default: "Default", on: "On", off: "Off",
    default: "Default", max: "Full area", batch_lock: "Send or discard the batch first",
    queue_title: (n) => `${n} ${n === 1 ? "scan" : "scans"} waiting`, queue_hint: "Saved for Paperless, will be sent again automatically.",
    queue_retry: "Send now", queue_next: (m) => `Next attempt in ${m} min`, queue_rejected: (n) => `${n} refused by Paperless (file stays in the ha_airscan_outbox folder)`, refused_head: (n) => `${n} refused by Paperless`,
    printer_offline: "Printer not reachable", printer_offline_hint: "Is it switched on and on the network? A scan will be attempted anyway.",
    printer_fault: (s) => `Printer fault: ${s}`, printer_fault_hint: "The printer reports a fault. Please check the device.",
    notice_blank_skipped: "Blank page detected", notice_blank_detail: "Not added to the batch.",
    scanned_n: (n) => `${n} ${n === 1 ? "page" : "pages"} scanned`, no_scan_yet: "No scan yet", open_short: "Paperless ↗",
    missing: "Entity not found – please select the scanner's status sensor.",
  },
};

const PAGE_SIZES = ["a4", "a5", "letter", "legal", "max"];
const RESOLUTIONS = [100, 200, 300, 600];
const FEEDER_KEYS = { loaded: "loaded", empty: "empty", processing: "processing", jam: "jam", cover_open: "cover_open", error: "feeder_error" };
const STATUS_KEYS = { idle: "ready", batch: "batch", running: "running", done: "done", queued: "queued", error: "error" };

const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));

const STYLE = `
:host{display:block}
ha-card{color:var(--primary-text-color)}
.body{padding:16px;display:flex;flex-direction:column;gap:12px}
.head{display:flex;align-items:center;gap:12px}
.logo{width:44px;height:44px;flex:none;border-radius:12px;background:var(--secondary-background-color);display:grid;place-items:center}
.logo svg{width:30px;height:30px}
.name{flex:1;min-width:0;font-weight:600;font-size:15px;line-height:1.2;overflow-wrap:anywhere;display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical;overflow:hidden}
.chip{flex:none;font-size:12px;font-weight:600;padding:5px 11px;border-radius:99px;white-space:nowrap}
.chip.feeder{font-size:11.5px;padding:4px 10px;background:var(--secondary-background-color);color:var(--secondary-text-color)}
.chip.feeder.loaded{background:color-mix(in srgb,var(--success-color,#15a850) 18%,transparent);color:var(--success-color,#15a850)}
.chip.feeder.processing{background:color-mix(in srgb,var(--primary-color) 16%,transparent);color:var(--primary-color)}
.chip.feeder.jam,.chip.feeder.cover_open,.chip.feeder.error{background:color-mix(in srgb,var(--error-color,#db4437) 16%,transparent);color:var(--error-color,#db4437)}
.chip.ready,.chip.done{background:color-mix(in srgb,var(--success-color,#15a850) 18%,transparent);color:var(--success-color,#15a850)}
.chip.running{background:color-mix(in srgb,var(--primary-color) 16%,transparent);color:var(--primary-color)}
.chip.batch,.chip.queued,.chip.notice{background:color-mix(in srgb,var(--warning-color,#ffa600) 22%,transparent);color:var(--warning-color,#b97700)}
.chip.error,.chip.unavailable{background:color-mix(in srgb,var(--error-color,#db4437) 16%,transparent);color:var(--error-color,#db4437)}
/* the one status area: always the same height, whatever it says */
.status{box-sizing:border-box;height:88px;border-radius:12px;padding:10px 12px;background:var(--secondary-background-color);display:flex;flex-direction:column;gap:4px;overflow:hidden}
.status.ok{background:color-mix(in srgb,var(--success-color,#15a850) 12%,var(--secondary-background-color))}
.status.warn{background:color-mix(in srgb,var(--warning-color,#ffa600) 16%,var(--secondary-background-color))}
.status.err{background:color-mix(in srgb,var(--error-color,#db4437) 12%,var(--secondary-background-color))}
.status.run{background:color-mix(in srgb,var(--primary-color) 10%,var(--secondary-background-color))}
.srow{display:flex;align-items:center;gap:8px;min-height:26px}
.headline{flex:1;min-width:0;font-weight:600;font-size:14.5px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.detail{font-size:12.5px;line-height:1.3;color:var(--secondary-text-color);display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical;overflow:hidden;word-break:break-word}
.act{flex:none;font-size:12.5px;font-weight:600;color:var(--primary-color);text-decoration:none;border:1.5px solid var(--primary-color);border-radius:8px;padding:3px 10px;background:transparent;font-family:inherit;cursor:pointer;white-space:nowrap}
.beam{display:grid;grid-template-columns:repeat(6,1fr);gap:4px;height:6px}
.beam i{border-radius:4px;opacity:.28;background:var(--c)}
.beam i:nth-child(1){--c:#0773BB}.beam i:nth-child(2){--c:#29ACE2}.beam i:nth-child(3){--c:#15A850}
.beam i:nth-child(4){--c:#FDDE0A}.beam i:nth-child(5){--c:#ED078E}.beam i:nth-child(6){--c:#EC2029}
.beam.done i,.beam.running i{opacity:1}
.beam.running i{animation:pulse 1.2s ease-in-out infinite}
.beam.running i:nth-child(2){animation-delay:.1s}.beam.running i:nth-child(3){animation-delay:.2s}
.beam.running i:nth-child(4){animation-delay:.3s}.beam.running i:nth-child(5){animation-delay:.4s}.beam.running i:nth-child(6){animation-delay:.5s}
@keyframes pulse{50%{opacity:.35}}
.beam.error i{background:var(--error-color,#db4437);opacity:1}
.seg{display:grid;grid-auto-flow:column;grid-auto-columns:1fr;background:var(--secondary-background-color);border-radius:12px;padding:4px;gap:4px}
.seg button{border:0;background:transparent;border-radius:9px;padding:8px 4px;font:inherit;font-weight:600;font-size:14px;line-height:1.15;color:var(--secondary-text-color);display:flex;flex-direction:column;align-items:center;justify-content:center;gap:2px;cursor:pointer;min-width:0}
.seg .l1{display:flex;align-items:center;gap:6px}
.seg button.on{background:var(--card-background-color,#fff);color:var(--primary-text-color);box-shadow:0 1px 3px rgba(0,0,0,.2)}
.seg button[disabled]{opacity:.5;cursor:not-allowed}
.seg small{font-weight:500;font-size:11.5px}
.opts{display:flex;flex-wrap:nowrap;gap:6px;align-items:center;min-height:34px}
.opts.off{opacity:.45;pointer-events:none}
.pill{font-size:12px;background:var(--secondary-background-color);color:var(--secondary-text-color);padding:5px 9px;border-radius:99px;font-weight:500;white-space:nowrap;min-width:0;overflow:hidden;text-overflow:ellipsis}
.pill.set{color:var(--primary-color)}
.gear{flex:none;margin-left:auto;border:0;background:transparent;color:var(--secondary-text-color);font-size:28px;line-height:1;cursor:pointer;padding:0 4px}
.gear.on{color:var(--primary-color)}
.panel{background:var(--secondary-background-color);border-radius:12px;padding:12px;display:grid;grid-template-columns:1fr 1fr;gap:10px 12px}
.panel h4{grid-column:1/-1;margin:0;font-size:12.5px;font-weight:600;color:var(--secondary-text-color)}
.panel label{display:flex;flex-direction:column;gap:4px;font-size:12px;color:var(--secondary-text-color)}
.panel select{font:inherit;font-size:14px;padding:8px;border-radius:8px;border:1px solid var(--divider-color);background:var(--card-background-color);color:var(--primary-text-color)}
.actions{display:grid;grid-auto-flow:column;grid-auto-columns:1fr;gap:8px}
.primary,.secondary{box-sizing:border-box;height:48px;border-radius:12px;font:inherit;font-weight:600;font-size:15px;padding:0 6px;width:100%;cursor:pointer;white-space:nowrap}
.primary{border:0;background:var(--primary-color);color:var(--text-primary-color,#fff)}
.primary[disabled]{background:var(--secondary-background-color);color:var(--secondary-text-color);cursor:default}
.secondary{border:1.5px solid var(--primary-color);background:transparent;color:var(--primary-color);font-size:14px}
.secondary.danger{border-color:var(--error-color,#db4437);color:var(--error-color,#db4437)}
.toast{font-size:12.5px;color:var(--error-color,#db4437)}
.missing{color:var(--error-color,#db4437);font-size:14px}
`;

const LOGO = `<svg viewBox="0 0 256 256" aria-hidden="true"><path d="M77 121h102l-12-67H89z" fill="#CDE6D2" stroke="#17541F" stroke-width="5" stroke-linejoin="round"/><rect x="100" y="70" width="56" height="6" rx="3" fill="#17541F"/><rect x="100" y="85" width="42" height="6" rx="3" fill="#17541F"/><rect x="100" y="100" width="28" height="6" rx="3" fill="#17541F"/><rect x="36" y="118" width="184" height="80" rx="18" fill="#0E0F12"/><rect x="52" y="148" width="22" height="14" rx="7" fill="#0773BB"/><rect x="78" y="148" width="22" height="14" rx="7" fill="#29ACE2"/><rect x="104" y="148" width="22" height="14" rx="7" fill="#15A850"/><rect x="130" y="148" width="22" height="14" rx="7" fill="#FDDE0A"/><rect x="156" y="148" width="22" height="14" rx="7" fill="#ED078E"/><rect x="182" y="148" width="22" height="14" rx="7" fill="#EC2029"/></svg>`;

class HaAirscanCard extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({ mode: "open" });
    this._ui = { source: "adf", duplex: false, open: false, resolution: "default", color: "default", page: "default", blank: "default" };
    this._sig = "";
    this._toast = "";
    this._tick = 0;
    this.shadowRoot.addEventListener("click", (e) => this._onClick(e));
    this.shadowRoot.addEventListener("change", (e) => this._onChange(e));
  }

  static getStubConfig(hass) {
    const reg = hass.entities || {};
    const id = Object.keys(reg).find((k) => reg[k].platform === "ha_airscan" && reg[k].translation_key === "status")
      || Object.keys(hass.states).find((k) => k.startsWith("sensor.") && hass.states[k].attributes.batch_pages !== undefined);
    return { entity: id || "" };
  }

  setConfig(config) {
    if (!config || !config.entity) throw new Error("entity (Status-Sensor des Scanners) fehlt");
    this._config = config;
    this._key = `ha-airscan-card:v2:${config.entity}`;
    try { Object.assign(this._ui, JSON.parse(localStorage.getItem(this._key) || "{}")); } catch (_) { /* no storage */ }
    this._ui.open = false;
    this._sig = "";
  }

  getCardSize() { return 5; }

  connectedCallback() {
    this._timer = setInterval(() => { this._tick++; this._update(); }, 30000);
  }

  disconnectedCallback() { clearInterval(this._timer); }

  set hass(hass) { this._hass = hass; this._update(); }

  get _t() { return T[(this._hass?.language || "en").slice(0, 2)] || T.en; }

  _save() { try { localStorage.setItem(this._key, JSON.stringify({ ...this._ui, open: false })); } catch (_) { /* ignore */ } }

  /** Find the other entities of the same scanner via the entity registry. */
  _siblings() {
    const reg = this._hass.entities || {};
    const me = reg[this._config.entity];
    const found = {};
    if (me && me.device_id) {
      for (const [id, e] of Object.entries(reg)) {
        if (e.device_id === me.device_id && e.platform === "ha_airscan" && e.translation_key) found[e.translation_key] = id;
      }
    }
    return { ...found, ...(this._config.entities || {}) };
  }

  _rel(iso) {
    if (!iso) return "";
    const diff = (new Date(iso).getTime() - Date.now()) / 1000;
    const rtf = new Intl.RelativeTimeFormat(this._hass.language || "en", { numeric: "auto", style: "short" });
    const a = Math.abs(diff);
    if (a < 45) return rtf.format(0, "second");
    if (a < 3600) return rtf.format(Math.round(diff / 60), "minute");
    if (a < 86400) return rtf.format(Math.round(diff / 3600), "hour");
    return rtf.format(Math.round(diff / 86400), "day");
  }

  _overrides(forBatch) {
    const o = {};
    if (this._ui.resolution !== "default") o.resolution = Number(this._ui.resolution);
    if (this._ui.color !== "default") o.color_mode = this._ui.color;
    if (this._ui.page !== "default") o.page_size = this._ui.page;
    if (this._ui.blank !== "default") o.skip_blank = this._ui.blank === "on";
    return o;
  }

  _call(service, data = {}) {
    if (this._config.config_entry) data = { config_entry: this._config.config_entry, ...data };
    this._hass.callService("ha_airscan", service, data).catch((err) => {
      this._toast = (err && err.message) || String(err);
      this._sig = ""; this._update();
      setTimeout(() => { this._toast = ""; this._sig = ""; this._update(); }, 10000);
    });
  }

  _onClick(e) {
    const el = e.target.closest("[data-act]");
    if (!el || el.disabled) return;
    const act = el.dataset.act;
    const ui = this._ui;
    if (act === "mode") {
      const v = el.dataset.v;
      ui.source = v === "platen" ? "platen" : "adf";
      if (v !== "platen") ui.duplex = v === "adf2";
      this._save(); this._sig = ""; this._update();
    }
    else if (act === "gear") { ui.open = !ui.open; this._sig = ""; this._update(); }
    else if (act === "scan") {
      if (ui.source === "adf") this._call("scan", { source: "adf", duplex: ui.duplex && this._caps.duplex, ...this._overrides(false) });
      else this._call("batch_add", this._overrides(true));
    }
    else if (act === "add") this._call("batch_add", this._overrides(true));
    else if (act === "send") this._call("batch_send");
    else if (act === "discard") this._call("batch_discard");
    else if (act === "retry") this._call("retry_queue");
  }

  _onChange(e) {
    const el = e.target.closest("[data-set]");
    if (!el) return;
    this._ui[el.dataset.set] = el.value;
    this._save(); this._sig = ""; this._update();
  }

  _update() {
    if (!this._hass || !this._config) return;
    const st = this._hass.states[this._config.entity];
    const sib = this._siblings();
    const get = (k) => (sib[k] ? this._hass.states[sib[k]] : undefined);
    const feeder = get("feeder");
    const last = get("last_scan");
    const queue = get("queue");
    const a = st ? st.attributes : {};
    const sig = JSON.stringify([st && st.state, a, feeder && feeder.state, last && last.state, queue && [queue.state, queue.attributes.next_retry, queue.attributes.rejected], this._ui, this._toast, this._tick, this._hass.language]);
    if (sig === this._sig) return;
    this._sig = sig;
    this._render(st, a, sib, feeder, last, queue);
  }

  _render(st, a, sib, feeder, last, queue) {
    const t = this._t;
    const root = this.shadowRoot;
    if (!st) { root.innerHTML = `<style>${STYLE}</style><ha-card><div class="body"><div class="missing">${esc(t.missing)}</div></div></ha-card>`; return; }

    const hasRegistry = Object.keys(sib).length > 0;
    const caps = hasRegistry
      ? { platen: !!sib.scan_platen, adf: !!sib.scan_adf_simplex, duplex: !!sib.scan_adf_duplex }
      : { platen: true, adf: !!feeder, duplex: true };
    this._caps = caps;
    const ui = this._ui;
    const status = ["unavailable", "unknown"].includes(st.state) ? "unavailable" : st.state;
    const batchPages = Number(a.batch_pages || 0);
    const locked = batchPages > 0 && caps.platen;           // a flatbed batch is open
    if (!caps.adf) ui.source = "platen";
    if (!caps.platen) ui.source = "adf";
    const source = locked ? "platen" : ui.source;
    const running = status === "running";
    const settings = a.settings || {};
    const finished = (last && !["unknown", "unavailable"].includes(last.state) ? last.state : a.finished_at) || null;

    const deviceName = (this._hass.devices && sib.status && this._hass.entities[this._config.entity]?.device_id
      && this._hass.devices[this._hass.entities[this._config.entity].device_id]?.name) || "";
    const name = this._config.name || deviceName || (st.attributes.friendly_name || "Scanner").replace(/\s+(Status|Zustand)$/i, "");

    // ---- the one status area: chip, headline, detail, optional action -------------------------
    const offline = a.printer_online === false && !running;
    const fault = a.printer_online !== false && ["Stopped", "Down"].includes(a.printer_state) && !running;
    const waiting = queue && !["unknown", "unavailable"].includes(queue.state) ? Number(queue.state) : 0;
    const refused = queue ? Number(queue.attributes.rejected || 0) : 0;
    const where = a.destination === "file" ? t.to_file : t.to_paperless;
    const resultBits = [a.document_id ? t.doc(a.document_id) : "", a.blank_removed ? t.blank_removed(a.blank_removed) : ""].filter(Boolean).join(" · ");
    const paperlessLink = a.paperless_url && a.document_id && a.destination === "paperless"
      ? { href: `${String(a.paperless_url).replace(/\/+$/, "")}/documents/${a.document_id}/details`, text: t.open_short } : null;
    let info;
    if (running) {
      const step = String(a.detail || "");
      const generic = /^(Seite \d+ gescannt|Scannt…?( \(Versuch \d+\))?|Scan startet)$/.test(step);   // the counter above already says this
      const modeText = source === "adf" ? `${t.adf} ${ui.duplex && caps.duplex ? t.duplex_lc : t.simplex}` : t.platen;
      info = { tone: "run", chip: "running", headline: Number(a.pages || 0) > 0 ? t.scanned_n(Number(a.pages)) : t.scanning, detail: generic || !step ? modeText : step };
    } else if (offline) {
      info = { tone: "err", chip: "offline", chipCls: "unavailable", headline: t.printer_offline, detail: t.printer_offline_hint };
    } else if (fault) {
      info = { tone: "err", chip: "error", headline: t.printer_fault(a.printer_state), detail: t.printer_fault_hint };
    } else if (status === "error") {
      info = { tone: "err", chip: "error", headline: t.failed, detail: String(a.detail || "").replace(/^Scan fehlgeschlagen:\s*/i, "") };
    } else if (a.notice === "blank_skipped" && a.notice_at && Date.now() - new Date(a.notice_at).getTime() < 600000) {
      info = { tone: "warn", chip: "notice", headline: t.notice_blank_skipped, detail: [t.notice_blank_detail, batchPages > 0 ? t.in_batch(batchPages) : ""].filter(Boolean).join(" ") };
    } else if (batchPages > 0) {
      const mins = a.batch_expires_at ? Math.ceil((new Date(a.batch_expires_at).getTime() - Date.now()) / 60000) : null;
      const timer = mins === null ? "" : (mins <= 0 ? t.auto_send_soon : (a.batch_auto_send ? t.auto_send(mins) : t.reminder(mins)));
      info = { tone: "warn", chip: "batch", headline: t.in_batch(batchPages), detail: `${t.batch_hint} ${timer}`.trim() };
    } else if (waiting > 0 || refused > 0) {
      const next = queue.attributes.next_retry ? Math.ceil((new Date(queue.attributes.next_retry).getTime() - Date.now()) / 60000) : null;
      const lastError = (queue.attributes.items || []).map((i) => i.last_error).filter(Boolean).pop() || "";
      info = { tone: "warn", chip: "queued", headline: waiting > 0 ? t.queue_title(waiting) : t.refused_head(refused),
        detail: [waiting > 0 ? `${t.queue_hint}${next && next > 0 ? " " + t.queue_next(next) : ""}` : t.queue_rejected(refused), waiting > 0 && refused > 0 ? t.queue_rejected(refused) : "", lastError].filter(Boolean).join(" "),
        action: waiting > 0 ? { act: "retry", text: t.queue_retry } : null };
    } else if (status === "done") {
      info = { tone: "ok", chip: "done", headline: t.pages_n(a.pages || 0), detail: [where("").trim(), resultBits, finished ? this._rel(finished) : ""].filter(Boolean).join(" · "), link: paperlessLink };
    } else {
      info = { tone: "", chip: status === "unavailable" ? "unavailable" : "ready", chipCls: status === "unavailable" ? "unavailable" : "ready",
        headline: finished ? `${t.last_scan} ${this._rel(finished)}` : t.no_scan_yet,
        detail: finished && a.destination ? [where(t.pages_n(a.pages || 0)), a.document_id ? t.doc(a.document_id) : ""].filter(Boolean).join(" · ") : "" };
    }
    const chipCls = info.chipCls || info.chip;
    const actionHtml = info.action
      ? `<button class="act" data-act="${info.action.act}">${esc(info.action.text)}</button>`
      : info.link ? `<a class="act" href="${esc(info.link.href)}" target="_blank" rel="noopener">${esc(info.link.text)}</a>` : "";
    const statusBox = `<div class="status ${info.tone}">
        <div class="srow"><span class="chip ${esc(chipCls)}">${esc(t[info.chip])}</span><span class="headline" title="${esc(info.headline)}">${esc(info.headline)}</span>${actionHtml}</div>
        <div class="detail" title="${esc(info.detail)}">${esc(info.detail)}</div>
      </div>`;

    // feeder state at the top right (not when the printer is unreachable)
    const feederState = caps.adf && feeder && FEEDER_KEYS[feeder.state] ? feeder.state : null;
    const feederChip = feederState
      ? `<span class="chip feeder ${esc(feederState)}">${esc(t.adf)}: ${esc(t[FEEDER_KEYS[feederState]])}</span>` : "";
    const beam = running ? "running" : status === "done" ? "done" : status === "error" ? "error" : "";

    // ---- scan mode -------------------------------------------------------------------------------
    const modes = [];
    if (caps.adf) {
      modes.push({ id: "adf1", feeder: true, l1: t.adf, l2: t.simplex });
      if (caps.duplex) modes.push({ id: "adf2", feeder: true, l1: t.adf, l2: t.duplex_lc });
    }
    if (caps.platen) modes.push({ id: "platen", feeder: false, l1: t.platen, l2: "" });
    const modeNow = source === "platen" ? "platen" : (ui.duplex && caps.duplex ? "adf2" : "adf1");
    const modeButton = (m) => `<button data-act="mode" data-v="${m.id}" class="${modeNow === m.id ? "on" : ""}" ${running || (locked && m.feeder) ? "disabled" : ""} ${locked && m.feeder ? `title="${esc(t.batch_lock)}"` : ""}>
        <span class="l1">${esc(m.l1)}</span>${m.l2 ? `<small>${esc(m.l2)}</small>` : ""}</button>`;
    const seg = modes.length > 1 ? `<div class="seg">${modes.map(modeButton).join("")}</div>` : "";

    // ---- options row (dimmed while scanning or while a batch is open) + settings panel ----------
    const off = running || locked;
    const eff = {
      res: ui.resolution !== "default" ? ui.resolution : settings.resolution,
      color: ui.color !== "default" ? ui.color : settings.color_mode,
      page: ui.page !== "default" ? ui.page : settings.page_size,
    };
    const blankOn = ui.blank !== "default" ? ui.blank === "on" : !!settings.blank_detection;
    const pill = (txt, set) => `<span class="pill ${set ? "set" : ""}">${esc(txt)}</span>`;
    const opts = `<div class="opts ${off ? "off" : ""}">
        ${eff.res ? pill(`${eff.res} dpi`, ui.resolution !== "default") : ""}
        ${eff.color ? pill(eff.color === "grayscale" ? t.gray : t.color, ui.color !== "default") : ""}
        ${eff.page ? pill(eff.page === "max" ? t.max : String(eff.page).toUpperCase(), ui.page !== "default") : ""}
        ${blankOn ? pill(`${t.blank} ✓`, ui.blank !== "default") : ""}
        <button class="gear ${ui.open ? "on" : ""}" data-act="gear" aria-label="${esc(t.settings)}" title="${esc(t.settings)}" ${off ? "disabled" : ""}>⚙︎</button>
      </div>`;
    let panel = "";
    if (ui.open && !off) {
      const sel = (key, items) => `<select data-set="${key}">${items.map(([v, l]) => `<option value="${esc(v)}" ${ui[key] === v ? "selected" : ""}>${esc(l)}</option>`).join("")}</select>`;
      panel = `<div class="panel"><h4>${esc(t.settings)}</h4>
          <label>${esc(t.resolution)}${sel("resolution", [["default", `${t.default} (${settings.resolution || "–"})`], ...RESOLUTIONS.map((r) => [String(r), `${r} dpi`])])}</label>
          <label>${esc(t.color)}${sel("color", [["default", t.default], ["color", t.color], ["grayscale", t.gray]])}</label>
          <label>${esc(t.paper)}${sel("page", [["default", t.default], ...PAGE_SIZES.map((p) => [p, p === "max" ? t.max : p.toUpperCase()])])}</label>
          <label>${esc(t.blank)}${sel("blank", [["default", t.blank_default], ["on", t.on], ["off", t.off]])}</label>
        </div>`;
    }

    // ---- buttons: one row, always the same height --------------------------------------------------
    let actions;
    if (running) actions = `<div class="actions"><button class="primary" disabled>${esc(t.scanning)}</button></div>`;
    else if (locked) actions = `<div class="actions"><button class="secondary" data-act="add">${esc(t.add_page)}</button><button class="primary" data-act="send">${esc(t.send)}</button><button class="secondary danger" data-act="discard">${esc(t.discard)}</button></div>`;
    else actions = `<div class="actions"><button class="primary" data-act="scan" ${status === "unavailable" ? "disabled" : ""}>${esc(status === "error" ? t.retry : t.scan)}</button></div>`;

    root.innerHTML = `<style>${STYLE}</style><ha-card><div class="body">
      <div class="head"><div class="logo">${LOGO}</div><div class="name" title="${esc(name)}">${esc(name)}</div>${feederChip}</div>
      <div class="beam ${beam}"><i></i><i></i><i></i><i></i><i></i><i></i></div>
      ${statusBox}${seg}${opts}${panel}${actions}
      ${this._toast ? `<div class="toast">${esc(this._toast)}</div>` : ""}
    </div></ha-card>`;
  }
}

if (!customElements.get("ha-airscan-card")) customElements.define("ha-airscan-card", HaAirscanCard);
window.customCards = window.customCards || [];
if (!window.customCards.some((c) => c.type === "ha-airscan-card")) {
  window.customCards.push({ type: "ha-airscan-card", name: "Scan to Paperless", description: "Scan via eSCL (flatbed, feeder, duplex, batch) and send to Paperless-ngx.", preview: false });
}
console.info(`%c AIRSCAN-CARD %c ${CARD_VERSION} `, "background:#0773BB;color:#fff;border-radius:3px 0 0 3px", "background:#eee;color:#333;border-radius:0 3px 3px 0");
