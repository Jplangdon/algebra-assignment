#!/usr/bin/env python3
"""Measuring and record keeping for the benchmark scripts.

Subcommands
  machine     describe this computer in results/environments.csv
  sequential  run the assignment program once, measure it, add a row to a CSV
  has         exit with status 0 if a CSV already has a matching row
  merge       add the rows of a result file from another machine to a local one
  check-row   turn the result of one ctest run into rows of a check file
  check-store put the rows of one run of scripts/check_library.sh into results/
  wrong-product  make one stored product wrong in a copy of the cached library

Only the Python standard library is used.
"""
import argparse
import csv
import datetime
import os
import platform
import re
import subprocess
import sys
import xml.etree.ElementTree

SEQUENTIAL_COLUMNS = [
    "label", "implementation", "size", "repeat", "wall_seconds", "user_seconds",
    "system_seconds", "peak_rss_mib", "generation_seconds", "product_seconds",
    "det_a_seconds", "det_b_seconds", "det_c_seconds", "total_seconds", "det_a", "det_b",
    "det_c", "verified", "exit_code", "finished",
]

MACHINE_COLUMNS = [
    "label", "cpu", "logical_cpus", "memory_gib", "system", "kernel", "compiler", "mpi",
    "recorded",
]

CHECK_COLUMNS = [
    "label", "check", "compiler", "standard_library", "build", "tests", "passed", "failed",
    "failed_tests", "detail", "library_commit", "recorded",
]

# The line of the cached library that stores a product on a cache miss, and what the
# wrong-product check puts in its place: for one ordered pair the sum is stored instead.
PRODUCT_LINE = ("        return store(products_[std::size_t{a} * order + b], "
                "elements[a].multiply(elements[b]));\n")
WRONG_PRODUCT = (
    "        if (a == %(a)d && b == %(b)d) {   // deliberately wrong: scripts/check_library.sh\n"
    "            return store(products_[std::size_t{a} * order + b], "
    "elements[a].add(elements[b]));\n"
    "        }\n")


def first_line(command):
    try:
        output = subprocess.run(command, capture_output=True, text=True, timeout=20)
    except (OSError, subprocess.SubprocessError):
        return ""
    lines = (output.stdout or output.stderr).strip().splitlines()
    return lines[0].strip() if lines else ""


def cpu_name():
    try:
        with open("/proc/cpuinfo", encoding="utf-8") as handle:
            for line in handle:
                if line.lower().startswith("model name"):
                    return line.split(":", 1)[1].strip()
    except OSError:
        pass
    return first_line(["sysctl", "-n", "machdep.cpu.brand_string"]) or platform.processor()


def memory_gib():
    try:
        with open("/proc/meminfo", encoding="utf-8") as handle:
            for line in handle:
                if line.startswith("MemTotal"):
                    return round(int(line.split()[1]) / 1048576, 1)
    except OSError:
        pass
    size = first_line(["sysctl", "-n", "hw.memsize"])
    return round(int(size) / 1073741824, 1) if size.isdigit() else ""


def system_name():
    name = ""
    try:
        with open("/etc/os-release", encoding="utf-8") as handle:
            for line in handle:
                if line.startswith("PRETTY_NAME="):
                    name = line.split("=", 1)[1].strip().strip('"')
    except OSError:
        name = f"{platform.system()} {platform.release()}"
    if "microsoft" in platform.release().lower():
        name += " on WSL2"
    elif is_virtual_machine():
        name += " (virtual machine)"
    return name


def is_virtual_machine():
    try:
        with open("/proc/cpuinfo", encoding="utf-8") as handle:
            for line in handle:
                if line.startswith("flags"):
                    return " hypervisor" in line
    except OSError:
        pass
    return False


