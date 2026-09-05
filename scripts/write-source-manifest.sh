#!/usr/bin/env bash

set -euo pipefail

output="${1:-COMMUNITY_SOURCES.txt}"
config_root="${GITHUB_WORKSPACE:-$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)}"
lock_file="$config_root/immortalwrt/community-sources.lock"
roots=(
    feeds/luci
    feeds/packages
    feeds/routing
    feeds/telephony
    feeds/video
)

tmp_file="$(mktemp "${output}.tmp.XXXXXX")"
trap 'rm -f "$tmp_file"' EXIT

for root in "${roots[@]}"; do
    [[ -d "$root/.git" ]] || continue
    remote="$(git -C "$root" remote get-url origin)"
    commit="$(git -C "$root" rev-parse HEAD)"
    printf '%s\t%s\t%s\t%s\n' "$root" "$commit" "$remote" all >> "$tmp_file"
done

test -f "$lock_file"
while IFS='|' read -r destination remote commit archive_spec; do
    [[ -n "$destination" ]] || continue
    [[ "$destination" != \#* ]] || continue
    [[ -d "$destination" ]]
    printf '%s\t%s\t%s\t%s\n' "$destination" "$commit" "$remote" "$archive_spec" >> "$tmp_file"
done < "$lock_file"

sort -u "$tmp_file" > "$output"
