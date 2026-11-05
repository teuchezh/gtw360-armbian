#!/usr/bin/env bash
set -euo pipefail
project_dir=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
revision=18e87d5385f9191419e6afa646080b68fbe7a1d5
source_dir="$project_dir/sources/armbian"
if [[ -d "$source_dir/.git" ]]; then
    [[ "$(git -C "$source_dir" rev-parse HEAD)" == "$revision" ]] || {
        echo "Existing Armbian checkout differs from the pinned revision" >&2
        exit 1
    }
    exit 0
fi
mkdir -p "$project_dir/sources"
git init "$source_dir"
git -C "$source_dir" remote add origin https://github.com/armbian/build.git
git -C "$source_dir" fetch --filter=blob:none --depth=1 origin "$revision"
git -C "$source_dir" checkout --detach FETCH_HEAD
