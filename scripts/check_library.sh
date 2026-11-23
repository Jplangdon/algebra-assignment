#!/usr/bin/env bash
# Checks the cached finite field library on this machine and records what happened in
# results/library_checks.csv, so that the report can say what was run where.
#
#   release        the library's 21 unit tests, optimized build, default compiler
#   sanitizers     the same tests under the address and undefined-behaviour sanitizers,
#                  and under the thread sanitizer
#   clang          the same tests with Clang, with libstdc++ and with libc++, if they
#                  are installed and Clang is not the default compiler already
#   matrices       the unit tests of algebra-matrices, built against the cached library
#   wrong-product  a check on the tests themselves: in a copy of the library the product
#                  of one pair of elements is stored wrongly, and the tests have to notice
#
# A step that cannot run here (no Clang, no sanitizer libraries) is skipped and named at
# the end. It is then not in the file, and the report does not mention it.
#
# Usage: scripts/check_library.sh --label NAME [--only "STEP ..."]
#
# --label is the name this machine has in the result files, the same one that was given
# to the benchmark scripts. A complete run replaces the rows that label had. With --only,
# just the named steps are run and only their rows are replaced.
set -euo pipefail
source "$(dirname "${BASH_SOURCE[0]}")/common.sh"

# The pair whose product the wrong-product step stores wrongly, as element indices. An
# element's index is c0 + 11*c1 + 121*c2 for the polynomial c0 + c1*x + c2*x^2, so these
# are 7 + 8x + 5x^2 and 9 + 4x + 7x^2. Their sum is stored where their product belongs.
WRONG_A=700
WRONG_B=900
WRONG_DETAIL="the product of the elements with indices $WRONG_A and $WRONG_B is stored as their sum"

LABEL=""
STEPS="release sanitizers clang matrices wrong-product"
PARTIAL=""
while [ $# -gt 0 ]; do
    case "$1" in
        --label) LABEL="$2"; shift 2 ;;
        --only) STEPS="$2"; PARTIAL="--partial"; shift 2 ;;
        *) fail "unknown option $1" ;;
    esac
done
if [ -z "$LABEL" ]; then
    known="$(tail -n +2 "$RESULTS/environments.csv" 2> /dev/null | cut -d, -f1 | paste -sd' ' -)"
    fail "give this machine's name: scripts/check_library.sh --label <machine name>" \
        "(names already in results/environments.csv: ${known:-none})"
fi
for step in $STEPS; do
    case "$step" in
        release | sanitizers | clang | matrices | wrong-product) ;;
        *) fail "unknown step $step" ;;
    esac
done
wanted() { case " $STEPS " in *" $1 "*) return 0 ;; *) return 1 ;; esac; }

COMPILER="$(command -v "${CXX:-c++}" || true)"
[ -n "$COMPILER" ] || fail "no C++ compiler found (looked for ${CXX:-c++})"
fetch_dependencies
if [ -n "${ALGEBRA_DEPS_DIR:-}" ]; then
    MATRICES="$ALGEBRA_DEPS_DIR/algebra-matrices"
else
    MATRICES="$BUILD_ROOT/_fetch/_deps/algebra_matrices-src"
fi

CHECKS="$BUILD_ROOT/checks"
ROWS="$CHECKS/rows.csv"
mkdir -p "$CHECKS"
rm -f "$ROWS"

# Which commit of the library is being checked, for the record.
COMMIT=""
if git -C "$CACHED_FIELDS" rev-parse --git-dir > /dev/null 2>&1; then
    COMMIT="$(git -C "$CACHED_FIELDS" rev-parse --short=7 HEAD)"
    if [ -n "$(git -C "$CACHED_FIELDS" status --porcelain)" ]; then
        COMMIT="$COMMIT with local changes"
    fi
    pinned="$(grep -A 4 'algebra-finite-fields-cached' "$ROOT/cmake/Dependencies.cmake" |
        grep -o 'GIT_TAG [0-9a-f]\{40\}' | cut -d' ' -f2 || true)"
    if [ -n "$pinned" ] && [ "$(git -C "$CACHED_FIELDS" rev-parse HEAD)" != "$pinned" ]; then
        echo "note: $CACHED_FIELDS is at commit $COMMIT," \
            "but cmake/Dependencies.cmake names ${pinned:0:7}"
    fi
fi

skipped=()
problems=()
# GoogleTest is downloaded by the first build that needs it and kept for the later ones.
GTEST_SOURCE=""
if [ -f "$CHECKS/googletest-src/CMakeLists.txt" ]; then
    GTEST_SOURCE="$CHECKS/googletest-src"
fi

