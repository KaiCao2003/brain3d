#!/bin/bash

set -euo pipefail

script_directory="$(cd "$(dirname "$0")" && pwd)"
package_root="$(cd "$script_directory/.." && pwd)"
configuration="${CONFIGURATION:-release}"
architecture="${ARCHITECTURE:-}"
output_root="${OUTPUT_DIR:-$package_root/build}"
app_bundle="$output_root/Brain3D.app"

case "$configuration" in
    debug|release) ;;
    *)
        echo "CONFIGURATION must be debug or release" >&2
        exit 2
        ;;
esac

swift_arguments=(
    --package-path "$package_root"
    --configuration "$configuration"
)
if [[ -n "$architecture" ]]; then
    swift_arguments+=(--arch "$architecture")
fi

swift build "${swift_arguments[@]}" --product Brain3D
binary_directory="$(
    swift build "${swift_arguments[@]}" --show-bin-path
)"

if [[ -z "$output_root" || "$output_root" == "/" || "$app_bundle" == "/Brain3D.app" ]]; then
    echo "Refusing to use a broad or empty app output path" >&2
    exit 2
fi

mkdir -p "$output_root"
rm -rf "$app_bundle"
mkdir -p "$app_bundle/Contents/MacOS" "$app_bundle/Contents/Resources"
install -m 755 "$binary_directory/Brain3D" "$app_bundle/Contents/MacOS/Brain3D"
install -m 644 "$package_root/Resources/Info.plist" "$app_bundle/Contents/Info.plist"
plutil -lint "$app_bundle/Contents/Info.plist"
codesign --force --sign - "$app_bundle"

echo "$app_bundle"
