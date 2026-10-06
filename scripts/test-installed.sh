#!/usr/bin/env bash
# Install the build exported to repo/ and run tests/check-installed.sh inside
# the installed app's sandbox, so the checks run against the Platform runtime
# rather than the SDK, with the German translations installed. Run from
# anywhere after building with --repo=repo.
set -euo pipefail
cd "$(dirname "$0")/.."

: "${APP_ID:=$(sed -n 's/^id: *//p' ./*.yml)}"
: "${FLATPAK_BRANCH:=stable}"
: "${FLATPAK_ARCH:=$(flatpak --default-arch)}"
ref="app/$APP_ID/$FLATPAK_ARCH/$FLATPAK_BRANCH"
locale_ref="runtime/$APP_ID.Locale/$FLATPAK_ARCH/$FLATPAK_BRANCH"

if ! flatpak --user remotes --columns=name | grep -qx local-test; then
  flatpak --user remote-add --no-gpg-verify local-test "$PWD/repo"
fi
url=$(flatpak --user remotes --columns=name,url | awk '$1 == "local-test" { print $2 }')
if [[ "$url" != "file://$PWD/repo" ]]; then
  echo "The local-test remote points to $url, not this checkout's repo/." >&2
  echo 'Remove it with: flatpak --user remote-delete local-test' >&2
  exit 1
fi

# Don't replace an existing installation when running locally.
for installed in "$ref" "$locale_ref"; do
  if flatpak info --user "$installed" >/dev/null 2>&1; then
    echo "These checks need a fresh installation; $installed is already installed." >&2
    echo "Remove it with: flatpak --user uninstall $installed" >&2
    exit 1
  fi
done

# flatpak-builder doesn't always refresh the summary of an existing repo.
flatpak build-update-repo repo
flatpak --user install --noninteractive --no-related local-test "$ref"
# The German translations, whatever the host's languages are.
flatpak --user install --noninteractive --no-related --subpath=/de local-test "$locale_ref"
flatpak run --user --arch="$FLATPAK_ARCH" --branch="$FLATPAK_BRANCH" --env=LANGUAGE=de_DE \
  --command=sh "$APP_ID" -s < tests/check-installed.sh
