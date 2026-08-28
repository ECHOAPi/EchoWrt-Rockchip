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
grep -Fq 'git -C "$checkout_dir" archive' immortalwrt/diy-part1.sh
grep -Fq 'done < "$lock_file"' scripts/write-source-manifest.sh
if grep -REn '192\.168\.11\.1' README.md docs immortalwrt scripts .github; then
    echo "Legacy management address must not remain in active repository files." >&2
    exit 1
fi

legacy_paths=(
    configs
    data/RKDevTool_v3.37_for_window.7z
    data/bg1.jpg
    data/emmc.md
    immortalwrt/system-Information.sh
    scripts/.zshrc
    scripts/create-acl.sh
    scripts/hook-feeds.sh
    scripts/init-settings.sh
    scripts/lede.sh
    scripts/preset-clash-core.sh
    scripts/preset-terminal-tools.sh
    scripts/remove-upx.sh
    upstream-source.md
)
for legacy_path in "${legacy_paths[@]}"; do
    [[ -z "$(git ls-files -- "$legacy_path")" ]] || {
        echo "Inactive legacy file must not return: $legacy_path" >&2
        exit 1
    }
done

declare -A lock_destinations=()
while IFS='|' read -r destination url commit archive_spec extra; do
    [[ -n "$destination" ]] || continue
    [[ "$destination" != \#* ]] || continue
    [[ -z "$extra" ]] || {
        echo "Too many fields in community source: $destination" >&2
        exit 1
    }
    [[ "$destination" == package/* || "$destination" == feeds/* ]]
    [[ "$destination" != *..* ]]
    [[ -z "${lock_destinations[$destination]:-}" ]] || {
        echo "Duplicate community destination: $destination" >&2
        exit 1
    }
    lock_destinations[$destination]=1
    [[ "$url" == https://github.com/*.git ]] || {
        echo "Invalid community source URL: $url" >&2
        exit 1
    }
    [[ "$commit" =~ ^[0-9a-f]{40}$ ]] || {
        echo "Community source is not pinned: $destination" >&2
        exit 1
    }
    [[ -n "$archive_spec" ]] || {
        echo "Community source has no archive scope: $destination" >&2
        exit 1
    }
    if [[ "$archive_spec" != "." ]]; then
        declare -A archive_paths_seen=()
        IFS=',' read -r -a archive_paths <<< "$archive_spec"
        ((${#archive_paths[@]} > 0))
        for archive_path in "${archive_paths[@]}"; do
            [[ "$archive_path" =~ ^[A-Za-z0-9][A-Za-z0-9._/-]*$ ]]
            [[ "$archive_path" != *..* ]]
            [[ -z "${archive_paths_seen[$archive_path]:-}" ]] || {
                echo "Duplicate archive path for $destination: $archive_path" >&2
                exit 1
            }
            archive_paths_seen[$archive_path]=1
        done
        unset archive_paths_seen
    fi
done < immortalwrt/community-sources.lock

grep -Fq 'luci-app-hypermodem,quectel_MHI' immortalwrt/community-sources.lock
if grep -Eq '(^|,)(luci-app-modem|quectel_cm_5G|rooter|sendat|sms-tool)(,|$)' immortalwrt/community-sources.lock; then
    echo "Conflicting legacy modem packages must not be imported." >&2
    exit 1
fi

obsolete_config_symbols=(
    CONFIG_LIBCURL_NGHTTP2
    CONFIG_PACKAGE_boost-system
    CONFIG_PACKAGE_cgroupfs-mount
    CONFIG_PACKAGE_kmod-asn1-encoder
    CONFIG_PACKAGE_luci-app-passwall2_INCLUDE_Shadowsocks_Libev_Client
    CONFIG_PACKAGE_luci-app-passwall2_INCLUDE_SingBox
    CONFIG_PACKAGE_luci-app-passwall_INCLUDE_tuic_client
    CONFIG_PACKAGE_luci-app-ssr-plus_INCLUDE_Hysteria
    CONFIG_PACKAGE_luci-app-ssr-plus_INCLUDE_IPT2Socks
    CONFIG_PACKAGE_luci-app-ssr-plus_INCLUDE_Trojan
    CONFIG_PACKAGE_luci-i18n-adguardhome-zh-cn
    CONFIG_PACKAGE_shadowsocks-libev-config
    CONFIG_PACKAGE_shadowsocks-libev-ss-local
    CONFIG_PACKAGE_shadowsocks-libev-ss-redir
    CONFIG_PACKAGE_shadowsocks-libev-ss-server
    CONFIG_SING_BOX_BUILD_ACME
    CONFIG_SING_BOX_BUILD_CLASH_API
    CONFIG_SING_BOX_BUILD_ECH
    CONFIG_SING_BOX_BUILD_GVISOR
    CONFIG_SING_BOX_BUILD_QUIC
    CONFIG_SING_BOX_BUILD_REALITY_SERVER
    CONFIG_SING_BOX_BUILD_UTLS
    CONFIG_SING_BOX_BUILD_WIREGUARD
    CONFIG_ZRAM_DEF_COMP_LZORLE
)
for obsolete_symbol in "${obsolete_config_symbols[@]}"; do
    if grep -Eq "^(${obsolete_symbol}=|# ${obsolete_symbol} is not set$)" immortalwrt/rockchip/defconfig; then
        echo "Obsolete 25.12 config symbol must not return: $obsolete_symbol" >&2
        exit 1
    fi
done

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
