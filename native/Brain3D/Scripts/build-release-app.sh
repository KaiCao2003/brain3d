#!/bin/bash

set -euo pipefail

script_directory="$(cd "$(dirname "$0")" && pwd)"
package_root="$(cd "$script_directory/.." && pwd)"
repository_root="$(cd "$package_root/../.." && pwd)"
output_root="${OUTPUT_DIR:-$package_root/dist}"
app_bundle="$output_root/Brain3D.app"
release_archive=""
bridge_entrypoint="$package_root/Bridge/brain3d_bridge.py"
codesign_identity="${CODE_SIGN_IDENTITY:-}"
atlas_pdf_source="${BRAIN3D_MBSC_PDF:-}"
local_lab_build="${BRAIN3D_LOCAL_LAB_BUILD:-0}"
atlas_expected_sha256="27b34540d9418bd6e4954f67dc99d342502216cb8d36fcc2e1ddde30671aeef8"
atlas_relative_path="Contents/Resources/SurgeryAtlas/MBSC_Figs_with_Layers.pdf"
release_python_version="3.12.12"
maximum_macos_version="14.0"
gui_app_pid=""
gui_bridge_pid=""

fail() {
    echo "release build failed: $*" >&2
    exit 1
}

case "$local_lab_build" in
    0)
        release_archive="$output_root/Brain3D-macOS-arm64.zip"
        [[ -z "$atlas_pdf_source" ]] \
            || fail "public release builds cannot include BRAIN3D_MBSC_PDF; set BRAIN3D_LOCAL_LAB_BUILD=1 for a local-only artifact"
        ;;
    1)
        [[ -n "$atlas_pdf_source" ]] \
            || fail "BRAIN3D_LOCAL_LAB_BUILD=1 requires BRAIN3D_MBSC_PDF"
        release_archive="$output_root/Brain3D-macOS-arm64-local-atlas.zip"
        ;;
    *)
        fail "BRAIN3D_LOCAL_LAB_BUILD must be 0 or 1"
        ;;
esac

[[ "$(uname -m)" == "arm64" ]] || fail "run this builder natively on Apple Silicon"
command -v uv >/dev/null || fail "uv is required"
command -v swift >/dev/null || fail "Swift is required"
command -v codesign >/dev/null || fail "codesign is required"
command -v lipo >/dev/null || fail "lipo is required"
command -v install_name_tool >/dev/null || fail "install_name_tool is required"
command -v sandbox-exec >/dev/null || fail "sandbox-exec is required for isolated verification"
command -v unzip >/dev/null || fail "unzip is required"

if [[ -z "$output_root" || "$output_root" == "/" || "$app_bundle" == "/Brain3D.app" ]]; then
    fail "refusing to use a broad or empty app output path"
fi

temporary_parent="${TMPDIR:-/tmp}"
temporary_parent="${temporary_parent%/}"
work_root="$(mktemp -d "$temporary_parent/brain3d-release.XXXXXX")"
cleanup() {
    if [[ -n "${gui_app_pid:-}" ]]; then
        kill "$gui_app_pid" 2>/dev/null || true
    fi
    if [[ -n "${gui_bridge_pid:-}" ]]; then
        kill "$gui_bridge_pid" 2>/dev/null || true
    fi
    if [[ -n "${work_root:-}" && "$work_root" == "$temporary_parent"/brain3d-release.* ]]; then
        rm -rf "$work_root"
    fi
}
trap cleanup EXIT

release_environment="$work_root/release-environment"
echo "Creating a clean locked Python 3.12 release environment..."
uv python install --managed-python "$release_python_version"
UV_PROJECT_ENVIRONMENT="$release_environment" uv sync \
    --project "$repository_root" \
    --frozen \
    --no-dev \
    --group release \
    --no-editable \
    --managed-python \
    --python "$release_python_version"
release_python="$release_environment/bin/python"

