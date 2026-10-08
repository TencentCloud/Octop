import AppKit
import UniformTypeIdentifiers
import ImageCaptureCore
import PDFKit

guard CommandLine.arguments.count == 3, ["scan", "photo", "album", "import"].contains(CommandLine.arguments[1]) else { exit(2) }

// Public AppKit Services API: the system owns device discovery and scan UI.
final class CaptureView: NSView, NSServicesMenuRequestor {
    override var acceptsFirstResponder: Bool { true }

    override func validRequestor(forSendType sendType: NSPasteboard.PasteboardType?,
                                returnType: NSPasteboard.PasteboardType?) -> Any? {
        if let type = returnType, type == .pdf || NSImage.imageTypes.contains(type.rawValue) {
            return self
        }
        return super.validRequestor(forSendType: sendType, returnType: returnType)
    }

    func readSelection(from pasteboard: NSPasteboard) -> Bool {
        do {
            if let pdf = pasteboard.data(forType: .pdf) {
                try pdf.write(to: output.appendingPathComponent("scan.pdf"), options: .atomic)
                finish("ok", ["scan.pdf"])
                return true
            }
            if let image = NSImage(pasteboard: pasteboard),
               let tiff = image.tiffRepresentation,
               let bitmap = NSBitmapImageRep(data: tiff),
               let png = bitmap.representation(using: .png, properties: [:]) {
                try png.write(to: output.appendingPathComponent("scan.png"), options: .atomic)
                finish("ok", ["scan.png"])
                return true
            }
        } catch {
            finish("error", [], error.localizedDescription)
        }
        return false
    }

    override func menu(for event: NSEvent) -> NSMenu? {
        // AppKit automatically inserts the Continuity Camera context menu item.
        return NSMenu()
    }
}

let output = URL(fileURLWithPath: CommandLine.arguments[2], isDirectory: true)
var captureFinished = false
func imagePreview(_ image: NSImage) -> Data? {
    let scale = min(1, 800 / max(image.size.width, image.size.height))
    let size = NSSize(width: image.size.width * scale, height: image.size.height * scale)
    let thumbnail = NSImage(size: size, flipped: false) { bounds in
        image.draw(in: bounds)
        return true
    }
    guard let tiff = thumbnail.tiffRepresentation else { return nil }
    return NSBitmapImageRep(data: tiff)?.representation(using: .png, properties: [:])
}
func finish(_ status: String, _ files: [String] = [], _ reason: String = "") {
    guard !captureFinished else { return }
    captureFinished = true
    var previews: [String: String] = [:]
    if status == "ok" {
        for name in files {
            let ext = (name as NSString).pathExtension.lowercased()
            if ["heic", "heif", "tif", "tiff", "bmp"].contains(ext),
               let image = NSImage(contentsOf: output.appendingPathComponent(name)),
               let png = imagePreview(image) {
                let preview = "preview-\(name).png"
                if (try? png.write(to: output.appendingPathComponent(preview))) != nil { previews[name] = preview }
            }
            guard ext == "pdf" else { continue }
            if let document = PDFDocument(url: output.appendingPathComponent(name)),
               let page = document.page(at: 0),
               let tiff = withExtendedLifetime(document, { page.thumbnail(of: NSSize(width: 600, height: 800), for: .mediaBox).tiffRepresentation }),
               let png = NSBitmapImageRep(data: tiff)?.representation(using: .png, properties: [:]) {
                let preview = "preview-\(name).png"
                if (try? png.write(to: output.appendingPathComponent(preview))) != nil { previews[name] = preview }
            }
        }
    }
    let result: [String: Any] = ["status": status, "files": files, "reason": reason, "previews": previews]
    do {
        let data = try JSONSerialization.data(withJSONObject: result)
        try data.write(to: output.appendingPathComponent("result.json"), options: .atomic)
    } catch { exit(1) }
    // In particular, readSelection must return true to AppKit before the
    // Services receiver exits. Terminating inside that callback interrupts
    // the pasteboard handoff even when the captured file was already saved.
    DispatchQueue.main.async {
        NSApplication.shared.terminate(nil)
    }
}

@available(macOS 13.0, *)
final class Delegate: NSObject, NSApplicationDelegate, NSWindowDelegate {
    var window: NSWindow?
    var cameraMenu: NSMenu?
    var captureView: CaptureView?
    var hostController: NSViewController?
    var statusLabel: NSTextField?
    var phoneAlbum: PhoneAlbum?
    var mode = CommandLine.arguments[1]
    let chinese = Locale.preferredLanguages.first?.hasPrefix("zh") ?? false

    func text(_ zh: String, _ en: String) -> String { chinese ? zh : en }

    // Match system-generated actions by title, never by an assumed item index.
    func scanItems(in menu: NSMenu) -> [(NSMenu, Int)] {
        actionItems(in: menu, photo: false)
    }

