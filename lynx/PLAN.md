# LynxSlicer – plan and research

Status as of 2026-11-10. This records decisions and the order of work.

Done so far: `lynx/core` (inventory, preset export, Bambu listener; reviewed, tests pass,
nothing run against a printer yet). In progress: first build of the fork, Spools plug-in.

## 1. Goal

A slicer with the PrusaSlicer 2.9 layout and setting names, built on OrcaSlicer, with a
spool inventory tied to slicing and to what the printer actually printed.

- PrusaSlicer 2.9 layout and setting names.
- Bambu and Prusa printers, several printers at once, AMS and external spool.
- Own spool inventory: slice for a spool, deduct after the print, estimate usage when a
  print fails.
- Calibration: a guided wizard for every printer, automatic where the printer can
  measure (lidar).
- Public project, AGPL-3.0 (required by the OrcaSlicer licence).

## 2. Base: fork of OrcaSlicer

| | Fork OrcaSlicer | Fork PrusaSlicer 2.9 |
|---|---|---|
| Bambu (Device tab, AMS, network plug-in, cloud) | there | LAN only, all to be written |
| Calibration prints, lidar calibration | there | none |
| Prusa printers | profiles MK3S to CORE One, XL, MINI; PrusaLink and PrusaConnect upload | there |
| Python plug-ins | there | none |
| PrusaSlicer layout and names | to be done | there |
| Upstream | active | moving to 3.0, which has a rewritten UI |

PrusaSlicer 3.0 (alpha) was ruled out: its UI is rewritten with a different layout.

## 3. What "PrusaSlicer look and settings" means here

**Layout.** OrcaSlicer still has the PrusaSlicer tab classes (`TabPrint`, `TabFilament`,
`TabPrinter`) and the Simple / Advanced / Expert switch. Today the print settings are
the left sidebar, and filament and printer settings open in a dialog (`ParamsDialog`)
that blocks the rest of the window. A `Tab` draws into a `ParamsPanel`, so PrusaSlicer's
tab code cannot be taken over as it is. Target, to be confirmed on the first prototype:

- top tabs: Plater, Print Settings, Filaments, Printers, Device, Spools
- right panel with preset selectors and the object list
- 3D / Preview switch at the bottom
- Simple / Advanced / Expert mode switch

Same arrangement, not pixel-identical: Orca has its own widgets and icons.

Estimate from reading the code, before any build (one experienced developer):

| Part | Days |
|---|---|
| Prototype: Filaments as a top-level tab | 1–2 |
| Printers tab | 1 |
| Print Settings tab, split from the per-object settings | 5–8 |
| Right panel with presets and object list only | 3–5 |
| Remove `ParamsDialog`, reroute everything that opens it | 2–3 |
| Plater tab merging Prepare and Preview | 3–5 |
| Tree-left / page-right inside the tabs (optional) | 4–8 |
| Mode switch in the top bar | 0.5–1 |
| Testing on Linux, Windows, macOS | 3–5 |

Hard parts: per-object settings live under the process panel's Global / Objects switch
(PrusaSlicer has them in the object list), and the dialog's close handler does real work
(temperature check, which filament slot an edit applies to) that needs a new home.

**Settings.** See [docs/settings-map.md](docs/settings-map.md). Of 563 PrusaSlicer 2.9.7
keys:

| Group | Keys | Work |
|---|---|---|
| Same key in both | 299 | none |
| Renamed in Orca, same purpose | 122 | show the PrusaSlicer label and placement |
| Renamed, behaves differently | 40 | decide per key: adapt the UI or accept Orca's behaviour |
| Missing in Orca (FFF) | 39 | port per key, only the ones chosen |
| SLA only | 34 | out of scope |
| Not user settings | 29 | none |

Orca has 697 more keys that PrusaSlicer does not; each needs a place in the tabs.

Limits:
- The same setting does not give the same G-code. The engines have diverged.
- PrusaSlicer `.ini` profiles will not load 1:1. A converter for the renamed keys is
  possible; Orca ships its own Prusa printer profiles.

## 4. Architecture

```
OrcaSlicer fork (C++/wxWidgets)           lynx-core (Python 3.12, no UI)
├─ PrusaSlicer layout and labels           ├─ inventory: SQLite
├─ usage table written at slice time ───►  ├─ printer drivers: bambu (MQTT), prusalink (REST)
└─ bundled "Spools" plug-in (HTML)  ◄───   ├─ deduction and failure estimate
                                           └─ filament preset export
```

