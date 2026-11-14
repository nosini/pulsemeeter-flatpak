# Development

## Layout

- `eu.nosini.Pulsemeeter.yml`: the Flatpak manifest.
- `eu.nosini.Pulsemeeter.metainfo.xml` and `.desktop`: software-center
  metadata and launcher.
- `icons/`: the upstream icons padded to a square and named after the app
  ID. Upstream has none larger than 192×192.
- `python3-requirements.json`: pinned Python dependencies, generated from
  `requirements.txt` by `scripts/generate-python-deps.sh`.
- `patches/`: changes to the upstream source, applied in order (see below).
- `pipewire/50-manager.conf`: PipeWire client configuration drop-in (see
  below).
- `lint-exceptions.json`: linter errors that don't apply to a self-hosted
  repository, each with its reason.
- `tests/check-installed.sh`: checks that run inside the installed app:
  imports, translations, the PipeWire configuration and packaged files.
- `scripts/test-installed.sh`: installs a local build with its German
  translations and runs those checks.
- `scripts/prepare-repository.sh`: signs tested builds for publishing.
- `scripts/update-upstream.sh`: proposes updates while keeping fixes on an
  open update branch.
- `scripts/filter-requirements.py`: evaluates dependency markers for the
  runtime's Python and target architectures.
- `scripts/tests/`: regression tests for the packaging scripts.
- `scripts/builder-tools.sh`: fetches the pinned
  [flatpak-builder-tools](https://github.com/flatpak/flatpak-builder-tools).

An upstream checkout in `upstream/` is ignored by Git. It is handy for
reading the source and for making patches.

## Building

The simplest way to build is with `org.flatpak.Builder` from Flathub. It
contains flatpak-builder and the linter in the versions Flathub uses:

```sh
flatpak install --user flathub org.flatpak.Builder
flatpak run org.flatpak.Builder --user --install --install-deps-from=flathub \
  --default-branch=stable --force-clean --repo=repo build-dir eu.nosini.Pulsemeeter.yml
```

The build downloads Pulsemeeter and its Python dependencies, so it needs a
network connection. Building from a checkout installs the app from a local
remote named `eu.nosini.Pulsemeeter-origin`. Once the build directories are
gone, `flatpak update` warns that it can't reach it. Switch to the published
remote as the README describes, or disable it with
`flatpak remote-modify --user --disable eu.nosini.Pulsemeeter-origin`.

To get a single-file bundle instead of installing:

```sh
flatpak build-bundle --runtime-repo=https://dl.flathub.org/repo/flathub.flatpakrepo \
  repo pulsemeeter.flatpak eu.nosini.Pulsemeeter stable
```

## Checking

CI runs the same linter checks as Flathub. Run them locally with:

```sh
alias lint='flatpak run --command=flatpak-builder-lint org.flatpak.Builder'
lint --exceptions --user-exceptions lint-exceptions.json manifest eu.nosini.Pulsemeeter.yml
lint appstream eu.nosini.Pulsemeeter.metainfo.xml
lint --exceptions --user-exceptions lint-exceptions.json repo repo
```

Only add an exception when the rule doesn't apply to a package published
outside Flathub, and say why in `lint-exceptions.json`.

To run the checks inside the installed app, build without `--install` (but
with `--repo=repo`), then run:

```sh
bash scripts/test-installed.sh
```

The script adds a `local-test` remote for `repo/`, installs the app and the
German part of its Locale extension from it and runs
`tests/check-installed.sh` with `flatpak run`, so the checks see the
Platform runtime the app runs with, not the SDK. No display or sound server
is needed. It refuses to replace an existing installation. Afterwards,
remove the test installation with
`flatpak --user uninstall eu.nosini.Pulsemeeter eu.nosini.Pulsemeeter.Locale`
and the remote with `flatpak --user remote-delete local-test`.

## Debugging

A shell in the sandbox of the last build, without installing it:

```sh
flatpak run org.flatpak.Builder --run build-dir eu.nosini.Pulsemeeter.yml sh
```

A shell in the installed app's sandbox, with the SDK and its debugging tools
in place of the Platform runtime (the SDK must be installed):

```sh
flatpak run --devel --command=sh eu.nosini.Pulsemeeter
```

To see which D-Bus names the app tries to reach, and so which `--talk-name`
permissions it needs:

```sh
flatpak run --log-session-bus eu.nosini.Pulsemeeter 2>&1 | grep '(required 1)'
```

Permissions granted through portals, such as notifications or background
running, are listed with `flatpak permission-show eu.nosini.Pulsemeeter` and
cleared with `flatpak permission-reset eu.nosini.Pulsemeeter`.

## GitHub Actions

`.github/workflows/flatpak.yml` runs when a `v*` version tag is pushed,
for pull requests and on manual runs. Pushes to `main` run the packaging
checks without building the app. Release builds use the tagged commit.
For each architecture, the workflow lints the manifest and metainfo,
builds with [flatpak-github-actions](https://github.com/flatpak/flatpak-github-actions),
lints the exported build, runs the installed-app checks and uploads an
installable bundle as an artifact. Install a downloaded artifact with
`flatpak install --user pulsemeeter-x86_64.flatpak`. Bundles are unsigned
and don't update; the published repository does.

Like Flathub, CI builds for x86_64 and aarch64. The aarch64 build uses
GitHub's Arm runners, which are free for public repositories only. To
limit the architectures, add a `flathub.json`, for example
`{"only-arches": ["x86_64"]}`.

`.github/workflows/checks.yml` lints the scripts and workflows, checks that
the manifest and metadata files parse, and runs the tests in
`scripts/tests/`. The publishing test makes small fake builds and publishes
them several times to a local web server.

### Build cache

CI restores `.flatpak-builder`, including downloaded sources and the results
of modules built from fixed sources. Flatpak checks the inputs and rebuilds
affected modules when sources, dependencies, patches or the SDK change. The
manifest's `metadata` module uses a directory source for the icons, which
flatpak-builder never caches, so it and the modules after it are rebuilt on
every run. There is no compiler cache, because every module installs prebuilt
wheels or files. Lint and installed-app checks still run on every build, and
a snapshot is saved only after they pass.

The key covers this workflow and `python3-requirements.json`, so changing
either starts a new snapshot; otherwise the newest earlier snapshot is
restored. The container image is pinned by digest, so a new image means a
workflow change and a new key. Downloads are carried over and not pruned when
a dependency is dropped, so a snapshot grows slowly. To start over, bump
`CACHE_PREFIX` in the workflow; the key and the restore prefix both use it,
so they can't drift apart. Cache misses build normally.

Snapshots are saved only on `main`, and only after the tests and the artifact
upload, because a snapshot saved on a tag or pull request can only be restored
by reruns of that ref. GitHub removes caches unused for more than seven days
and evicts older entries when the repository's storage limit is reached; see
its [cache access and retention rules](https://docs.github.com/en/actions/reference/workflows-and-actions/dependency-caching).

To populate the cache before a release without publishing, run the workflow
on `main` without the **publish** input, or use:

```sh
gh workflow run flatpak.yml --ref main
```

Run this from the package repository's checkout.

### Publishing

With the repository variable `PUBLISH_FLATPAK` set to `true`, pushing a
stable version tag publishes a signed Flatpak repository to GitHub Pages.
Manual runs build and test only unless the **publish** input is selected;
they can publish from `main`. Pull requests and prerelease tags never
publish. Runs that can publish wait for one another, so a tag pushed during
another publication isn't built from an outdated repository head. A separate
job, which never runs upstream build code, downloads the published repository
and checks it against the signing key. It adds the tested builds
of all architectures as new signed commits, generates static deltas, signs a
new software catalog and summary, and writes `pulsemeeter.flatpakrepo` and
`pulsemeeter.flatpakref` with the public key embedded. Both files take the
app's summary from its metainfo and point to a copy of its icon, which
software centers show when the remote or app is added. Before deploying, a
fresh remote that only knows the public key must accept the summary, every app
and extension commit, and each architecture's software catalog.

The repository keeps the five previous versions of the app and each
extension, so users can go back to one with `flatpak update --commit`. A
build whose files didn't change adds no version. A build older than the
published one, such as a rerun of an earlier tag or a packaging revision
before the current version, is refused, because it would become the head and
downgrade users on their next update. Static deltas let Flatpak
download an install or update as a few large files instead of one request
per file. If the published repository can't be downloaded or doesn't match
the signing key, for example after replacing the key, the job fails. Set the
variable `FLATPAK_KEEP_HISTORY` to `false` to publish a new repository without
the earlier versions.

After a tag build passes, the workflow creates its GitHub Release with the
runner's `GITHUB_TOKEN` and attaches the tested bundles. For stable
publication, it waits for the Pages deployment to succeed first. Rerunning a
tag build replaces assets on the existing release. Manual runs on version
tags create or update the release only with **publish** selected; manual runs
on branches do not create releases.

The repository URL defaults to `https://OWNER.github.io/REPOSITORY/`. For a
custom domain, set the `FLATPAK_REPO_URL` variable to the real URL. The
trailing slash is optional.

To set publishing up:

1. In **Settings → Pages**, select **GitHub Actions** as the source.
2. Store the signing key as the secret `FLATPAK_GPG_PRIVATE_KEY` (see
   below).
3. Set the variable:
   `gh variable set PUBLISH_FLATPAK --body true --repo nosini/pulsemeeter-flatpak`.
4. Push a version tag pointing to the commit to build, or run the Flatpak
   workflow manually on `main` with **publish** selected.

Stable tags have the form `v2.2.0`. A numeric suffix such as `v2.2.0-1`
identifies a stable packaging revision of the same upstream version.
Other suffixes, such as `v2.3.0-rc1`, create GitHub prereleases without
replacing the stable Flatpak repository or becoming the latest stable
GitHub Release. The workflow fails a stable tag whose version, without a
numeric packaging suffix, isn't the newest release in the metainfo file.
Tag the commit containing the intended package pins and workflow:

```sh
git tag -s v2.2.0 -m 'Pulsemeeter 2.2.0'
git push origin v2.2.0
```

In **Settings → Environments → github-pages**, make sure the deployment
rules allow version tags as well as `main`. If using **Selected branches
and tags**, retain a Branch rule for `main` and add a Tag rule for `v*`.
A branch rule for `main` alone doesn't allow release deployments. GitHub
documents these
[deployment rules](https://docs.github.com/en/actions/reference/workflows-and-actions/deployments-and-environments#deployment-branches-and-tags).

Release assets must remain mutable for reruns to replace them; GitHub's
[immutable release setting](https://cli.github.com/manual/gh_release_create#immutable-releases)
prevents asset updates.

### Signing key

The key has to be an ASCII-armored GnuPG private key without a passphrase.
An existing Flatpak signing key can be reused. To make a new one, generate
it on your own machine, outside the source checkout, in a separate GnuPG
directory:

```sh
mkdir -p -m 700 "$HOME/.gnupg-flatpak/private-keys-v1.d"
gpgconf --homedir "$HOME/.gnupg-flatpak" --create-socketdir
gpg --homedir "$HOME/.gnupg-flatpak" --batch --pinentry-mode loopback \
  --passphrase '' --quick-generate-key 'Nosini Flatpak signing' ed25519 sign 0
```

Upload it through a private temporary file, so a failed export can't upload
an empty secret:

```sh
(
  set -eu
  umask 077
  key_file=$(mktemp "$HOME/.gnupg-flatpak/export.XXXXXX")
  trap 'rm -f "$key_file"' EXIT
  gpg --homedir "$HOME/.gnupg-flatpak" --armor \
    --export-secret-keys 'Nosini Flatpak signing' > "$key_file"
  test -s "$key_file"
  gh secret set FLATPAK_GPG_PRIVATE_KEY --repo nosini/pulsemeeter-flatpak < "$key_file"
)
```

Keep a backup of the key. Installed copies trust the public key from the
`.flatpakref` they were installed with, so replacing the key breaks their
updates.

### Shared remote

[flatpak-repo](https://github.com/nosini/flatpak-repo) collects the
published packages into the shared `nosini` remote. Its `apps.json` already
lists this app with its `Locale` extension.

After a successful Pages deployment, the `announce` job sends an
`app-published` event to the collector, so the shared remote picks up the
update without waiting for its six-hour schedule. Failed deployments,
prereleases and manual builds without the **publish** input don't announce a
publication. A failed notification leaves the published repository intact;
rerun the failed job after correcting the token, or start collection
manually.

Create a [fine-grained personal access token](https://github.com/settings/personal-access-tokens/new)
with access to `nosini/flatpak-repo` only and **Contents: Read and write**.
Store it in this repository as `FLATPAK_REPO_DISPATCH_TOKEN`:

```sh
gh secret set FLATPAK_REPO_DISPATCH_TOKEN --repo nosini/pulsemeeter-flatpak
```

Enter the token at the prompt. The workflow passes it only to the
notification job, which neither checks out nor builds code. The job fails
with a clear error if the secret is missing. GitHub's default `GITHUB_TOKEN`
can't send events to a different repository.

To collect a release that has already been published:

```sh
gh workflow run publish.yml --repo nosini/flatpak-repo --ref main
```

## Updating

`.github/workflows/update.yml` runs
[flatpak-external-data-checker](https://github.com/flathub-infra/flatpak-external-data-checker)
every Monday at 05:17 UTC, and on manual runs. It follows the
`x-checker-data` of each source in the manifest: for Pulsemeeter, the
newest upstream tag matching `tag-pattern`, which leaves out prereleases;
for Babel, the newest wheel on PyPI. If anything is newer, it updates the
pins and adds a release to the metainfo file, pushes the change to the
`update/upstream` branch, opens a pull request and starts the Flatpak build
of that branch. Its result shows on the pull request. After merging,
push a version tag at the merged commit to build and publish the
update. The new release entry only has a version and a date; add upstream's
release notes on the update branch.

The workflow needs **Allow GitHub Actions to create and approve pull
requests** under **Settings → Actions → General**.

To merge updates without review, set the variable `AUTO_MERGE_UPDATES` to
`true`. The workflow then waits for the build and merges the pull request
when the build and the installed-app checks pass. Push a version tag
afterwards to ship it. A failed build leaves the pull request open.

Changes pushed to `update/upstream` by anyone but the workflow are kept:
while the pull request is open, later runs commit newer releases on top of
them, comment on the pull request and leave it for review even with
`AUTO_MERGE_UPDATES`. Once the pull request is closed or merged, the next
update starts again from `main`. If someone pushes to the branch while the
workflow runs, the run fails instead of replacing the branch; the next one
picks the push up.

GitHub disables scheduled workflows in public repositories after 60 days
without activity. Re-enable the workflow under **Actions** if that happens.

The checker doesn't follow the generated Python modules. Before merging an
update, compare upstream's `requirements.txt` with the one here; leave out
`pygobject`, which comes from the runtime. If it changed, update
`requirements.txt` on the update branch and regenerate the Python modules
(below). Patches that no longer apply fail the build: check out the new tag
in `upstream/`, check them with `git apply --check ../patches/*.patch`, make
the change again where needed and regenerate the patch with `git diff`,
keeping its explanation at the top.

## Python dependencies

`requirements.txt` lists the app's runtime dependencies; leave out what the
runtime already provides (PyGObject). After changing it, regenerate the
module:

```sh
flatpak install --user flathub org.gnome.Sdk//51
bash scripts/generate-python-deps.sh
```

The script runs flatpak-pip-generator from flatpak-builder-tools with pip
inside the manifest's SDK, so dependency markers match the runtime's Python.
It prefers pure-Python wheels. pydantic-core is compiled from Rust, so the
script selects its prebuilt wheels for x86_64 and aarch64 instead, which
needs `flatpak run`.

The script works around three problems of the generator. It doesn't
evaluate markers on the listed requirements, so
`scripts/filter-requirements.py` leaves out lines whose markers don't apply
to the runtime's Python on Linux, for every architecture CI builds, and
removes the markers of the lines it keeps, so pip doesn't evaluate them
again for the machine it runs on. A requirement needed on only some
architectures stops the script; add such a package as a module with
`only-arches` instead. The generator also skips packages it expects from the
SDK, including pip, wheel, Cython and Meson, which the Platform lacks, so
the script tells it to bundle them when needed. An explicit requirement for
packaging can be bundled too, although GNOME already provides it. And for
the prebuilt wheels it imports `packaging` inside the SDK; the script uses
pip's vendored copy, which also works with Freedesktop SDKs.

Set `PREFER_WHEELS` to a comma-separated list to change which packages use
native wheels; its default is `pydantic-core`. For requirements that don't
need native wheels, set it to an empty string and set `PIP_GENERATOR_PYTHON`
to an interpreter of the runtime's Python version, for example
`PREFER_WHEELS='' PIP_GENERATOR_PYTHON=python3.14 bash scripts/generate-python-deps.sh`.
This runs pip there without `flatpak run`.

The generated file pins exact wheels, so it changes only when the script
runs. Dependabot tracks the GitHub Actions but not these entries. To pick up
upstream releases, including security fixes, rerun the script before a
release and commit the changed `python3-requirements.json`; nothing in CI
regenerates it.

Babel is only needed while building, because `setup.py` compiles the
translations. It is a module of its own in the manifest, which the update
check follows, and its `cleanup` removes it from the finished app.

## Moving to a newer runtime

Change `runtime-version` in the manifest. The `gnome-51` container image tag
appears twice in `.github/workflows/flatpak.yml`, in the `build` and
`publish` jobs, and again in the `publishing` job of
`.github/workflows/checks.yml`; keep all three in step with the manifest.
Each is pinned by digest (`gnome-51@sha256:...`), because the publish job
imports the signing key inside it and the tag can be moved. Dependabot
doesn't update these, so look up the new tag's digest, for example with
`skopeo inspect --format '{{.Digest}}'
docker://ghcr.io/flathub-infra/flatpak-github-actions:gnome-51`, and refresh
it the same way to pick up a rebuilt image. The actions are pinned by commit,
which Dependabot keeps updated, and the actionlint download in `checks.yml`
by checksum; update its version and checksum by hand. `checks.yml` also pins
the runtimes' Python in `python-version` for the script tests; change it when
the runtime's Python version changes. If the new runtime has a different
Python version, regenerate the Python dependencies, and update the version
examples in this file and in `scripts/generate-python-deps.sh`.

## How the package works

### Runtime

GTK 4 isn't part of the Freedesktop runtime, so the app uses GNOME 51. That
runtime is built on Freedesktop 26.08 and provides Python 3.14, PyGObject,
setuptools, and the PipeWire tools Pulsemeeter calls (`pw-cli`, `pw-link`,
`pw-loopback`, `pw-dump`, `pw-metadata`). Only pulsectl, pulsectl-asyncio
and pydantic come from PyPI, and Babel while building.

### PipeWire permissions

PipeWire tags clients that connect from a Flatpak sandbox, and WirePlumber
0.5 restricts them:

- On the native socket, a Flatpak client gets read and execute permission
  on other clients' objects (`find-flatpak-access.lua`). That is not enough
  to write stream metadata or change other nodes. A client that sets
  `media.category = Manager` gets full permissions instead.
  `pipewire/50-manager.conf` sets that property in
  `context.properties`. The manifest copies the runtime's own `client.conf`
  next to it and points `PIPEWIRE_CONFIG_DIR` there. Every `pw-*` tool
  Pulsemeeter starts loads that configuration and announces the Manager role.
- On the PulseAudio socket, pipewire-pulse marks a Flatpak client as a
  Manager only when the app has `--device=all` (see
  `module-protocol-pulse/server.c` in PipeWire). Without that permission,
  pulsectl could not change volumes of other apps' streams or devices.

`PIPEWIRE_CONFIG_DIR` replaces the configuration search path entirely, so
the copied `client.conf` must be the complete file, not just an override.

### Patches

The patches are small enough to propose upstream. Each starts with a short
explanation.

- `0001-detect-pipewire-pulse-through-the-server.patch`: Pulsemeeter
  refuses to start unless a `pipewire-pulse` executable is on `PATH`. The
  sandbox has no such binary, so the check asks the PulseAudio server for
  its name instead (`PulseAudio (on PipeWire x.y.z)`).
- `0002-find-translations-installed-under-app.patch`: adds
  `/app/share/locale` to the folders searched for translations.
- `0003-find-app-icons-installed-on-the-host.patch`: Pulsemeeter shows each
  stream's `application.icon_name` from the icon theme. Flatpak only
  exposes the host's `/usr/share/icons` and `~/.local/share/icons`, but
  `xdg-icon-resource`, which browser packages such as Brave's RPM use,
  installs into `/usr/local/share/icons`. Flatpak refuses to expose paths
  under `/usr` individually, so the manifest grants `host-os:ro`, which
  mounts the host's `/usr` at `/run/host/usr`. The patch adds
  `/run/host/usr/local/share/icons` and the `pixmaps` folders to GTK's icon
  search path. They aren't added to `XDG_DATA_DIRS`, which would also make
  the host's GSettings schemas and MIME data visible to the app.

  Flatpak apps' icons stay unavailable: the exported icons are symlinks
  into each app's installation folder.

### App ID

The Flatpak ID is `eu.nosini.Pulsemeeter`, while Pulsemeeter's
`GtkApplication` registers `org.pulsemeeter.pulsemeeter` on the session
bus. The manifest allows that name with `--own-name`, and the launcher sets
`StartupWMClass` to it.

## Checking a build on a desktop

These parts can only be checked with a real PipeWire session:

- The app starts and lists the existing devices and apps.
- Creating a virtual input or output works, and the device shows up in the
  system sound settings.
- Routing a device to an output connects it (`pw-link -l` on the host shows
  the links).
- Apps playing audio show their icons, including apps whose icons are in
  `/usr/local/share/icons` on the host.
- Moving an app between devices and resetting it to "default" works.
  The reset uses `pw-metadata` and fails silently without the Manager role.
- A route with per-route volume plays audio, and its volume slider works.
- `flatpak run eu.nosini.Pulsemeeter init` recreates the devices after a
  PipeWire restart (`systemctl --user restart pipewire pipewire-pulse wireplumber`).
- With a non-English `LANGUAGE`, for example `LANGUAGE=de_DE flatpak run
  eu.nosini.Pulsemeeter`, the interface is translated.