    func actionItems(in menu: NSMenu, photo: Bool) -> [(NSMenu, Int)] {
        menu.update()
        let titles: Set<String> = photo
            ? ["Take Photo", "拍照", "拍摄照片", "拍攝照片"]
            : ["Scan Documents", "扫描文稿", "扫描文档", "掃描文稿", "掃描文件"]
        var result: [(NSMenu, Int)] = []
        for (index, item) in menu.items.enumerated() {
            if item.isEnabled && item.action != nil && titles.contains(item.title) {
                result.append((menu, index))
            }
            if let submenu = item.submenu {
                result.append(contentsOf: actionItems(in: submenu, photo: photo))
            }
        }
        return result
    }

    @objc func retry(_ sender: Any?) {
        if mode == "album" { showAlbum() } else { startCaptureWhenReady(attempt: 0) }
    }

    @objc func cancel(_ sender: Any?) { finish("cancelled") }

    func startCaptureWhenReady(attempt: Int) {
        guard let menu = cameraMenu, let view = captureView else { return }
        window?.makeFirstResponder(view)
        let candidates = actionItems(in: menu, photo: mode == "photo")
        if candidates.count == 1 {
            statusLabel?.stringValue = text("请在 iPhone 上完成操作", "Complete the capture on your iPhone")
            let (owner, index) = candidates[0]
            owner.performActionForItem(at: index)
        } else if candidates.isEmpty && attempt < 10 {
            DispatchQueue.main.asyncAfter(deadline: .now() + 0.2) {
                self.startCaptureWhenReady(attempt: attempt + 1)
            }
        } else {
            statusLabel?.stringValue = text("请选择可用设备", "Choose an available device")
            menu.popUp(positioning: nil, at: NSPoint(x: 28, y: 84), in: view)
        }
    }

    func showAlbum() {
        let album = PhoneAlbum()
        phoneAlbum = album
        window?.orderOut(nil)
        album.start()
    }

    func label(_ value: String, size: CGFloat, weight: NSFont.Weight = .regular,
               color: NSColor = .labelColor) -> NSTextField {
        let field = NSTextField(wrappingLabelWithString: value)
        field.font = .systemFont(ofSize: size, weight: weight)
        field.textColor = color
        field.alignment = .center
        field.translatesAutoresizingMaskIntoConstraints = false
        return field
    }

