#!/usr/bin/env python3
"""Sums a `callgrind_annotate --threshold=100` listing into a few categories.

Usage: callgrind_buckets.py ANNOTATE_TXT OUTPUT_CSV

Each row of the listing gives the instructions executed by code whose source
line is in one file while running inside one function. Summing by file shows
which repository's source the instructions belong to. Summing by function
shows which routine was running.
"""
import csv
import re
import sys
from collections import defaultdict

ROW = re.compile(r"^\s*([\d,]+)\s+\(\s*[\d.]+%\)\s+(.*)$")

REPOSITORIES = [
    ("algebra/polynomials/", "polynomials"),
    ("algebra/rings/", "rings"),
    ("algebra/groups/", "groups"),
    ("algebra/finite_fields/", "finite fields"),
    ("algebra/matrices/", "matrices"),
    ("algebra/core/", "core"),
]


def source_of(path):
    for fragment, name in REPOSITORIES:
        if fragment in path:
            return name
    if "malloc" in path or "arena.c" in path:
        return "heap allocator (libc)"
    if "/c++/" in path:
        return "std::vector and other library headers"
    if path.endswith("main.cpp"):
        return "assignment program"
    if path.startswith("???"):
        return "operator new and delete"
    return "other"


def routine_of(text):
    function = text.split(" [/")[0].partition(":")[2].strip()
    if "divmod" in function:
        return "polynomial reduction (divmod)"
    if "Polynomial" in function and "::multiply" in function and "Matrix" not in function:
        return "polynomial multiplication"
    if "Polynomial" in function and ("::add" in function or "::negate" in function):
        return "polynomial add and negate"
    if ("malloc" in function or "free" in function or "operator new" in function
            or "operator delete" in function or function.startswith("0x")):
        return "heap allocation"
    if "Matrix" in function or "determinant" in function:
        return "matrix loops"
    return "other"


def main():
    by_source = defaultdict(int)
    by_routine = defaultdict(int)
    total = 0
    in_table = False
    with open(sys.argv[1], encoding="utf-8", errors="replace") as handle:
        for line in handle:
            if "file:function" in line:
                in_table = True
                continue
            if not in_table:
                continue
            if line.startswith("-- "):
                break
            match = ROW.match(line)
            if not match or match.group(2).strip() == "PROGRAM TOTALS":
                continue
            count = int(match.group(1).replace(",", ""))
            total += count
            by_source[source_of(match.group(2).split(":")[0])] += count
            by_routine[routine_of(match.group(2))] += count
    with open(sys.argv[2], "w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(["grouping", "category", "instructions", "percent"])
        for grouping, table in (("source", by_source), ("routine", by_routine)):
            for category, count in sorted(table.items(), key=lambda item: -item[1]):
                writer.writerow([grouping, category, count, f"{100.0 * count / total:.2f}"])
    print(f"{total:,} instructions summarised in {sys.argv[2]}")


if __name__ == "__main__":
    main()
