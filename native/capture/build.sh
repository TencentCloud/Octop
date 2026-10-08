#!/bin/sh
set -eu
if [ "$(uname -s)" != Darwin ]; then
    echo "native-capture only supports macOS 13+." >&2
    exit 1
fi
cd "$(dirname "$0")"
bundle=OctopCapture.app
mkdir -p "$bundle/Contents/MacOS" "$bundle/Contents/Resources"
# Reuse the macOS desktop application's icon at standard and Retina sizes.
icon_dir="$(mktemp -d "${TMPDIR:-/tmp}/octop-capture-icon.XXXXXX")"
trap 'rm -rf "$icon_dir"' EXIT
mkdir -p "$icon_dir/AppIcon.iconset"
for size in 16 32 128 256 512; do
    sips -z "$size" "$size" ../../desktop/src/build/appicon-macos.png --out "$icon_dir/AppIcon.iconset/icon_${size}x${size}.png" >/dev/null
    retina=$((size * 2))
    sips -z "$retina" "$retina" ../../desktop/src/build/appicon-macos.png --out "$icon_dir/AppIcon.iconset/icon_${size}x${size}@2x.png" >/dev/null
done
iconutil -c icns "$icon_dir/AppIcon.iconset" -o "$bundle/Contents/Resources/AppIcon.icns"
xcrun swiftc -target "$(uname -m)-apple-macosx13.0" main.swift PhoneAlbum.swift -o "$bundle/Contents/MacOS/OctopCapture" -framework AppKit -framework ImageCaptureCore -framework PDFKit
cat > "$bundle/Contents/Info.plist" <<'PLIST'
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
<key>CFBundleIdentifier</key><string>com.octop.capture</string>
<key>CFBundleName</key><string>Octop Capture</string>
<key>CFBundleExecutable</key><string>OctopCapture</string>
<key>CFBundleIconFile</key><string>AppIcon.icns</string>
<key>LSMinimumSystemVersion</key><string>13.0</string>
<key>CFBundlePackageType</key><string>APPL</string>
<key>NSCameraUsageDescription</key><string>Import the photos you select from a connected iPhone.</string>
<key>NSHighResolutionCapable</key><true/>
</dict></plist>
PLIST
codesign --force --sign - "$bundle"