    func buildWindow() {
        let view = CaptureView(frame: NSRect(x: 0, y: 0, width: 460, height: 390))
        captureView = view
        let host = NSViewController()
        host.view = view
        hostController = host
        let background = NSVisualEffectView()
        background.material = .underWindowBackground
        background.blendingMode = .behindWindow
        background.state = .active
        background.translatesAutoresizingMaskIntoConstraints = false
        view.addSubview(background)
        NSLayoutConstraint.activate([
            background.leadingAnchor.constraint(equalTo: view.leadingAnchor),
            background.trailingAnchor.constraint(equalTo: view.trailingAnchor),
            background.topAnchor.constraint(equalTo: view.topAnchor),
            background.bottomAnchor.constraint(equalTo: view.bottomAnchor),
        ])

        let symbol = mode == "photo" ? "camera" : mode == "album" ? "photo.on.rectangle" : "doc.viewfinder"
        let icon = NSImageView()
        icon.image = NSImage(systemSymbolName: symbol, accessibilityDescription: nil)?
            .withSymbolConfiguration(.init(pointSize: 30, weight: .medium))
        icon.contentTintColor = .systemTeal
        icon.translatesAutoresizingMaskIntoConstraints = false
        icon.widthAnchor.constraint(equalToConstant: 52).isActive = true
        icon.heightAnchor.constraint(equalToConstant: 52).isActive = true

        let brand = label("OCTOP", size: 11, weight: .semibold, color: .secondaryLabelColor)
        let title = mode == "photo" ? text("用 iPhone 拍照", "Take a photo with iPhone")
            : mode == "album" ? text("从相册选择", "Choose from Photos")
            : text("扫描文稿", "Scan documents")
        let subtitle = mode == "photo" ? text("拍摄照片并确认，文件将保存到调用方指定的目录。", "Take a photo and confirm it to save to the selected directory.")
            : mode == "album" ? text("连接并解锁 iPhone，可多选手机上的照片。", "Connect and unlock iPhone to select photos directly.")
            : text("支持连续扫描多页，完成后在 iPhone 上点存储。", "Scan multiple pages, then tap Save on your iPhone.")
        let heading = label(title, size: 25, weight: .semibold)
        let detail = label(subtitle, size: 13, color: .secondaryLabelColor)
        let status = label(mode == "album" ? text("等待选择照片", "Waiting for photo selection")
                           : text("正在连接附近的 iPhone…", "Connecting to a nearby iPhone…"), size: 12, color: .secondaryLabelColor)
        statusLabel = status
        let stack = NSStackView(views: [brand, icon, heading, detail, status])
        stack.orientation = .vertical
        stack.alignment = .centerX
        stack.spacing = 14
        stack.translatesAutoresizingMaskIntoConstraints = false
        background.addSubview(stack)
        let retryButton = NSButton(title: mode == "album" ? text("选择照片", "Choose photos")
                                  : text("重新连接", "Reconnect"), target: self, action: #selector(retry(_:)))
        retryButton.bezelStyle = .rounded
        retryButton.controlSize = .large
        retryButton.contentTintColor = .systemTeal
        let cancelButton = NSButton(title: text("取消", "Cancel"), target: self, action: #selector(cancel(_:)))
        cancelButton.bezelStyle = .rounded
        cancelButton.controlSize = .large
        cancelButton.keyEquivalent = "\u{1b}"
        let buttons = NSStackView(views: [cancelButton, retryButton])
        buttons.spacing = 12
        buttons.translatesAutoresizingMaskIntoConstraints = false
        background.addSubview(buttons)
        let footer = label(text("完成后自动保存文件并返回调用方。", "Files are saved locally and returned to the caller."), size: 11, color: .tertiaryLabelColor)
        background.addSubview(footer)
        NSLayoutConstraint.activate([
            stack.topAnchor.constraint(equalTo: view.topAnchor, constant: 48),
            stack.leadingAnchor.constraint(equalTo: view.leadingAnchor, constant: 36),
            stack.trailingAnchor.constraint(equalTo: view.trailingAnchor, constant: -36),
            detail.widthAnchor.constraint(equalTo: stack.widthAnchor),
            buttons.centerXAnchor.constraint(equalTo: view.centerXAnchor),
            buttons.bottomAnchor.constraint(equalTo: footer.topAnchor, constant: -20),
            footer.leadingAnchor.constraint(equalTo: view.leadingAnchor, constant: 28),
            footer.trailingAnchor.constraint(equalTo: view.trailingAnchor, constant: -28),
            footer.bottomAnchor.constraint(equalTo: view.bottomAnchor, constant: -24),
            stack.bottomAnchor.constraint(lessThanOrEqualTo: buttons.topAnchor, constant: -20),
        ])
        let win = NSWindow(contentRect: view.frame, styleMask: [.titled, .closable, .fullSizeContentView], backing: .buffered, defer: false)
        win.title = "Octop Capture"
        win.titleVisibility = .hidden
        win.titlebarAppearsTransparent = true
        win.contentViewController = host
        win.delegate = self
        win.isReleasedWhenClosed = false
        win.center()
        win.makeKeyAndOrderFront(nil)
        win.makeFirstResponder(view)
        window = win
    }

    func applicationDidFinishLaunching(_ notification: Notification) {
        NSApp.activate(ignoringOtherApps: true)
        if mode == "import" {
            let panel = NSOpenPanel()
            panel.allowsMultipleSelection = true
            panel.canChooseDirectories = false
            panel.allowedContentTypes = [.pdf, .png, .jpeg, .tiff, .heic, .gif, .bmp]
            guard panel.runModal() == .OK else { finish("cancelled"); return }
            var files: [String] = []
            do {
                for (index, url) in panel.urls.enumerated() {
                    let name = "\(index + 1)-\(url.lastPathComponent)"
                    try FileManager.default.copyItem(at: url, to: output.appendingPathComponent(name))
                    files.append(name)
                }
                finish("ok", files)
            } catch { finish("error", [], error.localizedDescription) }
            return
        }
        if mode == "album" { showAlbum(); return }
        let mainMenu = NSMenu()
        let appItem = NSMenuItem()
        let appMenu = NSMenu()
        appMenu.addItem(withTitle: text("退出", "Quit"), action: #selector(NSApplication.terminate(_:)), keyEquivalent: "q")
        appItem.submenu = appMenu
        mainMenu.addItem(appItem)
        let fileItem = NSMenuItem(title: text("文件", "File"), action: nil, keyEquivalent: "")
        let fileMenu = NSMenu(title: text("文件", "File"))
        let camera = NSMenuItem(title: "Import from iPhone or iPad", action: nil, keyEquivalent: "")
        camera.identifier = NSMenuItem.importFromDeviceIdentifier
        fileMenu.addItem(camera)
        fileItem.submenu = fileMenu
        cameraMenu = fileMenu
        mainMenu.addItem(fileItem)
        NSApp.mainMenu = mainMenu
        buildWindow()
        DispatchQueue.main.async {
            if self.mode == "album" { self.showAlbum() }
            else { self.startCaptureWhenReady(attempt: 0) }
        }
    }

    func windowWillClose(_ notification: Notification) { finish("cancelled") }
    func applicationWillTerminate(_ notification: Notification) {
        if !FileManager.default.fileExists(atPath: output.appendingPathComponent("result.json").path) {
            try? JSONSerialization.data(withJSONObject: ["status": "cancelled", "files": []])
                .write(to: output.appendingPathComponent("result.json"))
        }
    }
}

let app = NSApplication.shared
guard #available(macOS 13.0, *) else { exit(2) }
let delegate = Delegate()
app.setActivationPolicy(.regular)
app.delegate = delegate
app.run()
