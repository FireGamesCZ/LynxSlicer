"""The Spools page: one self-contained HTML document. Talks to ui_api through
orca.postMessage / orca.onMessage. Database text is only ever set with textContent."""

PAGE = r"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>Spools</title>
<style>
  /* Inside OrcaSlicer the host injects --orca-* variables, data-orca-theme and color-scheme; the fallbacks
     (and prefers-color-scheme) only apply when they are absent, e.g. in the dev server. */
  :root { --bg:var(--orca-bg,#f6f6f7); --fg:var(--orca-fg,#1d1d1f); --muted:var(--orca-muted,#6a6a70);
          --line:var(--orca-border,#d5d5da); --accent:var(--orca-accent,#2b6fd6); --accent-fg:var(--orca-accent-fg,#fff);
          --card:color-mix(in srgb, var(--bg), var(--fg) 4%); --ctl:color-mix(in srgb, var(--bg), var(--fg) 55%);
          --bar:#e3e3e8; --ok:#2f9e5b; --warn:#d98a00; --bad:#b42318; --errbg:#fde8e8; }
  :root:not([data-orca-theme]) { color-scheme: light dark; }
  @media (prefers-color-scheme: dark) {
    :root:not([data-orca-theme]) { --bg:#1c1c1f; --fg:#ececef; --muted:#9a9aa3; --line:#3d4043; --accent:#5b9bff;
            --accent-fg:#0b0b0d; --bar:#3a3a40; --ok:#4cc27f; --warn:#f0b13a; --bad:#ff8a8a; --errbg:#4a2323; } }
  :root[data-orca-theme=dark] { --bar:#3a3a40; --ok:#4cc27f; --warn:#f0b13a; --bad:#ff8a8a; --errbg:#4a2323; }
  * { box-sizing: border-box; }
  body { margin:0; padding:16px; background:var(--bg); color:var(--fg); font:14px/1.4 system-ui, sans-serif; }
  h1 { font-size:18px; margin:0 0 12px; } h2 { font-size:14px; margin:0 0 8px; }
  main { max-width: 900px; margin: 0 auto; }
  button, input, select { font:inherit; color:inherit; }
  button { background:var(--card); border:1px solid var(--ctl); border-radius:6px; padding:4px 10px; cursor:pointer; }
  button.primary { background:var(--accent); color:var(--accent-fg); border-color:var(--accent); }
  button:focus-visible, input:focus-visible, select:focus-visible, summary:focus-visible { outline:2px solid var(--accent); outline-offset:2px; }
  input, select { background:var(--bg); border:1px solid var(--ctl); border-radius:6px; padding:4px 8px; }
  label { display:flex; flex-direction:column; gap:2px; font-size:12px; color:var(--muted); }
  form[hidden] { display:none; }
  form { display:flex; flex-wrap:wrap; gap:8px; align-items:flex-end; }
  details { background:var(--card); border:1px solid var(--line); border-radius:8px; padding:8px 12px; margin-bottom:8px; }
  summary { cursor:pointer; font-weight:600; }
  details form { margin-top:8px; }
  #error { background:var(--errbg); color:var(--bad); border:1px solid var(--bad); border-radius:6px; padding:8px 12px; margin-bottom:12px; }
  #error[hidden] { display:none; }
  ul { list-style:none; margin:12px 0 0; padding:0; display:grid; gap:8px; }
  li.spool { background:var(--card); border:1px solid var(--line); border-radius:8px; padding:10px 12px; }
  .head { display:flex; gap:10px; align-items:center; }
  .swatch { width:28px; height:28px; border-radius:50%; border:1px solid var(--line); flex:none; }
  .title { font-weight:600; } .sub { color:var(--muted); font-size:12px; }
  .grow { flex:1; min-width:0; }
  .amount { text-align:right; white-space:nowrap; font-variant-numeric:tabular-nums; }
  progress { width:100%; height:8px; margin:8px 0; appearance:none; border:0; border-radius:4px; background:var(--bar); }
  progress::-webkit-progress-bar { background:var(--bar); border-radius:4px; }
  progress::-webkit-progress-value { background:var(--ok); border-radius:4px; }
  progress::-moz-progress-bar { background:var(--ok); border-radius:4px; }
  progress.low::-webkit-progress-value { background:var(--warn); } progress.low::-moz-progress-bar { background:var(--warn); }
  progress.empty::-webkit-progress-value { background:var(--bad); } progress.empty::-moz-progress-bar { background:var(--bad); }
  .actions { display:flex; flex-wrap:wrap; gap:6px; }
  .panel { margin-top:8px; padding-top:8px; border-top:1px solid var(--line); }
  table { width:100%; border-collapse:collapse; } td, th { text-align:left; padding:2px 6px 2px 0; font-size:12px; }
  td.num { text-align:right; font-variant-numeric:tabular-nums; }
  .empty-note { color:var(--muted); }
</style></head>
<body><main>
<h1 tabindex="-1">Spools</h1>
<div id="error" role="alert" hidden></div>
<div id="forms"></div>
<ul id="spools" aria-label="Spools"></ul>
<p id="none" class="empty-note" hidden>No spools yet. Add a filament, then a spool.</p>
</main>
<script>
(function () {
  "use strict";
  var S = { filaments: [], printers: [], spools: [], open: null, usage: [], focus: null };
  var pending = {}, nextId = 1;

  function call(op, args, done, fail) {
    var id = nextId++;
    pending[id] = { ok: done || function () {}, fail: fail };
    orca.postMessage({ id: id, op: op, args: args || {} });
  }
  orca.onMessage(function (m) {
    var p = m && pending[m.id];
    if (!p) return;
    delete pending[m.id];
    if (m.ok) { showError(""); p.ok(m.result); } else { showError(m.error); if (p.fail) p.fail(); }
  });

  function showError(text) {
    var e = document.getElementById("error");
    e.textContent = text; e.hidden = !text;
  }

  // el("button", {type: "button", onclick: fn}, "label", childNode, ...) -- strings become text nodes.
  function el(tag, props) {
    var node = document.createElement(tag);
    Object.keys(props || {}).forEach(function (k) {
      if (k.slice(0, 2) === "on") node.addEventListener(k.slice(2), props[k]);
      else if (k in node) node[k] = props[k]; else node.setAttribute(k, props[k]);
    });
    for (var i = 2; i < arguments.length; i++) {
      var c = arguments[i];
      if (c != null) node.appendChild(typeof c === "object" ? c : document.createTextNode(String(c)));
    }
    return node;
  }
  // Like call() but the button stays disabled until the reply arrives, so a double click cannot repeat the request.
  function send(btn, op, args, done) {
    if (btn.disabled) return;
    btn.disabled = true;
    call(op, args, function (r) { btn.disabled = false; done(r); }, function () { btn.disabled = false; });
  }
  function field(label, input) { return el("label", {}, label, input); }
  function num(v) { v = v.trim(); if (v === "") return null; var n = Number(v); return isNaN(n) ? v : n; }
  function str(v) { v = v.trim(); return v === "" ? null : v; }
  function g(n) { return (Math.round(n * 10) / 10).toLocaleString() + " g"; }

  function refresh() {
    call("list_filaments", {}, function (f) { S.filaments = f;
      call("list_printers", {}, function (p) { S.printers = p;
        call("list_spools", {}, function (s) { S.spools = s;
          if (S.open && S.open.kind === "history")
            call("list_usage", { spool_id: S.open.id }, function (u) { S.usage = u; render(); });
          else render();
        }); }); });
  }
  function key(id, kind) { return "s" + id + "-" + kind; }
  // Run an op from a panel button, close the panel, return focus to the control that opened it.
  function act(btn, op, args) {
    var k = key(S.open.id, S.open.kind);
    send(btn, op, args, function () { S.open = null; S.focus = { key: k }; refresh(); });
  }
  function toggle(id, kind) {
    var opening = !(S.open && S.open.id === id && S.open.kind === kind);
    S.open = opening ? { id: id, kind: kind } : null;
    S.focus = { key: key(id, kind), panel: opening };
    refresh();
  }

  function option(value, text) { return el("option", { value: value }, text); }
  function fillPrinters(sel) {
    var v = sel.value;
    sel.textContent = "";
    sel.appendChild(option("", "Not loaded"));
    S.printers.forEach(function (p) { sel.appendChild(option(p.id, p.name)); });
    sel.value = v;
  }
  function printerSelect() { var sel = el("select"); fillPrinters(sel); return sel; }

  // The three "add" forms are built once and only their selects are refilled, so typed text and focus survive re-renders.
  var F = {};
  function buildForms() {
    var box = document.getElementById("forms");
    var fMat = el("input", { required: true, placeholder: "PLA" }), fVen = el("input"), fName = el("input"),
        fCol = el("input", { type: "color", value: "#888888" }), fUseCol = el("input", { type: "checkbox" }),
        fTare = el("input", { type: "number", min: "0", step: "any", placeholder: "e.g. 200" });
    fCol.addEventListener("input", function () { fUseCol.checked = true; }); // picking a colour is an explicit act
    var addFil = el("button", { type: "submit", className: "primary" }, "Add filament");
    box.appendChild(el("details", {}, el("summary", {}, "Add filament"),
      el("form", { onsubmit: function (e) {
        e.preventDefault();
        var form = e.target;
        send(addFil, "add_filament", { material: str(fMat.value), vendor: str(fVen.value), name: str(fName.value),
          color_hex: fUseCol.checked ? fCol.value : null, spool_tare_g: num(fTare.value) },
          function () { form.reset(); refresh(); });
      } },
        field("Material", fMat), field("Vendor", fVen), field("Name", fName), field("Colour", fCol),
        field("Use this colour (otherwise none)", fUseCol), field("Empty spool weight (g)", fTare), addFil)));

    var sFil = el("select", { required: true }), sG = el("input", { type: "number", min: "0", step: "any", required: true, value: "1000" }),
        sPr = printerSelect(), sSlot = el("input", { placeholder: "e.g. ams0-1 or ext" });
    var addSpool = el("button", { type: "submit", className: "primary" }, "Add spool");
    var spoolForm = el("form", { onsubmit: function (e) {
        e.preventDefault();
        var form = e.target;
        send(addSpool, "add_spool", { filament_id: Number(sFil.value), initial_g: num(sG.value),
          printer_id: sPr.value === "" ? null : Number(sPr.value), slot: str(sSlot.value) },
          function () { form.reset(); refresh(); });
      } },
        field("Filament", sFil), field("Filament on spool (g)", sG), field("Printer", sPr), field("Slot", sSlot), addSpool);
    var spoolNote = el("p", { className: "empty-note" }, "Add a filament first.");
    box.appendChild(el("details", {}, el("summary", {}, "Add spool"), spoolNote, spoolForm));

    var pName = el("input", { required: true }), pDrv = el("select", {}, option("bambu", "Bambu"), option("prusalink", "PrusaLink"));
    var addPrinter = el("button", { type: "submit", className: "primary" }, "Add printer");
    box.appendChild(el("details", {}, el("summary", {}, "Add printer"),
      el("form", { onsubmit: function (e) {
        e.preventDefault();
        var form = e.target;
        send(addPrinter, "add_printer", { name: str(pName.value), driver: pDrv.value }, function () { form.reset(); refresh(); });
      } }, field("Name", pName), field("Driver", pDrv), addPrinter)));
    F = { sFil: sFil, sPr: sPr, spoolForm: spoolForm, spoolNote: spoolNote };
  }

  function updateForms() {
    var v = F.sFil.value;
    F.sFil.textContent = "";
    S.filaments.forEach(function (f) {
      F.sFil.appendChild(option(f.id, [f.vendor, f.material, f.name].filter(Boolean).join(" ")));
    });
    F.sFil.value = v;
    if (F.sFil.selectedIndex < 0 && S.filaments.length) F.sFil.selectedIndex = 0;
    fillPrinters(F.sPr);
    F.spoolForm.hidden = S.filaments.length === 0;
    F.spoolNote.hidden = S.filaments.length > 0;
  }

  function panel(s) {
    var o = S.open;
    if (!o || o.id !== s.id) return null;
    var input, form;
    function numInput() { return el("input", { type: "number", min: "0", step: "any", required: true }); }
    if (o.kind === "weigh") {
      input = numInput();
      var wb = el("button", { type: "submit", className: "primary" }, "Save weight");
      form = el("form", { onsubmit: function (e) { e.preventDefault(); act(wb, "weigh_spool", { spool_id: s.id, gross_g: num(input.value) }); } },
        field("Gross weight, spool included (g)", input), wb);
      if (s.tare_g == null) form.appendChild(el("span", { className: "sub" }, "This filament has no empty spool weight, so weighing will be refused."));
    } else if (o.kind === "use") {
      input = numInput();
      var note = el("input");
      var ub = el("button", { type: "submit", className: "primary" }, "Log usage");
      form = el("form", { onsubmit: function (e) { e.preventDefault(); act(ub, "log_manual_usage", { spool_id: s.id, grams: num(input.value), note: str(note.value) }); } },
        field("Used (g)", input), field("Note", note), ub);
    } else if (o.kind === "move") {
      var pr = printerSelect(), slot = el("input", { placeholder: "e.g. ams0-1 or ext" });
      var mb = el("button", { type: "submit", className: "primary" }, "Assign");
      form = el("form", { onsubmit: function (e) {
        e.preventDefault();
        act(mb, "assign_spool", { spool_id: s.id, printer_id: pr.value === "" ? null : Number(pr.value), slot: pr.value === "" ? null : str(slot.value) });
      } }, field("Printer", pr), field("Slot", slot), mb);
    } else if (o.kind === "archive") {
      form = el("div", {}, "Archive this spool? It leaves the list and frees its slot; its usage history is kept. ",
        el("button", { type: "button", className: "primary", onclick: function (e) { act(e.currentTarget, "archive_spool", { spool_id: s.id }); } }, "Archive"));
    } else {
      var tbody = el("tbody");
      S.usage.forEach(function (u) {
        tbody.appendChild(el("tr", {}, el("td", {}, (u.created_at || "").replace("T", " ").slice(0, 16)),
          el("td", {}, u.source), el("td", { className: "num" }, g(u.grams)), el("td", {}, u.note || ""),
          el("td", {}, el("button", { type: "button", "aria-label": "Undo usage of " + g(u.grams),
            onclick: function (e) { act2(e.currentTarget, "undo_usage", { usage_id: u.id }); } }, "Undo"))));
      });
      form = S.usage.length ? el("table", {}, el("thead", {}, el("tr", {}, el("th", {}, "When"), el("th", {}, "Source"),
        el("th", { className: "num" }, "Grams"), el("th", {}, "Note"), el("th"))), tbody)
        : el("p", { className: "empty-note" }, "No usage recorded.");
    }
    return el("div", { className: "panel" }, form);
  }
  // Like act() but keeps the history panel open.
  function act2(btn, op, args) {
    send(btn, op, args, function () { S.focus = { key: key(S.open.id, "history") }; refresh(); });
  }

  function render() {
    updateForms();
    var list = document.getElementById("spools");
    list.textContent = "";
    document.getElementById("none").hidden = S.spools.length > 0;
    S.spools.forEach(function (s) {
      var title = [s.vendor, s.material, s.name].filter(Boolean).join(" ");
      var swatch = el("span", { className: "swatch", "aria-hidden": "true" });
      if (s.color_hex) swatch.style.background = s.color_hex;
      var bar = el("progress", { max: 100, value: Math.max(0, Math.min(100, s.percent)),
        className: s.remaining_g <= 0 ? "empty" : s.percent < 15 ? "low" : "" });
      bar.setAttribute("aria-label", "Remaining " + s.percent + " percent");
      function btn(kind, label) {
        return el("button", { type: "button", "aria-expanded": String(!!S.open && S.open.id === s.id && S.open.kind === kind),
          "data-key": key(s.id, kind), onclick: function () { toggle(s.id, kind); } }, label);
      }
      list.appendChild(el("li", { className: "spool" },
        el("div", { className: "head" }, swatch,
          el("div", { className: "grow" }, el("div", { className: "title" }, title), el("div", { className: "sub" }, s.location)),
          el("div", { className: "amount" }, el("div", { className: "title" }, g(s.remaining_g)),
            el("div", { className: "sub" }, s.percent + "% of " + g(s.initial_g)))),
        bar,
        el("div", { className: "actions" }, btn("weigh", "Weigh"), btn("use", "Manual usage"), btn("move", "Move"),
          btn("history", "History"), btn("archive", "Archive")),
        panel(s)));
    });
    // Every action rebuilds the list: put keyboard focus back (first field of a freshly opened panel, else the trigger).
    var f = S.focus; S.focus = null;
    if (f) {
      var t = (f.panel && list.querySelector(".panel input, .panel select, .panel button")) ||
              list.querySelector('[data-key="' + f.key + '"]') || document.querySelector("h1");
      t.focus();
    }
  }

  buildForms();
  refresh();
})();
</script></body></html>
"""