def mpi_name():
    """Name and version of the MPI library behind mpirun, if there is one."""
    def lines_of(command):
        try:
            output = subprocess.run(command, capture_output=True, text=True, timeout=20)
        except (OSError, subprocess.SubprocessError):
            return []
        # Some installations print a warning in a box of dashes before the
        # version, so lines without a letter or a digit are dropped and the
        # version line is looked for instead of taking the first line.
        return [line.strip() for line in (output.stdout + "\n" + output.stderr).splitlines()
                if re.search(r"[A-Za-z0-9]", line)]

    lines = lines_of(["mpirun", "--version"])
    for line in lines:                              # mpirun (Open MPI) 4.1.6
        if re.match(r"^\S+ \((Open MPI|OpenRTE)\) v?\d", line):
            return line
    if any(line.startswith("HYDRA") for line in lines):    # MPICH prints its build details
        for line in lines:
            if line.startswith("Version:"):
                return "MPICH " + line.split(":", 1)[1].strip()
    for line in lines:                              # Intel(R) MPI Library for Linux* OS, Version ...
        if "Intel(R) MPI" in line:
            return line
    for line in lines_of(["ompi_info", "--version"]):      # Open MPI v5.0.8
        match = re.match(r"^Open MPI v?(\d\S*)", line)
        if match:
            return "mpirun (Open MPI) " + match.group(1)
    return ""


