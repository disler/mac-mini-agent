import ArgumentParser
import Foundation

private func jsonEscape(_ s: String) -> String {
    guard let data = try? JSONSerialization.data(withJSONObject: s),
          let encoded = String(data: data, encoding: .utf8) else {
        return s.replacingOccurrences(of: "\\", with: "\\\\")
                .replacingOccurrences(of: "\"", with: "\\\"")
                .replacingOccurrences(of: "\n", with: "\\n")
                .replacingOccurrences(of: "\r", with: "\\r")
                .replacingOccurrences(of: "\t", with: "\\t")
    }
    return String(encoded.dropFirst().dropLast())
}

struct Type: ParsableCommand {
    static let configuration = CommandConfiguration(
        commandName: "type",
        abstract: "Type text into the focused element, or click a target first."
    )

    @Argument(help: "Text to type")
    var text: String

    @Option(name: .long, help: "Target element ID or label — clicks to focus first")
    var into: String?

    @Option(name: .long, help: "Snapshot ID")
    var snapshot: String?

    @Option(name: .long, help: "Screen index — translates local screenshot coords to global")
    var screen: Int?

    @Flag(name: .long, help: "Clear field first (Cmd+A, Delete)")
    var clear = false

    @Flag(name: .long, help: "Output JSON")
    var json = false

    func run() throws {
        if let into = into {
            let el = try ElementStore.resolve(into, snap: snapshot)
            MouseControl.click(x: Double(el.centerX), y: Double(el.centerY))
            usleep(100_000) // 100ms for focus
        }
        if clear {
            Keyboard.hotkey("cmd+a")
            usleep(50_000)
            Keyboard.hotkey("delete")
            usleep(50_000)
        }
        Keyboard.typeText(text)

        if json {
            let escaped = jsonEscape(text)
            print("{\"action\":\"type\",\"text\":\"\(escaped)\",\"ok\":true}")
        } else {
            print("Typed \"\(text)\"\(into != nil ? " into \(into!)" : "")")
        }
    }
}
