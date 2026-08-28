#!/usr/bin/env bash

set -euo pipefail

output="${1:-COMMUNITY_SOURCES.txt}"
roots=(
    feeds/luci
    feeds/packages
    feeds/routing
    feeds/telephony
    feeds/video
    package/community
    package/mosdns
)

tmp_file="$(mktemp "${output}.tmp.XXXXXX")"
trap 'rm -f "$tmp_file"' EXIT

for root in "${roots[@]}"; do
    [[ -d "$root/.git" ]] || continue
    remote="$(git -C "$root" remote get-url origin)"
    commit="$(git -C "$root" rev-parse HEAD)"
    printf '%s\t%s\t%s\n' "$root" "$commit" "$remote" >> "$tmp_file"
done

find package/community -mindepth 2 -maxdepth 2 -type d -name .git -print0 |
    while IFS= read -r -d '' git_dir; do
        root="${git_dir%/.git}"
        remote="$(git -C "$root" remote get-url origin)"
        commit="$(git -C "$root" rev-parse HEAD)"
        printf '%s\t%s\t%s\n' "$root" "$commit" "$remote" >> "$tmp_file"
    done

sort -u "$tmp_file" > "$output"
