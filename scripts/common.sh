#!/usr/bin/env bash
# Shared helpers for the scripts in this folder. Other scripts source this file.

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SCRIPTS="$ROOT/scripts"
RESULTS="${RESULTS:-$ROOT/results}"
BUILD_ROOT="${BUILD_ROOT:-$ROOT/build}"
BUILD_JOBS="${BUILD_JOBS:-$(nproc 2>/dev/null || echo 2)}"

# The cached finite field library. By default a checkout next to this repository.
CACHED_FIELDS="${CACHED_FIELDS:-$ROOT/../algebra-finite-fields-cached}"

# The original finite field library, at the commit the assignment pins.
ORIGINAL_FIELDS_URL="https://github.com/nathanjrussell/algebra-finite-fields.git"
ORIGINAL_FIELDS_COMMIT="74b3d569fb48818f4c10f3c32889f2128485f1a7"

# The dependency files give their repositories as SSH addresses. Reading a
# public repository does not need an SSH key, so git is told to use HTTPS for
# those addresses while these scripts run. Your own git settings do not change.
export GIT_CONFIG_COUNT=1
export GIT_CONFIG_KEY_0="url.https://github.com/.insteadOf"
export GIT_CONFIG_VALUE_0="git@github.com:"

fail() {
    echo "error: $*" >&2
    exit 1
}

# Name used for this machine in the result files.
default_label() {
    hostname -s 2>/dev/null || hostname
}

# Finds the other algebra repositories once and remembers where they are.
#   ALGEBRA_DEPS_DIR set    use existing clones in that folder (no network needed)
#   otherwise               let CMake fetch them once into build/_fetch
# Sets DEPENDENCY_ARGS (for cmake) and ORIGINAL_FIELDS (path to the original library).
fetch_dependencies() {
    [ -f "$CACHED_FIELDS/CMakeLists.txt" ] ||
        fail "the cached finite field library was not found at $CACHED_FIELDS (set CACHED_FIELDS)"
    mkdir -p "$BUILD_ROOT"
    DEPENDENCY_ARGS=()
    local name upper
    if [ -n "${ALGEBRA_DEPS_DIR:-}" ]; then
        for name in core groups rings polynomials matrices; do
            upper="$(echo "$name" | tr '[:lower:]' '[:upper:]')"
            [ -d "$ALGEBRA_DEPS_DIR/algebra-$name" ] ||
                fail "$ALGEBRA_DEPS_DIR/algebra-$name is missing"
            DEPENDENCY_ARGS+=("-DFETCHCONTENT_SOURCE_DIR_ALGEBRA_$upper=$ALGEBRA_DEPS_DIR/algebra-$name")
        done
        ORIGINAL_FIELDS="$ALGEBRA_DEPS_DIR/algebra-finite-fields"
        return
    fi
    local fetch="$BUILD_ROOT/_fetch"
    if [ ! -f "$fetch/.complete" ]; then
        echo "Fetching the algebra repositories (first run only)"
        cmake -S "$ROOT" -B "$fetch" -DALGEBRA_ASSIGNMENT_BUILD_CACHED_TOOLS=OFF \
            "-DFETCHCONTENT_SOURCE_DIR_ALGEBRA_FINITE_FIELDS=$CACHED_FIELDS" \
            > "$BUILD_ROOT/_fetch.log" 2>&1 ||
            fail "could not fetch the dependencies, see $BUILD_ROOT/_fetch.log"
        touch "$fetch/.complete"
    fi
    for name in core groups rings polynomials matrices; do
        upper="$(echo "$name" | tr '[:lower:]' '[:upper:]')"
        DEPENDENCY_ARGS+=("-DFETCHCONTENT_SOURCE_DIR_ALGEBRA_$upper=$fetch/_deps/algebra_$name-src")
    done
    ORIGINAL_FIELDS="$BUILD_ROOT/_original/algebra-finite-fields"
    if [ ! -f "$ORIGINAL_FIELDS/CMakeLists.txt" ]; then
        echo "Fetching the original finite field library"
        rm -rf "$ORIGINAL_FIELDS"
        git clone -q "$ORIGINAL_FIELDS_URL" "$ORIGINAL_FIELDS" ||
            fail "could not clone $ORIGINAL_FIELDS_URL"
        git -C "$ORIGINAL_FIELDS" checkout -q "$ORIGINAL_FIELDS_COMMIT" ||
            fail "could not check out $ORIGINAL_FIELDS_COMMIT"
    fi
}