- Keep the C++ changes small so upstream merges stay cheap. All spool logic is Python
  and runs in the fork as a plug-in (Orca 2.5 embeds CPython 3.12; plug-in UI is HTML).
- Usage per layer already exists: with the `export_statistics` preference Orca writes
  `<gcode>.statistics.json` next to the G-code and into the 3MF
  (`GCodeStatistics.cpp`). The per-layer numbers are totals over all filaments and leave
  out flush, so multi-filament plates need a per-extruder split there. `layers[i]` is
  layer `i + 1` of `M73 L`.
- `GCodeExportFinished` gives the plug-in the G-code path; print state comes through
  `PrintStateChanged` and the core's own listener.
- Printing goes through Orca's existing code. Lynx only listens to printers.
- Core dependencies: `sqlite3` from the standard library and `paho-mqtt`.

### Data model
- **filament**: vendor, material, colour, diameter, density, temperature range, bed
  temperature, drying, price, empty spool weight. Calibrated values (flow ratio,
  pressure advance, max volumetric speed, retraction, temperature) are stored **per
  filament + printer + nozzle**, each with a source: `vendor` / `calibrated` / `lidar` /
  `default`.
- **spool**: filament, initial grams, location (printer + AMS slot / external / MMU /
  XL tool head), date opened.
- **printer**: driver type, address. Access codes go to the system keyring.
- **usage log**: spool, job, grams, source (`slicer` / `estimate` / `manual` /
  `weighed`), time. Remaining = initial − sum of the log, so every deduction can be
  undone.

### Slicing for a spool
A spool is assigned to a slot; its filament and the calibration for that printer produce
the preset. After slicing, the need is compared with what is left on the spool and the
user is warned before sending if it is not enough.

### Deduction
| Case | Bambu | Prusa (PrusaLink) |
|---|---|---|
| Finished | full usage from the slicer | same |
| Failed / cancelled | usage up to the last reported layer + half of the current one, ± 1 layer | usage at the last reported `progress`, coarser |
| Lynx was not running | computed from the last state after reconnecting | same, otherwise manual |
| Correction | weighing the spool overwrites the remaining amount | same |

- AMS with an RFID spool: `remain` is only a cross-check, it is a percentage.
- Spool swapped mid-print: ask how much went to which.
- Printer reachable only through PrusaConnect: no status, the end of the print is
  confirmed by hand.

### Calibration
- Wizard: for each missing value it generates Orca's calibration print, the user enters
  the best result, the value is saved. Order: temperature → flow → pressure advance →
  max volumetric speed → retraction.
- Printers that measure themselves (lidar on X1, load cell on A1/H2): run Orca's
  existing calibration and store the result automatically.

## 5. Research notes

**OrcaSlicer** (`main`, af5f680)
- Plug-in events: `SlicingJobComplete`, `SendJobStarted/Finished`,
  `PrintJobStarted/Finished`, `UploadStarted/Finished`, `PrintStateChanged`,
  `DeviceOnline/Offline`, `DeviceDiscovered`, `PresetSelected`, plus project, object and
  plate events. The context carries name, device id, code and message only.
  `PrintJob*` is about sending the job; print state comes through `PrintStateChanged`.
- Printer-side calibration commands exist: `extrusion_cali`,
  `extrusion_cali_get_result`, `flowrate_cali`, `flowrate_get_result` (`DevCalib.cpp`,
  `DeviceManager.cpp`, `CalibrationWizard*.cpp`).
- The plug-in API is new and may change. A plug-in cannot create presets; it writes the
  preset files and reloads the local bundle. A user preset needs its `.info` sidecar and
  must inherit from an existing system preset. There is no mechanism for plug-ins shipped
  with the app; the fork has to copy the plug-in into the data directory at start.
- A page talks to its Python code by JSON messages; page handlers run on the UI thread.
  Sockets, HTTP and threads need permissions requested at load. The embedded Python has
  `sqlite3` and `ssl`; `paho-mqtt` installs from the plug-in's dependency list.
- No `bgcode` support in `libslic3r`.
- Fedora build script: `scripts/linux.d/fedora`, `build_linux.sh`.
- CLI `--export-statistics` writes filament usage per layer and per object.