python_architecture="$($release_python -c 'import platform; print(platform.machine())')"
python_version="$($release_python -c 'import platform; print(platform.python_version())')"
[[ "$python_architecture" == "arm64" ]] \
    || fail "release Python is $python_architecture, expected arm64"
[[ "$python_version" == "$release_python_version" ]] \
    || fail "release Python is $python_version, expected $release_python_version"

$release_python -c '
from importlib.metadata import PackageNotFoundError, distribution
for name in ("mypy", "pytest", "pytest-cov", "ruff"):
    try:
        distribution(name)
    except PackageNotFoundError:
        continue
    raise SystemExit(f"development dependency leaked into release environment: {name}")
'

pyinstaller_arguments=(
    --noconfirm
    --clean
    --onedir
    --console
    --name brain3d-bridge
    --target-arch arm64
    --distpath "$work_root/pyinstaller-dist"
    --workpath "$work_root/pyinstaller-work"
    --specpath "$work_root/pyinstaller-spec"
    --collect-data mouse_brain_planner
    --recursive-copy-metadata mouse-brain-planner
    --hidden-import brainglobe_atlasapi
    --hidden-import brainglobe_atlasapi.config
    --hidden-import brainglobe_atlasapi.core
    --exclude-module altgraph
    --exclude-module _tkinter
    --exclude-module macholib
    --exclude-module mypy
    --exclude-module pkg_resources
    --exclude-module pytest
    --exclude-module PyInstaller
    --exclude-module ruff
    --exclude-module setuptools
    --exclude-module tkinter
    --exclude-module PIL.ImageTk
    --exclude-module wheel
)

if [[ -z "$codesign_identity" ]]; then
    codesign_identity="$(
        security find-identity -v -p codesigning 2>/dev/null \
            | awk '/Developer ID Application:/ {print $2; exit}'
    )"
fi
if [[ -n "$codesign_identity" ]]; then
    pyinstaller_arguments+=(--codesign-identity "$codesign_identity")
else
    codesign_identity="-"
fi

echo "Freezing the production bridge with PyInstaller..."
env -u PYTHONPATH -u VIRTUAL_ENV \
    "$release_python" -m PyInstaller \
    "${pyinstaller_arguments[@]}" \
    "$bridge_entrypoint"

bridge_directory="$work_root/pyinstaller-dist/brain3d-bridge"
bridge_executable="$bridge_directory/brain3d-bridge"
[[ -x "$bridge_executable" ]] || fail "PyInstaller did not emit the bridge executable"
archive_listing="$(
    "$release_environment/bin/pyi-archive_viewer" --recursive --brief "$bridge_executable"
)"
if grep -Eq \
    '^[[:space:]]+(_tkinter|altgraph|macholib|mypy|pkg_resources|pytest|PyInstaller|ruff|setuptools|tkinter|wheel)(\.|$)' \
    <<<"$archive_listing"
then
    fail "build/development Python modules leaked into the frozen bridge"
fi
for forbidden_directory in \
    altgraph macholib mypy pkg_resources pytest PyInstaller ruff setuptools wheel
do
    [[ ! -e "$bridge_directory/_internal/$forbidden_directory" ]] \
        || fail "build/development package leaked into bridge: $forbidden_directory"
done
if find "$bridge_directory/_internal" -maxdepth 1 \
    \( -name '_tcl_data' -o -name '_tk_data' -o -name '_tkinter*' \
       -o -name 'libtcl*' -o -name 'libtk*' -o -name 'tcl9' \) \
    -print -quit | grep -q .
then
    fail "unused Tcl/Tk runtime leaked into the frozen bridge"
fi

echo "Building the arm64 Swift application..."
swift_output="$work_root/swift-app"
BRAIN3D_MBSC_PDF="$atlas_pdf_source" \
    ARCHITECTURE=arm64 CONFIGURATION=release OUTPUT_DIR="$swift_output" \
    "$script_directory/build-app.sh" >/dev/null
