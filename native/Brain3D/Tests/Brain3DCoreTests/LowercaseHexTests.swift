import Brain3DCore
import CryptoKit
import Foundation
import Testing

@Suite("Native lowercase hexadecimal encoding")
struct LowercaseHexTests {
    @Test("Every nibble is encoded with a leading zero when required")
    func byteBoundaries() {
        let bytes: [UInt8] = [
            0x00, 0x01, 0x09, 0x0A, 0x0F, 0x10, 0x7F, 0x80, 0xFE, 0xFF,
        ]

        #expect(LowercaseHex.encode(bytes) == "0001090a0f107f80feff")
    }

    @Test("CryptoKit SHA-256 digests use the native byte encoder")
    func cryptoKitDigest() {
        let digest = SHA256.hash(data: Data("abc".utf8))

        #expect(
            LowercaseHex.encode(digest)
                == "ba7816bf8f01cfea414140de5dae2223"
                + "b00361a396177a9cb410ff61f20015ad"
        )
    }
}
