---
name: macos-cli-dev
description: How to develop, iterate, sign, and ship a macOS Swift app entirely from the terminal — pure SwiftPM + a hand-rolled Makefile bundle + Apple Development cert codesign, never opening Xcode IDE. Triggers on "build a mac app", "做 mac app", "幫我寫一個 menubar app", "wrap swift binary into .app", "codesign mac app", "apple development cert hash", "TCC accessibility permission", "screen recording permission", "LSUIElement menubar-only", "NSStatusItem popover", "NSPanel overlay floating window", "AXUIElement under cursor", "CGEventTap intercept mouse", "ScreenCaptureKit screenshot excluding self", "怎麼簽 mac app", "怎麼不開 xcode 寫 mac app", "swift package mac app bundle 結構", "sourcekit cannot find type in scope but build passes", "Cocoa vs CG 座標系". Skip when user explicitly wants Xcode IDE features (live SwiftUI preview, LLDB GUI, Instruments profiling), provisioning profiles, push notifications / iCloud entitlements, or is submitting to Mac App Store.
---

# /utils:macos-cli-dev — develop macOS apps from the terminal

Edit code → `make bundle` → `open .app` → verify with `pgrep` / `osascript` / `log stream`. No `.xcodeproj`, never open Xcode IDE. SwiftPM produces the executable; a Makefile wraps it into a `.app` bundle and codesigns. Reference impl: [zyx1121/shake](https://github.com/zyx1121/shake).

## 何時走這條

- 個人 / 內部 Mac app — menubar tool、overlay、AppKit + SwiftUI
- 想要乾淨 diff、可重現 build、agent 也能改
- 沒打算上 Mac App Store

不要走（直接打開 Xcode 比較快）：

- 需要 live SwiftUI Preview（rebuild 比 Preview 慢）
- 需要 LLDB step-debug GUI 或 Instruments 剖效能
- 需要 provisioning profile / Push / iCloud / 任何沒 entitlement 就跑不起來的 capability
- 上架 Mac App Store（沙箱 + 完整 entitlements 流程）

## 環境 check

```bash
xcode-select -p                                # /Applications/Xcode.app/Contents/Developer
swift --version                                # 6.x+
security find-identity -p codesigning -v       # 至少一張 Apple Development cert
```

沒 cert 就只能 ad-hoc（`--sign -`）— 也能跑，但 TCC 權限每次 rebuild 都要重 grant。看下面 codesign 章。

## 骨架

```
your-app/
├── Package.swift
├── Makefile
├── Resources/Info.plist
├── Sources/<App>/
└── .gitignore
```

### Package.swift

```swift
// swift-tools-version: 6.0
import PackageDescription

let package = Package(
    name: "<App>",
    platforms: [.macOS(.v14)],
    targets: [
        .executableTarget(name: "<App>", path: "Sources/<App>")
    ]
)
```

SwiftPM 預設 recursive 抓 path 下所有 `.swift`，子資料夾隨便切。

### Resources/Info.plist 關鍵欄位

| Key | Value | Why |
|-----|-------|-----|
| `CFBundleIdentifier` | `dev.<you>.<app>` | TCC 認 bundle id + team id，跨 rebuild 沿用權限 |
| `CFBundleName` / `Executable` / `DisplayName` | `<App>` | |
| `CFBundlePackageType` | `APPL` | |
| `CFBundleVersion` / `CFBundleShortVersionString` | `1` / `0.1.0` | |
| `LSMinimumSystemVersion` | `14.0` | 對齊 Package.swift platforms |
| `NSPrincipalClass` | `NSApplication` | |
| `NSHighResolutionCapable` | `<true/>` | retina |
| `LSUIElement` | `<true/>` | menubar-only：無 Dock、不在 Cmd-Tab |
| `LSApplicationCategoryType` | `public.app-category.<...>` | App Store 分類，列在 about |
| `NSHumanReadableCopyright` | `© YYYY ...` | about dialog |

### Makefile（核心 — bundle + codesign）

```makefile
APP_NAME    := <App>
BUNDLE_ID   := dev.<you>.<app>
BIN_PATH    := .build/release/$(APP_NAME)
APP_BUNDLE  := build/$(APP_NAME).app
CONTENTS    := $(APP_BUNDLE)/Contents

# 鎖 SHA-1 hash，比名字穩。撈：security find-identity -p codesigning -v
SIGN_ID := <40-char hash>

.PHONY: all build bundle run clean rebuild
all: bundle

build:
	swift build -c release

bundle: build
	@rm -rf $(APP_BUNDLE)
	@mkdir -p $(CONTENTS)/MacOS $(CONTENTS)/Resources
	@cp $(BIN_PATH) $(CONTENTS)/MacOS/$(APP_NAME)
	@cp Resources/Info.plist $(CONTENTS)/Info.plist
	@codesign --force --deep --options runtime --sign $(SIGN_ID) $(APP_BUNDLE)
	@echo "[OK] $(APP_BUNDLE) built and signed"

run: bundle
	open $(APP_BUNDLE)

rebuild: clean bundle

clean:
	rm -rf .build build
```

### .gitignore

```
.build/
build/
.swiftpm/
.DS_Store
Package.resolved
*.xcodeproj/
xcuserdata/
```

## Codesigning — 為什麼用 Apple Dev cert 不用 ad-hoc

| 簽法 | 何時用 | 結果 |
|------|--------|------|
| `--sign -` (ad-hoc) | 不戳 TCC 的 app（純 UI、無 Accessibility / Screen Recording / Camera） | 每次 rebuild cdhash 變 → TCC 要重 grant |
| `--sign <hash>` (Apple Development) | 戳 TCC 的 app | Team ID 穩定 → bundle id + team id 認，rebuild 不失權限 |

`--options runtime` 開 Hardened Runtime — Notarization 必須，平常啟用也無害（除非你動態 dlopen / JIT，那要加 entitlements）。

驗簽：

```bash
codesign -dvvv build/<App>.app 2>&1 | head
# 看：
#   Authority=Apple Development: <email> (<TeamID>)
#   TeamIdentifier=<10 chars>
#   CDHash=<40 chars>
#   flags=0x10000(runtime)
```

注意：cert 名字裡的 `(FJW6JALJHP)` 跟 codesign 報的 `TeamIdentifier` 可能是兩個不同字串 — 後者才是 TCC 真正認的。看 `TeamIdentifier` 那行。

## 開發 loop

| 動作 | 指令 |
|------|------|
| Build + bundle | `make bundle` |
| Launch | `open build/<App>.app`（或 `make run`） |
| Confirm running | `pgrep -l <App>` |
| Window state | `osascript -e 'tell application "System Events" to get name of every window of process "<App>"'` |
| Log (NSLog 全進來) | `log stream --predicate 'process == "<App>"' --style compact` |
| Quit | `osascript -e 'quit app "<App>"'` |
| Verify sig | `codesign -dvvv build/<App>.app` |
| Symbol exists? | `nm .build/release/<App> \| grep <Type>` |

`osascript` 那條超實用 — 不用 screenshot 就能確認視窗有沒有開、標題對不對。

## SourceKit LSP 亂叫 — 信 build，不信 LSP

寫 Swift 時 LSP 會一直噴 `Cannot find type 'X' in scope` 即便 X 在同 module 別檔。`sourcekit-lsp` 對單檔孤立 parse，看不到 cross-file symbols。

**`swift build` 是 whole-module compilation**，全 module 一起跑、symbol 找得到。Build pass 就 work，LSP 抱怨忽略。

## TCC 權限：流程 + 程式

```swift
// Accessibility
let trusted = AXIsProcessTrusted()                          // 不彈
let opts: NSDictionary = ["AXTrustedCheckOptionPrompt": true]
AXIsProcessTrustedWithOptions(opts)                         // 彈 prompt

// Screen Recording
CGPreflightScreenCaptureAccess()                            // 不彈
CGRequestScreenCaptureAccess()                              // 彈

// 直接開設定 deep link
NSWorkspace.shared.open(URL(string: "x-apple.systempreferences:com.apple.preference.security?Privacy_Accessibility")!)
NSWorkspace.shared.open(URL(string: "x-apple.systempreferences:com.apple.preference.security?Privacy_ScreenCapture")!)
```

UX 慣例：主視窗 / popover 顯示權限狀態 badge + 引導按鈕 + relaunch 按鈕。Ad-hoc 簽通常 grant 後要重 launch；Apple Dev cert 簽的多半當下就認，rebuild 後也維持。

關於 Swift 6 strict concurrency：`kAXTrustedCheckOptionPrompt` 是 CFString global var，編譯會抱怨「concurrency-safe」。直接用字面值 `"AXTrustedCheckOptionPrompt"` 繞過。

## Menubar-only app（無 Dock、無一般視窗）

Info.plist `LSUIElement = true` 配：

```swift
@main
struct <App>App: App {
    @NSApplicationDelegateAdaptor(AppDelegate.self) var delegate
    var body: some Scene { Settings { EmptyView() } }       // 沒一般視窗
}

@MainActor
final class AppDelegate: NSObject, NSApplicationDelegate {
    private var statusItem: NSStatusItem!
    private var popover: NSPopover!

    func applicationDidFinishLaunching(_ n: Notification) {
        statusItem = NSStatusBar.system.statusItem(withLength: NSStatusItem.variableLength)
        statusItem.button?.image = NSImage(systemSymbolName: "<sf-symbol>", accessibilityDescription: "<App>")
        statusItem.button?.image?.isTemplate = true         // adapt menubar 主題
        statusItem.button?.action = #selector(togglePopover)
        statusItem.button?.target = self

        popover = NSPopover()
        popover.behavior = .transient
        popover.contentSize = NSSize(width: 480, height: 480)
        popover.contentViewController = NSHostingController(rootView: ContentView())
    }

    @objc func togglePopover() {
        guard let button = statusItem.button else { return }
        if popover.isShown { popover.performClose(nil) }
        else { popover.show(relativeTo: button.bounds, of: button, preferredEdge: .minY) }
    }
}
```

## Overlay 視窗（floating-on-everything）

要做 spotlight / heads-up / pin overlay 用 `NSPanel` 不是 `NSWindow`，subclass 寫成 AX-隱形（不會被自己的 AXUIElement query 抓到）：

```swift
final class OverlayPanel: NSPanel {
    override var canBecomeKey: Bool { false }
    override var canBecomeMain: Bool { false }
    override func accessibilityRole() -> NSAccessibility.Role? { nil }
    override func accessibilityChildren() -> [Any]? { [] }
    override func isAccessibilityElement() -> Bool { false }
}

let panel = OverlayPanel(
    contentRect: ...,
    styleMask: [.borderless, .nonactivatingPanel],
    backing: .buffered,
    defer: false
)
panel.isOpaque = false
panel.backgroundColor = .clear
panel.hasShadow = false
panel.level = .screenSaver                                  // 蓋所有 app（含 Dock / menubar）
panel.collectionBehavior = [.canJoinAllSpaces, .stationary, .fullScreenAuxiliary]
panel.ignoresMouseEvents = false                            // false = panel 自己接 click
```

兩個高度 level 常用：

- `.statusBar` (25) — 高過普通視窗、低於系統 UI
- `.screenSaver` (1000) — 蓋系統 UI，做 spotlight overlay 用這個

要 panel **跨 Space 跟著走**：`collectionBehavior` 含 `.canJoinAllSpaces`。
要 panel 不會因為 user 切 Mission Control 而閃：加 `.stationary`。

## 座標系 — Cocoa vs CG，整個 mac dev 最大坑

| 系統 | 原點 | Y | 出現處 |
|------|------|---|--------|
| Cocoa | 主螢幕**左下** | 向上 | `NSEvent.mouseLocation`、`NSWindow.frame`、`NSScreen.frame` |
| CG / Quartz | 主螢幕**左上** | 向下 | `CGEvent.location`、`AXValue` position、`CGDisplayBounds` |

任一點轉換：

```swift
let primary = NSScreen.screens.first(where: { $0.frame.origin == .zero }) ?? NSScreen.main!
let cgY    = primary.frame.height - cocoaY
let cocoaY = primary.frame.height - cgY
```

多螢幕：用 `CGDisplayBounds(displayID)` 拿每個 display 在 CG 的 rect，做 intersection / containment。`NSScreen.cgDisplayID` 可由 `deviceDescription[NSScreenNumber]` 拿。

## CGEventTap — 全域擋 / 改滑鼠、鍵盤

需 Accessibility 權限。重點：

```swift
guard let tap = CGEvent.tapCreate(
    tap: .cgSessionEventTap,
    place: .headInsertEventTap,
    options: .defaultTap,
    eventsOfInterest: mask,
    callback: { _, type, event, refcon in
        // 這 callback 跑在 tap thread，不是 main。要動 main-actor 物件用 DispatchQueue.main.async
        return Unmanaged.passUnretained(event)              // 放行
        // return nil                                       // 吞掉
    },
    userInfo: Unmanaged.passUnretained(self).toOpaque()
) else { /* AX 沒給 */ }

CGEvent.tapEnable(tap: tap, enable: false)                  // 先 disable
let src = CFMachPortCreateRunLoopSource(kCFAllocatorDefault, tap, 0)
CFRunLoopAddSource(CFRunLoopGetCurrent(), src, .commonModes)
```

兩個重要陷阱：

1. **Tap 創出來預設 enabled**。要先 `tapEnable(false)` 再加 runloop，否則中間有空窗會吞 event。
2. **`tapDisabledByTimeout` / `tapDisabledByUserInput` 會被觸發**（callback 太慢、或 OS 自動關）。Re-enable 前先看你自己的 intent flag，否則明明該關的 tap 又被你打開亂吞 click。

intent flag 用 lock 保護（callback 在 tap thread、setter 在 main）：

```swift
private let lock = NSLock()
private var _intercept = false
private func intent() -> Bool { lock.lock(); defer { lock.unlock() }; return _intercept }
```

## ScreenCaptureKit — 截圖排除自家視窗

```swift
import ScreenCaptureKit

let content = try await SCShareableContent.excludingDesktopWindows(
    false,
    onScreenWindowsOnly: true
)
let display = content.displays.first(where: { CGDisplayBounds($0.displayID).contains(point) })!
let mine = content.windows.filter { $0.owningApplication?.bundleIdentifier == Bundle.main.bundleIdentifier }
let filter = SCContentFilter(display: display, excludingWindows: mine)

let cfg = SCStreamConfiguration()
cfg.sourceRect = rectInDisplayLocalCoords                   // CG points，display-local origin
cfg.width  = Int(rect.width  * backingScale)                // backingScale → retina 解析度
cfg.height = Int(rect.height * backingScale)
cfg.showsCursor = false

let cg = try await SCScreenshotManager.captureImage(
    contentFilter: filter,
    configuration: cfg
)
let nsImage = NSImage(cgImage: cg, size: NSSize(width: rect.width, height: rect.height))
```

需 Screen Recording 權限。`sourceRect` 是 display-local（每個 display 原點 (0,0)），用 `CGDisplayBounds` 把 global CG point 轉成 local。

## 何時切回 Xcode IDE

| 需求 | 走 IDE |
|------|--------|
| Live SwiftUI Preview | ✓ |
| LLDB step-debug GUI | ✓ |
| Instruments profiling | ✓ |
| Provisioning profile workflow | ✓ |
| App Store submission | ✓ |

要時直接 `open Package.swift` — Xcode 14+ 直接吃 SwiftPM，不用 generate `.xcodeproj`。寫好就回 CLI。

## 真實案例

[zyx1121/shake](https://github.com/zyx1121/shake) — menubar overlay 工具，從零到 ship 都這 workflow。看 `Makefile` / `Resources/Info.plist` / `Sources/Shake/App/` 是參考實作。