staged_app="$swift_output/Brain3D.app"
swift_executable="$staged_app/Contents/MacOS/Brain3D"
staged_atlas="$staged_app/$atlas_relative_path"
atlas_bundle_sha256=""
if [[ -n "$atlas_pdf_source" ]]; then
    [[ -f "$staged_atlas" ]] || fail "Swift app is missing its requested included atlas"
    atlas_bundle_sha256="$(shasum -a 256 "$staged_atlas" | awk '{print $1}')"
    [[ "$atlas_bundle_sha256" == "$atlas_expected_sha256" ]] \
        || fail "included atlas identity changed in the staged app"
else
    [[ ! -e "$staged_atlas" ]] || fail "an unrequested atlas leaked into the staged app"
fi
while IFS= read -r host_rpath; do
    [[ -n "$host_rpath" ]] || continue
    case "$host_rpath" in
        /usr/lib/swift|@loader_path*|@executable_path*|@rpath*) continue ;;
    esac
    install_name_tool -delete_rpath "$host_rpath" "$swift_executable"
done < <(
    otool -l "$swift_executable" \
        | awk '$1 == "cmd" && $2 == "LC_RPATH" { active=1; next }
               active && $1 == "path" { print $2; active=0 }'
)
required_swift_libraries="$(
    xcrun swift-stdlib-tool --print --platform macosx --scan-executable "$swift_executable"
)"
[[ -z "$required_swift_libraries" ]] \
    || fail "Swift runtime libraries must be embedded before release: $required_swift_libraries"

mkdir -p "$staged_app/Contents/Resources/Bridge"
/usr/bin/ditto "$bridge_directory" "$staged_app/Contents/Resources/Bridge"

release_resources="$staged_app/Contents/Resources/Release"
mkdir -p "$release_resources"
install -m 644 "$repository_root/LICENSE" "$release_resources/Brain3D-LICENSE.txt"
install -m 644 "$repository_root/THIRD_PARTY.md" "$release_resources/THIRD_PARTY.md"
python_license="$(
    "$release_python" -c \
        'import pathlib, sys; print(pathlib.Path(sys.base_prefix) / "lib/python3.12/LICENSE.txt")'
)"
[[ -f "$python_license" ]] || fail "managed CPython license text is missing"
install -m 644 "$python_license" "$release_resources/CPython-LICENSE.txt"
"$release_python" "$script_directory/collect-release-licenses.py" \
    --output "$release_resources"
uv export \
    --project "$repository_root" \
    --frozen \
    --no-dev \
    --format cyclonedx1.5 \
    --output-file "$release_resources/production-sbom.cdx.json" >/dev/null
application_version="$(
    /usr/libexec/PlistBuddy -c 'Print :CFBundleShortVersionString' \
        "$staged_app/Contents/Info.plist"
)"

/usr/libexec/PlistBuddy -c 'Delete :LSArchitecturePriority' \
    "$staged_app/Contents/Info.plist" 2>/dev/null || true
/usr/libexec/PlistBuddy -c 'Add :LSArchitecturePriority array' \
    "$staged_app/Contents/Info.plist"
/usr/libexec/PlistBuddy -c 'Add :LSArchitecturePriority:0 string arm64' \
    "$staged_app/Contents/Info.plist"

echo "Verifying every bundled Mach-O is arm64-only..."
macho_inventory="$(
    "$release_python" "$script_directory/verify-apple-silicon-bundle.py" \
        --bundle "$staged_app" \
        --maximum-macos "$maximum_macos_version" \
        --forbidden-prefix "$repository_root"
)"
macho_count="$(
    "$release_python" -c 'import json, sys; print(json.load(sys.stdin)["machOCount"])' \
        <<<"$macho_inventory"
)"
maximum_bundled_deployment_target="$(
    "$release_python" -c \
        'import json, sys; print(json.load(sys.stdin)["maximumDeploymentTarget"])' \
        <<<"$macho_inventory"
)"
release_metadata_arguments=(
    --output "$release_resources/release-build.json"
    --repository "$repository_root"
    --application-version "$application_version"
    --declared-minimum-macos "$maximum_macos_version"
    --maximum-bundled-deployment-target "$maximum_bundled_deployment_target"
)
if [[ -n "$atlas_bundle_sha256" ]]; then
    release_metadata_arguments+=(
        --surgery-atlas-sha256 "$atlas_bundle_sha256"
    )