**Bambu**
- LAN: MQTT over TLS on 8883, user `bblp`, password = LAN access code, topic
  `device/<serial>/report`. Reports carry `gcode_state`, `mc_percent`, `layer_num`,
  `total_layer_num`, and for AMS `remain` (percent, `-1` = unknown) and
  `tray_info_idx`. Field names come from community sources; Bambu does not document
  them.
- Orca 2.5 uses Bambu's official network plug-in, series 02.08. For the newer 02.09
  series there is a check that only lets Bambu-signed apps load it.
- `open-bambu-networking-plugin` embeds a client secret taken from Bambu Studio. Not
  for a public project.

**Prusa**
- PrusaLink REST: `/api/v1/status` and `/api/v1/job` with `progress`, `time_printing`,
  `time_remaining`, header `X-Api-Key`. No layer number. Fields known from client
  libraries only, not from the specification.

**Development machine**: P1P without AMS, Fedora, 16 cores, 31 GB RAM. No AMS, lidar or
Prusa printer to test on.

## 6. Milestones

| | Content | Done when |
|---|---|---|
| **M0** | Build the fork on Fedora as LynxSlicer. Check: Bambu network plug-in loads in the renamed build and the P1P connects; a second MQTT connection next to the app; effort to move one settings panel into a top tab | the app runs, three yes/no answers, an estimate for the layout work |
| **M1** | Inventory: SQLite, model, preset export | tests pass; the preset loads and slices |
| **M2** | Per-extruder split of the per-layer statistics, Bambu driver, deduction and estimate | a cancelled print on the P1P deducts within ± 1 layer of the scale |
| **M3** | Spools plug-in: inventory, slot assignment, remaining check, several printers | the whole flow works without a command line |
| **M4** | PrusaSlicer layout, labels and placement for the renamed keys | approved on a build |
| **M5** | Calibration wizard and storing printer-measured results | a new filament goes from entry to saved values |
| **M6** | Chosen missing settings, PrusaLink driver, AMS, release (CI, packages, README) | tested on recorded reports and by the community |

M4 does not depend on M1–M3 and can run in parallel.

## 7. Risks

1. **Bambu network plug-in in a renamed build.** If it does not load, Bambu is left with
   LAN + Developer Mode. Checked first, in M0, because it can change the plan.
2. **No hardware.** AMS, lidar and Prusa printers can only be tested on recorded reports
   and by users after release; marked experimental until then.
3. **Fork maintenance.** Upstream lands dozens of commits a week. The layout change
   touches the most-edited GUI files and will conflict the most.
4. **Plug-in API is alpha.** The fork controls it, but upstream changes must be taken
   over.
5. **Bambu may restrict MQTT in firmware.** Fallback is confirming the end of a print
   by hand.
6. **Bambu listener is untested on hardware.** Fixtures are synthetic, built from Orca's
   parser. Telling a cancel from a failure relies on an error code from community
   sources. Record real traffic with `lynx/core/tools/bambu_record.py` first.
7. **Toolchain.** Fedora 45 ships GCC 16 and CMake 4.3; whether Orca builds with them is
   not known yet.

## 8. Open decisions

- Which of the 39 missing settings to port (see the priority column in the settings map).
- For the 40 keys that behave differently: PrusaSlicer behaviour or Orca behaviour.

## Sources

- https://github.com/OrcaSlicer/OrcaSlicer
- https://github.com/prusa3d/PrusaSlicer (branches `stable` and `master`)
- https://www.orcaslicer.com/wiki/releases/release_2_5_0_alpha.html
- https://www.orcaslicer.com/wiki/developer_reference/plugin_development/plugin_development.html
- https://www.3dprintingjournal.com/p/prusa-research-presents-prusaslicer
- https://wiki.bambulab.com/en/general/printer-network-ports
- https://wiki.bambulab.com/en/software/bambu-studio/calibration_pa
- https://blog.bambulab.com/updates-and-third-party-integration-with-bambu-connect
- https://synman.github.io/bambu-printer-manager/mqtt-protocol-reference
- https://github.com/OrcaSlicer/OrcaSlicer/pull/14156
- https://github.com/persano/open-bambu-networking-plugin
- https://hexdocs.pm/prusa_link/PrusaLink.Api.html
- https://github.com/maziggy/bambuddy
