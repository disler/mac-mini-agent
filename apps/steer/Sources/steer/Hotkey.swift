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

struct Hotkey: ParsableCommand {
    static let configuration = CommandConfiguration(
        abstract: "Press a key combination: cmd+s, ctrl+c, return, escape, etc."
    )

    @Argument(help: "Key combo: cmd+s, cmd+shift+n, return, escape, tab, etc.")
    var combo: String

    @Flag(name: .long, help: "Output JSON")
    var json = false

    func run() throws {
        Keyboard.hotkey(combo)

        if json {
            let escaped = jsonEscape(combo)
            print("{\"action\":\"hotkey\",\"combo\":\"\(escaped)\",\"ok\":true}")
        } else {
            print("Pressed \(combo)")
        }
    }
}
