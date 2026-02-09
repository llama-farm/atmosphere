// swift-tools-version: 5.9
import PackageDescription

let package = Package(
    name: "AtmosphereMac",
    platforms: [
        .macOS(.v13)
    ],
    products: [
        .executable(
            name: "AtmosphereMac",
            targets: ["AtmosphereMac"]
        )
    ],
    targets: [
        .executableTarget(
            name: "AtmosphereMac",
            path: "AtmosphereMac",
            resources: [
                .process("Atmosphere.entitlements"),
                .process("Info.plist")
            ]
        )
    ]
)