# Builds the assignment program for one implementation and one matrix size.
#   build_program original|cached SIZE
# The program ends up in $BUILD_ROOT/<implementation>-<size>/src/algebra_determinants.
build_program() {
    local implementation="$1" size="$2" fields
    local dir="$BUILD_ROOT/$implementation-$size"
    case "$implementation" in
        original) fields="$ORIGINAL_FIELDS" ;;
        cached) fields="$CACHED_FIELDS" ;;
        *) fail "unknown implementation $implementation" ;;
    esac
    if [ -x "$dir/src/algebra_determinants" ]; then
        return
    fi
    cmake -S "$ROOT" -B "$dir" -DCMAKE_BUILD_TYPE=Release "-DALGEBRA_ASSIGNMENT_SIZE=$size" \
        -DALGEBRA_ASSIGNMENT_BUILD_CACHED_TOOLS=OFF \
        "-DFETCHCONTENT_SOURCE_DIR_ALGEBRA_FINITE_FIELDS=$fields" "${DEPENDENCY_ARGS[@]}" \
        > "$dir.configure.log" 2>&1 || fail "configure failed, see $dir.configure.log"
    cmake --build "$dir" --target algebra_determinants --parallel "$BUILD_JOBS" \
        > "$dir.build.log" 2>&1 || fail "build failed, see $dir.build.log"
}

# Builds the MPI program and the benchmark tools into $BUILD_ROOT/tools.
build_tools() {
    local dir="$BUILD_ROOT/tools"
    cmake -S "$ROOT" -B "$dir" -DCMAKE_BUILD_TYPE=Release -DALGEBRA_ASSIGNMENT_SIZE=100 \
        -DALGEBRA_ASSIGNMENT_BUILD_CACHED_TOOLS=ON \
        "-DFETCHCONTENT_SOURCE_DIR_ALGEBRA_FINITE_FIELDS=$CACHED_FIELDS" "${DEPENDENCY_ARGS[@]}" \
        > "$dir.configure.log" 2>&1 || fail "configure failed, see $dir.configure.log"
    cmake --build "$dir" --parallel "$BUILD_JOBS" > "$dir.build.log" 2>&1 ||
        fail "build failed, see $dir.build.log"
    TOOLS="$dir"
}

# Starts an MPI program on a number of processes.
#   mpi_launch PROCESSES program [arguments...]
# Set MPI_LAUNCHER to use something other than mpirun, for example "srun".
mpi_launch() {
    local processes="$1"
    shift
    local launcher="${MPI_LAUNCHER:-mpirun}"
    local arguments=()
    if [ "$launcher" = mpirun ] && mpirun --version 2>&1 | grep -q "Open MPI"; then
        # Open MPI refuses to start more processes than cores, or to run as
        # root, unless told to. Neither applies on a normal cluster run.
        if [ -z "${SLURM_JOB_ID:-}" ] && [ "$processes" -gt "$(nproc)" ]; then
            arguments+=(--oversubscribe --mca mpi_yield_when_idle 1)
        fi
        if [ "$(id -u)" = 0 ]; then
            arguments+=(--allow-run-as-root)
        fi
    fi
    # shellcheck disable=SC2086
    $launcher ${MPI_LAUNCHER_FLAGS:-} ${arguments[@]+"${arguments[@]}"} -n "$processes" "$@"
}
