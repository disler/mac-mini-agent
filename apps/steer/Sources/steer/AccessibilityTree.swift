import ApplicationServices
import AppKit
import Foundation

struct UIElement: Codable {
    let id: String
    let role: String
    let label: String
    let value: String?
    let x: Int
    let y: Int
    let width: Int
    let height: Int
    let isEnabled: Bool
    let depth: Int
    var centerX: Int { x + width / 2 }
    var centerY: Int { y + height / 2 }
}

enum AccessibilityTree {
    private struct RawEl {
        let role: String; let label: String; let value: String?
        let b: CGRect; let enabled: Bool; let depth: Int
    }

    static func isAccessibilityGranted() -> Bool {
        AXIsProcessTrusted()
    }

    static func requestAccess() {
        let opts = [kAXTrustedCheckOptionPrompt.takeUnretainedValue(): true] as CFDictionary
        AXIsProcessTrustedWithOptions(opts)
    }

    static func focusedElement(app: NSRunningApplication) -> UIElement? {
        guard isAccessibilityGranted() else { return nil }
        let root = AXUIElementCreateApplication(app.processIdentifier)
        var focusRef: CFTypeRef?
        guard AXUIElementCopyAttributeValue(root, kAXFocusedUIElementAttribute as CFString, &focusRef) == .success,
              let focused = focusRef else { return nil }
        let axEl = focused as! AXUIElement
        let role = axStr(axEl, kAXRoleAttribute) ?? "unknown"
        let label = axStr(axEl, kAXTitleAttribute)
            ?? axStr(axEl, kAXDescriptionAttribute)
            ?? axStr(axEl, kAXIdentifierAttribute) ?? ""
        let value = axStr(axEl, kAXValueAttribute)
        var p = CGPoint.zero; var s = CGSize.zero
        if let pv = axVal(axEl, kAXPositionAttribute) { AXValueGetValue(pv, .cgPoint, &p) }
        if let sv = axVal(axEl, kAXSizeAttribute) { AXValueGetValue(sv, .cgSize, &s) }
        let en = axBool(axEl, kAXEnabledAttribute) ?? true
        return UIElement(
            id: "F0", role: role.replacingOccurrences(of: "AX", with: "").lowercased(),
            label: label, value: value,
            x: Int(p.x), y: Int(p.y), width: Int(s.width), height: Int(s.height),
            isEnabled: en, depth: 0
        )
    }

    static func walk(app: NSRunningApplication, maxDepth: Int = 10) -> [UIElement] {
        if !isAccessibilityGranted() {
            requestAccess()
            return []
        }
        let root = AXUIElementCreateApplication(app.processIdentifier)
        var raw: [RawEl] = []
        walkEl(root, depth: 0, max: maxDepth, out: &raw)
        let visible = raw.filter { $0.b.width > 1 && $0.b.height > 1 && isInteractive($0.role) }
        return assignIDs(visible)
    }

    private static func walkEl(_ el: AXUIElement, depth: Int, max: Int, out: inout [RawEl]) {
        guard depth < max else { return }
        let role = axStr(el, kAXRoleAttribute) ?? "unknown"
        let label = axStr(el, kAXTitleAttribute)
            ?? axStr(el, kAXDescriptionAttribute)
            ?? axStr(el, kAXIdentifierAttribute) ?? ""
        let value = axStr(el, kAXValueAttribute)
        var p = CGPoint.zero; var s = CGSize.zero
        if let pv = axVal(el, kAXPositionAttribute) { AXValueGetValue(pv, .cgPoint, &p) }
        if let sv = axVal(el, kAXSizeAttribute) { AXValueGetValue(sv, .cgSize, &s) }
        let en = axBool(el, kAXEnabledAttribute) ?? true
        out.append(RawEl(role: role, label: label, value: value,
                         b: CGRect(origin: p, size: s), enabled: en, depth: depth))
        var cr: CFTypeRef?
        guard AXUIElementCopyAttributeValue(el, kAXChildrenAttribute as CFString, &cr) == .success,
              let kids = cr as? [AXUIElement] else { return }
        for kid in kids { walkEl(kid, depth: depth + 1, max: max, out: &out) }
    }

    private static func assignIDs(_ els: [RawEl]) -> [UIElement] {
        var c: [String: Int] = [:]
        return els.map { r in
            let pre = prefix(r.role); c[pre, default: 0] += 1
            return UIElement(
                id: "\(pre)\(c[pre]!)",
                role: r.role.replacingOccurrences(of: "AX", with: "").lowercased(),
                label: r.label, value: r.value,
                x: Int(r.b.origin.x), y: Int(r.b.origin.y),
                width: Int(r.b.size.width), height: Int(r.b.size.height),
                isEnabled: r.enabled, depth: r.depth)
        }
    }

    private static func prefix(_ role: String) -> String {
        switch role {
        case "AXButton": return "B"
        case "AXTextField","AXTextArea","AXSearchField","AXComboBox": return "T"
        case "AXStaticText": return "S"
        case "AXImage": return "I"
        case "AXCheckBox": return "C"
        case "AXRadioButton": return "R"
        case "AXPopUpButton": return "P"
        case "AXSlider": return "SL"
        case "AXLink": return "L"
        case "AXMenuItem","AXMenuBarItem": return "M"
        case "AXTab": return "TB"
        default: return "E"
        }
    }

    private static func isInteractive(_ role: String) -> Bool {
        ["AXButton","AXTextField","AXTextArea","AXSearchField","AXComboBox","AXCheckBox",
         "AXRadioButton","AXPopUpButton","AXSlider","AXLink","AXMenuItem","AXMenuBarItem",
         "AXTab","AXToolbarButton","AXStaticText","AXImage","AXCell"].contains(role)
    }

    // MARK: - AX Helpers
    static func axStr(_ el: AXUIElement, _ a: String) -> String? {
        var v: CFTypeRef?
        guard AXUIElementCopyAttributeValue(el, a as CFString, &v) == .success else { return nil }
        return v as? String
    }
    static func axBool(_ el: AXUIElement, _ a: String) -> Bool? {
        var v: CFTypeRef?
        guard AXUIElementCopyAttributeValue(el, a as CFString, &v) == .success else { return nil }
        return (v as? NSNumber)?.boolValue
    }
    static func axVal(_ el: AXUIElement, _ a: String) -> AXValue? {
        var v: CFTypeRef?
        guard AXUIElementCopyAttributeValue(el, a as CFString, &v) == .success else { return nil }
        return v as? AXValue
    }
}
