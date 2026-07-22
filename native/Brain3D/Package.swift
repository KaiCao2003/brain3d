// swift-tools-version: 6.0

import PackageDescription

let package = Package(
    name: "Brain3D",
    platforms: [
        .macOS(.v14)
    ],
    products: [
        .executable(name: "Brain3D", targets: ["Brain3DApp"]),
        .library(name: "Brain3DCore", targets: ["Brain3DCore"]),
    ],
    targets: [
        .target(name: "Brain3DCore"),
        .executableTarget(
            name: "Brain3DApp",
            dependencies: ["Brain3DCore"]
        ),
        .testTarget(
            name: "Brain3DCoreTests",
            dependencies: ["Brain3DCore"]
        ),
    ]
)