def read_rows(path):
    if not os.path.exists(path):
        return []
    with open(path, newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def write_rows(path, columns, rows):
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    with open(path, "w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns)
        writer.writeheader()
        writer.writerows(rows)


def append_row(path, columns, row):
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    new_file = not os.path.exists(path)
    with open(path, "a", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns)
        if new_file:
            writer.writeheader()
        writer.writerow(row)


def command_machine(arguments):
    row = {
        "label": arguments.label,
        "cpu": cpu_name(),
        "logical_cpus": os.cpu_count(),
        "memory_gib": memory_gib(),
        "system": system_name(),
        "kernel": platform.release(),
        "compiler": first_line([os.environ.get("CXX", "c++"), "--version"]),
        "mpi": mpi_name(),
        "recorded": datetime.date.today().isoformat(),
    }
    rows = [r for r in read_rows(arguments.csv) if r.get("label") != arguments.label]
    rows.append(row)
    write_rows(arguments.csv, MACHINE_COLUMNS, rows)
    print(f"{row['label']}: {row['cpu']}, {row['logical_cpus']} logical CPUs, "
          f"{row['memory_gib']} GiB, {row['system']}, {row['compiler']}")
    return 0


def parse_program_output(text):
    """Pulls the timings and determinants out of the assignment program's output."""
    values = {}

    def number(pattern):
        match = re.search(pattern, text, re.MULTILINE)
        return match.group(1) if match else ""

    values["generation_seconds"] = number(r"^Generation seconds ([0-9.]+)")
    values["product_seconds"] = number(r"^Product seconds ([0-9.]+)")
    values["total_seconds"] = number(r"^Total seconds ([0-9.]+)")
    for name in ("A", "B", "C"):
        match = re.search(
            rf"^det\({name}\) = (.*)\n(?:Coefficients .*\n)?Seconds ([0-9.]+)", text, re.MULTILINE)
        values[f"det_{name.lower()}"] = match.group(1).strip() if match else ""
        values[f"det_{name.lower()}_seconds"] = match.group(2) if match else ""
    verified = re.search(r"^Identity verified (\w+)", text, re.MULTILINE)
    values["verified"] = verified.group(1) if verified else ""
    return values


def command_sequential(arguments):
    command = arguments.command
    if command and command[0] == "--":
        command = command[1:]
    if not command:
        print("no program given", file=sys.stderr)
        return 64
    # The launcher sends the program's output straight to the log file, so a
    # long run can be followed with: tail -f <log>
    os.makedirs(os.path.dirname(os.path.abspath(arguments.log)), exist_ok=True)
    measured = subprocess.run([arguments.launcher, arguments.log] + command,
                              capture_output=True, text=True)
    fields = measured.stdout.split()
    if measured.returncode != 0 or len(fields) != 5:
        print(measured.stderr or "the launcher did not report a measurement", file=sys.stderr)
        return 1
    wall, user, system = fields[0], fields[1], fields[2]
    peak_mib = int(fields[3]) / 1024.0
    exit_code = int(fields[4])
    with open(arguments.log, encoding="utf-8", errors="replace") as log:
        output = log.read()
    row = {
        "label": arguments.label,
        "implementation": arguments.implementation,
        "size": arguments.size,
        "repeat": arguments.repeat,
        "wall_seconds": wall,
        "user_seconds": user,
        "system_seconds": system,
        "peak_rss_mib": f"{peak_mib:.1f}",
        "exit_code": exit_code,
        "finished": datetime.datetime.now().isoformat(timespec="seconds"),
    }
    row.update(parse_program_output(output))
    append_row(arguments.csv, SEQUENTIAL_COLUMNS, row)
    print(f"  {arguments.implementation} {arguments.size}: {float(wall):.1f} s, "
          f"{row['peak_rss_mib']} MiB, identity verified {row['verified'] or 'unknown'}")
    return 0 if exit_code == 0 else 1


def command_has(arguments):
    wanted = dict(item.split("=", 1) for item in arguments.where)
    for row in read_rows(arguments.csv):
        if all(row.get(key) == value for key, value in wanted.items()):
            return 0
    return 1


def command_merge(arguments):
    """Adds the rows of SOURCE that TARGET does not have yet.

    Machine descriptions (a file with a label but no size column) are replaced
    per label. Measurement rows are added unless the same row is already there.
    """
    incoming = read_rows(arguments.source)
    if not incoming:
        print(f"{arguments.source} has no rows", file=sys.stderr)
        return 1
    existing = read_rows(arguments.target)
    columns = list(incoming[0].keys())
    if existing and list(existing[0].keys()) != columns:
        print("the two files do not have the same columns", file=sys.stderr)
        return 1
    if "size" not in columns:
        labels = {row["label"] for row in incoming}
        merged = [row for row in existing if row["label"] not in labels] + incoming
        added = len(incoming)
    else:
        seen = {tuple(row.values()) for row in existing}
        fresh = [row for row in incoming if tuple(row.values()) not in seen]
        merged = existing + fresh
        added = len(fresh)
    write_rows(arguments.target, columns, merged)
    print(f"{added} rows from {arguments.source} are now in {arguments.target}")
    return 0


def test_results(junit):
    """[(test name, passed)] from the file `ctest --output-junit` writes."""
    results = []
    for case in xml.etree.ElementTree.parse(junit).getroot().iter("testcase"):
        passed = case.get("status") == "run" and case.find("failure") is None
        results.append((case.get("name", ""), passed))
    return results


def command_check_row(arguments):
    """Adds what one ctest run showed to a file of check rows.

    With --split-at the tests are counted in two groups, those whose name contains the
    given text ("new tests") and the others ("original tests"), one row for each.
    """
    results = test_results(arguments.junit)
    if not results:
        print(f"{arguments.junit} lists no tests", file=sys.stderr)
        return 1
    if arguments.split_at:
        groups = [(f"{arguments.check}: new tests",
                   [r for r in results if arguments.split_at in r[0]]),
                  (f"{arguments.check}: original tests",
                   [r for r in results if arguments.split_at not in r[0]])]
    else:
        groups = [(arguments.check, results)]
    for check, group in groups:
        failed = [name for name, passed in group if not passed]
        # Test names start with the library's prefix, which says nothing here.
        short = [name.split(".", 1)[1] if "." in name else name for name in failed]
        append_row(arguments.csv, CHECK_COLUMNS, {
            "label": arguments.label,
            "check": check,
            "compiler": arguments.compiler,
            "standard_library": arguments.standard_library,
            "build": arguments.build,
            "tests": len(group),
            "passed": len(group) - len(failed),
            "failed": len(failed),
            "failed_tests": ";".join(short),
            "detail": arguments.detail,
            "library_commit": arguments.commit,
            "recorded": datetime.date.today().isoformat(),
        })
        print(f"  {check}: {len(group) - len(failed)} of {len(group)} pass"
              + (f"; failing: {', '.join(short)}" if failed else ""))
    return 0


def command_check_store(arguments):
    """Puts the rows of one run into the results file, in place of the label's older rows.

    A complete run replaces everything the label had. A partial run (--partial) replaces
    only the rows for the same check, compiler, standard library and build.
    """
    fresh = read_rows(arguments.rows)
    if not fresh:
        print("no check produced a result, so the results file is left as it is",
              file=sys.stderr)
        return 1

    def key(row):
        return (row["check"], row["compiler"], row["standard_library"], row["build"])

    replaced = {key(row) for row in fresh}
    kept = [row for row in read_rows(arguments.csv)
            if row["label"] != arguments.label
            or (arguments.partial and key(row) not in replaced)]
    write_rows(arguments.csv, CHECK_COLUMNS, kept + fresh)
    print(f"{len(fresh)} rows for {arguments.label} are now in {arguments.csv}")
    # A failing test in a normal build is a problem. In the wrong-product check a failing
    # new test is the point, and none failing is the problem.
    status = 0
    for row in fresh:
        wrong = row["check"].startswith("wrong product")
        if not wrong and row["failed"] != "0":
            print(f"PROBLEM: {row['failed']} of {row['tests']} tests fail: {row['check']}, "
                  f"{row['compiler']}, {row['build']}")
            status = 1
        if row["check"] == "wrong product: new tests" and row["failed"] == "0":
            print("PROBLEM: no new test noticed the wrong product")
            status = 1
    return status


def command_wrong_product(arguments):
    """Edits a copy of the cached library so that one product is stored wrongly."""
    with open(arguments.header, encoding="utf-8") as handle:
        source = handle.read()
    if source.count(PRODUCT_LINE) != 1:
        print(f"{arguments.header} does not store products the way this check expects",
              file=sys.stderr)
        return 1
    wrong = WRONG_PRODUCT % {"a": arguments.a, "b": arguments.b}
    with open(arguments.header, "w", encoding="utf-8") as handle:
        handle.write(source.replace(PRODUCT_LINE, wrong + PRODUCT_LINE))
    return 0


def main():
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    commands = parser.add_subparsers(dest="name", required=True)

    machine = commands.add_parser("machine")
    machine.add_argument("--label", required=True)
    machine.add_argument("--csv", required=True)
    machine.set_defaults(run=command_machine)

    sequential = commands.add_parser("sequential")
    sequential.add_argument("--label", required=True)
    sequential.add_argument("--implementation", required=True)
    sequential.add_argument("--size", required=True)
    sequential.add_argument("--repeat", default="1")
    sequential.add_argument("--csv", required=True)
    sequential.add_argument("--log", required=True)
    sequential.add_argument("--launcher", required=True,
                            help="path to the algebra_measure program")
    sequential.add_argument("command", nargs=argparse.REMAINDER)
    sequential.set_defaults(run=command_sequential)

    has = commands.add_parser("has")
    has.add_argument("--csv", required=True)
    has.add_argument("where", nargs="+")
    has.set_defaults(run=command_has)

    merge = commands.add_parser("merge")
    merge.add_argument("source", help="result file copied from another machine")
    merge.add_argument("target", help="local result file to add its rows to")
    merge.set_defaults(run=command_merge)

    check_row = commands.add_parser("check-row")
    check_row.add_argument("--label", required=True)
    check_row.add_argument("--csv", required=True)
    check_row.add_argument("--junit", required=True)
    check_row.add_argument("--check", required=True)
    check_row.add_argument("--compiler", required=True)
    check_row.add_argument("--standard-library", default="")
    check_row.add_argument("--build", required=True)
    check_row.add_argument("--detail", default="")
    check_row.add_argument("--commit", default="")
    check_row.add_argument("--split-at", default="")
    check_row.set_defaults(run=command_check_row)

    check_store = commands.add_parser("check-store")
    check_store.add_argument("--label", required=True)
    check_store.add_argument("--rows", required=True)
    check_store.add_argument("--csv", required=True)
    check_store.add_argument("--partial", action="store_true")
    check_store.set_defaults(run=command_check_store)

    wrong_product = commands.add_parser("wrong-product")
    wrong_product.add_argument("header")
    wrong_product.add_argument("--a", type=int, required=True)
    wrong_product.add_argument("--b", type=int, required=True)
    wrong_product.set_defaults(run=command_wrong_product)

    arguments = parser.parse_args()
    return arguments.run(arguments)


if __name__ == "__main__":
    sys.exit(main())
