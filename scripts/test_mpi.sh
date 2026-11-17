#!/usr/bin/env bash
# Checks the MPI determinant against the sequential one.
#
# Every run of the MPI program computes the determinant both ways and exits
# with an error if the two disagree. This script tries process counts, panel
# widths, awkward sizes and matrices that force row swaps or a zero result,
# and compares the random case with the values the assignment program prints.
#
# Usage: scripts/test_mpi.sh [path to algebra_mpi_determinant]
set -euo pipefail
source "$(dirname "${BASH_SOURCE[0]}")/common.sh"

PROGRAM="${1:-}"
if [ -z "$PROGRAM" ]; then
    fetch_dependencies
    build_tools
    PROGRAM="$TOOLS/src/algebra_mpi_determinant"
fi
[ -x "$PROGRAM" ] || fail "$PROGRAM is not an executable"

passed=0
failed=0

check() {   # processes, then the program's arguments
    local processes="$1"
    shift
    if mpi_launch "$processes" "$PROGRAM" "$@" > /tmp/test_mpi.$$.out 2>&1 &&
        ! grep -q "Results match false" /tmp/test_mpi.$$.out; then
        passed=$((passed + 1))
    else
        failed=$((failed + 1))
        echo "FAILED: $processes processes, $*"
        tail -5 /tmp/test_mpi.$$.out
    fi
}

# What the assignment program prints for seed 123456.
expect() {   # size, matrix name, expected determinant text
    local size="$1" name="$2" expected="$3" processes
    for processes in 1 2 3; do
        if mpi_launch "$processes" "$PROGRAM" --size "$size" --block 5 2> /dev/null |
            grep -qxF "det($name) = $expected"; then
            passed=$((passed + 1))
        else
            failed=$((failed + 1))
            echo "FAILED: size $size det($name) is not $expected with $processes processes"
        fi
    done
}

echo "Random matrices against the assignment program's output"
expect 100 A "2 + 10*x^1 + 2*x^2"
expect 100 B "4 + 10*x^1 + 2*x^2"
expect 200 A "3 + 2*x^1 + 6*x^2"
expect 200 B "6*x^2"
expect 400 A "7 + 3*x^1 + 8*x^2"
expect 400 B "2 + 10*x^1 + 3*x^2"

echo "Process counts, panel widths and sizes"
for processes in 1 2 3 4; do
    for block in 1 3 16; do
        for size in 1 2 5 17 64; do
            check "$processes" --size "$size" --block "$block" --no-warm
        done
    done
done

echo "Matrices that force row swaps, zero multipliers or a zero determinant"
for matrix_case in sparse permutation singular zero-leading; do
    for processes in 1 2 4; do
        for block in 1 4; do
            for size in 1 7 33; do
                for seed in 1 2; do
                    check "$processes" --size "$size" --block "$block" --case "$matrix_case" \
                        --seed "$seed" --no-warm
                done
            done
        done
    done
done

rm -f /tmp/test_mpi.$$.out
echo "$passed passed, $failed failed"
# The report quotes this count.
mkdir -p "$RESULTS"
printf 'passed,failed\n%s,%s\n' "$passed" "$failed" > "$RESULTS/mpi_tests.csv"
[ "$failed" -eq 0 ]
