#!/usr/bin/env bash
# Build a drag-to-Applications installer DMG from an existing .app bundle.
#
# Usage: create-installer-dmg.sh <app-bundle> <output.dmg> [volume-name]
set -euo pipefail

if [[ $# -lt 2 ]]; then
  echo "Usage: create-installer-dmg.sh <app-bundle> <output.dmg> [volume-name]" >&2
  exit 2
fi

app_path="$1"
output="$2"
volname="${3:-Octop}"

if [[ ! -d "$app_path" ]]; then
  echo "app bundle not found: $app_path" >&2
  exit 1
fi

app_name="$(basename "$app_path")"
script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
bg_src="${script_dir}/dmg-background.jpeg"
work="$(mktemp -d "${TMPDIR:-/tmp}/octop-dmg.XXXXXX")"
staging="${work}/root"
rw_dmg="${work}/rw.dmg"
device=""
mount_point=""

cleanup() {
  if [[ -n "$device" ]]; then
    hdiutil detach "$device" -quiet >/dev/null 2>&1 || \
      hdiutil detach "$device" -force -quiet >/dev/null 2>&1 || true
  fi
  if [[ -n "$mount_point" && -d "$mount_point" ]]; then
    hdiutil detach "$mount_point" -quiet >/dev/null 2>&1 || \
      hdiutil detach "$mount_point" -force -quiet >/dev/null 2>&1 || true
  fi
  rm -rf "$work"
}
trap cleanup EXIT

mkdir -p "$staging"
ditto "$app_path" "${staging}/${app_name}"
ln -s /Applications "${staging}/Applications"
if [[ -f "$bg_src" ]]; then
  mkdir -p "${staging}/.background"
  cp "$bg_src" "${staging}/.background/background.png"
fi

create_plain_dmg() {
  rm -f "$output"
  hdiutil create -volname "$volname" -srcfolder "$staging" -ov -format UDRO "$output"
}

if [[ -d "/Volumes/${volname}" ]]; then
  hdiutil detach "/Volumes/${volname}" -quiet >/dev/null 2>&1 || \
    hdiutil detach "/Volumes/${volname}" -force -quiet >/dev/null 2>&1 || true
fi

rm -f "$rw_dmg"
hdiutil create -volname "$volname" -srcfolder "$staging" -ov -format UDRW "$rw_dmg" >/dev/null

attach_out="$(hdiutil attach -readwrite -noverify -noautoopen "$rw_dmg")"
device="$(awk '/^\/dev\// { print $1; exit }' <<<"$attach_out")"
mount_point="$(awk -F'\t' '/\/Volumes\// { print $NF; exit }' <<<"$attach_out")"
if [[ -z "$device" || -z "$mount_point" || ! -d "$mount_point" ]]; then
  echo "warning: could not mount writable DMG; falling back to plain installer image" >&2
  create_plain_dmg
  exit 0
fi

# Finder layout is cosmetic. The Applications symlink is already in the image.
# Window 600x400 matches dmg-background.jpeg; icons sit in the white well.
if ! osascript - "$volname" "$app_name" <<'APPLESCRIPT'
on run argv
  set volName to item 1 of argv
  set appName to item 2 of argv
  tell application "Finder"
    tell disk volName
      open
      set current view of container window to icon view
      set toolbar visible of container window to false
      set statusbar visible of container window to false
      set the bounds of container window to {200, 120, 800, 520}
      set viewOptions to the icon view options of container window
      set arrangement of viewOptions to not arranged
      set icon size of viewOptions to 128
      try
        set background picture of viewOptions to file ".background:background.png"
      end try
      set position of item appName of container window to {150, 250}
      set position of item "Applications" of container window to {450, 250}
      close
      open
      update without registering applications
      delay 1
    end tell
  end tell
end run
APPLESCRIPT
then
  echo "warning: could not set Finder icon layout; Applications drop link is still present" >&2
fi

sync
hdiutil detach "$device" -quiet
device=""
mount_point=""

rm -f "$output"
hdiutil convert "$rw_dmg" -ov -format UDRO -o "$output" >/dev/null

if [[ ! -s "$output" ]]; then
  echo "DMG was not created: $output" >&2
  exit 1
fi