fi
"$release_python" "$script_directory/write-release-metadata.py" \
    "${release_metadata_arguments[@]}"

echo "Signing the complete application..."
codesign_arguments=(--force --sign "$codesign_identity")
if [[ "$codesign_identity" != "-" ]]; then
    codesign_arguments+=(--options runtime --timestamp)
fi
codesign "${codesign_arguments[@]}" "$staged_app"
codesign --verify --deep --strict "$staged_app"

mkdir -p "$output_root"
rm -rf "$app_bundle"
/usr/bin/ditto "$staged_app" "$app_bundle"
codesign --verify --deep --strict "$app_bundle"

echo "Creating a release archive with exactly one top-level Brain3D.app..."
rm -f "$release_archive"
/usr/bin/ditto -c -k --keepParent "$app_bundle" "$release_archive"
archive_entries="$(unzip -Z1 "$release_archive")"
[[ -n "$archive_entries" ]] || fail "release archive is empty"
if grep -Ev '^Brain3D\.app(/|$)' <<<"$archive_entries" | grep -q .; then
    fail "release archive contains a top-level entry other than Brain3D.app"
fi

echo "Testing the unzipped app with source checkout reads denied..."
verification_root="$work_root/isolated-verification"
verification_app="$verification_root/unzipped/Brain3D.app"
mkdir -p "$verification_root/unzipped" "$verification_root/home" "$verification_root/cwd"
/usr/bin/ditto -x -k "$release_archive" "$verification_root/unzipped"
top_level_entries="$(find "$verification_root/unzipped" -mindepth 1 -maxdepth 1 -print)"
[[ "$top_level_entries" == "$verification_app" ]] \
    || fail "unzipped release does not contain exactly one top-level Brain3D.app"
verification_bridge="$verification_app/Contents/Resources/Bridge/brain3d-bridge"
[[ -x "$verification_bridge" ]] || fail "unzipped app is missing its bundled bridge"
verification_atlas="$verification_app/$atlas_relative_path"
if [[ -n "$atlas_bundle_sha256" ]]; then
    [[ -f "$verification_atlas" ]] || fail "unzipped app is missing its included atlas"
    [[ "$(shasum -a 256 "$verification_atlas" | awk '{print $1}')" == \
        "$atlas_bundle_sha256" ]] \
        || fail "included atlas identity changed after archive extraction"
else
    [[ ! -e "$verification_atlas" ]] \
        || fail "an unrequested atlas leaked into the release archive"
fi
[[ "$repository_root" != *'"'* ]] || fail "repository path cannot be sandbox-escaped"
sandbox_profile="(version 1) (allow default) (deny file-read* (subpath \"$repository_root\"))"
smoke_output="$(
    cd "$verification_root/cwd"
    printf '%s\n' \
        '{"id":"release-smoke","method":"hello","params":{"protocolVersion":1,"client":"release-builder"}}' \
        '{"id":"release-shutdown","method":"shutdown","params":{"protocolVersion":1}}' \
        | /usr/bin/sandbox-exec -p "$sandbox_profile" /usr/bin/env -i \
            HOME="$verification_root/home" \
            PATH="/usr/bin:/bin" \
            TMPDIR="$verification_root" \
            "$verification_bridge"
)"
grep -Fq '"id":"release-smoke"' <<<"$smoke_output" \
    || fail "bundled bridge did not preserve the hello request id"
grep -Fq '"service":"mouse-brain-planner"' <<<"$smoke_output" \
    || fail "bundled bridge hello did not identify the expected service"
grep -Fq '"protocolVersion":1' <<<"$smoke_output" \
    || fail "bundled bridge hello did not negotiate protocol v1"
