#!/usr/bin/env bash
# Run from the repository root after exporting a build to repo/.
set -euo pipefail

url=$(flatpak --user remotes --columns=name,url | awk '$1 == "local-test" { print $2 }')
if [[ "$url" != "file://$PWD/repo" ]]; then
  echo 'Add local-test pointing to this build before running the checks:' >&2
  echo "  flatpak --user remote-add --no-gpg-verify local-test \"\$PWD/repo\"" >&2
  exit 1
fi

# Avoid replacing an existing user installation when running locally.
for ref in app/eu.nosini.Pulsemeeter/x86_64/stable runtime/eu.nosini.Pulsemeeter.Locale/x86_64/stable; do
  if flatpak info --user "$ref" >/dev/null 2>&1; then
    echo "These checks need a fresh installation; $ref is already installed." >&2
    exit 1
  fi
done

test -s build-dir/export/share/icons/hicolor/128x128/apps/eu.nosini.Pulsemeeter.png
test -s build-dir/export/share/applications/eu.nosini.Pulsemeeter.desktop

flatpak build-update-repo repo
flatpak --user install --noninteractive --no-related local-test app/eu.nosini.Pulsemeeter/x86_64/stable
# Explicitly install German translations, regardless of the host's languages.
flatpak --user install --noninteractive --no-related --subpath=/de local-test runtime/eu.nosini.Pulsemeeter.Locale/x86_64/stable
flatpak run --user --arch=x86_64 --branch=stable --env=LANGUAGE=de_DE \
  --command=python3 eu.nosini.Pulsemeeter - < scripts/check-installed.py
