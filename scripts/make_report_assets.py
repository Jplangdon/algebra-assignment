#!/usr/bin/env python3
"""Turns the result files into the report's figures, tables and numbers.

    python3 scripts/make_report_assets.py
    python3 scripts/make_report_assets.py --sequential-label Lemmen --mpi-label cluster

Reads   results/*.csv
Writes  report/figures/*.pdf      figures for the paper
        slides/figures/*.png      the same figures sized for slides
        slides/data.json          the same results as data, for slides/make_slides.js
        report/generated/*.tex    tables and \\newcommand numbers used in the text

Nothing in the report is typed in by hand from the measurements: rerun this
script after new runs and recompile.  Needs matplotlib.
"""
import argparse
import csv
import json
import math
import re
import os
import statistics
import sys
from collections import defaultdict

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib.patches import FancyArrowPatch, FancyBboxPatch  # noqa: E402
from matplotlib.ticker import FuncFormatter, LogLocator, NullLocator  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RESULTS = os.path.join(ROOT, "results")
REPORT_FIGURES = os.path.join(ROOT, "report", "figures")
SLIDE_FIGURES = os.path.join(ROOT, "slides", "figures")
GENERATED = os.path.join(ROOT, "report", "generated")

# Colours. One fixed colour per thing that is plotted, the same in every figure.
SURFACE = "#ffffff"
INK = "#0b0b0b"
INK_SECONDARY = "#52514e"
INK_MUTED = "#898781"
GRID = "#e1e0d9"
BASELINE = "#c3c2b7"
ORIGINAL = "#2a78d6"        # the original library
CACHED = "#eb6834"          # the cached library, including the sequential reference
HASH_MAP = "#1baf7a"        # the std::unordered_map variant
# Process counts are an ordered scale, so they share one hue from light to dark.
PROCESS_RAMP = ["#86b6ef", "#3987e5", "#1c5cab", "#0d366b"]

README_REFERENCE = [
    # size, implementation, seconds, peak memory in GB (Apple M3 Max, one thread)
    (4000, "original", 6 * 3600 + 40 * 60, 2.6),
    (4000, "cached", 20 * 60 + 16, 0.53),
    (6000, "original", 22 * 3600 + 30 * 60, 5.8),
    (6000, "cached", 68 * 60, 1.2),
]


# ----------------------------------------------------------------------------
# Reading and summarising the result files
# ----------------------------------------------------------------------------

