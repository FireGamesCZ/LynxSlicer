# /// script
# requires-python = ">=3.12"
#
# [tool.orcaslicer.plugin]
# name = "Spools"
# description = "Spool inventory: filaments, spools, remaining grams, manual usage and weighing."
# author = "LynxSlicer"
# version = "0.1.0"
# ///
"""Spools tab. Needs the lynx_core package in the same folder as this file (see README.md).

Everything here runs on the UI thread: the page's messages arrive there and each request is a handful
of tiny SQLite statements, so no worker thread (and no `threading` permission) is used. The one
sqlite3 connection is opened lazily on that same thread. No permissions are requested.
"""
import json
import os

import orca

from lynx_core import inventory, spools_page, ui_api


class SpoolsPage(orca.pages.PagesPluginCapabilityBase):
    conn = None

    def get_name(self):
        return "Spools"

    def get_ui(self):
        return spools_page.PAGE

    def on_message(self, message):
        try:
            request = json.loads(message)
            if self.conn is None:  # storage() only works inside a plug-in callback, so not at import time
                self.conn = inventory.connect(os.path.join(orca.host.plugin.storage(), "spools.sqlite3"))
            reply = ui_api.handle(self.conn, request)
        except Exception as error:  # the page must always get an answer
            reply = {"id": request.get("id") if isinstance(request, dict) else None, "ok": False,
                     "error": f"Spools could not handle the request: {error}"}
        self.post_message(reply)


@orca.plugin
class SpoolsPlugin(orca.base):
    def register_capabilities(self):
        orca.register_capability(SpoolsPage)
