#!/usr/bin/env python3
"""Headless checks run inside the installed app's Platform runtime."""

import gettext
import os
from pathlib import Path

import gi
import pulsectl
import pulsectl_asyncio
from pydantic import TypeAdapter

gi.require_version("Gtk", "4.0")
from gi.repository import Gtk
from pulsemeeter.settings import LOCALE_DIR

assert Gtk.get_major_version() == 4
assert TypeAdapter(int).validate_python("42") == 42
assert LOCALE_DIR == "/app/share/locale", LOCALE_DIR
with Path(LOCALE_DIR, "de_DE/LC_MESSAGES/pulsemeeter.mo").open("rb") as catalog:
    gettext.GNUTranslations(catalog)

launcher = Path("/app/bin/pulsemeeter")
assert launcher.is_file() and os.access(launcher, os.X_OK), launcher

for relative in (
    "share/pulsemeeter/pipewire/client.conf",
    "share/pulsemeeter/pipewire/client.conf.d/50-manager.conf",
    "share/icons/hicolor/128x128/apps/eu.nosini.Pulsemeeter.png",
    "share/applications/eu.nosini.Pulsemeeter.desktop",
):
    path = Path("/app", relative)
    assert path.is_file() and path.stat().st_size > 0, path

# Babel is a build dependency and must have been cleaned from the app.
for path in Path("/app").rglob("*"):
    assert "babel" not in path.name.lower(), path

print("Installed app: imports, translations and packaged files passed.")
