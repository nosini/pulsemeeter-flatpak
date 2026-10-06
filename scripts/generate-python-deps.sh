#!/usr/bin/env bash
# Regenerate python3-requirements.json from requirements.txt with
# flatpak-pip-generator. pip runs inside the manifest's SDK, so environment
# markers and wheel tags match the runtime's Python; that needs a working
# `flatpak run`. Where Flatpak can't run, set PIP_GENERATOR_PYTHON to an
# interpreter of the runtime's Python version (python3.14 for Freedesktop
# 26.08 and GNOME 51) to run pip there instead.
#
# pydantic-core uses prebuilt wheels because building it needs Rust. Set
# PREFER_WHEELS to an empty string to disable this, or to other package names
# separated by commas. Extra arguments go to the generator.
set -euo pipefail
cd "$(dirname "$0")/.."

tools=$(bash scripts/builder-tools.sh)
manifest=$(grep -l '^id: ' ./*.yml)
sdk=$(sed -n 's/^sdk: *//p' "$manifest")
version=$(sed -n 's/^runtime-version: *//p' "$manifest" | tr -d "'\"")

python=${PIP_GENERATOR_PYTHON:-python3}
venv=.cache/pip-generator-$(basename "$python")
if [[ ! -x "$venv/bin/python" ]]; then
  "$python" -m venv "$venv"
fi
"$venv/bin/pip" install -q --disable-pip-version-check 'requirements-parser>=0.11,<1' 'packaging>=23'

version_probe='import platform; print(platform.python_version())'
args=(--requirements-file=.cache/requirements.txt --output=python3-requirements)
if [[ -n "${PREFER_WHEELS-pydantic-core}" ]]; then
  args+=(--prefer-wheels="${PREFER_WHEELS-pydantic-core}")
fi
if [[ -n "${PIP_GENERATOR_PYTHON:-}" ]]; then
  # The generator runs pip3 from PATH.
  PATH="$PWD/$venv/bin:$PATH"
  runtime_python=$("$python" -c "$version_probe")
else
  args+=(--runtime="$sdk//$version")
  runtime_python=$(flatpak run --command=python3 "$sdk//$version" -c "$version_probe")
fi

# The generator ignores markers on the listed requirements; leave out the
# lines that don't apply to the runtime (see the script for details).
"$venv/bin/python" scripts/filter-requirements.py "$runtime_python" \
  requirements.txt .cache/requirements.txt flathub.json

# For --prefer-wheels, the generator reads the runtime's wheel tags with
# `from packaging import tags`, but the Freedesktop SDK only has the copy
# vendored in pip. Run a copy of the generator that imports that one.
generator=.cache/flatpak-pip-generator.py
sed 's/"from packaging import tags; "/"from pip._vendor.packaging import tags; "/' \
  "$tools/pip/flatpak-pip-generator.py" > "$generator"
grep -q 'from pip._vendor.packaging import tags' "$generator"
# The generator skips packages it expects from the SDK. The Platform the app
# runs with has setuptools, Mako and Markdown; GNOME also has packaging.
# Bundle the others when needed (packaging can be bundled explicitly too).
# Check the list after updating the generator.
skipped=$(sed -n '/^    system_packages = \[$/,/^    \]$/s/^ *"\([^"]*\)",$/\1/p' "$generator" | sort | tr '\n' ' ')
if [[ "$skipped" != 'cython mako markdown meson packaging pip setuptools wheel ' ]]; then
  echo "The generator's system_packages changed: $skipped" >&2
  exit 1
fi
args+=('--ignore-installed=cython,meson,packaging,pip,wheel')
"$venv/bin/python" "$generator" "${args[@]}" "$@"