version_of() { "$1" --version 2> /dev/null | head -n 1; }

# Builds and runs a one-line program with the given flags. Tells whether those flags work
# on this machine at all, before a long build is started with them.
#   probe COMPILER [flags...]      sets PROBE_RUNNER to a prefix the tests need, if any
PROBE_RUNNER=""
probe() {
    local compiler="$1" source="$CHECKS/probe.cpp" program="$CHECKS/probe"
    shift
    PROBE_RUNNER=""
    printf '#include <vector>\nint main() { std::vector<int> v(3, 1); return v[0] - 1; }\n' > "$source"
    "$compiler" -std=c++20 "$@" "$source" -o "$program" > "$CHECKS/probe.log" 2>&1 || return 1
    if "$program" >> "$CHECKS/probe.log" 2>&1; then
        return 0
    fi
    # The thread sanitizer of some compilers cannot start while the kernel places memory
    # at random addresses. Starting the tests with that switched off for them helps.
    if command -v setarch > /dev/null &&
        setarch "$(uname -m)" -R "$program" >> "$CHECKS/probe.log" 2>&1; then
        PROBE_RUNNER="setarch $(uname -m) -R"
        return 0
    fi
    return 1
}

# Configures, builds and runs one set of unit tests and records the result.
#   run_tests NAME SOURCE CHECK BUILD STANDARD_LIBRARY COMPILER RUNNER DETAIL SPLIT [cmake arguments...]
run_tests() {
    local name="$1" source="$2" check="$3" build="$4" library="$5" compiler="$6" runner="$7"
    local detail="$8" split="$9"
    shift 9
    local dir="$CHECKS/$name"
    echo "$check, $(version_of "$compiler")${library:+, $library}, $build"
    rm -rf "$dir"
    local gtest=()
    if [ -n "$GTEST_SOURCE" ]; then
        gtest=("-DFETCHCONTENT_SOURCE_DIR_GOOGLETEST=$GTEST_SOURCE")
    fi
    if ! cmake -S "$source" -B "$dir" "-DCMAKE_CXX_COMPILER=$compiler" "$@" \
        "${DEPENDENCY_ARGS[@]}" ${gtest[@]+"${gtest[@]}"} > "$dir.configure.log" 2>&1; then
        problems+=("$name: configure failed, see $dir.configure.log")
        return 0
    fi
    if [ -z "$GTEST_SOURCE" ] && [ -d "$dir/_deps/googletest-src" ]; then
        cp -r "$dir/_deps/googletest-src" "$CHECKS/googletest-src"
        GTEST_SOURCE="$CHECKS/googletest-src"
    fi
    if ! cmake --build "$dir" --parallel "$BUILD_JOBS" > "$dir.build.log" 2>&1; then
        problems+=("$name: build failed, see $dir.build.log")
        return 0
    fi
    # ctest's own exit status is not used: failing tests are counted from its report.
    # shellcheck disable=SC2086
    $runner ctest --test-dir "$dir" --output-junit "$dir/tests.xml" --parallel "$BUILD_JOBS" \
        > "$dir.test.log" 2>&1 || true
    if [ ! -s "$dir/tests.xml" ]; then
        problems+=("$name: the tests did not run, see $dir.test.log")
        return 0
    fi
    python3 "$SCRIPTS/bench.py" check-row --label "$LABEL" --csv "$ROWS" \
        --junit "$dir/tests.xml" --check "$check" --compiler "$(version_of "$compiler")" \
        --standard-library "$library" --build "$build" --detail "$detail" \
        --commit "$COMMIT" --split-at "$split" ||
        problems+=("$name: no test results, see $dir.test.log")
}

# The library's examples are not part of any check, so they are not built.
LIBRARY=(-DALGEBRA_FINITE_FIELDS_BUILD_EXAMPLES=OFF)

if wanted release; then
    run_tests release "$CACHED_FIELDS" "library tests" "release" "" "$COMPILER" "" "" "" \
        -DCMAKE_BUILD_TYPE=Release "${LIBRARY[@]}"
fi

