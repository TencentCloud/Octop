#!/bin/sh
# Hardware-independent regression checks for selecting the system scan action.
set -eu
if [ "$(uname -s)" != Darwin ]; then
    echo "Native capture UI regression requires macOS." >&2
    exit 1
fi
cd "$(dirname "$0")"
test_dir="$(mktemp -d "${TMPDIR:-/tmp}/octop-scan-test.XXXXXX")"
trap 'rm -rf "$test_dir"' EXIT
# Keep the production classes and omit the actual application launch.
sed '/^let app = NSApplication.shared/,$d' main.swift > "$test_dir/main.swift"
cat >> "$test_dir/main.swift" <<'SWIFT'
final class Counter: NSObject {
    var calls = 0
    @objc func selected(_ sender: Any?) { calls += 1 }
}
let application = NSApplication.shared
application.setActivationPolicy(.prohibited)
application.finishLaunching()
// ImageCaptureCore transport values are identifiers, not display names.
assert(ICDeviceTransport.transportTypeUSB.rawValue == "ICTransportTypeUSB")
let album = PhoneAlbum()
let usbCamera = ICCameraDevice()
usbCamera.setValue(ICDeviceTransport.transportTypeUSB.rawValue, forKey: "transportType")
usbCamera.setValue(0x05ac, forKey: "usbVendorID")
album.deviceBrowser(album.browser, didAdd: usbCamera, moreComing: false)
assert(album.cameras.count == 1)
let secondCamera = ICCameraDevice()
secondCamera.setValue(ICDeviceTransport.transportTypeUSB.rawValue, forKey: "transportType")
secondCamera.setValue(0x05ac, forKey: "usbVendorID")
album.deviceBrowser(album.browser, didAdd: secondCamera, moreComing: false)
album.devices.selectItem(at: 1)
album.selectDevice()
let thirdCamera = ICCameraDevice()
thirdCamera.setValue(ICDeviceTransport.transportTypeUSB.rawValue, forKey: "transportType")
thirdCamera.setValue(0x05ac, forKey: "usbVendorID")
album.deviceBrowser(album.browser, didAdd: thirdCamera, moreComing: false)
assert(album.camera === secondCamera && album.devices.indexOfSelectedItem == 1)
album.deviceBrowser(album.browser, didRemove: usbCamera, moreGoing: false)
assert(album.camera === secondCamera && album.devices.indexOfSelectedItem == 0)
let networkCamera = ICCameraDevice()
networkCamera.setValue(ICDeviceTransport.transportTypeTCPIP.rawValue, forKey: "transportType")
networkCamera.setValue(0x05ac, forKey: "usbVendorID")
album.deviceBrowser(album.browser, didAdd: networkCamera, moreComing: false)
assert(album.cameras.count == 2)
let counter = Counter()
guard #available(macOS 13.0, *) else { exit(2) }
let delegate = Delegate()
let menu = NSMenu()
menu.autoenablesItems = false
func item(_ title: String, enabled: Bool = true) -> NSMenuItem {
    let result = NSMenuItem(title: title, action: #selector(Counter.selected(_:)), keyEquivalent: "")
    result.target = counter
    result.isEnabled = enabled
    return result
}
menu.addItem(item("Take Photo"))
menu.addItem(item("Scan Documents"))
menu.addItem(item("Add Sketch"))
let candidates = delegate.scanItems(in: menu)
assert(candidates.count == 1 && candidates[0].1 == 1)
candidates[0].0.performActionForItem(at: candidates[0].1)
assert(counter.calls == 1)
let photoCandidates = delegate.actionItems(in: menu, photo: true)
assert(photoCandidates.count == 1 && photoCandidates[0].1 == 0)
menu.addItem(item("扫描文稿", enabled: false))
assert(delegate.scanItems(in: menu).count == 1)
menu.addItem(item("扫描文稿"))
assert(delegate.scanItems(in: menu).count == 2)
let unknown = NSMenu()
unknown.autoenablesItems = false
unknown.addItem(item("Unknown localized action"))
assert(delegate.scanItems(in: unknown).isEmpty)
let parent = NSMenu()
parent.autoenablesItems = false
let device = NSMenuItem(title: "Device", action: nil, keyEquivalent: "")
device.submenu = menu
parent.addItem(device)
assert(delegate.scanItems(in: parent).count == 2)
let image = NSImage(size: NSSize(width: 100, height: 100))
image.lockFocus()
NSColor.white.setFill()
NSRect(x: 0, y: 0, width: 100, height: 100).fill()
image.unlockFocus()
let largeImage = NSImage(size: NSSize(width: 2400, height: 1200))
largeImage.lockFocus()
NSColor.white.setFill()
NSRect(x: 0, y: 0, width: 2400, height: 1200).fill()
largeImage.unlockFocus()
let thumbnail = NSBitmapImageRep(data: imagePreview(largeImage)!)!
assert(thumbnail.pixelsWide <= 1600 && thumbnail.pixelsHigh <= 800)
let pdf = PDFDocument()
pdf.insert(PDFPage(image: image)!, at: 0)
assert(pdf.write(to: output.appendingPathComponent("saved.pdf")))
finish("ok", ["saved.pdf"])
delegate.windowWillClose(Notification(name: NSWindow.willCloseNotification))
let result = try! JSONSerialization.jsonObject(with: Data(contentsOf: output.appendingPathComponent("result.json"))) as! [String: Any]
assert(result["status"] as? String == "ok")
assert(result["files"] as? [String] == ["saved.pdf"])
assert((result["previews"] as? [String: String])?["saved.pdf"] == "preview-saved.pdf.png")
assert(FileManager.default.fileExists(atPath: output.appendingPathComponent("preview-saved.pdf.png").path))
print("PASS: USB device discovery and network filtering, successful result survives window close, PDF thumbnail, scan action, disabled actions, ambiguity, unknown locale, nested devices")
SWIFT
xcrun swiftc "$test_dir/main.swift" PhoneAlbum.swift -o "$test_dir/check" -framework AppKit -framework ImageCaptureCore -framework PDFKit
"$test_dir/check" scan "$test_dir"