codesign --verify --deep --strict "$verification_app"
unzipped_macho_inventory="$(
    "$release_python" "$script_directory/verify-apple-silicon-bundle.py" \
        --bundle "$verification_app" \
        --maximum-macos "$maximum_macos_version" \
        --forbidden-prefix "$repository_root"
)"
unzipped_macho_count="$(
    "$release_python" -c 'import json, sys; print(json.load(sys.stdin)["machOCount"])' \
        <<<"$unzipped_macho_inventory"
)"
[[ "$unzipped_macho_inventory" == "$macho_inventory" ]] \
    || fail "unzipped app Mach-O inventory changed"

echo "Launching the unzipped Swift app and observing its bundled bridge child..."
gui_stdout="$verification_root/gui-stdout.log"
gui_stderr="$verification_root/gui-stderr.log"
(
    cd "$verification_root/cwd"
    exec /usr/bin/sandbox-exec -p "$sandbox_profile" /usr/bin/env -i \
        HOME="$verification_root/home" \
        PATH="/usr/bin:/bin" \
        TMPDIR="$verification_root" \
        "$verification_app/Contents/MacOS/Brain3D" \
        >"$gui_stdout" 2>"$gui_stderr"
) &
gui_app_pid=$!
for _ in $(seq 1 100); do
    if ! kill -0 "$gui_app_pid" 2>/dev/null; then
        break
    fi
    gui_bridge_pid="$(
        ps -axo ppid=,pid=,command= \
            | awk -v parent="$gui_app_pid" \
                '$1 == parent && /Contents\/Resources\/Bridge\/brain3d-bridge$/ && !found {print $2; found=1}'
    )"
    [[ -n "$gui_bridge_pid" ]] && break
    sleep 0.1
done
if ! kill -0 "$gui_app_pid" 2>/dev/null; then
    sed -n '1,120p' "$gui_stderr" >&2
    fail "unzipped Swift app exited during launch verification"
fi
[[ -n "$gui_bridge_pid" ]] || fail "Swift app did not launch its bundled bridge child"
observed_bridge_command="$(ps -p "$gui_bridge_pid" -o command=)"
[[ "$observed_bridge_command" == "$verification_bridge" ]] \
    || fail "Swift app launched unexpected bridge: $observed_bridge_command"
sleep 2
kill -0 "$gui_app_pid" || fail "Swift app crashed during launch verification"
kill -0 "$gui_bridge_pid" || fail "bundled bridge exited during launch verification"
kill "$gui_app_pid"
wait "$gui_app_pid" 2>/dev/null || true
gui_app_pid=""
for _ in $(seq 1 50); do
    kill -0 "$gui_bridge_pid" 2>/dev/null || break
    sleep 0.1
done
if kill -0 "$gui_bridge_pid" 2>/dev/null; then
    kill "$gui_bridge_pid"
    fail "bundled bridge did not stop when the Swift app stopped"
fi
gui_bridge_pid=""

bundle_kib="$(du -sk "$app_bundle" | awk '{print $1}')"
bundle_sha256="$(shasum -a 256 "$app_bundle/Contents/MacOS/Brain3D" | awk '{print $1}')"
archive_sha256="$(shasum -a 256 "$release_archive" | awk '{print $1}')"
echo "Release app: $app_bundle"
if [[ "$local_lab_build" == "1" ]]; then
    echo "Local lab archive (not for public redistribution): $release_archive"
else
    echo "GitHub release archive: $release_archive"
fi
echo "Bundle size: $bundle_kib KiB"
echo "Mach-O inventory: $macho_inventory"
echo "Bundled bridge launched by Swift: Contents/Resources/Bridge/brain3d-bridge"
if [[ -n "$atlas_bundle_sha256" ]]; then
    echo "Included local atlas SHA-256: $atlas_bundle_sha256"
else
    echo "Included local atlas: none"
fi
echo "Swift executable SHA-256: $bundle_sha256"
echo "Release archive SHA-256: $archive_sha256"
echo "Code-sign identity: $codesign_identity"
