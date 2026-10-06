#!/usr/bin/env bash
# Regenerate python3-requirements.json from requirements.txt with
# flatpak-pip-generator. pip runs inside the manifest's SDK, so environment
# markers and wheel tags match the runtime's Python. pydantic-core comes as
# prebuilt wheels, because building it from source would need Rust; picking
# them needs a working `flatpak run` and the SDK (org.gnome.Sdk//51).
#
# Extra arguments go to the generator.
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
args=(--requirements-file=.cache/requirements.txt --output=python3-requirements
  --prefer-wheels=pydantic-core)
if [[ -n "${PIP_GENERATOR_PYTHON:-}" ]]; then
  # The generator runs pip3 from PATH.
  PATH="$PWD/$venv/bin:$PATH"
  runtime_python=$("$python" -c "$version_probe")
else
  args+=(--runtime="$sdk//$version")
  runtime_python=$(flatpak run --command=python3 "$sdk//$version" -c "$version_probe")
fi

# The generator doesn't evaluate python_version markers on the listed
# requirements, so a line like `tomli; python_version < "3.11"` would become
# a module without sources. Drop the lines whose markers don't apply to the
# runtime's Python. pip handles the markers of indirect dependencies itself.
"$venv/bin/python" - "$runtime_python" requirements.txt .cache/requirements.txt <<'PYTHON'
import sys
from packaging.requirements import Requirement

python_version, source, target = sys.argv[1:]
environment = {
    "python_version": ".".join(python_version.split(".")[:2]),
    "python_full_version": python_version,
}
kept = []
for line in open(source):
    text = line.split("#", 1)[0].strip()
    if text and not text.startswith("-"):
        requirement = Requirement(text)
        if requirement.marker and not requirement.marker.evaluate(environment):
            print(f"Leaving out {text}: not needed on Python {python_version}")
            continue
    kept.append(line)
open(target, "w").writelines(kept)
PYTHON

# For --prefer-wheels, the generator reads the runtime's wheel tags with
# `from packaging import tags`, but the Freedesktop SDK only has the copy
# vendored in pip. Run a copy of the generator that imports that one.
generator=.cache/flatpak-pip-generator.py
sed 's/"from packaging import tags; "/"from pip._vendor.packaging import tags; "/' \
  "$tools/pip/flatpak-pip-generator.py" > "$generator"
grep -q 'from pip._vendor.packaging import tags' "$generator"
"$venv/bin/python" "$generator" "${args[@]}" "$@"
