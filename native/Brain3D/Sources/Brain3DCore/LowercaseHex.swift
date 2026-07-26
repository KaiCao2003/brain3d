public enum LowercaseHex {
    private static let digits = Array("0123456789abcdef".utf8)

    public static func encode<Bytes: Sequence>(_ bytes: Bytes) -> String
    where Bytes.Element == UInt8 {
        var encoded: [UInt8] = []
        for byte in bytes {
            encoded.append(digits[Int(byte >> 4)])
            encoded.append(digits[Int(byte & 0x0F)])
        }
        return String(decoding: encoded, as: UTF8.self)
    }
}
