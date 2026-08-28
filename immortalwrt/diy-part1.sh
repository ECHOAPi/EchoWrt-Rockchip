#!/usr/bin/env bash

set -euo pipefail

config_root="${GITHUB_WORKSPACE:-$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)}"
lock_file="$config_root/immortalwrt/community-sources.lock"
patch_root="$config_root/immortalwrt/patches"
prune_dir="$(mktemp -d "$PWD/.pruned-sources.XXXXXX")"

cleanup_pruned() {
    [[ ! -e "$prune_dir" ]] || find "$prune_dir" -depth -delete
}

prune_path() {
    local path="$1"
    local quarantine_name

    [[ -e "$path" || -L "$path" ]] || return 0
    quarantine_name="${path//\//__}"
    mv -- "$path" "$prune_dir/$quarantine_name"
    [[ ! -e "$path" && ! -L "$path" ]]
}

trap cleanup_pruned EXIT

clone_locked() {
    local destination="$1"
    local url="$2"
    local commit="$3"
    local archive_spec="$4"
    local archive_path
    local checkout_dir
    local -a archive_paths=()

    mkdir -p "$(dirname "$destination")"
    mkdir -p "$destination"
    checkout_dir="$(mktemp -d "$PWD/.source-checkout.XXXXXX")"

    if ! (
        set -euo pipefail
        git init -q "$checkout_dir"
        git -C "$checkout_dir" remote add origin "$url"
        git -C "$checkout_dir" fetch -q --depth=1 --no-tags origin "$commit"
        [[ "$(git -C "$checkout_dir" rev-parse FETCH_HEAD)" == "$commit" ]]

        if [[ "$archive_spec" == "." ]]; then
            git -C "$checkout_dir" archive --format=tar FETCH_HEAD |
                tar -xf - -C "$destination"
        else
            IFS=',' read -r -a archive_paths <<< "$archive_spec"
            ((${#archive_paths[@]} > 0))
            for archive_path in "${archive_paths[@]}"; do
                [[ "$archive_path" =~ ^[A-Za-z0-9][A-Za-z0-9._/-]*$ ]]
                [[ "$archive_path" != *..* ]]
            done
            git -C "$checkout_dir" archive --format=tar FETCH_HEAD -- "${archive_paths[@]}" |
                tar -xf - -C "$destination"
        fi
    ); then
        find "$checkout_dir" -depth -delete
        return 1
    fi

    find "$checkout_dir" -depth -delete
    [[ ! -e "$destination/.git" ]]
}

apply_compatibility_patches() {
    local mhi_root="package/community/5g-modem/quectel_MHI"
    local mhi_patch="$patch_root/quectel-mhi-linux-6.12.patch"

    test -f "$mhi_patch"
    test -f "$mhi_root/src/core/mhi_init.c"
    patch --batch --forward --fuzz=0 -d "$mhi_root" -p1 < "$mhi_patch"
    grep -Fq $'.llseek =\tnoop_llseek' "$mhi_root/src/core/mhi_init.c"
    grep -Fq 'const struct device_driver *drv' "$mhi_root/src/core/mhi_init.c"
}

test -f "$lock_file"
test -f include/toplevel.mk
test -x scripts/feeds

prune_path feeds/packages/net/mosdns
prune_path package/community
prune_path package/mosdns

while IFS='|' read -r destination url commit archive_spec; do
    [[ -n "$destination" ]] || continue
    [[ "$destination" != \#* ]] || continue
    [[ "$destination" == package/* || "$destination" == feeds/* ]]
    [[ "$destination" != *..* ]]
    clone_locked "$destination" "$url" "$commit" "$archive_spec"
done < "$lock_file"

apply_compatibility_patches

test ! -e feeds/packages/net/mosdns
test -f package/community/helloworld/luci-app-ssr-plus/Makefile
test -f package/community/helloworld/mihomo/Makefile
test -f package/community/helloworld/shadowsocksr-libev/Makefile
test ! -e package/community/helloworld/hysteria
test -f package/community/nikki/luci-app-nikki/Makefile
test -f package/community/nikki/nikki/Makefile
test ! -e package/community/nikki/mihomo-alpha
test ! -e package/community/nikki/mihomo-meta
test -f package/community/5g-modem/luci-app-hypermodem/Makefile
test -f package/community/5g-modem/quectel_MHI/Makefile
test ! -e package/community/5g-modem/luci-app-modem
test ! -e package/community/5g-modem/quectel_cm_5G
test ! -e package/community/5g-modem/rooter
test ! -e package/community/5g-modem/sendat
test ! -e package/community/5g-modem/sms-tool

cleanup_pruned
trap - EXIT
