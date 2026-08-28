#!/usr/bin/env bash

set -euo pipefail

config_root="${GITHUB_WORKSPACE:-$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)}"
lock_file="$config_root/immortalwrt/community-sources.lock"

clone_locked() {
    local destination="$1"
    local url="$2"
    local commit="$3"

    mkdir -p "$(dirname "$destination")"
    git init -q "$destination"
    git -C "$destination" remote add origin "$url"
    git -C "$destination" fetch -q --depth=1 --no-tags origin "$commit"
    git -C "$destination" -c advice.detachedHead=false checkout -q --detach FETCH_HEAD

    [[ "$(git -C "$destination" rev-parse HEAD)" == "$commit" ]]
}

test -f "$lock_file"
test -f include/toplevel.mk
test -x scripts/feeds

rm -rf feeds/packages/net/mosdns
rm -rf package/community package/mosdns

while IFS='|' read -r destination url commit; do
    [[ -n "$destination" ]] || continue
    [[ "$destination" != \#* ]] || continue
    [[ "$destination" == package/* || "$destination" == feeds/* ]]
    [[ "$destination" != *..* ]]
    clone_locked "$destination" "$url" "$commit"
done < "$lock_file"

official_helloworld_packages=(
    chinadns-ng dns2socks dns2tcp dnsproxy gn hysteria ipt2socks lua-neturl
    microsocks mosdns naiveproxy redsocks2 shadow-tls shadowsocks-rust
    simple-obfs tcping tuic-client v2ray-core v2ray-plugin v2raya xray-core
    xray-plugin
)
for package_name in "${official_helloworld_packages[@]}"; do
    rm -rf "package/community/helloworld/$package_name"
    test ! -e "package/community/helloworld/$package_name"
done

rm -rf package/community/5G-Modem-Support/rooter
rm -rf package/community/5G-Modem-Support/sendat
rm -rf package/community/5G-Modem-Support/sms-tool
test ! -e feeds/packages/net/mosdns
test ! -e package/community/5G-Modem-Support/rooter
test ! -e package/community/5G-Modem-Support/sendat
test ! -e package/community/5G-Modem-Support/sms-tool
