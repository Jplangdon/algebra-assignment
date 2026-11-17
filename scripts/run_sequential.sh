#!/usr/bin/env bash
# Before and after: runs the assignment program built against the original and
# against the cached finite field, and records runtime and peak memory.
#
#   scripts/run_sequential.sh                       standard set of sizes
#   scripts/run_sequential.sh --preset quick        a few minutes
#   scripts/run_sequential.sh --preset overnight    includes 4000 x 4000 for both
#   scripts/run_sequential.sh --original "500" --cached "500 3000"
#
# Results are added to results/sequential.csv. A size that is already in the
# file for this machine is skipped, so an interrupted run can simply be started
# again. Each program's own output goes to results/logs/<label>/.
set -euo pipefail
source "$(dirname "${BASH_SOURCE[0]}")/common.sh"

LABEL="$(default_label)"
ORIGINAL_SIZES="100 200 400 800"
CACHED_SIZES="100 200 400 800 1000 2000"
REPEATS=1

while [ $# -gt 0 ]; do
    case "$1" in
        --label) LABEL="$2"; shift 2 ;;
        --original) ORIGINAL_SIZES="$2"; shift 2 ;;
        --cached) CACHED_SIZES="$2"; shift 2 ;;
        --repeat) REPEATS="$2"; shift 2 ;;
        --preset)
            case "$2" in
                quick) ORIGINAL_SIZES="100 200 400"; CACHED_SIZES="100 200 400 800 1000" ;;
                standard) ;;
                overnight)
                    ORIGINAL_SIZES="100 200 400 800 1000 2000 4000"
                    CACHED_SIZES="100 200 400 800 1000 2000 4000 6000"
                    ;;
                *) fail "unknown preset $2 (quick, standard or overnight)" ;;
            esac
            shift 2
            ;;
        *) fail "unknown option $1" ;;
    esac
done

CSV="$RESULTS/sequential.csv"
mkdir -p "$RESULTS/logs/$LABEL"
fetch_dependencies
build_tools
python3 "$SCRIPTS/bench.py" machine --label "$LABEL" --csv "$RESULTS/environments.csv"

run_one() {   # implementation size repeat
    local implementation="$1" size="$2" repeat="$3"
    if python3 "$SCRIPTS/bench.py" has --csv "$CSV" "label=$LABEL" \
        "implementation=$implementation" "size=$size" "repeat=$repeat"; then
        echo "  $implementation $size: already recorded, skipping"
        return
    fi
    build_program "$implementation" "$size"
    python3 "$SCRIPTS/bench.py" sequential --label "$LABEL" --implementation "$implementation" \
        --size "$size" --repeat "$repeat" --csv "$CSV" \
        --launcher "$TOOLS/benchmarks/algebra_measure" \
        --log "$RESULTS/logs/$LABEL/$implementation-$size-r$repeat.txt" \
        -- "$BUILD_ROOT/$implementation-$size/src/algebra_determinants"
}

# The cached runs are short, so they go first.
echo "Cached finite field: $CACHED_SIZES"
for size in $CACHED_SIZES; do
    for repeat in $(seq 1 "$REPEATS"); do
        run_one cached "$size" "$repeat"
    done
done
echo "Original finite field: $ORIGINAL_SIZES"
for size in $ORIGINAL_SIZES; do
    for repeat in $(seq 1 "$REPEATS"); do
        run_one original "$size" "$repeat"
    done
done
echo "Done. Results are in $CSV"
