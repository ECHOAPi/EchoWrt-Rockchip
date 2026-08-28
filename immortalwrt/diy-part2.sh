#!/usr/bin/env bash

set -euo pipefail

# Modify default IP
config_generate="package/base-files/files/bin/config_generate"
shadow_file="package/base-files/files/etc/shadow"
test -f "$config_generate"
test -f "$shadow_file"
grep -q "192.168.1.1" "$config_generate"
sed -i 's/192.168.1.1/192.168.8.1/g' "$config_generate"
sed -i 's/ImmortalWrt/EchoWrt/g' "$config_generate"

# Keep the upstream root account without a preset password so LuCI can guide
# the owner to set one on first login. Fail the build if upstream changes it.
awk -F: '$1 == "root" && $2 == "" { found = 1 } END { exit !found }' "$shadow_file"
