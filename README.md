# Pulsemeeter Flatpak

An unofficial Flatpak package of [Pulsemeeter](https://github.com/theRealCarneiro/pulsemeeter),
a Voicemeeter-style mixer for PipeWire. Pulsemeeter creates virtual inputs and
outputs and lets you route any input to any output, with volume, mute and
channel mapping for each device.

This repository only contains the packaging. The app itself, its
documentation and its issue tracker live upstream.

## Requirements

Pulsemeeter needs PipeWire with pipewire-pulse and WirePlumber, which is the
default sound setup on current Linux desktops. It does not work with the
original PulseAudio server.

## Installing

Install [Flatpak](https://flatpak.org/setup/) if you don't already have it,
then:

```sh
flatpak remote-add --user --if-not-exists flathub https://dl.flathub.org/repo/flathub.flatpakrepo
flatpak install --user https://nosini.github.io/pulsemeeter-flatpak/pulsemeeter.flatpakref
```

This adds a remote named `pulsemeeter`. Updates come through it like any
other Flatpak, from GNOME Software or with:

```sh
flatpak update --user eu.nosini.Pulsemeeter
```

The package is built for x86_64.

### Switching from a self-built install

If you installed Pulsemeeter with `flatpak-builder --install`, move it to the
published remote so it receives updates:

```sh
flatpak remote-add --user --if-not-exists pulsemeeter https://nosini.github.io/pulsemeeter-flatpak/pulsemeeter.flatpakrepo
flatpak install --user --reinstall pulsemeeter eu.nosini.Pulsemeeter
flatpak remote-delete --user eu.nosini.Pulsemeeter-origin
```

Your settings are kept, since they are stored outside the app.

## Using it

Start Pulsemeeter from your application menu, or with:

```sh
flatpak run eu.nosini.Pulsemeeter
```

The [upstream guide](https://github.com/theRealCarneiro/pulsemeeter/wiki/How-to-use)
explains how to add devices and routes. The command-line interface works the
same way as a regular install, for example:

```sh
flatpak run eu.nosini.Pulsemeeter volume vi 1 80
flatpak run eu.nosini.Pulsemeeter --help
```

### Restoring devices after login

Virtual devices and routes last until PipeWire restarts, which usually
means until you log out. To recreate them at login without opening the
window, add a login item that runs:

```sh
flatpak run eu.nosini.Pulsemeeter init
```

On GNOME you can do this with a file
`~/.config/autostart/pulsemeeter-init.desktop`:

```ini
[Desktop Entry]
Type=Application
Name=Pulsemeeter devices
Exec=flatpak run eu.nosini.Pulsemeeter init
NoDisplay=true
```

### Differences from a regular install

- **Routes with per-route volume only run while Pulsemeeter is open.** Each
  of these routes is a `pw-loopback` helper process. A regular install
  leaves the helpers running after you close the window, but a Flatpak
  app's processes end with it, and `init` from a login item can't keep them
  either. Plain routes, without per-route volume, are PipeWire links and
  keep working after you close Pulsemeeter.
- The settings file is the same one a regular install uses,
  `~/.config/pulsemeeter/config.json`. You can switch between the two
  installs without losing your setup.
- Apps that are themselves installed as Flatpaks may show a generic icon,
  because their icons are only visible to Flatpak apps with access to the
  other apps' installation folders.
- The log file is in
  `~/.var/app/eu.nosini.Pulsemeeter/.local/state/pulsemeeter/`.

## Permissions

Pulsemeeter manages the sound setup of the whole session, so the sandbox
gives it full control over audio:

- the PulseAudio socket and the native PipeWire socket. Pulsemeeter uses
  both, for volumes and default devices and for creating devices and links;
- access to all devices (`--device=all`). pipewire-pulse only lets a
  Flatpak app change other apps' streams and devices when the app has this
  permission. Pulsemeeter does not open device files itself;
- read-only access to the system's installed programs (`/usr`), so it can
  show the icons of apps playing audio. Icons installed under `/usr/local`,
  which is where browser packages such as Brave's put theirs, aren't visible
  to Flatpak apps otherwise;
- its own settings folder, `~/.config/pulsemeeter`.

It has no network access and no access to your other files.

## License

The packaging files in this repository are licensed under the GNU Affero
General Public License, version 3 (see [LICENSE](LICENSE)). Pulsemeeter
itself is under the MIT license; see its
[repository](https://github.com/theRealCarneiro/pulsemeeter).

Building it yourself, publishing, and how the package works are described
in [docs/development.md](docs/development.md).
