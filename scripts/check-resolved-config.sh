#!/usr/bin/env bash

set -euo pipefail

config_root="${GITHUB_WORKSPACE:-$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)}"
requested_config="$config_root/immortalwrt/rockchip/defconfig"
resolved_config="${1:-.config}"
result_file="$(mktemp "${TMPDIR:-/tmp}/echowrt-config-check.XXXXXX")"
trap 'rm -f "$result_file"' EXIT

test -f "$requested_config"
test -f "$resolved_config"

awk '
    function read_value(line, symbol, value, separator) {
        if (line ~ /^CONFIG_[^=]+=/) {
            separator = index(line, "=")
            symbol = substr(line, 1, separator - 1)
            value = substr(line, separator + 1)
        } else if (line ~ /^# CONFIG_[^ ]+ is not set$/) {
            symbol = $2
            value = "n"
        } else {
            return
        }

        if (FNR == NR)
            requested[symbol] = value
        else
            resolved[symbol] = value
    }

    { read_value($0) }

    END {
        for (symbol in requested) {
            if (!(symbol in resolved))
                print symbol ": missing"
            else if (requested[symbol] != resolved[symbol])
                print symbol ": requested=" requested[symbol] ", resolved=" resolved[symbol]
        }
    }
' "$requested_config" "$resolved_config" | LC_ALL=C sort > "$result_file"

if [[ -s "$result_file" ]]; then
    echo "Resolved configuration does not match defconfig:" >&2
    cat "$result_file" >&2
    exit 1
fi

echo "Resolved configuration matches all requested symbols."
