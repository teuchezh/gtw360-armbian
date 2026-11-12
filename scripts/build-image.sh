#!/usr/bin/env bash
set -euo pipefail
project_dir=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
"$project_dir/scripts/prepare-armbian.sh"
cp -a "$project_dir/armbian-userpatches/." "$project_dir/sources/armbian/userpatches/"
cd "$project_dir/sources/armbian"
./compile.sh build BOARD=gtw360 BRANCH=current RELEASE=trixie \
    BUILD_MINIMAL=yes BUILD_DESKTOP=no KERNEL_CONFIGURE=no ALLOW_ROOT=yes \
    GTW360_EXPORT_ROOTFS=yes GTW360_ROOTFS_ARCHIVE="$project_dir/artifacts/gtw360-armbian-rootfs.tar.zst" "$@"
cd "$project_dir"
python3 scripts/make-armbian-image.py \
    --rootfs-archive artifacts/gtw360-armbian-rootfs.tar.zst \
    --usb-only --generic --output-dir artifacts
