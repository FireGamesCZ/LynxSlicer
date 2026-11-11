# Spools plug-in (M3, first version)

Shows and edits the spool inventory in a tab. All logic is in `lynx/core/lynx_core`
(`ui_api.py` handles the page's requests, `spools_page.py` is the page); `lynx_spools.py`
only wires them to OrcaSlicer. It requests no permissions.

## Install

In the LynxSlicer fork the application installs the plug-in itself into `orca_plugins/lynx_spools`
(bundled, managed by a manifest it writes there). A folder without that manifest, such as one made by
hand as below, is left alone. Print tracking (the activity list and automatic deduction) only works in
the fork's build: stock OrcaSlicer 2.5 lacks `device_status` and `slice_statistics`, so there the plug-in
is an inventory only.

### Manual side-load (stock OrcaSlicer 2.5, or to test changes)

The Plugins dialog copies only the single `.py` file, so `lynx_core` would be missing. Instead drop a
folder into the plug-in directory by hand (it must hold exactly one `.py`):

```sh
D=~/.var/app/com.orcaslicer.OrcaSlicer/config/OrcaSlicer/orca_plugins/lynx_spools   # flatpak
# non-flatpak Linux: ~/.config/OrcaSlicer/orca_plugins/lynx_spools
mkdir -p "$D"
cp lynx/plugin/lynx_spools.py "$D"/
cp -r lynx/core/lynx_core "$D"/        # run again after changing lynx_core
```

Restart OrcaSlicer, open the **Plugins** dialog (File menu, or the top-bar menu) and enable the
"Spools" plug-in and its "Spools" capability. It then appears as a tab next to the built-in
ones (extra plug-in tabs go into an overflow button when the Preferences limit is exceeded).
The database is `spools.sqlite3` in the plug-in's storage folder, `orca_plugins/plugin_data/lynx_spools/`.

## Try the page without OrcaSlicer

```sh
cd lynx/core
uv run python ../plugin/dev_server.py            # then open the printed http://127.0.0.1:8765/ URL
uv run python ../plugin/dev_server.py --db /tmp/spools.sqlite3   # keep the data
Add `?theme=dark` or `?theme=light` to the URL to emulate the colours OrcaSlicer injects (without it the page follows the OS theme). The server only answers requests whose Host is `127.0.0.1:<port>` or `localhost:<port>` and whose POSTs are `application/json`.
```

Binds to 127.0.0.1 only; without `--db` it uses a temporary database.
