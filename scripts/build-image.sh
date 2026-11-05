#!/usr/bin/env bash
set -euo pipefail
project_dir=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
"$project_dir/scripts/prepare-armbian.sh"
cp -a "$project_dir/armbian-userpatches/." "$project_dir/sources/armbian/userpatches/"
: "${GTW360_ADDRESS:?Set GTW360_ADDRESS}"
: "${GTW360_GATEWAY:?Set GTW360_GATEWAY}"
: "${GTW360_DNS:?Set GTW360_DNS}"
: "${GTW360_MAC:?Set GTW360_MAC}"
cd "$project_dir/sources/armbian"
./compile.sh build BOARD=gtw360 BRANCH=current RELEASE=trixie \
    BUILD_MINIMAL=yes BUILD_DESKTOP=no KERNEL_CONFIGURE=no ALLOW_ROOT=yes \
    GTW360_EXPORT_ROOTFS=yes GTW360_ROOTFS_ARCHIVE="$project_dir/artifacts/gtw360-armbian-rootfs.tar.zst" "$@"
cd "$project_dir"
python3 scripts/make-armbian-image.py \
    --rootfs-archive artifacts/gtw360-armbian-rootfs.tar.zst \
    --vendor-prefix backups/emmc-first-4MiB.bin \
    --authorized-key backups/rescue-access.pub --output-dir artifacts \
    --ip-address "$GTW360_ADDRESS" --gateway "$GTW360_GATEWAY" \
    --dns "$GTW360_DNS" --mac-address "$GTW360_MAC"
