import AppKit
import ImageCaptureCore
import UniformTypeIdentifiers

// Read-only device browsing. Only explicitly selected files are downloaded.
final class PhoneAlbum: NSObject, ICDeviceBrowserDelegate, ICCameraDeviceDelegate,
                        ICCameraDeviceDownloadDelegate, NSTableViewDataSource, NSTableViewDelegate {
    let browser = ICDeviceBrowser()
    var cameras: [ICCameraDevice] = []
    var camera: ICCameraDevice?
    var files: [ICCameraFile] = []
    var queue: [ICCameraFile] = []
    var saved: [String] = []
    var window: NSWindow?
    let table = NSTableView()
    let devices = NSPopUpButton()
    let status = NSTextField(wrappingLabelWithString: "")
    let importButton = NSButton(title: "", target: nil, action: nil)
    let chinese = Locale.preferredLanguages.first?.hasPrefix("zh") ?? false
    func text(_ zh: String, _ en: String) -> String { chinese ? zh : en }

    func start() {
        let view = NSView(frame: NSRect(x: 0, y: 0, width: 740, height: 540))
        devices.target = self
        devices.action = #selector(selectDevice)
        devices.addItem(withTitle: text("等待 iPhone…", "Waiting for iPhone…"))
        status.stringValue = text("通过 USB 连接 iPhone，解锁并选择“信任此电脑”。", "Connect iPhone by USB, unlock it and trust this computer.")
        status.textColor = .secondaryLabelColor
        let scroll = NSScrollView()
        scroll.hasVerticalScroller = true
        scroll.borderType = .bezelBorder
        table.allowsMultipleSelection = true
        table.rowHeight = 64
        for (id, title, width) in [("image", "", 72.0), ("name", text("手机上的照片", "Photos on iPhone"), 430.0), ("date", text("日期", "Date"), 170.0)] {
            let column = NSTableColumn(identifier: NSUserInterfaceItemIdentifier(id))
            column.title = title
            column.width = width
            table.addTableColumn(column)
        }
        table.dataSource = self
        table.delegate = self
        scroll.documentView = table
        let cancel = NSButton(title: text("取消", "Cancel"), target: self, action: #selector(cancelSelection))
        cancel.keyEquivalent = "\u{1b}"
        importButton.title = text("导入所选照片", "Import selected photos")
        importButton.target = self
        importButton.action = #selector(importSelected)
        importButton.isEnabled = false
        let buttons = NSStackView(views: [cancel, importButton])
        buttons.spacing = 12
        for element in [devices, status, scroll, buttons] {
            element.translatesAutoresizingMaskIntoConstraints = false
            view.addSubview(element)
        }
        NSLayoutConstraint.activate([
            devices.topAnchor.constraint(equalTo: view.topAnchor, constant: 24),
            devices.leadingAnchor.constraint(equalTo: view.leadingAnchor, constant: 24),
            devices.widthAnchor.constraint(equalToConstant: 330),
            status.topAnchor.constraint(equalTo: devices.bottomAnchor, constant: 12),
            status.leadingAnchor.constraint(equalTo: view.leadingAnchor, constant: 24),
            status.trailingAnchor.constraint(equalTo: view.trailingAnchor, constant: -24),
            scroll.topAnchor.constraint(equalTo: status.bottomAnchor, constant: 18),
            scroll.leadingAnchor.constraint(equalTo: view.leadingAnchor, constant: 24),
            scroll.trailingAnchor.constraint(equalTo: view.trailingAnchor, constant: -24),
            scroll.bottomAnchor.constraint(equalTo: buttons.topAnchor, constant: -20),
            buttons.trailingAnchor.constraint(equalTo: view.trailingAnchor, constant: -24),
            buttons.bottomAnchor.constraint(equalTo: view.bottomAnchor, constant: -24),
        ])
        let win = NSWindow(contentRect: view.frame, styleMask: [.titled, .closable], backing: .buffered, defer: false)
        win.title = text("从 iPhone 导入照片", "Import photos from iPhone")
        win.contentView = view
        win.isReleasedWhenClosed = false
        win.delegate = NSApp.delegate as? NSWindowDelegate
        win.center()
        win.makeKeyAndOrderFront(nil)
        window = win
        browser.delegate = self
        browser.browsedDeviceTypeMask = ICDeviceTypeMask(rawValue: ICDeviceTypeMask.camera.rawValue | ICDeviceLocationTypeMask.local.rawValue)!
        browser.start()
    }

    @objc func cancelSelection() {
        camera?.cancelDownload()
        camera?.requestCloseSession()
        browser.stop()
        finish("cancelled")
    }
    @objc func selectDevice() {
        guard cameras.indices.contains(devices.indexOfSelectedItem) else { return }
        camera?.requestCloseSession()
        camera = cameras[devices.indexOfSelectedItem]
        files = []
        table.reloadData()
        camera?.delegate = self
        status.stringValue = text("正在读取手机照片，请保持解锁…", "Reading photos. Keep your iPhone unlocked…")
        camera?.requestOpenSession()
    }
    func deviceBrowser(_ browser: ICDeviceBrowser, didAdd device: ICDevice, moreComing: Bool) {
        guard let device = device as? ICCameraDevice, device.transportType == ICDeviceTransport.transportTypeUSB.rawValue,
              device.usbVendorID == 0x05ac else { return }
        cameras.append(device)
        updateDevices()
        if camera == nil { selectDevice() }
    }
    func deviceBrowserDidEnumerateLocalDevices(_ browser: ICDeviceBrowser) {
        guard cameras.isEmpty else { return }
        status.stringValue = text(
            "未发现 USB 连接的 iPhone。请使用支持数据传输的线缆，解锁手机并信任此电脑；也可打开 macOS“图像捕捉”确认手机是否可见。连接后会自动刷新。",
            "No iPhone found over USB. Use a data cable, unlock your iPhone and trust this computer. Check whether it appears in macOS Image Capture. This list updates automatically when connected.")
    }
    func deviceBrowser(_ browser: ICDeviceBrowser, didRemove device: ICDevice, moreGoing: Bool) {
        cameras.removeAll { $0 === device }
        updateDevices()
        if camera === device {
            camera = nil
            files = []
            table.reloadData()
            importButton.isEnabled = false
            status.stringValue = text("iPhone 已断开，请重新连接。", "iPhone disconnected. Reconnect it.")
            if !queue.isEmpty { finish("error", [], status.stringValue) }
        }
    }
    func updateDevices() {
        devices.removeAllItems()
        // NSPopUpButton.addItem replaces an existing item with the same title.
        // Distinct phones may share a name; preserve one menu row per device.
        for device in cameras {
            devices.menu?.addItem(NSMenuItem(title: device.name ?? "iPhone", action: nil, keyEquivalent: ""))
        }
        if let current = camera, let index = cameras.firstIndex(where: { $0 === current }) {
            devices.selectItem(at: index)
        }
    }
    func refresh(_ device: ICCameraDevice) {
        guard device === camera, queue.isEmpty else { return }
        let selected = Set(table.selectedRowIndexes.compactMap { $0 < files.count ? ObjectIdentifier(files[$0]) : nil })
        files = (device.mediaFiles ?? []).compactMap { $0 as? ICCameraFile }.filter {
            guard let name = $0.name else { return false }
            let ext = (name as NSString).pathExtension.lowercased()
            guard ["jpg", "jpeg", "png", "heic", "heif", "tif", "tiff", "gif", "bmp", "webp", "avif"].contains(ext), let type = UTType(filenameExtension: ext) else { return false }
            return type.conforms(to: .image)
        }.sorted { ($0.creationDate ?? .distantPast) > ($1.creationDate ?? .distantPast) }
        table.reloadData()
        table.selectRowIndexes(IndexSet(files.indices.filter { selected.contains(ObjectIdentifier(files[$0])) }), byExtendingSelection: false)
        status.stringValue = text("\(files.count) 张照片 · 可多选；仅导入所选原件", "\(files.count) photos · Select multiple photos to import")
    }
    func numberOfRows(in tableView: NSTableView) -> Int { files.count }
    func tableViewSelectionDidChange(_ notification: Notification) {
        importButton.isEnabled = !table.selectedRowIndexes.isEmpty && queue.isEmpty
    }
    func tableView(_ tableView: NSTableView, viewFor column: NSTableColumn?, row: Int) -> NSView? {
        let file = files[row]
        if column?.identifier.rawValue == "image" {
            let image = NSImageView()
            image.imageScaling = .scaleProportionallyUpOrDown
            if let thumb = file.thumbnail { image.image = NSImage(cgImage: thumb, size: .zero) }
            else { file.requestThumbnail() }
            return image
        }
        let value = column?.identifier.rawValue == "date" ? file.creationDate.map { DateFormatter.localizedString(from: $0, dateStyle: .short, timeStyle: .none) } ?? "" : file.name ?? ""
        return NSTextField(labelWithString: value)
    }
    @objc func importSelected() {
        guard queue.isEmpty, camera != nil else { return }
        queue = table.selectedRowIndexes.map { files[$0] }
        guard !queue.isEmpty else { return }
        devices.isEnabled = false
        table.isEnabled = false
        importButton.isEnabled = false
        downloadNext()
    }
    func downloadNext() {
        guard let file = queue.first, let camera = camera else {
            finish("ok", saved)
            return
        }
        status.stringValue = text("正在导入第 \(saved.count + 1) 张照片…", "Importing photo \(saved.count + 1)…")
        let name = "\(saved.count + 1)-\(file.name ?? "photo.jpg")"
        camera.requestDownloadFile(file, options: [.downloadsDirectoryURL: output, .saveAsFilename: name, .deleteAfterSuccessfulDownload: false], downloadDelegate: self, didDownloadSelector: #selector(didDownloadFile(_:error:options:contextInfo:)), contextInfo: nil)
    }
    @objc func didDownloadFile(_ file: ICCameraFile, error: Error?, options: [String: Any], contextInfo: UnsafeMutableRawPointer?) {
        guard error == nil else { finish("error", [], error!.localizedDescription); return }
        guard let name = options[ICDownloadOption.savedFilename.rawValue] as? String, FileManager.default.fileExists(atPath: output.appendingPathComponent(name).path) else {
            finish("error", [], text("照片下载失败。", "Photo download failed.")); return
        }
        saved.append(name)
        queue.removeFirst()
        downloadNext()
    }
    func device(_ device: ICDevice, didOpenSessionWithError error: Error?) {
        if let error = error { status.stringValue = error.localizedDescription }
    }
    func device(_ device: ICDevice, didCloseSessionWithError error: Error?) {}
    func didRemove(_ device: ICDevice) {}
    func deviceDidBecomeReady(_ device: ICDevice) {}
    func device(_ device: ICDevice, didEncounterError error: Error?) {
        status.stringValue = error?.localizedDescription ?? text("设备错误", "Device error")
    }
    func cameraDevice(_ camera: ICCameraDevice, didAdd items: [ICCameraItem]) { refresh(camera) }
    func cameraDevice(_ camera: ICCameraDevice, didRemove items: [ICCameraItem]) { refresh(camera) }
    func cameraDevice(_ camera: ICCameraDevice, didRenameItems items: [ICCameraItem]) { refresh(camera) }
    func cameraDevice(_ camera: ICCameraDevice, didReceiveThumbnail thumbnail: CGImage?, for item: ICCameraItem, error: Error?) {
        if thumbnail != nil, let row = files.firstIndex(where: { $0 === item }) { table.reloadData(forRowIndexes: IndexSet(integer: row), columnIndexes: IndexSet(integer: 0)) }
    }
    func cameraDevice(_ camera: ICCameraDevice, didReceiveMetadata metadata: [AnyHashable: Any]?, for item: ICCameraItem, error: Error?) {}
    func cameraDeviceDidChangeCapability(_ camera: ICCameraDevice) {}
    func cameraDevice(_ camera: ICCameraDevice, didReceivePTPEvent eventData: Data) {}
    func deviceDidBecomeReady(withCompleteContentCatalog device: ICCameraDevice) { refresh(device) }
    func cameraDeviceDidRemoveAccessRestriction(_ device: ICDevice) { (device as? ICCameraDevice)?.requestOpenSession() }
    func cameraDeviceDidEnableAccessRestriction(_ device: ICDevice) {
        status.stringValue = text("请解锁 iPhone，并信任此电脑。", "Unlock iPhone and trust this computer.")
    }
}
