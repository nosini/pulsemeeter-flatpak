# Runs inside the installed app's sandbox (see scripts/test-installed.sh).
# There is no display, sound server or session bus in CI, so keep these checks
# headless: import modules, load the translations, look for files.
set -eu

test -x /app/bin/pulsemeeter

# -P keeps a checkout in the working directory from shadowing the installed
# package.
python3 -P - <<'PYTHON'
import gettext
from pathlib import Path

import gi
import pulsectl
import pulsectl_asyncio
from pydantic import TypeAdapter

gi.require_version("Gtk", "4.0")
from gi.repository import Gtk

import pulsemeeter
from pulsemeeter.settings import LOCALE_DIR

assert pulsemeeter.__file__.startswith("/app/"), pulsemeeter.__file__
assert Gtk.get_major_version() == 4
# pydantic-core is the one compiled dependency.
assert TypeAdapter(int).validate_python("42") == 42

# Patch 0002: translations are found under /app. test-installed.sh installs
# the German ones from the Locale extension.
assert LOCALE_DIR == "/app/share/locale", LOCALE_DIR
with Path(LOCALE_DIR, "de_DE/LC_MESSAGES/pulsemeeter.mo").open("rb") as catalog:
    gettext.GNUTranslations(catalog)

# Babel only compiles the translations during the build.
for path in Path("/app").rglob("*"):
    assert "babel" not in path.name.lower(), path
PYTHON

# The PipeWire client configuration that gives the pw-* tools the Manager role.
test "$PIPEWIRE_CONFIG_DIR" = /app/share/pulsemeeter/pipewire
test -s /app/share/pulsemeeter/pipewire/client.conf
grep -q 'media.category = Manager' /app/share/pulsemeeter/pipewire/client.conf.d/50-manager.conf
for tool in pw-cli pw-link pw-loopback pw-dump pw-metadata; do
  command -v "$tool" >/dev/null
done

test -s "/app/share/applications/$FLATPAK_ID.desktop"
test -s "/app/share/icons/hicolor/128x128/apps/$FLATPAK_ID.png"
# The welcome window looks up the upstream icon name.
test -s /app/share/icons/hicolor/128x128/apps/Pulsemeeter.png

# flatpak-builder records the license files it finds at the root of each
# module's source; the app's must be there.
test -n "$(ls "/app/share/licenses/$FLATPAK_ID/pulsemeeter")"

echo 'Installed app checks passed.'
