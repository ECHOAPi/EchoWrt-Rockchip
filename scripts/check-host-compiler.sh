#!/usr/bin/env bash

set -euo pipefail

command -v clang++ >/dev/null
command -v g++ >/dev/null

clang++ --version
g++ --version

clang_major="$(clang++ -dumpversion | cut -d. -f1)"
[[ "$clang_major" =~ ^[0-9]+$ ]]
if ((clang_major < 17)); then
    echo "Clang 17 or newer is required to build the current GN host tool." >&2
    exit 1
fi

echo "Host compiler validation passed (Clang $clang_major)."

