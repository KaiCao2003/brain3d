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
        .library(name: "Brain3DScene", targets: ["Brain3DScene"]),
    ],
    targets: [
        .target(name: "Brain3DCore"),
        .target(
            name: "Brain3DScene",
            dependencies: ["Brain3DCore"]
        ),
        .executableTarget(
            name: "Brain3DApp",
            dependencies: ["Brain3DCore", "Brain3DScene"]
        ),
        .testTarget(
            name: "Brain3DCoreTests",
            dependencies: ["Brain3DCore"],
            resources: [.copy("Fixtures")]
        ),
        .testTarget(
            name: "Brain3DSceneTests",
            dependencies: ["Brain3DScene", "Brain3DCore"]
        ),
    ]
)
