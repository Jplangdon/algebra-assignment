#!/usr/bin/env bash
# Builds the cached finite field library on its own and runs its unit tests:
# the original library's tests, unchanged, and the tests that compare the
# cached class with the original element by element and pair by pair.
#
# Usage: scripts/test_library.sh
set -euo pipefail
source "$(dirname "${BASH_SOURCE[0]}")/common.sh"

[ -f "$CACHED_FIELDS/CMakeLists.txt" ] ||
    fail "the cached finite field library was not found at $CACHED_FIELDS (set CACHED_FIELDS)"

dir="$BUILD_ROOT/library-tests"
mkdir -p "$BUILD_ROOT"

# With ALGEBRA_DEPS_DIR set, existing clones of the other algebra repositories
# are used. GoogleTest is still downloaded by the library's own build files.
arguments=()
if [ -n "${ALGEBRA_DEPS_DIR:-}" ]; then
    for name in core groups rings polynomials; do
        upper="$(echo "$name" | tr '[:lower:]' '[:upper:]')"
        [ -d "$ALGEBRA_DEPS_DIR/algebra-$name" ] || fail "$ALGEBRA_DEPS_DIR/algebra-$name is missing"
        arguments+=("-DFETCHCONTENT_SOURCE_DIR_ALGEBRA_$upper=$ALGEBRA_DEPS_DIR/algebra-$name")
    done
fi

echo "Building the library's tests"
cmake -S "$CACHED_FIELDS" -B "$dir" -DCMAKE_BUILD_TYPE=Release \
    ${arguments[@]+"${arguments[@]}"} > "$dir.configure.log" 2>&1 ||
    fail "configure failed, see $dir.configure.log"
cmake --build "$dir" --parallel "$BUILD_JOBS" > "$dir.build.log" 2>&1 ||
    fail "build failed, see $dir.build.log"

ctest --test-dir "$dir" --output-on-failure