def read_csv(name):
    path = os.path.join(RESULTS, name)
    if not os.path.exists(path):
        return []
    with open(path, newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def number(text):
    try:
        return float(text)
    except (TypeError, ValueError):
        return None


def quartile(values, which):
    """First (1) or third (3) quartile; the value itself when there is only one."""
    if not values:
        return None
    if len(values) == 1:
        return values[0]
    return statistics.quantiles(values, n=4, method="inclusive")[which - 1]


def pick_label(rows, wanted, what):
    labels = sorted({row["label"] for row in rows})
    if not labels:
        return None
    if wanted:
        if wanted not in labels:
            sys.exit(f"no {what} results for label {wanted!r}; available: {', '.join(labels)}")
        return wanted
    # Default: the machine with the most measurements.
    return max(labels, key=lambda label: sum(1 for row in rows if row["label"] == label))


def summarise_sequential(rows, label):
    """{implementation: {size: {...medians...}}} for one machine."""
    grouped = defaultdict(list)
    for row in rows:
        if row["label"] == label and row.get("exit_code") == "0":
            grouped[(row["implementation"], int(row["size"]))].append(row)
    summary = defaultdict(dict)
    for (implementation, size), group in grouped.items():
        def median(column):
            values = [number(r[column]) for r in group if number(r[column]) is not None]
            return statistics.median(values) if values else None
        summary[implementation][size] = {
            "runs": len(group),
            "walls": sorted(number(r["wall_seconds"]) for r in group),
            "wall": median("wall_seconds"),
            "memory": max(number(r["peak_rss_mib"]) for r in group),
            "generation": median("generation_seconds"),
            "product": median("product_seconds"),
            "determinants": sum(median(c) or 0.0 for c in
                                ("det_a_seconds", "det_b_seconds", "det_c_seconds")),
            "verified": all(r["verified"] == "true" for r in group),
            "det_a": group[0]["det_a"],
            "det_b": group[0]["det_b"],
            "det_c": group[0]["det_c"],
        }
    return summary


def summarise_mpi(rows, label):
    """Medians per (processes, block, size) and the sequential median per size.

    Every run times the sequential and the MPI determinant one after the other on
    the same matrix. The ratio between them is therefore taken run by run and the
    median of those ratios is reported, which keeps slow moments of the machine
    from being counted against only one of the two programs.
    """
    rows = [row for row in rows if row["label"] == label and row["case"] == "random"]
    sequential = defaultdict(list)
    grouped = defaultdict(list)
    for row in rows:
        size = int(row["size"])
        if number(row["sequential_seconds"]) is not None:
            sequential[size].append(number(row["sequential_seconds"]))
        grouped[(int(row["processes"]), int(row["block"]), size)].append(row)
    summary = {}
    for key, group in grouped.items():
        def median(column):
            return statistics.median(number(r[column]) for r in group)
        pairs = [(number(r["sequential_seconds"]), number(r["mpi_seconds"])) for r in group]
        ratios = [before / after for before, after in pairs if before and after]
        own_sequential = [before for before, _ in pairs if before]
        summary[key] = {
            "samples": len(group),
            "mpi": median("mpi_seconds"),
            "sequential": statistics.median(own_sequential) if own_sequential else None,
            "ratio": statistics.median(ratios) if ratios else None,
            "ratio_low": quartile(ratios, 1),
            "ratio_high": quartile(ratios, 3),
            "wins": sum(1 for ratio in ratios if ratio > 1.0),
            "runs": len(ratios),
            "distribute": median("distribute_seconds"),
            "eliminate": median("eliminate_seconds"),
            "broadcast_wait": median("broadcast_seconds_max"),
            "update": median("update_seconds_max"),
            "panels": int(group[0]["panels"]),
            "broadcast_bytes": int(group[0]["broadcast_bytes"]),
            "distributed_bytes": int(group[0]["distributed_bytes"]),
            "nodes": max(int(r["nodes"]) for r in group),
            "all_match": all(r["match"] in ("yes", "") for r in group),
        }
    sequential_median = {size: statistics.median(values) for size, values in sequential.items()}
    return summary, sequential_median


# ----------------------------------------------------------------------------
# Formatting
# ----------------------------------------------------------------------------

def duration(seconds):
    """A time the way a person would say it."""
    if seconds is None:
        return "n/a"
    if seconds < 0.001:
        return f"{seconds * 1e6:.0f} µs"
    if seconds < 1:
        return f"{seconds * 1000:.0f} ms" if seconds >= 0.0995 else f"{seconds * 1000:.1f} ms"
    if seconds < 60:
        return f"{seconds:.1f} s"
    if seconds < 3600:
        minutes, rest = divmod(round(seconds), 60)
        return f"{minutes} min {rest:02d} s"
    hours, rest = divmod(round(seconds / 60), 60)
    return f"{hours} h {rest:02d} min"


def tex_duration(seconds):
    return duration(seconds).replace("µs", r"$\mu$s")


def seconds_cell(seconds):
    """Seconds with about three significant figures."""
    if seconds is None:
        return "--"
    if seconds >= 1000:
        return f"{seconds:,.0f}".replace(",", r"\,")
    if seconds >= 100:
        return f"{seconds:.0f}"
    if seconds >= 10:
        return f"{seconds:.1f}"
    if seconds >= 1:
        return f"{seconds:.2f}"
    return f"{seconds:.3f}"


def memory_cell(mib):
    if mib is None:
        return "--"
    return f"{mib:,.0f}".replace(",", r"\,") if mib >= 100 else f"{mib:.1f}"


def memory_text(mib):
    if mib is None:
        return "n/a"
    return f"{mib / 1024:.2f} GiB" if mib >= 1024 else f"{mib:.0f} MiB"


def ratio_text(value):
    if value is None:
        return "n/a"
    return f"{value:.0f}" if value >= 100 else f"{value:.1f}"


def tex_escape(text):
    replacements = {"&": r"\&", "%": r"\%", "_": r"\_", "#": r"\#", "$": r"\$",
                    "{": r"\{", "}": r"\}", "~": r"\textasciitilde{}",
                    "^": r"\textasciicircum{}", "\\": r"\textbackslash{}"}
    return "".join(replacements.get(character, character) for character in str(text))


def plain(tex):
    """The text of a generated LaTeX snippet without its markup, for the slides."""
    text = str(tex)
    for old, new in ((r"Table~\ref{tab:blocks}", "The table"), (r"$\mu$s", "µs"),
                     (r"$\times$", "×"), (r"\%", "%"), (r"\,", ","), ("~", " "),
                     (r"\&", "&"), (r"\_", "_"), (r"\textasciitilde{}", "~"), ("$", "")):
        text = text.replace(old, new)
    return re.sub(r"\s+", " ", text).strip()


def nanoseconds(value):
    """Whole nanoseconds from 10 up, one decimal below. Halves round up, as in a spreadsheet,
    so the report, the figures and the slide charts all show the same digits."""
    if value >= 10:
        return str(int(math.floor(value + 0.5)))
    return f"{math.floor(value * 10 + 0.5) / 10:.1f}"


def significant(value):
    if value >= 100:
        return f"{value:.0f}"
    if value >= 10:
        return f"{value:.1f}"
    return f"{value:.2f}"


def time_cell(seconds):
    """A time with three significant figures and its unit, for tables."""
    if seconds is None:
        return "--"
    for limit, scale, unit in ((1e-6, 1e9, "ns"), (1e-3, 1e6, r"$\mu$s"), (1.0, 1e3, "ms")):
        if seconds < limit:
            return f"{significant(seconds * scale)} {unit}"
    return f"{significant(seconds)} s"


def spread_text(spread):
    """How far apart two medians are: a percentage, or a factor when it is large."""
    if spread >= 1.0:
        return f"a factor of {1 + spread:.1f}"
    return f"{100 * spread:.0f}\\%"


def listing(items):
    """1, 2 and 4"""
    items = [str(item) for item in items]
    if len(items) <= 1:
        return "".join(items)
    return ", ".join(items[:-1]) + " and " + items[-1]


def write(path, text):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as handle:
        handle.write(text)


# ----------------------------------------------------------------------------
# Figures
# ----------------------------------------------------------------------------

class Style:
    """Sizes for one output medium."""

    def __init__(self, name, width, height, font, folder, extension, dpi):
        self.name = name
        self.width = width
        self.height = height
        self.font = font
        self.folder = folder
        self.extension = extension
        self.dpi = dpi
        self.line = 1.6 if name == "paper" else 2.6
        self.marker = 5.5 if name == "paper" else 9.0
        self.ring = 1.2 if name == "paper" else 2.0


PAPER = Style("paper", 3.45, 2.35, 7.5, REPORT_FIGURES, "pdf", 300)
SLIDE = Style("slide", 8.6, 4.5, 15.0, SLIDE_FIGURES, "png", 200)


def new_axes(style, height_factor=1.0):
    plt.rcParams.update({
        "font.family": "DejaVu Sans",
        "font.size": style.font,
        "axes.edgecolor": BASELINE,
        "axes.labelcolor": INK_SECONDARY,
        "axes.linewidth": 0.8,
        "xtick.color": INK_MUTED,
        "ytick.color": INK_MUTED,
        "xtick.labelcolor": INK_SECONDARY,
        "ytick.labelcolor": INK_SECONDARY,
        "text.color": INK,
        "pdf.fonttype": 42,
    })
    figure, axes = plt.subplots(figsize=(style.width, style.height * height_factor))
    figure.patch.set_facecolor(SURFACE)
    axes.set_facecolor(SURFACE)
    for side in ("top", "right", "left"):
        axes.spines[side].set_visible(False)
    axes.tick_params(length=0)
    axes.grid(True, axis="y", color=GRID, linewidth=0.6)
    axes.set_axisbelow(True)
    return figure, axes


def save(figure, style, name):
    os.makedirs(style.folder, exist_ok=True)
    path = os.path.join(style.folder, f"{name}.{style.extension}")
    figure.savefig(path, dpi=style.dpi, bbox_inches="tight", pad_inches=0.04,
                   facecolor=SURFACE)
    plt.close(figure)
    return path


def placeholder(style, name):
    """Stands in for a figure whose measurements do not exist yet, so the report compiles."""
    figure, axes = plt.subplots(figsize=(style.width, style.height * 0.6))
    figure.patch.set_facecolor(SURFACE)
    axes.axis("off")
    axes.text(0.5, 0.5, "Not measured yet", ha="center", va="center", color=INK_MUTED,
              fontsize=style.font, transform=axes.transAxes)
    return save(figure, style, name)


def plot_line(axes, style, xs, ys, colour, label):
    axes.plot(xs, ys, color=colour, linewidth=style.line, solid_capstyle="round",
              solid_joinstyle="round", marker="o", markersize=style.marker,
              markeredgecolor=SURFACE, markeredgewidth=style.ring, label=label, zorder=3)


def end_label(axes, style, x, y, text, above=False):
    """Labels the last point of a line: to its right, or above and to the left of it."""
    if above:
        axes.annotate(text, (x, y), xytext=(-3, 6), textcoords="offset points", va="bottom",
                      ha="right", color=INK_SECONDARY, fontsize=style.font, clip_on=False)
    else:
        axes.annotate(text, (x, y), xytext=(6, 0), textcoords="offset points", va="center",
                      ha="left", color=INK_SECONDARY, fontsize=style.font, clip_on=False)


def legend(axes, style, **options):
    defaults = {"frameon": False, "fontsize": style.font, "labelcolor": INK_SECONDARY,
                "handlelength": 1.6, "borderaxespad": 0.2}
    defaults.update(options)
    return axes.legend(**defaults)


def size_axis(axes, sizes):
    axes.set_xscale("log")
    axes.set_xticks(sizes)
    axes.set_xticklabels([str(size) for size in sizes])
    axes.minorticks_off()
    axes.set_xlabel("Matrix dimension N")


def thin_ticks(sizes, limit=7):
    """Keeps the tick labels from running into each other on a log axis."""
    sizes = sorted(sizes)
    if not sizes:
        return sizes
    gap = 1.6 if len(sizes) <= limit else 1.9
    kept = [sizes[0]]
    for size in sizes[1:]:
        if size / kept[-1] >= gap:
            kept.append(size)
        elif size == sizes[-1] and len(kept) > 1:
            kept[-1] = size     # the largest size is always labelled
    return kept


def plain_log_axis(axes):
    """Log scale on the y axis with ordinary numbers as labels: 0.1, 1, 10, 100."""
    axes.set_yscale("log")
    low, high = axes.get_ylim()
    subs = (1.0,) if high / low >= 300 else (1.0, 2.0, 5.0)
    axes.yaxis.set_major_locator(LogLocator(base=10, subs=subs))
    axes.yaxis.set_major_formatter(FuncFormatter(lambda value, _: f"{value:g}"))
    axes.yaxis.set_minor_locator(NullLocator())


def horizontal_bars(axes, style, labels, values, colour, value_text):
    thickness = 0.56
    positions = list(range(len(labels)))[::-1]
    axes.barh(positions, values, height=thickness, color=colour, zorder=3)
    axes.set_yticks(positions)
    axes.set_yticklabels(labels, color=INK_SECONDARY)
    axes.grid(False, axis="y")
    axes.grid(True, axis="x", color=GRID, linewidth=0.6)
    axes.spines["bottom"].set_visible(False)
    axes.spines["left"].set_visible(True)
    for position, value, text in zip(positions, values, value_text):
        axes.annotate(text, (value, position), xytext=(4, 0), textcoords="offset points",
                      va="center", ha="left", color=INK, fontsize=style.font)


def figure_dependencies(style):
    figure = plt.figure(figsize=(style.width, style.height * 0.95))
    figure.patch.set_facecolor(SURFACE)
    axes = figure.add_axes([0, 0, 1, 1])
    axes.set_xlim(0, 10)
    axes.set_ylim(0, 6.2)
    axes.axis("off")
    boxes = {
        "assignment": (5.0, 5.55, "algebra-assignment\n(product and determinants)"),
        "matrices": (2.3, 3.95, "algebra-matrices"),
        "fields": (7.2, 3.95, "algebra-finite-fields\n(the class we cache)"),
        "polynomials": (5.1, 2.3, "algebra-polynomials"),
        "rings": (8.6, 2.3, "algebra-rings"),
        "core": (3.0, 0.65, "algebra-core"),
        "groups": (8.6, 0.65, "algebra-groups"),
    }
    renderer = figure.canvas.get_renderer()
    edges = {}
    for key, (x, y, text) in boxes.items():
        highlighted = key == "fields"
        label = axes.text(x, y, text, ha="center", va="center", fontsize=style.font * 0.95,
                          color=INK, linespacing=1.2, zorder=3)
        extent = label.get_window_extent(renderer).transformed(axes.transData.inverted())
        left, right = extent.x0 - 0.24, extent.x1 + 0.24
        bottom, top = extent.y0 - 0.17, extent.y1 + 0.17
        axes.add_patch(FancyBboxPatch((left, bottom), right - left, top - bottom,
                                      boxstyle="round,pad=0,rounding_size=0.12",
                                      linewidth=1.4 if highlighted else 0.8,
                                      edgecolor=CACHED if highlighted else BASELINE,
                                      facecolor="#fdf1eb" if highlighted else SURFACE,
                                      zorder=2))
        edges[key] = (left, right, bottom, top)

    def arrow(source, target):
        sx, sy, _ = boxes[source]
        tx, ty, _ = boxes[target]
        s_left, s_right, s_bottom, _ = edges[source]
        t_left, t_right, _, t_top = edges[target]
        if sy > ty:
            start, finish = (sx, s_bottom), (tx, t_top)
        elif sx > tx:
            start, finish = (s_left, sy), (t_right, ty)
        else:
            start, finish = (s_right, sy), (t_left, ty)
        axes.add_patch(FancyArrowPatch(start, finish, arrowstyle="-|>", mutation_scale=7,
                                       linewidth=0.8, color=INK_MUTED, shrinkA=1.5,
                                       shrinkB=1.5, zorder=1))

    arrow("assignment", "matrices")
    arrow("assignment", "fields")
    arrow("fields", "polynomials")
    arrow("fields", "rings")
    arrow("rings", "groups")
    arrow("matrices", "core")
    arrow("polynomials", "core")
    arrow("groups", "core")
    return save(figure, style, "dependencies")


def figure_profile(style, profile):
    routines = [row for row in profile if row["grouping"] == "routine"]
    if not routines:
        return None
    labels = [row["category"] for row in routines]
    values = [float(row["percent"]) for row in routines]
    figure, axes = new_axes(style, 0.82)
    horizontal_bars(axes, style, labels, values, ORIGINAL, [f"{v:.1f}%" for v in values])
    axes.set_xlim(0, max(values) * 1.22)
    axes.set_xlabel("Share of executed instructions (%)")
    return save(figure, style, "profile_original")


def figure_lookup(style, lookup):
    if not lookup:
        return None
    patterns = [("add", "independent", "add"), ("multiply", "independent", "multiply"),
                ("multiply-add", "chained", "multiply then add,\neach add waits\nfor the last")]
    methods = [("original", "Original arithmetic", ORIGINAL),
               ("unordered_map", "std::unordered_map", HASH_MAP),
               ("table", "Table (this work)", CACHED)]
    cost = {(r["method"], r["operation"], r["pattern"]): float(r["ns_per_operation"])
            for r in lookup}
    figure, axes = new_axes(style, 1.12)
    thickness = 0.24
    largest = max(cost.values())
    for group, (operation, pattern, _) in enumerate(patterns):
        centre = len(patterns) - 1 - group
        for index, (method, label, colour) in enumerate(methods):
            value = cost.get((method, operation, pattern))
            if value is None:
                continue
            position = centre + (1 - index) * (thickness + 0.035)
            axes.barh(position, value, height=thickness, color=colour, zorder=3,
                      label=label if group == 0 else None)
            text = f"{nanoseconds(value)} ns"
            axes.annotate(text, (value, position), xytext=(4, 0), textcoords="offset points",
                          va="center", ha="left", color=INK, fontsize=style.font * 0.95)
    axes.set_yticks([len(patterns) - 1 - g for g in range(len(patterns))])
    axes.set_yticklabels([label for _, _, label in patterns], color=INK_SECONDARY)
    axes.grid(False, axis="y")
    axes.grid(True, axis="x", color=GRID, linewidth=0.6)
    axes.spines["bottom"].set_visible(False)
    axes.spines["left"].set_visible(True)
    axes.set_xlim(0, largest * 1.2)
    axes.set_xlabel("Time per operation (ns)")
    legend(axes, style, loc="lower right", bbox_to_anchor=(1.0, 1.0), ncol=3,
           columnspacing=1.0, handlelength=0.9, handletextpad=0.4)
    return save(figure, style, "lookup_cost")


def figure_runtime(style, sequential):
    original, cached = sequential.get("original", {}), sequential.get("cached", {})
    if not cached:
        return None
    figure, axes = new_axes(style)
    for data, colour, label in ((original, ORIGINAL, "Original"), (cached, CACHED, "Cached")):
        sizes = sorted(data)
        if sizes:
            plot_line(axes, style, sizes, [data[s]["wall"] for s in sizes], colour, label)
            end_label(axes, style, sizes[-1], data[sizes[-1]]["wall"],
                      duration(data[sizes[-1]]["wall"]), above=data is original)
    plain_log_axis(axes)
    size_axis(axes, thin_ticks(set(original) | set(cached)))
    axes.set_ylabel("Run time (s)")
    axes.margins(x=0.08, y=0.12)
    axes.set_xlim(right=axes.get_xlim()[1] * 1.45)
    legend(axes, style, loc="lower right")
    return save(figure, style, "runtime")


def figure_speedup(style, sequential):
    original, cached = sequential.get("original", {}), sequential.get("cached", {})
    sizes = sorted(set(original) & set(cached))
    if not sizes:
        return None
    speedups = [original[s]["wall"] / cached[s]["wall"] for s in sizes]
    figure, axes = new_axes(style, 0.9)
    plot_line(axes, style, sizes, speedups, CACHED, None)
    best = max(range(len(sizes)), key=lambda i: speedups[i])
    last = len(sizes) - 1
    # When the best size is next to the last one, the two centred labels overlap,
    # so push them apart.
    neighbours = best == last - 1
    for index in sorted({0, best, last}):
        if neighbours and index == best:
            offset, align = (-2, 7), "right"
        elif neighbours and index == last:
            offset, align = (2, 7), "left"
        else:
            offset, align = (0, 7), "center"
        axes.annotate(f"{speedups[index]:.1f}×", (sizes[index], speedups[index]),
                      xytext=offset, textcoords="offset points", ha=align, va="bottom",
                      color=INK, fontsize=style.font)
    size_axis(axes, thin_ticks(sizes))
    axes.set_ylabel("Original time / cached time")
    axes.set_ylim(0, max(speedups) * 1.22)
    axes.margins(x=0.08)
    if neighbours:
        # Room for the last label, which now sits to the right of its point.
        axes.set_xlim(right=axes.get_xlim()[1] * 1.18)
    return save(figure, style, "speedup")


def figure_memory(style, sequential):
    original, cached = sequential.get("original", {}), sequential.get("cached", {})
    if not cached:
        return None
    figure, axes = new_axes(style)
    for data, colour, label in ((original, ORIGINAL, "Original"), (cached, CACHED, "Cached")):
        sizes = sorted(data)
        if sizes:
            plot_line(axes, style, sizes, [data[s]["memory"] for s in sizes], colour, label)
            end_label(axes, style, sizes[-1], data[sizes[-1]]["memory"],
                      memory_text(data[sizes[-1]]["memory"]), above=data is original)
    plain_log_axis(axes)
    size_axis(axes, thin_ticks(set(original) | set(cached)))
    axes.set_ylabel("Peak memory (MiB)")
    axes.margins(x=0.08, y=0.12)
    axes.set_xlim(right=axes.get_xlim()[1] * 1.5)
    legend(axes, style, loc="lower right")
    return save(figure, style, "memory")


def cache_rates(cache):
    """size -> (share of pair slots filled, share of operations answered from the tables)."""
    rates = {}
    for row in cache:
        if row["phase"] != "determinants":
            continue
        size = int(row["size"])
        slots = 2 * int(row["pair_slots"])
        filled = int(row["sums_filled"]) + int(row["products_filled"])
        operations = int(row["adds"]) + int(row["multiplies"])
        rates[size] = (100.0 * filled / slots, 100.0 * (1 - filled / operations))
    return rates


def figure_cache(style, cache):
    rates = cache_rates(cache)
    if not rates:
        return None
    sizes = sorted(rates)
    figure, axes = new_axes(style, 0.95)
    plot_line(axes, style, sizes, [rates[s][0] for s in sizes], INK_MUTED,
              "Table slots filled")
    plot_line(axes, style, sizes, [rates[s][1] for s in sizes], CACHED,
              "Operations answered from a table")
    size_axis(axes, thin_ticks(sizes, 6))
    axes.set_ylabel("Percent")
    axes.set_ylim(0, 108)
    axes.set_yticks([0, 25, 50, 75, 100])
    axes.margins(x=0.06)
    legend(axes, style, loc="lower left", bbox_to_anchor=(0.0, 1.0), ncol=1)
    return save(figure, style, "cache_fill")


def mpi_series(summary, block):
    """{processes: {size: entry}} for one panel width."""
    series = defaultdict(dict)
    for (processes, entry_block, size), entry in summary.items():
        if entry_block == block:
            series[processes][size] = entry
    return series


def main_block(summary):
    """The panel width with the most measurements."""
    counts = defaultdict(int)
    for (_, block, _), entry in summary.items():
        counts[block] += entry["samples"]
    return max(counts, key=counts.get) if counts else None


def figure_mpi_speedup(style, summary):
    block = main_block(summary)
    if block is None:
        return None
    series = mpi_series(summary, block)
    figure, axes = new_axes(style)
    all_sizes = set()
    highest = 1.0
    for index, processes in enumerate(sorted(series)):
        colour = PROCESS_RAMP[min(index, len(PROCESS_RAMP) - 1)]
        own = [s for s in sorted(series[processes]) if series[processes][s]["ratio"]]
        if not own:
            continue
        ratios = [series[processes][s]["ratio"] for s in own]
        # The middle half of the individual runs, to show how steady each point is.
        axes.fill_between(own, [series[processes][s]["ratio_low"] for s in own],
                          [series[processes][s]["ratio_high"] for s in own],
                          color=colour, alpha=0.18, linewidth=0, zorder=1)
        all_sizes.update(own)
        highest = max(highest, max(series[processes][s]["ratio_high"] for s in own))
        label = "1 process" if processes == 1 else f"{processes} processes"
        plot_line(axes, style, own, ratios, colour, label)
        end_label(axes, style, own[-1], ratios[-1], f"{ratios[-1]:.2f}\u00d7")
    # The reference line stops at the last size, so it does not run through the end labels.
    axes.hlines(1.0, min(all_sizes), max(all_sizes), color=INK_SECONDARY, linewidth=0.8,
                zorder=2)
    size_axis(axes, thin_ticks(all_sizes, 6))
    axes.set_ylabel("Sequential time / MPI time")
    axes.set_ylim(0, highest * 1.08)
    axes.margins(x=0.06)
    axes.set_xlim(right=axes.get_xlim()[1] * 1.4)
    # Above the plot, where no line can run through it whatever the results look like.
    legend(axes, style, loc="lower left", bbox_to_anchor=(0.0, 1.0),
           ncol=min(len(series), 4), columnspacing=1.0, handlelength=1.3)
    return save(figure, style, "mpi_speedup")


# ----------------------------------------------------------------------------
# Tables and numbers for the text
# ----------------------------------------------------------------------------

def table(columns, header, rows, note=None):
    lines = [r"\begin{tabular}{" + columns + "}", r"\toprule", header + r" \\", r"\midrule"]
    lines += [row + r" \\" for row in rows]
    lines += [r"\bottomrule", r"\end{tabular}"]
    if note:
        lines.append(r"\\[2pt] {\footnotesize " + note + "}")
    return "\n".join(lines) + "\n"


def tidy_compiler(text):
    """'c++ (Ubuntu 13.3.0-6ubuntu2~24.04.1) 13.3.0' -> 'GCC 13.3.0'."""
    match = re.search(r"clang version (\d+(?:\.\d+)*)", text)
    if match:
        return ("Apple Clang " if "Apple" in text else "Clang ") + match.group(1)
    match = re.match(r"^(?:c\+\+|g\+\+|gcc)\s.*?(\d+\.\d+(?:\.\d+)?)\s*$", text)
    if match:
        return "GCC " + match.group(1)
    # 'c++ (GCC) 11.5.0 20240719 (Red Hat 11.5.0-5)' -> 'GCC 11.5.0'
    match = re.match(r"^(?:c\+\+|g\+\+|gcc)\s+\(GCC\)\s+(\d+\.\d+(?:\.\d+)?)", text)
    if match:
        return "GCC " + match.group(1)
    return text


def tidy_mpi(text):
    """'mpirun (Open MPI) 4.1.6' -> 'Open MPI 4.1.6'."""
    match = re.match(r"^mpirun \((.+)\) (\S+)", text)
    return f"{match.group(1)} {match.group(2)}" if match else text


def environments_table(environments, labels):
    rows = []
    for row in environments:
        if row["label"] in labels:
            tools = [tidy_compiler(row["compiler"])] if row["compiler"] else []
            if row["mpi"]:
                tools.append(tidy_mpi(row["mpi"]))
            rows.append(" & ".join([
                tex_escape(row["label"]),
                tex_escape(row["cpu"].replace("(R)", "").replace("(TM)", "")
                           + f", {row['logical_cpus']} CPUs, {row['memory_gib']} GiB"),
                tex_escape(row["system"] + ("; " + "; ".join(tools) if tools else "")),
            ]))
    if not rows:
        rows = [r"\multicolumn{3}{c}{No machine has been recorded yet.}"]
    return table(r"@{}l p{3.0cm} p{3.6cm}@{}", r"Label & Processor and memory & Software",
                 rows)


def sequential_table(sequential):
    original, cached = sequential.get("original", {}), sequential.get("cached", {})
    rows = []
    for size in sorted(set(original) | set(cached)):
        before, after = original.get(size), cached.get(size)
        speedup = before["wall"] / after["wall"] if before and after else None
        rows.append(" & ".join([
            f"{size}",
            seconds_cell(before["wall"]) if before else "--",
            seconds_cell(after["wall"]) if after else "--",
            (ratio_text(speedup) + r"$\times$") if speedup else "--",
            memory_cell(before["memory"]) if before else "--",
            memory_cell(after["memory"]) if after else "--",
        ]))
    if not rows:
        rows = [r"\multicolumn{6}{c}{No sequential measurements have been recorded yet.}"]
    return table(r"@{}r r r r r r@{}",
                 r"& \multicolumn{3}{c}{Run time (s)} & \multicolumn{2}{c}{Peak memory (MiB)} \\"
                 "\n" r"\cmidrule(lr){2-4}\cmidrule(l){5-6}" "\n"
                 r"$N$ & Original & Cached & Speedup & Original & Cached", rows)


def machines_block(sequential_rows):
    """A table that compares the machines. Empty unless several have sequential results."""
    rows = []
    for label in sorted({row["label"] for row in sequential_rows}):
        summary = summarise_sequential(sequential_rows, label)
        original, cached = summary.get("original", {}), summary.get("cached", {})
        both = sorted(set(original) & set(cached))
        if not both:
            continue
        size = both[-1]
        speedup = original[size]["wall"] / cached[size]["wall"]
        rows.append(" & ".join([
            tex_escape(label), str(size), seconds_cell(original[size]["wall"]),
            seconds_cell(cached[size]["wall"]), ratio_text(speedup) + r"$\times$",
            memory_cell(original[size]["memory"]), memory_cell(cached[size]["memory"]),
        ]))
    if len(rows) < 2:
        return "% Only one machine has sequential results, so there is nothing to compare.\n"
    body = table(r"@{}l r r r r r r@{}",
                 r"& & \multicolumn{3}{c}{Run time (s)} & \multicolumn{2}{c}{Memory (MiB)} \\"
                 "\n" r"\cmidrule(lr){3-5}\cmidrule(l){6-7}" "\n"
                 r"Machine & $N$ & Original & Cached & Speedup & Original & Cached", rows)
    return ("Table~\\ref{tab:machines} gives the same comparison for every machine the "
            "program was run on, at the largest size each of them ran with both libraries.\n\n"
            "\\begin{table}[t]\n"
            "  \\caption{Original and cached finite field on each machine.}\n"
            "  \\label{tab:machines}\n  \\centering\n  \\footnotesize\n"
            "  \\setlength{\\tabcolsep}{4pt}\n" + body + "\\end{table}\n")


def phases_table(sequential):
    rows = []
    for implementation in ("original", "cached"):
        data = sequential.get(implementation, {})
        if not data:
            continue
        size = max(data)
        entry = data[size]
        total = entry["wall"]
        rows.append(" & ".join([
            implementation.capitalize(), f"{size}",
            seconds_cell(entry["product"]), seconds_cell(entry["determinants"]),
            f"{100 * entry['product'] / total:.0f}\\%",
        ]))
    if not rows:
        rows = [r"\multicolumn{5}{c}{No sequential measurements have been recorded yet.}"]
    return table(r"@{}l r r r r@{}",
                 r"Library & $N$ & Product (s) & Three det. (s) & Product share", rows)


def reference_table(sequential):
    cached = sequential.get("cached", {})
    original = sequential.get("original", {})
    rows = []
    for size, implementation, seconds, gigabytes in README_REFERENCE:
        ours = (cached if implementation == "cached" else original).get(size)
        rows.append(" & ".join([
            f"{size}", implementation.capitalize(), tex_duration(seconds), f"{gigabytes:g} GB",
            tex_duration(ours["wall"]) if ours else "--",
            (f"{ours['memory'] / 1024:.2f} GiB" if ours else "--"),
        ]))
    return table(r"@{}r l r r r r@{}",
                 r"& & \multicolumn{2}{c}{Assignment text} & \multicolumn{2}{c}{Measured here} \\"
                 "\n" r"\cmidrule(lr){3-4}\cmidrule(l){5-6}" "\n"
                 r"$N$ & Library & Time & Memory & Time & Memory", rows)


def mpi_table(summary, sequential):
    """Sequential and MPI time per size. With many process counts only ratios are shown."""
    block = main_block(summary)
    if block is None:
        return table("c", "", [r"No MPI measurements have been recorded yet."]), []
    series = mpi_series(summary, block)
    process_counts = sorted(series)
    wide = len(process_counts) > 3

    def ratio_cell(entry):
        if entry is None or entry["ratio"] is None:
            return "--"
        text = f"{entry['ratio']:.2f}"
        return r"\textbf{" + text + "}" if is_faster(entry) else text

    if wide:
        most = process_counts[-1]
        header = (r"& & & \multicolumn{%d}{c}{Ratio with $p$ processes} \\" % len(process_counts)
                  + "\n" + r"\cmidrule(l){4-%d}" % (3 + len(process_counts)) + "\n"
                  + f"$N$ & Seq. & $p={most}$ & "
                  + " & ".join(f"$p={p}$" for p in process_counts))
        columns = "@{}r r r" + " r" * len(process_counts) + "@{}"
    else:
        header = r"$N$ & Seq."
        for processes in process_counts:
            header += f" & $p={processes}$ & ratio"
        columns = "@{}r r" + " r r" * len(process_counts) + "@{}"
    rows = []
    for size in sorted(sequential):
        cells = [f"{size}", time_cell(sequential[size])]
        if wide:
            entry = series[process_counts[-1]].get(size)
            cells.append(time_cell(entry["mpi"]) if entry else "--")
            cells += [ratio_cell(series[processes].get(size)) for processes in process_counts]
        else:
            for processes in process_counts:
                entry = series[processes].get(size)
                cells += [time_cell(entry["mpi"]) if entry else "--", ratio_cell(entry)]
        rows.append(" & ".join(cells))
    return table(columns, header, rows), process_counts


def block_widths(summary):
    """The process count that was run with several panel widths, the widths and the sizes."""
    by_processes = defaultdict(set)
    for (processes, block, _), _entry in summary.items():
        by_processes[processes].add(block)
    candidates = [p for p, blocks in by_processes.items() if len(blocks) > 1]
    if not candidates:
        return None, [], []
    processes = max(candidates)
    blocks = sorted(by_processes[processes])
    sizes = sorted({size for (p, block, size) in summary if p == processes
                    and all((processes, b, size) in summary
                            and summary[(processes, b, size)]["ratio"] for b in blocks)})
    if not sizes:
        return None, [], []
    return processes, blocks, sizes


def block_table(summary):
    """Sequential time over MPI time for each panel width. Higher is better."""
    processes, blocks, sizes = block_widths(summary)
    if processes is None:
        return None
    header = "$N$ & " + " & ".join(f"$b={block}$" for block in blocks)
    rows = []
    for size in sizes:
        ratios = [summary[(processes, block, size)]["ratio"] for block in blocks]
        best = max(ratios)
        cells = [f"{size}"] + [
            (r"\textbf{" + f"{r:.2f}" + "}") if r == best else f"{r:.2f}" for r in ratios]
        rows.append(" & ".join(cells))
    return table("@{}r" + " r" * len(blocks) + "@{}", header, rows)


def is_faster(entry):
    return entry["ratio"] is not None and entry["ratio"] > 1.0


def break_even(series):
    """First tested size at which MPI is faster, and the size from which it stays faster."""
    sizes = [s for s in sorted(series) if series[s]["ratio"] is not None]
    faster = [s for s in sizes if is_faster(series[s])]
    first = faster[0] if faster else None
    stays = None
    for size in reversed(sizes):
        if is_faster(series[size]):
            stays = size
        else:
            break
    return first, stays


class Numbers:
    def __init__(self):
        self.lines = ["% Generated by scripts/make_report_assets.py. Do not edit."]
        self.values = {}

    def add(self, name, value):
        self.lines.append(r"\newcommand{\%s}{%s}" % (name, value))
        self.values[name] = value

    def text(self):
        return "\n".join(self.lines) + "\n"


def main():
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--sequential-label", default="")
    parser.add_argument("--mpi-label", default="")
    arguments = parser.parse_args()

    environments = read_csv("environments.csv")
    sequential_rows = read_csv("sequential.csv")
    mpi_rows = read_csv("mpi.csv")
    profile = read_csv("profile_original.csv")
    cache = read_csv("cache_statistics.csv")
    lookup = read_csv("lookup_benchmark.csv")

    sequential_label = pick_label(sequential_rows, arguments.sequential_label, "sequential")
    mpi_label = pick_label(mpi_rows, arguments.mpi_label, "MPI")
    sequential = summarise_sequential(sequential_rows, sequential_label) if sequential_label else {}
    mpi, mpi_sequential = summarise_mpi(mpi_rows, mpi_label) if mpi_label else ({}, {})
    print(f"sequential results from: {sequential_label}")
    print(f"MPI results from:        {mpi_label}")

    for style in (PAPER, SLIDE):
        figure_dependencies(style)
        made = {
            "profile_original": figure_profile(style, profile),
            "lookup_cost": figure_lookup(style, lookup),
            "runtime": figure_runtime(style, sequential),
            "speedup": figure_speedup(style, sequential),
            "memory": figure_memory(style, sequential),
            "cache_fill": figure_cache(style, cache),
            "mpi_speedup": figure_mpi_speedup(style, mpi),
        }
        for name, path in made.items():
            if path is None:
                placeholder(style, name)

    labels = {label for label in (sequential_label, mpi_label) if label}
    labels |= {row["label"] for row in sequential_rows}
    write(os.path.join(GENERATED, "table_environments.tex"),
          environments_table(environments, labels))
    write(os.path.join(GENERATED, "machines.tex"), machines_block(sequential_rows))
    write(os.path.join(GENERATED, "table_sequential.tex"), sequential_table(sequential))
    write(os.path.join(GENERATED, "table_phases.tex"), phases_table(sequential))
    write(os.path.join(GENERATED, "table_reference.tex"), reference_table(sequential))
    mpi_tex, process_counts = mpi_table(mpi, mpi_sequential)
    write(os.path.join(GENERATED, "table_mpi.tex"), mpi_tex)
    block_tex = block_table(mpi)
    block_processes, block_list, block_sizes = block_widths(mpi)
    write(os.path.join(GENERATED, "table_blocks.tex"),
          block_tex or table("c", "", ["Only one panel width has been measured."]))

    numbers = Numbers()
    numbers.add("SequentialMachine", tex_escape(sequential_label or "none"))
    numbers.add("MpiMachine", tex_escape(mpi_label or "none"))

    # Instruction profile of the original program.
    routine = {row["category"]: float(row["percent"]) for row in profile
               if row["grouping"] == "routine"}
    field_share = sum(value for key, value in routine.items() if key != "matrix loops"
                      and key != "other")
    numbers.add("ProfileReduction", f"{routine.get('polynomial reduction (divmod)', 0):.0f}")
    numbers.add("ProfileHeap", f"{routine.get('heap allocation', 0):.0f}")
    numbers.add("ProfileMultiply", f"{routine.get('polynomial multiplication', 0):.0f}")
    numbers.add("ProfileMatrix", f"{routine.get('matrix loops', 0):.0f}")
    numbers.add("ProfileField", f"{field_share:.0f}")

    # Cost per operation.
    cost = {(r["method"], r["operation"], r["pattern"]): float(r["ns_per_operation"])
            for r in lookup}

    def ns(method, operation, pattern):
        value = cost.get((method, operation, pattern))
        return "n/a" if value is None else nanoseconds(value)

    for method, name in (("original", "Original"), ("unordered_map", "Map"), ("table", "Table")):
        numbers.add(f"Lookup{name}Add", ns(method, "add", "independent"))
        numbers.add(f"Lookup{name}Multiply", ns(method, "multiply", "independent"))
        numbers.add(f"Lookup{name}Chained", ns(method, "multiply-add", "chained"))
    chained_original = cost.get(("original", "multiply-add", "chained"))
    chained_map = cost.get(("unordered_map", "multiply-add", "chained"))
    chained_table = cost.get(("table", "multiply-add", "chained"))
    if chained_original and chained_map and chained_table:
        numbers.add("LookupChainedTableGain", ratio_text(chained_original / chained_table))
        if chained_map > chained_original:
            sentence = (f"In the chained pattern the hash map is slower than the original "
                        f"arithmetic it replaces ({nanoseconds(chained_map)}~ns against "
                        f"{nanoseconds(chained_original)}~ns)")
        else:
            sentence = (f"In the chained pattern the hash map is only "
                        f"{chained_original / chained_map:.1f} times faster than the original "
                        f"arithmetic ({nanoseconds(chained_map)}~ns against "
                        f"{nanoseconds(chained_original)}~ns)")
        numbers.add("LookupChainedMapSentence", sentence)
        if chained_map > chained_original:
            phrase = ("in the pattern of the matrix product it was slower than the original "
                      "arithmetic")
        else:
            phrase = ("in the pattern of the matrix product it was only "
                      f"{chained_original / chained_map:.1f} times faster than the original "
                      "arithmetic")
        numbers.add("LookupConclusionPhrase", phrase)
    else:
        numbers.add("LookupChainedTableGain", "n/a")
        numbers.add("LookupChainedMapSentence", "The hash map comparison has not been run")
        numbers.add("LookupConclusionPhrase", "it has not been measured here")

    # Cache behaviour.
    rates = cache_rates(cache)
    reached = [size for size in sorted(rates) if rates[size][1] >= 99.0]
    half = [size for size in sorted(rates) if rates[size][1] >= 50.0]
    numbers.add("CacheHitNinetyNineSize", str(reached[0]) if reached else "n/a")
    numbers.add("CacheHitHalfSize", str(half[0]) if half else "n/a")
    numbers.add("CacheHitAtHundred", f"{rates[100][1]:.0f}" if 100 in rates else "n/a")
    numbers.add("CacheFillAtHundred", f"{rates[100][0]:.0f}" if 100 in rates else "n/a")

    # Sequential before and after.
    original, cached = sequential.get("original", {}), sequential.get("cached", {})
    both = sorted(set(original) & set(cached))
    if both:
        largest = both[-1]
        speedups = {size: original[size]["wall"] / cached[size]["wall"] for size in both}
        best = max(speedups, key=speedups.get)
        numbers.add("SeqLargestBoth", str(largest))
        numbers.add("SeqOriginalAtLargest", tex_duration(original[largest]["wall"]))
        numbers.add("SeqCachedAtLargest", tex_duration(cached[largest]["wall"]))
        numbers.add("SeqSpeedupAtLargest", ratio_text(speedups[largest]))
        numbers.add("SeqBestSpeedup", ratio_text(speedups[best]))
        numbers.add("SeqBestSpeedupSize", str(best))
        numbers.add("SeqSmallestSize", str(both[0]))
        numbers.add("SeqSpeedupAtSmallest", ratio_text(speedups[both[0]]))
        smallest = both[0]
        times = (f"{seconds_cell(cached[smallest]['wall'])}~s against "
                 f"{seconds_cell(original[smallest]['wall'])}~s")
        if speedups[smallest] < 0.97:
            sentence = (f"at $N = {smallest}$ the cached program is even slower than the "
                        f"original ({times})")
        elif speedups[smallest] < 1.03:
            sentence = (f"at $N = {smallest}$ the two programs take about the same time "
                        f"({times})")
        else:
            sentence = (f"at $N = {smallest}$ the cached program is only "
                        f"{ratio_text(speedups[smallest])} times faster ({times})")
        numbers.add("SeqSmallestSentence", sentence)
        numbers.add("SeqOriginalMemoryAtLargest", memory_text(original[largest]["memory"]))
        numbers.add("SeqCachedMemoryAtLargest", memory_text(cached[largest]["memory"]))
        numbers.add("SeqMemoryRatioAtLargest",
                    ratio_text(original[largest]["memory"] / cached[largest]["memory"]))
        crossover = [s for s in both if cached[s]["memory"] < original[s]["memory"]]
        numbers.add("SeqMemoryCrossover", str(crossover[0]) if crossover else "n/a")
        identical = all(original[s][key] == cached[s][key] for s in both
                        for key in ("det_a", "det_b", "det_c"))
        numbers.add("SeqIdenticalSizes", listing(both))
        numbers.add("SeqIdenticalVerdict", "identical" if identical else "NOT identical")
        numbers.add("SeqOriginalProductShare",
                    f"{100 * original[largest]['product'] / original[largest]['wall']:.0f}")
        # Bytes per matrix entry, from how peak memory grows between the two largest sizes.
        # The program holds four N x N matrices at its peak.
        if len(original) >= 2:
            small, large = sorted(original)[-2:]
            growth = (original[large]["memory"] - original[small]["memory"]) * 1048576
            numbers.add("SeqOriginalBytesPerEntry",
                        f"{growth / (4 * (large ** 2 - small ** 2)):.0f}")
        else:
            numbers.add("SeqOriginalBytesPerEntry", "n/a")
        if not crossover:
            sentence = ("In our runs the cached program used more memory than the original "
                        "at every size we ran with both")
        elif crossover[0] == both[0]:
            sentence = ("In our runs the cached program used less memory than the original "
                        "at every size")
        else:
            sentence = ("For very small matrices the cached program therefore uses more "
                        "memory than the original; in our runs it uses less from "
                        f"$N = {crossover[0]}$ upward")
        numbers.add("SeqMemoryCrossoverSentence", sentence)
        # What the original would need at larger sizes if it keeps growing as N^3.
        top_original = max(original)
        if top_original >= 4000:
            note = ""
        else:
            estimate = original[top_original]["wall"] * (4000 / top_original) ** 3
            note = ("We did not run the original library at these sizes. If its run time "
                    f"keeps growing with $N^3$ from $N = {top_original}$, our largest run of "
                    f"it, the original would need about {tex_duration(estimate)} at "
                    "$N = 4000$ on this machine. That figure is an extrapolation, not a "
                    "measurement.")
        # Where a size from the assignment text was also run here, put the two side by side.
        for size, implementation, seconds, gigabytes in README_REFERENCE:
            ours = (cached if implementation == "cached" else original).get(size)
            if ours:
                note += (f" At $N = {size}$ the {implementation} program needs "
                         f"{tex_duration(ours['wall'])} and {ours['memory'] / 1024:.2f}~GiB "
                         f"here, against {tex_duration(seconds)} and {gigabytes:g}~GB in the "
                         "assignment text, which was measured on a different processor.")
        numbers.add("SeqReferenceNote", note.strip())
        entries = [entry for data in (original, cached) for entry in data.values()]
        runs = [entry["runs"] for entry in entries]
        if max(runs) == 1:
            phrase = "single runs"
        elif min(runs) == max(runs):
            phrase = f"{max(runs)} runs per size; the table gives the median"
        elif (min(runs), max(runs)) == (1, 2):
            phrase = "one or two runs per size; the table gives the median"
        else:
            phrase = f"{min(runs)} to {max(runs)} runs per size; the table gives the median"
        numbers.add("SeqRunsPhrase", phrase)
        # How far apart repeated runs of the same program and size are.
        short = [entry["walls"][-1] / entry["walls"][0] - 1 for entry in entries
                 if entry["runs"] > 1 and entry["wall"] < 10]
        long = [entry["walls"][-1] / entry["walls"][0] - 1 for entry in entries
                if entry["runs"] > 1 and entry["wall"] >= 10]
        if short and long:
            sentence = ("Where a size was run more than once, the slowest run took up to "
                        f"{spread_text(max(short))} longer than the fastest for runs under "
                        f"10~s, and up to {spread_text(max(long))} longer for longer runs.")
        elif short or long:
            sentence = ("Where a size was run more than once, the slowest run took up to "
                        f"{spread_text(max(short + long))} longer than the fastest.")
        else:
            sentence = ""
        numbers.add("SeqRepeatSentence", sentence)
    else:
        for name in ("SeqLargestBoth", "SeqOriginalAtLargest", "SeqCachedAtLargest",
                     "SeqSpeedupAtLargest", "SeqBestSpeedup", "SeqBestSpeedupSize",
                     "SeqSmallestSize", "SeqSpeedupAtSmallest", "SeqSmallestSentence",
                     "SeqOriginalMemoryAtLargest",
                     "SeqCachedMemoryAtLargest", "SeqMemoryRatioAtLargest",
                     "SeqMemoryCrossover", "SeqIdenticalSizes", "SeqIdenticalVerdict",
                     "SeqOriginalProductShare", "SeqOriginalBytesPerEntry", "SeqRunsPhrase"):
            numbers.add(name, "n/a")
        numbers.add("SeqRepeatSentence", "")
        numbers.add("SeqMemoryCrossoverSentence",
                    "The two libraries have not been run at a common size yet")
        numbers.add("SeqReferenceNote", "")
    if cached:
        top = max(cached)
        numbers.add("SeqLargestCached", str(top))
        numbers.add("SeqCachedAtLargestCached", tex_duration(cached[top]["wall"]))
        numbers.add("SeqCachedMemoryAtLargestCached", memory_text(cached[top]["memory"]))
        numbers.add("SeqCachedProductShare", f"{100 * cached[top]['product'] / cached[top]['wall']:.0f}")
        numbers.add("SeqAllVerified", "true" if all(e["verified"] for e in cached.values())
                    and all(e["verified"] for e in original.values()) else "false")
    else:
        for name in ("SeqLargestCached", "SeqCachedAtLargestCached",
                     "SeqCachedMemoryAtLargestCached", "SeqCachedProductShare", "SeqAllVerified"):
            numbers.add(name, "n/a")

    # MPI.
    block = main_block(mpi)
    if block is not None:
        series = mpi_series(mpi, block)
        parallel = {p: data for p, data in series.items() if p > 1}
        nodes = max(entry["nodes"] for entry in mpi.values())
        sizes = sorted(mpi_sequential)
        numbers.add("MpiBlock", str(block))
        numbers.add("MpiSizes", ", ".join(str(s) for s in sizes))
        numbers.add("MpiProcessCounts", listing(sorted(series)))
        numbers.add("MpiNodes", str(nodes))
        numbers.add("MpiAllMatch", "agreed" if all(e["all_match"] for e in mpi.values())
                    else "DID NOT agree")
        if nodes > 1:
            numbers.add("MpiNodesLimitation",
                        f"The processes ran on {nodes} machines of one cluster. Another "
                        "network, or other machines, will give a different break-even point.")
        else:
            numbers.add("MpiNodesLimitation",
                        "The break-even measurements were taken with all processes on one "
                        "machine. They have to be repeated across several machines before "
                        "they say anything about a network.")
        if nodes > 1:
            numbers.add("MpiNodesSentence",
                        f"The processes ran on up to {nodes} different machines, so the "
                        "broadcasts crossed the network")
        else:
            numbers.add("MpiNodesSentence",
                        "All processes ran on one machine, so the messages passed through "
                        "shared memory and not through a network. These figures therefore show "
                        "the smallest overhead the algorithm can have, and a run across several "
                        "machines will move the break-even point upward")
        if parallel:
            most = max(parallel)
            first, stays = break_even(parallel[most])
            ratios = {s: e["ratio"] for s, e in parallel[most].items() if e["ratio"]}
            best_size = max(ratios, key=ratios.get)
            numbers.add("MpiMostProcesses", str(most))
            numbers.add("MpiBestRatio", f"{ratios[best_size]:.2f}")
            numbers.add("MpiBestRatioSize", str(best_size))
            largest_entry = parallel[most][max(parallel[most])]
            numbers.add("MpiLargestSize", str(max(parallel[most])))
            numbers.add("MpiLargestSequential", tex_duration(mpi_sequential[max(parallel[most])]))
            numbers.add("MpiLargestTime", tex_duration(largest_entry["mpi"]))
            numbers.add("MpiLargestRatio", f"{largest_entry['ratio']:.2f}")
            numbers.add("MpiLargestPanels", str(largest_entry["panels"]))
            numbers.add("MpiLargestBroadcastMegabytes",
                        f"{largest_entry['broadcast_bytes'] / 1e6:.1f}")
            numbers.add("MpiLargestDistributedMegabytes",
                        f"{largest_entry['distributed_bytes'] / 1e6:.1f}")
            if first is None:
                sentence = (f"With {most} processes MPI was not faster than the sequential "
                            "program at any tested size")
            elif stays == first:
                sentence = (f"With {most} processes the smallest tested size at which MPI was "
                            f"faster is $N={first}$, and it stayed faster at every larger size")
            elif stays is not None:
                sentence = (f"With {most} processes MPI was first faster at $N={first}$, but "
                            f"below $N={stays}$ the result changes from one size to the next; "
                            f"from $N={stays}$ upward it was faster at every tested size")
            else:
                sentence = (f"With {most} processes MPI was first faster at $N={first}$ but "
                            "was not faster at the largest tested size")
            numbers.add("MpiBreakEvenSentence", sentence)
            numbers.add("MpiBreakEvenSize", str(first) if first else "none")
            numbers.add("MpiStaysFasterSize", str(stays) if stays else "none")
            # How consistently MPI won the individual runs from the break-even size on.
            wins = ""
            if stays is not None:
                above = [parallel[most][s] for s in sorted(parallel[most]) if s >= stays]
                if all(e["wins"] == e["runs"] for e in above):
                    wins = "From that size on, MPI also won every individual run."
                else:
                    worst = min(above, key=lambda e: e["wins"] / e["runs"])
                    wins = (f"From that size on, MPI won at least {worst['wins']} of the "
                            f"{worst['runs']} individual runs at each size.")
                below = [s for s in sorted(parallel[most]) if s < stays and s in mpi_sequential]
                if below and stays != first:
                    wins += (" Below it, one determinant takes "
                             f"{tex_duration(mpi_sequential[below[-1]])} or less, and the "
                             "two programs trade places from run to run.")
            numbers.add("MpiWinsSentence", wins)
            if 1 in series:
                same = [s for s in series[1] if s in parallel[most]]
                top = max(same)
                numbers.add("MpiParallelGain",
                            f"{series[1][top]['mpi'] / parallel[most][top]['mpi']:.2f}")
                one = series[1][top]["ratio"]
                numbers.add("MpiOneProcessRatio", f"{one:.2f}")
                if one > 1.03:
                    sentence = (f"At $N = {top}$ the single-process run is {one:.2f} times as "
                                "fast as the sequential program, without any parallelism.")
                elif one < 0.97:
                    sentence = (f"At $N = {top}$ the single-process run is slower than the "
                                f"sequential program, a ratio of {one:.2f}, which is the "
                                "price of the column layout and of the panel bookkeeping.")
                else:
                    sentence = (f"At $N = {top}$ the single-process run takes about as long "
                                f"as the sequential program, a ratio of {one:.2f}, so the "
                                "column layout by itself neither costs nor gains much.")
                numbers.add("MpiOneProcessSentence", sentence)
            else:
                numbers.add("MpiParallelGain", "n/a")
                numbers.add("MpiOneProcessRatio", "n/a")
                numbers.add("MpiOneProcessSentence", "")
        else:
            for name in ("MpiMostProcesses", "MpiBestRatio", "MpiBestRatioSize",
                         "MpiLargestSize", "MpiLargestSequential", "MpiLargestTime",
                         "MpiLargestRatio",
                         "MpiLargestPanels", "MpiLargestBroadcastMegabytes",
                         "MpiLargestDistributedMegabytes", "MpiBreakEvenSize",
                         "MpiStaysFasterSize", "MpiParallelGain", "MpiOneProcessRatio"):
                numbers.add(name, "n/a")
            numbers.add("MpiBreakEvenSentence",
                        "Only single-process MPI runs have been recorded so far")
            numbers.add("MpiWinsSentence", "")
            numbers.add("MpiOneProcessSentence", "")
    else:
        for name in ("MpiBlock", "MpiSizes", "MpiProcessCounts", "MpiNodes", "MpiAllMatch",
                     "MpiMostProcesses", "MpiBestRatio", "MpiBestRatioSize", "MpiLargestSize",
                     "MpiLargestSequential", "MpiLargestTime", "MpiLargestRatio",
                     "MpiLargestPanels",
                     "MpiLargestBroadcastMegabytes", "MpiLargestDistributedMegabytes",
                     "MpiBreakEvenSize", "MpiStaysFasterSize", "MpiParallelGain",
                     "MpiOneProcessRatio"):
            numbers.add(name, "n/a")
        numbers.add("MpiNodesSentence", "No MPI measurements have been recorded yet")
        numbers.add("MpiNodesLimitation", "No MPI measurements have been recorded yet.")
        numbers.add("MpiBreakEvenSentence", "No MPI measurements have been recorded yet")
        numbers.add("MpiWinsSentence", "")
        numbers.add("MpiOneProcessSentence", "")
    numbers.add("MpiBlockProcesses", str(block_processes) if block_processes else "n/a")

    # Time each process needs to fill its tables before the timed part.
    warm = [number(row["warm_seconds"]) for row in mpi_rows
            if row["label"] == mpi_label and row["warm"] == "1"]
    numbers.add("CacheWarmSeconds", f"{statistics.median(warm):.1f}" if warm else "n/a")

    # How often each configuration was timed.
    if block is not None:
        per_matrix = sorted({entry["samples"] // 2 for (_, b, _), entry in mpi.items()
                             if b == block})
        if len(per_matrix) == 1:
            times = {1: "once", 2: "twice"}.get(per_matrix[0], f"{per_matrix[0]} times")
            numbers.add("MpiRepeatsSentence",
                        f"Every configuration was timed {times} on each of the two matrices")
        else:
            numbers.add("MpiRepeatsSentence",
                        f"Every configuration was timed between {per_matrix[0]} and "
                        f"{per_matrix[-1]} times on each of the two matrices")
    else:
        numbers.add("MpiRepeatsSentence", "No configuration has been timed yet")

    # One sentence for the abstract.
    if block is not None and any(p > 1 for p in mpi_series(mpi, block)):
        series = mpi_series(mpi, block)
        most = max(series)
        first, stays = break_even(series[most])
        nodes = max(entry["nodes"] for entry in mpi.values())
        place = (f"across {nodes} machines" if nodes > 1 else
                 "on a single machine, where messages do not cross a network")
        if first is None:
            abstract = (f"With {most} processes {place}, the MPI program was not faster than "
                        "the cached sequential program at any size we tested.")
        else:
            abstract = (f"With {most} processes {place}, the MPI program is faster than the "
                        f"cached sequential program from $N = {stays or first}$ upward.")
    else:
        abstract = "The MPI program has not been timed on more than one process yet."
    numbers.add("MpiAbstractSentence", abstract)

    # How much the same sequential determinant varies between jobs on this machine.
    by_size = defaultdict(list)
    for (_, _, size), entry in mpi.items():
        if entry["sequential"]:
            by_size[size].append(entry["sequential"])
    short, long = [], []
    for size, values in by_size.items():
        if len(values) > 1:
            (long if mpi_sequential[size] >= 0.1 else short).append(max(values) / min(values) - 1)
    if short and long:
        numbers.add("MpiNoiseSentence",
                    "The same sequential determinant was timed in several jobs. The medians "
                    f"of those jobs differ by up to {spread_text(max(short))} for determinants "
                    f"shorter than 0.1~s and by up to {spread_text(max(long))} for longer "
                    "ones, so ratios close to 1 carry little meaning.")
    elif short or long:
        numbers.add("MpiNoiseSentence",
                    "The same sequential determinant was timed in several jobs, and the "
                    f"medians of those jobs differ by up to {spread_text(max(short + long))}, "
                    "so ratios close to 1 carry little meaning.")
    else:
        numbers.add("MpiNoiseSentence", "")

    # The MPI test script records how many configurations it ran.
    tests = read_csv("mpi_tests.csv")
    if tests:
        passed, failed = int(tests[0]["passed"]), int(tests[0]["failed"])
        numbers.add("MpiTestCount", str(passed + failed))
        numbers.add("MpiTestVerdict", "all of which pass" if failed == 0 else
                    f"of which {failed} FAIL")
    else:
        numbers.add("MpiTestCount", "many")
        numbers.add("MpiTestVerdict", "which have not been recorded for this report yet")

    # Panel widths.
    if block_processes:
        def width_ratios(size):
            return {b: mpi[(block_processes, b, size)]["ratio"] for b in block_list}
        top = block_sizes[-1]
        at_top = width_ratios(top)
        sentence = (r"Table~\ref{tab:blocks} repeats the measurement for other panel widths. "
                    f"At $N = {top}$ the ratio lies between {min(at_top.values()):.2f} and "
                    f"{max(at_top.values()):.2f} for all {len(block_list)} widths.")
        widest = max(block_sizes, key=lambda size: max(width_ratios(size).values())
                     / min(width_ratios(size).values()))
        if widest != top:
            there = width_ratios(widest)
            worst, best = min(there, key=there.get), max(there, key=there.get)
            sentence += (f" The choice matters most at $N = {widest}$, where $b = {worst}$ "
                         f"reaches {there[worst]:.2f} and $b = {best}$ reaches "
                         f"{there[best]:.2f}.")
        numbers.add("MpiBlockSentence", sentence)
    else:
        numbers.add("MpiBlockSentence", "Only one panel width has been measured so far.")

    # Does the gain of the single-process MPI run depend on the panel width?
    one_widths = sorted({b for (processes, b, _) in mpi if processes == 1})
    sentence = ""
    if len(one_widths) > 1:
        common = sorted({s for (processes, b, s) in mpi if processes == 1 and all(
            (1, w, s) in mpi and mpi[(1, w, s)]["ratio"] for w in one_widths)})
        if common:
            top = common[-1]
            at_top = {w: mpi[(1, w, top)]["ratio"] for w in one_widths}
            narrowest, best = one_widths[0], max(at_top, key=at_top.get)
            lowest_everywhere = all(
                mpi[(1, narrowest, s)]["ratio"] <= min(mpi[(1, w, s)]["ratio"]
                                                       for w in one_widths[1:]) + 0.005
                for s in common)
            if lowest_everywhere and best != narrowest:
                sentence = (f"With one process the ratio was lowest for $b = {narrowest}$ at "
                            f"every size where we compared widths. At $N = {top}$ it is "
                            f"{at_top[narrowest]:.2f} for $b = {narrowest}$ and "
                            f"{at_top[best]:.2f} for $b = {best}$. That fits a column staying "
                            "in the processor's cache while several steps are applied to it.")
            else:
                sentence = (f"With one process and $N = {top}$ the ratio lies between "
                            f"{min(at_top.values()):.2f} and {max(at_top.values()):.2f} for "
                            f"panel widths from {one_widths[0]} to {one_widths[-1]}, without "
                            "a clear order.")
    numbers.add("MpiOneProcessWidthSentence", sentence)

    # The sequential reference inside the MPI program against the assignment program itself.
    common = sorted(set(cached) & set(mpi_sequential)) if cached else []
    if common and sequential_label == mpi_label:
        top = common[-1]
        program = cached[top]["determinants"] / 3
        reference = mpi_sequential[top]
        verdict = ("so the reference used here is the faster of the two and the comparison "
                   "is the stricter one for MPI" if reference < program else
                   "so the reference used here is not faster than the program itself")
        numbers.add("MpiReferenceSentence",
                    f"At $N = {top}$ the assignment program needs {tex_duration(program)} for "
                    f"one determinant and the reference {tex_duration(reference)}, {verdict}.")
    else:
        numbers.add("MpiReferenceSentence",
                    "The two were not timed on the same machine, so we do not compare them.")

    write(os.path.join(GENERATED, "numbers.tex"), numbers.text())

    # The same results as plain data, for the slide generator (slides/make_slides.js).
    def described(label):
        for row in environments:
            if row["label"] == label:
                cpu = row["cpu"].replace("(R)", "").replace("(TM)", "")
                return (f"{cpu}, {row['logical_cpus']} CPUs, {row['memory_gib']} GiB, "
                        f"{row['system']}")
        return ""

    all_sizes = sorted(set(original) | set(cached))
    deck = {
        "machines": {
            "sequential": sequential_label or "", "mpi": mpi_label or "",
            "sequential_description": described(sequential_label),
            "mpi_description": described(mpi_label),
        },
        "profile": {
            "categories": [row["category"] for row in profile if row["grouping"] == "routine"],
            "percent": [float(row["percent"]) for row in profile if row["grouping"] == "routine"],
        },
        "lookup": {
            "groups": ["add", "multiply", "multiply then add (chained)"],
            "series": [
                {"name": name, "values": [cost.get((method, operation, pattern))
                                          for operation, pattern in (("add", "independent"),
                                                                     ("multiply", "independent"),
                                                                     ("multiply-add", "chained"))]}
                for method, name in (("original", "Original arithmetic"),
                                     ("unordered_map", "std::unordered_map"),
                                     ("table", "Table"))],
        },
        "sequential": {
            "sizes": all_sizes,
            "original_seconds": [original[s]["wall"] if s in original else None for s in all_sizes],
            "cached_seconds": [cached[s]["wall"] if s in cached else None for s in all_sizes],
            "original_mib": [original[s]["memory"] if s in original else None for s in all_sizes],
            "cached_mib": [cached[s]["memory"] if s in cached else None for s in all_sizes],
            "speedup": [original[s]["wall"] / cached[s]["wall"]
                        if s in original and s in cached else None for s in all_sizes],
        },
        "cache": {
            "sizes": sorted(rates),
            "slots_filled": [rates[s][0] for s in sorted(rates)],
            "answered": [rates[s][1] for s in sorted(rates)],
        },
        "mpi": {"block": block, "sizes": [], "sequential_seconds": [], "series": []},
        "text": {name: plain(value) for name, value in numbers.values.items()},
    }
    if block is not None:
        series = mpi_series(mpi, block)
        sizes = sorted(mpi_sequential)
        deck["mpi"]["sizes"] = sizes
        deck["mpi"]["sequential_seconds"] = [mpi_sequential[s] for s in sizes]
        for processes in sorted(series):
            entries = [series[processes].get(s) for s in sizes]
            deck["mpi"]["series"].append({
                "processes": processes,
                "seconds": [e["mpi"] if e else None for e in entries],
                "ratio": [e["ratio"] if e else None for e in entries],
            })
    write(os.path.join(ROOT, "slides", "data.json"), json.dumps(deck, indent=1) + "\n")

    print(f"figures: {REPORT_FIGURES} and {SLIDE_FIGURES}")
    print(f"tables and numbers: {GENERATED}")
    print(f"data for the slides: {os.path.join(ROOT, 'slides', 'data.json')}")


if __name__ == "__main__":
    main()
