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
    ready: "Bereit", running: "Läuft", batch: "Stapel", done: "Fertig", queued: "Wartet", error: "Fehler", unavailable: "Nicht verfügbar", offline: "Offline",
    platen: "Flachbett", adf: "Einzug", loaded: "Geladen", empty: "Leer", processing: "Arbeitet", jam: "Papierstau",
    cover_open: "Abdeckung offen", feeder_error: "Fehler",
    simplex: "einseitig", duplex_lc: "beidseitig", feeder_reports: "Einzug meldet:", scan_glass: "Seite scannen", scan_adf: "Einzug scannen", scan_adf_duplex: "Einzug scannen · beidseitig",
    scanning: "Scannt …", retry: "Erneut versuchen", add_page: "+ Weitere Seite", send: "Senden", discard: "Stapel verwerfen",
    last_scan: "Letzter Scan", pages_n: (n) => `${n} ${n === 1 ? "Seite" : "Seiten"}`,
    pages_scanned: "Seiten gescannt", in_batch: (n) => `${n} ${n === 1 ? "Seite" : "Seiten"} im Stapel`,
    batch_hint: "Noch eine Seite? Auf das Flachbett legen.", auto_send: (m) => `Wird in ${m} min automatisch gesendet`,
    reminder: (m) => `Erinnerung in ${m} min`, auto_send_soon: "Wird gleich automatisch gesendet",
    to_paperless: (n) => `${n} → Paperless`, to_file: (n) => `${n} → Datei`, doc: (id) => `Dokument #${id}`,
    blank_removed: (n) => `${n} ${n === 1 ? "Leerseite" : "Leerseiten"} entfernt`, open_paperless: "In Paperless öffnen ↗",
    failed: "Scan fehlgeschlagen", settings: "Einstellungen für den nächsten Scan", resolution: "Auflösung", color: "Farbe",
    gray: "Graustufen", paper: "Format", blank: "Leerseiten", blank_default: "Standard", on: "An", off: "Aus",
    default: "Standard", max: "Volle Fläche", batch_lock: "Erst den Stapel senden oder verwerfen",
    queue_title: (n) => `${n} ${n === 1 ? "Scan wartet" : "Scans warten"} auf Paperless`, queue_hint: "Gespeichert, wird automatisch erneut gesendet.",
    queue_retry: "Jetzt senden", queue_next: (m) => `Nächster Versuch in ${m} min`, queue_rejected: (n) => `${n} von Paperless abgelehnt (Datei bleibt im Ordner ha_airscan_outbox)`,
    printer_offline: "Drucker nicht erreichbar", printer_offline_hint: "Ist er eingeschaltet und im Netzwerk? Ein Scan wird trotzdem versucht.",
    printer_fault: (s) => `Der Drucker meldet einen Fehler (${s}).`,
    missing: "Entität nicht gefunden – bitte den Status-Sensor des Scanners angeben.",
  },
  en: {
    ready: "Ready", running: "Running", batch: "Batch", done: "Done", queued: "Waiting", error: "Error", unavailable: "Unavailable", offline: "Offline",
    platen: "Flatbed", adf: "Feeder", loaded: "Loaded", empty: "Empty", processing: "Busy", jam: "Jam",
    cover_open: "Cover open", feeder_error: "Error",
    simplex: "one-sided", duplex_lc: "two-sided", feeder_reports: "Feeder reports:", scan_glass: "Scan page", scan_adf: "Scan feeder", scan_adf_duplex: "Scan feeder · two-sided",
    scanning: "Scanning …", retry: "Try again", add_page: "+ Another page", send: "Send", discard: "Discard batch",
    last_scan: "Last scan", pages_n: (n) => `${n} ${n === 1 ? "page" : "pages"}`,
    pages_scanned: "pages scanned", in_batch: (n) => `${n} ${n === 1 ? "page" : "pages"} in the batch`,
    batch_hint: "Another page? Put it on the flatbed.", auto_send: (m) => `Sent automatically in ${m} min`,
    reminder: (m) => `Reminder in ${m} min`, auto_send_soon: "Will be sent automatically soon",
    to_paperless: (n) => `${n} → Paperless`, to_file: (n) => `${n} → file`, doc: (id) => `Document #${id}`,
    blank_removed: (n) => `${n} blank ${n === 1 ? "page" : "pages"} removed`, open_paperless: "Open in Paperless ↗",
    failed: "Scan failed", settings: "Settings for the next scan", resolution: "Resolution", color: "Color",
    gray: "Grayscale", paper: "Format", blank: "Blank pages", blank_default: "Default", on: "On", off: "Off",
    default: "Default", max: "Full area", batch_lock: "Send or discard the batch first",
    queue_title: (n) => `${n} ${n === 1 ? "scan is" : "scans are"} waiting for Paperless`, queue_hint: "Saved, will be sent again automatically.",
    queue_retry: "Send now", queue_next: (m) => `Next attempt in ${m} min`, queue_rejected: (n) => `${n} refused by Paperless (file stays in the ha_airscan_outbox folder)`,
    printer_offline: "Printer not reachable", printer_offline_hint: "Is it switched on and on the network? A scan will be attempted anyway.",
    printer_fault: (s) => `The printer reports a fault (${s}).`,
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
.t{flex:1;min-width:0}
.name{font-weight:600;font-size:16px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.sub{font-size:12.5px;color:var(--secondary-text-color);margin-top:2px;line-height:1.3}
.chip{flex:none;font-size:12px;font-weight:600;padding:5px 11px;border-radius:99px;white-space:nowrap}
.chip.ready,.chip.done{background:color-mix(in srgb,var(--success-color,#15a850) 18%,transparent);color:var(--success-color,#15a850)}
.chip.running{background:color-mix(in srgb,var(--primary-color) 16%,transparent);color:var(--primary-color)}
.chip.batch,.chip.queued{background:color-mix(in srgb,var(--warning-color,#ffa600) 22%,transparent);color:var(--warning-color,#b97700)}
.chip.error,.chip.unavailable{background:color-mix(in srgb,var(--error-color,#db4437) 16%,transparent);color:var(--error-color,#db4437)}
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
.dot{width:8px;height:8px;border-radius:50%;background:var(--disabled-text-color,#9e9e9e)}
.dot.loaded{background:var(--success-color,#15a850)}.dot.empty,.dot.jam,.dot.cover_open,.dot.error{background:var(--error-color,#db4437)}.dot.processing{background:#29ACE2}
.opts{display:flex;flex-wrap:wrap;gap:6px;align-items:center}
.feeder-hint{font-size:12.5px;margin:-4px 2px 0;color:var(--error-color,#db4437)}
.pill{font-size:12px;background:var(--secondary-background-color);color:var(--secondary-text-color);padding:5px 9px;border-radius:99px;font-weight:500;white-space:nowrap}
.pill.set{color:var(--primary-color)}
.gear{margin-left:auto;border:0;background:transparent;color:var(--secondary-text-color);font-size:20px;cursor:pointer;padding:2px 6px}
.gear.on{color:var(--primary-color)}
.panel{background:var(--secondary-background-color);border-radius:12px;padding:12px;display:grid;grid-template-columns:1fr 1fr;gap:10px 12px}
.panel h4{grid-column:1/-1;margin:0;font-size:12.5px;font-weight:600;color:var(--secondary-text-color)}
.panel label{display:flex;flex-direction:column;gap:4px;font-size:12px;color:var(--secondary-text-color)}
.panel select{font:inherit;font-size:14px;padding:8px;border-radius:8px;border:1px solid var(--divider-color);background:var(--card-background-color);color:var(--primary-text-color)}
.primary,.secondary{border-radius:12px;font:inherit;font-weight:600;font-size:15px;padding:14px;width:100%;cursor:pointer}
.primary{border:0;background:var(--primary-color);color:var(--text-primary-color,#fff)}
.primary[disabled]{background:var(--secondary-background-color);color:var(--secondary-text-color);cursor:default}
.secondary{border:1.5px solid var(--primary-color);background:transparent;color:var(--primary-color);font-size:14px}
.link{border:0;background:transparent;font:inherit;font-weight:600;font-size:13px;padding:2px;color:var(--secondary-text-color);cursor:pointer;align-self:center}
.link.danger{color:var(--error-color,#db4437)}
.row{display:grid;grid-template-columns:1fr 1fr;gap:10px}
.live,.stack{display:flex;align-items:center;gap:14px;background:var(--secondary-background-color);border-radius:12px;padding:14px}
.big{font-size:44px;font-weight:700;line-height:1;color:var(--primary-color);min-width:48px;text-align:center}
.lt{display:flex;flex-direction:column;gap:3px;min-width:0}.lt b{font-size:15px}.lt span{font-size:12.5px;color:var(--secondary-text-color)}
.banner{border-radius:12px;padding:12px 14px;display:flex;flex-direction:column;gap:3px}
.banner b{font-size:14.5px}.banner span{font-size:12.5px;word-break:break-word}
.banner a{font-size:13px;font-weight:600;margin-top:4px;color:inherit}
.banner.ok{background:color-mix(in srgb,var(--success-color,#15a850) 16%,transparent);color:var(--success-color,#0e7a3a)}
.banner.warn{background:color-mix(in srgb,var(--warning-color,#ffa600) 20%,transparent);color:var(--warning-color,#8a5a00)}
.banner .retry{align-self:flex-start;margin-top:6px;border:1.5px solid currentColor;background:transparent;color:inherit;border-radius:8px;font:inherit;font-weight:600;font-size:13px;padding:6px 12px;cursor:pointer}
.banner.err{background:color-mix(in srgb,var(--error-color,#db4437) 14%,transparent);color:var(--error-color,#b3141b)}
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
    if (!forBatch && this._ui.blank !== "default") o.skip_blank = this._ui.blank === "on";
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

    // sub line
    let sub = "";
    if (status === "batch" || (batchPages > 0 && !running)) {
      const mins = a.batch_expires_at ? Math.ceil((new Date(a.batch_expires_at).getTime() - Date.now()) / 60000) : null;
      if (mins !== null) sub = mins <= 0 ? t.auto_send_soon : (a.batch_auto_send ? t.auto_send(mins) : t.reminder(mins));
    } else if (running) sub = `${t[source === "adf" ? "adf" : "platen"]}${source === "adf" && ui.duplex && caps.duplex ? ` · ${t.duplex_lc}` : ""} · ${t.scanning.replace(/ …$/, "")}`;
    else if (finished) sub = `${t.last_scan} ${this._rel(finished)}` + (status === "done" && a.pages ? ` · ${t.pages_n(a.pages)}` : "");

    // The printer did not answer the status polls (shown unless a scan is running or being delivered)
    const offline = a.printer_online === false && !running;
    const fault = a.printer_online !== false && ["Stopped", "Down"].includes(a.printer_state) && !running;
    let chipKey = status === "unavailable" ? "unavailable" : (STATUS_KEYS[status] || "ready");
    let chipCls = status === "idle" ? "ready" : (status === "unavailable" ? "unavailable" : status);
    if (offline && ["idle", "done", "error"].includes(status)) { chipKey = "offline"; chipCls = "unavailable"; }
    const beam = running ? "running" : status === "done" ? "done" : status === "error" ? "error" : "";

    // source selector
    const feederKey = feeder ? (FEEDER_KEYS[feeder.state] || null) : null;
    const modes = [];
    if (caps.adf) {
      modes.push({ id: "adf1", feeder: true, l1: t.adf, l2: t.simplex });
      if (caps.duplex) modes.push({ id: "adf2", feeder: true, l1: t.adf, l2: t.duplex_lc });
    }
    if (caps.platen) modes.push({ id: "platen", feeder: false, l1: t.platen, l2: "" });
    const modeNow = source === "platen" ? "platen" : (ui.duplex && caps.duplex ? "adf2" : "adf1");
    const modeButton = (m) => `<button data-act="mode" data-v="${m.id}" class="${modeNow === m.id ? "on" : ""}" ${running || (locked && m.feeder) ? "disabled" : ""} ${locked && m.feeder ? `title="${esc(t.batch_lock)}"` : ""}>
        <span class="l1">${m.feeder && feederKey ? `<span class="dot ${esc(feeder.state)}" title="${esc(t[feederKey])}"></span>` : ""}${esc(m.l1)}</span>${m.l2 ? `<small>${esc(m.l2)}</small>` : ""}</button>`;
    const seg = modes.length > 1 ? `<div class="seg">${modes.map(modeButton).join("")}</div>` : "";
    // the feeder state as text only when it needs attention (it can be stale after standby)
    const feederHint = source === "adf" && feederKey && !running && !["loaded", "processing"].includes(feeder.state)
      ? `<div class="feeder-hint">${esc(t.feeder_reports)} ${esc(t[feederKey])}</div>` : "";

    // middle part by status
    let middle = "";
    if (running) {
      middle = `<div class="live"><div class="big">${Number(a.pages || 0)}</div><div class="lt"><b>${esc(t.pages_scanned)}</b><span>${esc(a.detail || "")}</span></div></div>`;
    } else if (batchPages > 0) {
      middle = `<div class="stack"><div class="lt"><b>${esc(t.in_batch(batchPages))}</b><span>${esc(t.batch_hint)}</span></div></div>`;
    }
    let banner = "";
    if (!running && status === "done" && !batchPages) {
      const where = a.destination === "file" ? t.to_file(t.pages_n(a.pages || 0)) : t.to_paperless(t.pages_n(a.pages || 0));
      const bits = [a.document_id ? t.doc(a.document_id) : "", a.blank_removed ? t.blank_removed(a.blank_removed) : ""].filter(Boolean).join(" · ");
      const link = a.paperless_url && a.document_id && a.destination === "paperless"
        ? `<a href="${esc(String(a.paperless_url).replace(/\/+$/, ""))}/documents/${esc(a.document_id)}/details" target="_blank" rel="noopener">${esc(t.open_paperless)}</a>` : "";
      banner = `<div class="banner ok"><b>${esc(where)}</b>${bits ? `<span>${esc(bits)}</span>` : ""}${link}</div>`;
    } else if (status === "queued") {
      banner = "";   // the queue box below explains it
    } else if (status === "error") {
      banner = `<div class="banner err"><b>${esc(t.failed)}</b><span>${esc(String(a.detail || "").replace(/^Scan fehlgeschlagen:\s*/i, ""))}</span></div>`;
    }

    const printerBox = offline
      ? `<div class="banner err"><b>${esc(t.printer_offline)}</b><span>${esc(t.printer_offline_hint)}</span></div>`
      : fault ? `<div class="banner err"><b>${esc(t.printer_fault(a.printer_state))}</b></div>` : "";

    // scans waiting for Paperless (stored on disk, retried automatically)
    const waiting = queue && !["unknown", "unavailable"].includes(queue.state) ? Number(queue.state) : 0;
    const refused = queue ? Number(queue.attributes.rejected || 0) : 0;
    let queueBox = "";
    if (waiting > 0 || refused > 0) {
      const next = queue.attributes.next_retry ? Math.ceil((new Date(queue.attributes.next_retry).getTime() - Date.now()) / 60000) : null;
      const lastError = (queue.attributes.items || []).map((i) => i.last_error).filter(Boolean).pop() || "";
      queueBox = `<div class="banner warn">${waiting > 0 ? `<b>${esc(t.queue_title(waiting))}</b><span>${esc(t.queue_hint)}${next && next > 0 ? " " + esc(t.queue_next(next)) : ""}</span>${lastError ? `<span>${esc(lastError)}</span>` : ""}` : ""}${refused > 0 ? `<span>${esc(t.queue_rejected(refused))}</span>` : ""}${waiting > 0 ? `<button class="retry" data-act="retry">${esc(t.queue_retry)}</button>` : ""}</div>`;
    }

    // options row + settings panel (not while running or while a batch is open)
    let opts = "", panel = "";
    if (!running && !locked) {
      const eff = {
        res: ui.resolution !== "default" ? ui.resolution : settings.resolution,
        color: ui.color !== "default" ? ui.color : settings.color_mode,
        page: ui.page !== "default" ? ui.page : settings.page_size,
      };
      const blankOn = ui.blank !== "default" ? ui.blank === "on" : !!settings.blank_detection;
      const pill = (txt, set) => `<span class="pill ${set ? "set" : ""}">${esc(txt)}</span>`;
      opts = `<div class="opts">
        ${eff.res ? pill(`${eff.res} dpi`, ui.resolution !== "default") : ""}
        ${eff.color ? pill(eff.color === "grayscale" ? t.gray : t.color, ui.color !== "default") : ""}
        ${eff.page ? pill(eff.page === "max" ? t.max : String(eff.page).toUpperCase(), ui.page !== "default") : ""}
        ${source === "adf" && blankOn ? pill(`${t.blank} ✓`, ui.blank !== "default") : ""}
        <button class="gear ${ui.open ? "on" : ""}" data-act="gear" aria-label="${esc(t.settings)}" title="${esc(t.settings)}">⚙︎</button>
      </div>`;
      if (ui.open) {
        const sel = (key, items) => `<select data-set="${key}">${items.map(([v, l]) => `<option value="${esc(v)}" ${ui[key] === v ? "selected" : ""}>${esc(l)}</option>`).join("")}</select>`;
        panel = `<div class="panel"><h4>${esc(t.settings)}</h4>
          <label>${esc(t.resolution)}${sel("resolution", [["default", `${t.default} (${settings.resolution || "–"})`], ...RESOLUTIONS.map((r) => [String(r), `${r} dpi`])])}</label>
          <label>${esc(t.color)}${sel("color", [["default", t.default], ["color", t.color], ["grayscale", t.gray]])}</label>
          <label>${esc(t.paper)}${sel("page", [["default", t.default], ...PAGE_SIZES.map((p) => [p, p === "max" ? t.max : p.toUpperCase()])])}</label>
          ${source === "adf" ? `<label>${esc(t.blank)}${sel("blank", [["default", t.blank_default], ["on", t.on], ["off", t.off]])}</label>` : ""}
        </div>`;
      }
    }

    // actions
    let actions = "";
    if (running) actions = `<button class="primary" disabled>${esc(t.scanning)}</button>`;
    else if (locked) actions = `<div class="row"><button class="secondary" data-act="add">${esc(t.add_page)}</button><button class="primary" data-act="send">${esc(t.send)}</button></div>
        <button class="link danger" data-act="discard">${esc(t.discard)}</button>`;
    else {
      const label = status === "error" ? t.retry : source === "adf" ? (ui.duplex && caps.duplex ? t.scan_adf_duplex : t.scan_adf) : t.scan_glass;
      actions = `<button class="primary" data-act="scan" ${status === "unavailable" ? "disabled" : ""}>${esc(label)}</button>`;
    }

    root.innerHTML = `<style>${STYLE}</style><ha-card><div class="body">
      <div class="head"><div class="logo">${LOGO}</div><div class="t"><div class="name">${esc(name)}</div><div class="sub">${esc(sub)}</div></div><span class="chip ${chipCls}">${esc(t[chipKey])}</span></div>
      <div class="beam ${beam}"><i></i><i></i><i></i><i></i><i></i><i></i></div>
      ${seg}${feederHint}${middle}${printerBox}${banner}${queueBox}${opts}${panel}${actions}
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
