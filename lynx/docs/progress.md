# Progress notes

Working log for the Lynx fork: what is done, how it was checked, what is open. Newest
state first; update it whenever a piece of work lands. The plan and the reasons behind it
are in [../PLAN.md](../PLAN.md).

Last updated: 2026-11-11.

## Where things stand

| Area | State | Checked how |
|---|---|---|
| Fork builds on Fedora 45 (GCC 16, CMake 4.3) | done | built; CLI slices a cube identically to stock 2.5 |
| GUI of our build, Bambu network plug-in, P1P connects | works | by hand (user), 2026-11-11, before the layout change |
| `lynx/core` inventory, preset export | done, reviewed | unit tests; exported preset sliced with the real CLI |
| Bambu LAN listener (`bambu.py`) | done, reviewed | unit tests on synthetic fixtures only |
| Spools plug-in: inventory tab | works in the app | by hand (user): tab shows, a filament was added |
| Per-layer statistics split by filament (C++) | done | Catch2 tests, CLI check |
| Slice plan + "enough filament?" check | done, reviewed | unit tests; not yet seen in the app |
| Print tracking through the host (deduct on finish, estimate on fail) | done, reviewed | unit tests; **no real print yet** |
| Host API `device_status`, `slice_statistics`; plate index in events | done, reviewed | builds; not exercised in the app |
| Plug-in shipped with the app, installed at start-up | done, reviewed | Catch2 tests; first install seen by hand |
| Filaments as a top-level tab (layout prototype) | built | **manual test script not run yet** |

## Commits on `lynx` (on top of upstream `3538f239c2`)

| Commit | What |
|---|---|
| `2a2ed8f0e8` | plan, settings map, `lynx/core`, first Spools plug-in |
| `47818599da` | plug-in review fixes (host passes a dict; dev server hardening; theme, focus) |
| `cce272292c` | per-layer statistics split by filament |
| `49143182b1` | `plan.py`, remaining-filament check in the page |
| `7b538ad657` | prototype: Filaments top-level tab |
| `9fb4da692d` | host functions, bundled plug-in, print tracker |

## How to build, run, test

- Build: `./build_linux.sh -s -j 8` (add `t` for tests). Unlimited parallelism ran out of
  memory once. Never run two builds at the same time; they share `build/`.
- Run: `build/package/orca-slicer` from the repo root. `build/orca-slicer` one level up is
  a different script and does not work.
- First start shows a small "Do you want to continue?" dialog about the TLS certificate
  store before the splash screen; it can hide behind other windows. Tick "Remember my
  choice".
- Our build's data folder is `~/.config/OrcaSlicer` (separate from the Flatpak install).
- Python tests: `cd lynx/core && uv run -q --with paho-mqtt python3 -m unittest discover -s tests`.
- C++ tests: `ctest --test-dir build/tests/<suite>`; ours are in `fff_print`
  (`-L GCodeStatistics`) and `slic3rutils` (`[PluginFsUtils]`).
- Page without the app: `cd lynx/core && uv run python ../plugin/dev_server.py`.
- The CLI writes `result.json` into its working directory; run it from a scratch folder.

## Things learned that are easy to forget

- The plug-in host hands `on_message` a parsed dict, not a JSON string.
- Page handlers run on the UI thread; lifecycle events run on the thread that fired them
  (`PrintJobStarted` on a worker). SQLite and `post_message` only from the UI thread.
- `PrintStateChanged` fires on state changes (and on a new job id), not per layer. The
  layer is read with `device_status` at that moment; when the printer gives none, the
  plug-in asks for manual entry instead of guessing.
- Statistics `layers[i]` is printer layer `i + 1` (`M73 L`). Flush at filament changes has
  no layer in the data; `plan.py` spreads it in proportion to extrusion.
- A user filament preset needs its `.info` sidecar and must inherit from an existing
  system preset. A plug-in cannot create presets through the API.
- The bundled plug-in is synced into `orca_plugins/lynx_spools` using a manifest
  (`.bundled_files`). A folder without that manifest is treated as the user's own and
  never touched, so a hand-made copy there blocks updates.
- Stock OrcaSlicer 2.5 lacks our host functions: there the plug-in is an inventory only.
- GitHub: a fork of a public repository cannot be private. `origin` is the public fork;
  `upstream` has its push URL disabled on purpose. The old private repository is
  `LynxSlicer-old`.
- A code graph of `src/slic3r` is in `graphify-out/` (ignored); `graphify query "..."`.

## Open

To check by hand:
- Filaments tab (main risk: which filament slot edits go to with two or more filaments):
  1. Tabs read Home, Prepare, Preview, Filaments, Device; Filaments shows the page tree
     and settings, without a Global/Objects bar.
  2. Change the nozzle temperature: preset shows as modified and can be saved.
  3. With two or more filaments: edit in the tab, change filament 1's preset in Prepare,
     return. No crash; note which slot later edits go to.
  4. The edit button next to filament 2 opens the tab on that filament; picking another
     preset there shows up in slot 2.
  5. First-layer temperature 40 °C away from the other layers, then click Prepare: the
     temperature check appears; "Back" stays, "Continue" leaves; Ctrl+Tab warns once.
  6. Search "Nozzle temperature" in Prepare opens the Filaments tab on that option.
  7. The printer edit button still opens the printer dialog.
  8. Switching the mode changes the options shown in the tab.
  9. Dark mode: the tab is dark.
  10. A changed nozzle temperature appears in the sliced G-code.
  11. Filament manager → edit a preset → Edit opens the tab with the combo disabled;
      leaving the tab reopens the edit dialog.
- One real print with the plug-in enabled, and one cancelled print: does the job name from
  the printer match the project name, does a cancel arrive with error code `0x0300400C`,
  is the layer present at the end, how long from send to RUNNING.
- Record real traffic with `lynx/core/tools/bambu_record.py` to replace synthetic fixtures.

Not done yet:
- AMS: which filament goes to which tray is unknown to the plug-in; multi-filament prints
  end with a prompt to assign spools by hand.
- Rename the application to LynxSlicer (then re-check that the Bambu network plug-in
  still loads).
- Layout beyond the prototype: Printers tab, Print Settings tab, right panel, removing
  `ParamsDialog`, merged Plater tab (estimate in PLAN.md section 3).
- Calibration wizard, PrusaLink driver, edit/delete for filaments and printers in the page.
- macOS packaging rule for the plug-in is written but untested.

Decisions waiting for the owner:
- Default branch of the fork: `main` (plain OrcaSlicer) or `lynx`.
- Commit author e-mail is visible in the public repository.
- Which of the 39 settings missing in OrcaSlicer to port (settings-map.md).
