#!/usr/bin/env bash
# show_tree_and_contents.sh
# Display directory tree, then the content of every regular file.
#
# Usage:
#   ./show_tree_and_contents.sh [directory]
#   (defaults to current directory)

set -euo pipefail

TARGET="${1:-.}"

if [[ ! -d "$TARGET" ]]; then
    echo "Error: '$TARGET' is not a directory" >&2
    exit 1
fi

TARGET="$(cd "$TARGET" && pwd)"

echo "════════════════════════════════════════════════════════════"
echo "  Directory tree of: $TARGET"
echo "════════════════════════════════════════════════════════════"
echo

if command -v tree >/dev/null 2>&1; then
    tree -a --dirsfirst "$TARGET"
else
    find "$TARGET" | sed -e "s|[^-][^/]*/| |g" -e "s|^\( *\)\([^ ]\)|\1├── \2|"
fi

echo
echo "════════════════════════════════════════════════════════════"
echo "  File contents"
echo "════════════════════════════════════════════════════════════"
echo

# Portable way: use a temporary file list
tmpdir=$(mktemp -d)
trap 'rm -rf "$tmpdir"' EXIT
filelist="$tmpdir/files"

find "$TARGET" -type f | sort > "$filelist"

while IFS= read -r file; do
    [[ -z "$file" ]] && continue

    rel="${file#$TARGET/}"
    [[ "$rel" == "$file" ]] && rel="."

    echo "──────────────────────── $rel ────────────────────────"
    echo

    # Heuristic: if the first 512 bytes look like text → print it
    if head -c 512 "$file" 2>/dev/null | grep -qI .; then
        cat "$file"
    else
        size=$(wc -c < "$file" 2>/dev/null || echo 0)
        if [[ "$size" -eq 0 ]]; then
            echo "[empty file]"
        else
            echo "[binary or non-text file – content skipped]"
            echo "  size: $size bytes"
        fi
    fi

    echo
    echo
done < "$filelist"

echo "════════════════════════════════════════════════════════════"
echo "  Done."
echo "════════════════════════════════════════════════════════════"
