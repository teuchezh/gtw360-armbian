#!/usr/bin/env bash
set -euo pipefail
project_dir=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
"$project_dir/scripts/prepare-armbian.sh"
cp -a "$project_dir/armbian-userpatches/." "$project_dir/sources/armbian/userpatches/"
cd "$project_dir/sources/armbian"
exec ./compile.sh kernel BOARD=gtw360 BRANCH=current RELEASE=trixie \
    BUILD_MINIMAL=yes BUILD_DESKTOP=no KERNEL_CONFIGURE=no ALLOW_ROOT=yes "$@"
