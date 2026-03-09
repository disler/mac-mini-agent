import ArgumentParser
import Foundation

/// Escape a string for embedding inside a JSON string literal.
/// Uses JSONSerialization to handle all control characters per the JSON spec.
private func jsonEscape(_ s: String) -> String {
    guard let data = try? JSONSerialization.data(withJSONObject: s),
          let encoded = String(data: data, encoding: .utf8) else {
        // Fallback: manual escaping of the most common characters
        return s.replacingOccurrences(of: "\\", with: "\\\\")
                .replacingOccurrences(of: "\"", with: "\\\"")
                .replacingOccurrences(of: "\n", with: "\\n")
                .replacingOccurrences(of: "\r", with: "\\r")
                .replacingOccurrences(of: "\t", with: "\\t")
    }
    // JSONSerialization wraps the value in quotes — strip them
    return String(encoded.dropFirst().dropLast())
}

struct Clipboard: ParsableCommand {
    static let configuration = CommandConfiguration(
        abstract: "Read or write the system clipboard."
    )

    @Argument(help: "Action: read | write")
    var action: String

    @Argument(help: "Text to write (for write action)")
    var text: String?

    @Option(name: .long, help: "Content type: text | image (default: text)")
    var type: String = "text"

    @Option(name: .long, help: "File path for image read/write")
    var file: String?

    @Flag(name: .long, help: "Output JSON")
    var json = false

    func run() throws {
        switch action.lowercased() {
        case "read":
            switch type.lowercased() {
            case "text":
                let content = ClipboardControl.readText()
                if json {
                    let escaped = jsonEscape(content ?? "")
                    print("{\"action\":\"read\",\"type\":\"text\",\"content\":\"\(escaped)\",\"ok\":true}")
                } else {
                    print(content ?? "(clipboard empty)")
                }
            case "image":
                let path = try ClipboardControl.readImage(saveTo: file)
                print(json ? "{\"action\":\"read\",\"type\":\"image\",\"file\":\"\(path)\",\"ok\":true}" : "Saved clipboard image to \(path)")
            default:
                throw ValidationError("Type must be: text, image")
            }
        case "write":
            switch type.lowercased() {
            case "text":
                guard let text = text else { throw ValidationError("Provide text to write") }
                ClipboardControl.writeText(text)
                if json {
                    let escaped = jsonEscape(text)
                    print("{\"action\":\"write\",\"type\":\"text\",\"content\":\"\(escaped)\",\"ok\":true}")
                } else {
                    print("Copied to clipboard: \"\(text.prefix(80))\(text.count > 80 ? "..." : "")\"")
                }
            case "image":
                guard let file = file else { throw ValidationError("Provide --file path for image write") }
                try ClipboardControl.writeImage(fromPath: file)
                print(json ? "{\"action\":\"write\",\"type\":\"image\",\"file\":\"\(file)\",\"ok\":true}" : "Copied image to clipboard from \(file)")
            default:
                throw ValidationError("Type must be: text, image")
            }
        default:
            throw ValidationError("Action must be: read, write")
        }
    }
}