if wanted sanitizers; then
    flags="-fsanitize=address,undefined -fno-sanitize-recover=all -fno-omit-frame-pointer"
    # shellcheck disable=SC2086
    if probe "$COMPILER" $flags; then
        run_tests address-undefined "$CACHED_FIELDS" "library tests" \
            "address and undefined-behaviour sanitizers" "" "$COMPILER" "$PROBE_RUNNER" "" "" \
            -DCMAKE_BUILD_TYPE=RelWithDebInfo "-DCMAKE_CXX_FLAGS=$flags" "${LIBRARY[@]}"
    else
        cp "$CHECKS/probe.log" "$CHECKS/probe-address-undefined.log"
        skipped+=("address and undefined-behaviour sanitizers: a program built with them does not build or run here, see $CHECKS/probe-address-undefined.log")
    fi
    flags="-fsanitize=thread"
    if probe "$COMPILER" $flags; then
        run_tests thread "$CACHED_FIELDS" "library tests" "thread sanitizer" "" "$COMPILER" \
            "$PROBE_RUNNER" "" "" -DCMAKE_BUILD_TYPE=RelWithDebInfo "-DCMAKE_CXX_FLAGS=$flags" \
            "${LIBRARY[@]}"
    else
        cp "$CHECKS/probe.log" "$CHECKS/probe-thread.log"
        skipped+=("thread sanitizer: a program built with it does not build or run here, see $CHECKS/probe-thread.log")
    fi
fi

if wanted clang; then
    CLANG="$(command -v clang++ || true)"
    if [ -z "$CLANG" ]; then
        skipped+=("clang: clang++ is not installed")
    elif version_of "$COMPILER" | grep -qi clang; then
        skipped+=("clang: it is the default compiler here, so the other steps already use it")
    else
        if probe "$CLANG"; then
            run_tests clang "$CACHED_FIELDS" "library tests" "release" "libstdc++" "$CLANG" "" \
                "" "" -DCMAKE_BUILD_TYPE=Release "${LIBRARY[@]}"
        else
            cp "$CHECKS/probe.log" "$CHECKS/probe-clang.log"
            skipped+=("clang with libstdc++: a program does not build or run, see $CHECKS/probe-clang.log")
        fi
        if probe "$CLANG" -stdlib=libc++; then
            run_tests clang-libcxx "$CACHED_FIELDS" "library tests" "release" "libc++" "$CLANG" \
                "" "" "" -DCMAKE_BUILD_TYPE=Release -DCMAKE_CXX_FLAGS=-stdlib=libc++ \
                "${LIBRARY[@]}"
        else
            skipped+=("clang with libc++: libc++ is not installed")
        fi
    fi
fi

if wanted matrices; then
    if [ -f "$MATRICES/CMakeLists.txt" ]; then
        run_tests matrices "$MATRICES" "matrix tests" "release" "" "$COMPILER" "" "" "" \
            -DCMAKE_BUILD_TYPE=Release -DALGEBRA_MATRICES_BUILD_EXAMPLES=OFF \
            "-DFETCHCONTENT_SOURCE_DIR_ALGEBRA_FINITE_FIELDS=$CACHED_FIELDS"
    else
        problems+=("matrices: algebra-matrices was not found at $MATRICES")
    fi
fi

if wanted wrong-product; then
    copy="$CHECKS/wrong-product-source"
    rm -rf "$copy"
    mkdir -p "$copy"
    (cd "$CACHED_FIELDS" && tar --exclude=.git --exclude=build -cf - .) | (cd "$copy" && tar -xf -)
    if python3 "$SCRIPTS/bench.py" wrong-product \
        "$copy/include/algebra/finite_fields/finite_field.hpp" --a "$WRONG_A" --b "$WRONG_B"; then
        run_tests wrong-product "$copy" "wrong product" "release" "" "$COMPILER" "" \
            "$WRONG_DETAIL" ".CachedFiniteField." -DCMAKE_BUILD_TYPE=Release "${LIBRARY[@]}"
    else
        problems+=("wrong-product: the copy of the library could not be changed")
    fi
fi

echo
[ -f "$ROWS" ] || fail "no step produced a result: ${problems[*]:-nothing was run}"
# The machine goes into the list of machines if it is not there yet, so that the report's
# table can describe it. A description that is already there is left as it was recorded.
if ! python3 "$SCRIPTS/bench.py" has --csv "$RESULTS/environments.csv" "label=$LABEL"; then
    python3 "$SCRIPTS/bench.py" machine --label "$LABEL" --csv "$RESULTS/environments.csv"
fi
# check-store also judges the rows: a failing test in a normal build is a problem, and in
# the wrong-product step a new test that fails is the point.
status=0
# shellcheck disable=SC2086
python3 "$SCRIPTS/bench.py" check-store --label "$LABEL" --rows "$ROWS" \
    --csv "$RESULTS/library_checks.csv" $PARTIAL || status=1
for line in ${skipped[@]+"${skipped[@]}"}; do
    echo "skipped: $line"
done
for line in ${problems[@]+"${problems[@]}"}; do
    echo "PROBLEM: $line"
    status=1
done
if [ "$status" -eq 0 ]; then
    echo "Done. The results are in $RESULTS/library_checks.csv"
fi
exit "$status"
