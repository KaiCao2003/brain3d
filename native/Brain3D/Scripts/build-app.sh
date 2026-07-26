#!/bin/bash

set -euo pipefail

script_directory="$(cd "$(dirname "$0")" && pwd)"
package_root="$(cd "$script_directory/.." && pwd)"
configuration="${CONFIGURATION:-release}"
architecture="${ARCHITECTURE:-}"
output_root="${OUTPUT_DIR:-$package_root/build}"
app_bundle="$output_root/Brain3D.app"
atlas_pdf_source="${BRAIN3D_MBSC_PDF:-}"
atlas_expected_bytes="12461500"
atlas_expected_sha256="27b34540d9418bd6e4954f67dc99d342502216cb8d36fcc2e1ddde30671aeef8"

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

if [[ -n "$atlas_pdf_source" ]]; then
    [[ -f "$atlas_pdf_source" ]] || {
        echo "BRAIN3D_MBSC_PDF is not a regular file" >&2
        exit 2
    }
    atlas_source_bytes="$(stat -f '%z' "$atlas_pdf_source")"
    atlas_source_sha256="$(shasum -a 256 "$atlas_pdf_source" | awk '{print $1}')"
    [[ "$atlas_source_bytes" == "$atlas_expected_bytes" ]] || {
        echo "BRAIN3D_MBSC_PDF has an unexpected file size" >&2
        exit 2
    }
    [[ "$atlas_source_sha256" == "$atlas_expected_sha256" ]] || {
        echo "BRAIN3D_MBSC_PDF failed its SHA-256 identity check" >&2
        exit 2
    }

    atlas_resource_directory="$app_bundle/Contents/Resources/SurgeryAtlas"
    atlas_resource="$atlas_resource_directory/MBSC_Figs_with_Layers.pdf"
    mkdir -p "$atlas_resource_directory"
    install -m 644 "$atlas_pdf_source" "$atlas_resource"
    [[ "$(stat -f '%z' "$atlas_resource")" == "$atlas_expected_bytes" ]] || {
        echo "The included atlas changed size while being copied" >&2
        exit 2
    }
    [[ "$(shasum -a 256 "$atlas_resource" | awk '{print $1}')" == \
        "$atlas_expected_sha256" ]] || {
        echo "The included atlas changed identity while being copied" >&2
        exit 2
    }
fi

plutil -lint "$app_bundle/Contents/Info.plist"
codesign --force --sign - "$app_bundle"

echo "$app_bundle"
