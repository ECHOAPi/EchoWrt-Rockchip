#!/usr/bin/env bash

set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$repo_root"

find immortalwrt scripts -type f -name '*.sh' -print0 |
    while IFS= read -r -d '' script; do
        bash -n "$script"
    done

find .github -type f \( -name '*.yml' -o -name '*.yaml' \) -print |
    while IFS= read -r workflow; do
        python3 -c 'import pathlib, sys, yaml; yaml.safe_load(pathlib.Path(sys.argv[1]).read_text())' "$workflow"
    done

floating_refs='uses:[[:space:]]+[^[:space:]]+@(main|master|v[0-9]+)([[:space:]]|$)'
if grep -REn "$floating_refs" .github/workflows; then
    echo "GitHub Actions must be pinned to a full commit SHA." >&2
    exit 1
fi

if grep -REn 'DHDAXCW/(immortalwrt|lede-rockchip)' .github/workflows; then
    echo "The active workflow must use the official ImmortalWrt source." >&2
    exit 1
fi

grep -Fq "192.168.8.1" immortalwrt/diy-part2.sh
grep -Fq "ImmortalWrt/EchoWrt" immortalwrt/diy-part2.sh
grep -Fq 'root" && $2 == ""' immortalwrt/diy-part2.sh
if grep -REn '192\.168\.11\.1' README.md docs immortalwrt scripts .github; then
    echo "Legacy management address must not remain in active repository files." >&2
    exit 1
fi

while IFS='|' read -r destination url commit; do
    [[ -n "$destination" ]] || continue
    [[ "$destination" != \#* ]] || continue
    [[ "$destination" == package/* || "$destination" == feeds/* ]]
    [[ "$destination" != *..* ]]
    [[ "$url" == https://github.com/*.git ]] || {
        echo "Invalid community source URL: $url" >&2
        exit 1
    }
    [[ "$commit" =~ ^[0-9a-f]{40}$ ]] || {
        echo "Community source is not pinned: $destination" >&2
        exit 1
    }
done < immortalwrt/community-sources.lock

duplicate_config_symbols="$({
    sed -n 's/^\(CONFIG_[^=]*\)=.*/\1/p' immortalwrt/rockchip/defconfig
    sed -n 's/^# \(CONFIG_[^ ]*\) is not set$/\1/p' immortalwrt/rockchip/defconfig
} | sort | uniq -d)"
if [[ -n "$duplicate_config_symbols" ]]; then
    echo "Conflicting or duplicate defconfig symbols:" >&2
    echo "$duplicate_config_symbols" >&2
    exit 1
fi

sed -n 's/^CONFIG_TARGET_DEVICE_rockchip_armv8_DEVICE_\(.*\)=y$/\1/p' \
    immortalwrt/rockchip/defconfig |
    while IFS= read -r device; do
        grep -Fq "$device" README.md || {
            echo "Device missing from README: $device" >&2
            exit 1
        }
    done

echo "Repository validation passed."
