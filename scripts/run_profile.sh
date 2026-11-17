#!/usr/bin/env bash
# Collects the three profiles used in the report.
#
#   1. Where the original program spends its instructions (needs valgrind).
#   2. How the cached field's tables fill up as the matrices grow.
#   3. The cost of one operation: original arithmetic, a hash map, the tables.
#
# Usage: scripts/run_profile.sh [--label NAME]
set -euo pipefail
source "$(dirname "${BASH_SOURCE[0]}")/common.sh"

LABEL="$(default_label)"
while [ $# -gt 0 ]; do
    case "$1" in
        --label) LABEL="$2"; shift 2 ;;
        *) fail "unknown option $1" ;;
    esac
done

fetch_dependencies
build_tools
mkdir -p "$RESULTS/logs/$LABEL"
python3 "$SCRIPTS/bench.py" machine --label "$LABEL" --csv "$RESULTS/environments.csv"

PROFILE_SIZE=60
if command -v valgrind > /dev/null && command -v callgrind_annotate > /dev/null; then
    echo "Instruction profile of the original program at size $PROFILE_SIZE"
    dir="$BUILD_ROOT/original-profile"
    cmake -S "$ROOT" -B "$dir" -DCMAKE_BUILD_TYPE=RelWithDebInfo \
        "-DALGEBRA_ASSIGNMENT_SIZE=$PROFILE_SIZE" -DALGEBRA_ASSIGNMENT_BUILD_CACHED_TOOLS=OFF \
        "-DFETCHCONTENT_SOURCE_DIR_ALGEBRA_FINITE_FIELDS=$ORIGINAL_FIELDS" \
        "${DEPENDENCY_ARGS[@]}" > "$dir.configure.log" 2>&1 ||
        fail "configure failed, see $dir.configure.log"
    cmake --build "$dir" --target algebra_determinants --parallel "$BUILD_JOBS" \
        > "$dir.build.log" 2>&1 || fail "build failed, see $dir.build.log"
    valgrind --tool=callgrind "--callgrind-out-file=$dir/callgrind.out" \
        "$dir/src/algebra_determinants" > "$RESULTS/logs/$LABEL/profile-original.txt" 2>&1
    callgrind_annotate --threshold=100 --auto=no "$dir/callgrind.out" \
        > "$dir/callgrind.txt" 2> /dev/null
    python3 "$SCRIPTS/callgrind_buckets.py" "$dir/callgrind.txt" "$RESULTS/profile_original.csv"
else
    echo "valgrind is not installed, skipping the instruction profile"
fi

echo "Cache fill by matrix size"
rm -f "$RESULTS/cache_statistics.csv"
for size in 10 20 30 40 60 80 100 150 200 300 400 600; do
    "$TOOLS/benchmarks/algebra_cache_statistics" "$size" "$RESULTS/cache_statistics.csv"
done

echo "Cost per operation"
rm -f "$RESULTS/lookup_benchmark.csv"
"$TOOLS/benchmarks/algebra_lookup_benchmark" "$RESULTS/lookup_benchmark.csv" \
    > "$RESULTS/logs/$LABEL/lookup-benchmark.txt"
cat "$RESULTS/logs/$LABEL/lookup-benchmark.txt"
echo "Done. Profiles are in $RESULTS"
