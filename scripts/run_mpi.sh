#!/usr/bin/env bash
# Times the MPI determinant against the sequential one over a range of sizes.
#
#   scripts/run_mpi.sh                           standard sweep on this machine
#   scripts/run_mpi.sh --processes "1 2 4 8"     choose the process counts
#   scripts/run_mpi.sh --blocks "1 4 16 64"      compare panel widths
#   scripts/run_mpi.sh --build-only              only build (do this on a login node)
#   scripts/run_mpi.sh --skip-build              use the program that is already built
#
# Every run computes each determinant sequentially and with MPI on the same
# matrix, checks that the two agree, and adds a line to results/mpi.csv. Runs
# that are already in the file for this label are skipped. Inside a Slurm job
# the processes are spread over the allocated nodes.
set -euo pipefail
source "$(dirname "${BASH_SOURCE[0]}")/common.sh"

LABEL="$(default_label)"
SIZES="10 20 30 40 50 75 100 150 200 300 400 600 800 1000 1500 2000"
PROCESSES=""
BLOCKS="8"
REPEATS=5
BUILD_ONLY=0
SKIP_BUILD=0

while [ $# -gt 0 ]; do
    case "$1" in
        --label) LABEL="$2"; shift 2 ;;
        --sizes) SIZES="$2"; shift 2 ;;
        --processes) PROCESSES="$2"; shift 2 ;;
        --blocks) BLOCKS="$2"; shift 2 ;;
        --repeat) REPEATS="$2"; shift 2 ;;
        --build-only) BUILD_ONLY=1; shift ;;
        --skip-build) SKIP_BUILD=1; shift ;;
        *) fail "unknown option $1" ;;
    esac
done

if [ "$SKIP_BUILD" = 1 ]; then
    # Compute nodes often have no compiler, no CMake and no internet access.
    TOOLS="$BUILD_ROOT/tools"
    [ -x "$TOOLS/src/algebra_mpi_determinant" ] ||
        fail "nothing is built yet, run scripts/run_mpi.sh --build-only first"
else
    fetch_dependencies
    build_tools
fi
PROGRAM="$TOOLS/src/algebra_mpi_determinant"
[ -x "$PROGRAM" ] || fail "the MPI program was not built (is an MPI compiler installed?)"
if [ "$BUILD_ONLY" = 1 ]; then
    echo "Built $PROGRAM"
    exit 0
fi

# Without a list, use 1, 2, 4, ... up to the processors that are available.
if [ -z "$PROCESSES" ]; then
    available="${SLURM_NTASKS:-$(nproc)}"
    PROCESSES="1"
    count=2
    while [ "$count" -le "$available" ]; do
        PROCESSES="$PROCESSES $count"
        count=$((count * 2))
    done
fi

CSV="$RESULTS/mpi.csv"
mkdir -p "$RESULTS/logs/$LABEL"
# The record keeping uses Python. Without it the measurements still run, but
# nothing is skipped and the machine is not described in environments.csv.
if command -v python3 > /dev/null 2>&1; then
    python3 "$SCRIPTS/bench.py" machine --label "$LABEL" --csv "$RESULTS/environments.csv"
else
    echo "python3 was not found: this machine is not added to results/environments.csv"
fi
already_recorded() {
    command -v python3 > /dev/null 2>&1 || return 1
    python3 "$SCRIPTS/bench.py" has --csv "$CSV" "$@"
}
echo "Sizes: $SIZES"
echo "Processes: $PROCESSES"
echo "Panel widths: $BLOCKS"

for processes in $PROCESSES; do
    for block in $BLOCKS; do
        for size in $SIZES; do
            if already_recorded "label=$LABEL" "processes=$processes" "size=$size" \
                "block=$block"; then
                echo "  $processes processes, size $size, panel $block: already recorded"
                continue
            fi
            log="$RESULTS/logs/$LABEL/mpi-p$processes-b$block-n$size.txt"
            if mpi_launch "$processes" "$PROGRAM" --size "$size" --block "$block" \
                --repeat "$REPEATS" --csv "$CSV" --label "$LABEL" > "$log" 2>&1; then
                echo "  $processes processes, size $size, panel $block: done"
            else
                echo "  $processes processes, size $size, panel $block: FAILED, see $log"
            fi
        done
    done
done
echo "Done. Results are in $CSV"
