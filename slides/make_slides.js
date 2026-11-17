// Builds slides/presentation.pptx from slides/data.json.
//
//     node slides/make_slides.js
//
// slides/data.json is written by scripts/make_report_assets.py from the files in
// results/, so the numbers and charts on the slides are the same ones the report
// uses. After new measurements: run that script, then this one.
//
// Needs Node.js and the pptxgenjs package (npm install pptxgenjs, in this folder).
// Running this again replaces presentation.pptx, including any edits made to it
// by hand in PowerPoint. Keep hand-edited decks under another file name.
const fs = require("fs");
const path = require("path");
const pptxgen = require("pptxgenjs");
// jszip is installed together with pptxgenjs.
const JSZip = require(require.resolve("jszip", { paths: [require.resolve("pptxgenjs")] }));

const HERE = __dirname;
const data = JSON.parse(fs.readFileSync(path.join(HERE, "data.json"), "utf8"));
const T = data.text;
const OUTPUT = path.join(HERE, "presentation.pptx");

// ---------------------------------------------------------------------------
// Theme. The chart colours are the ones the report's figures use:
// orange for the cached library, blue for the original, green for the hash map.
// ---------------------------------------------------------------------------
const THEME = {
  name: "Finite field determinants",
  headFontFace: "Cambria",
  bodyFontFace: "Calibri",
  colors: {
    dk1: "14181F", lt1: "FFFFFF", dk2: "10243E", lt2: "F1F3F6",
    accent1: "EB6834", accent2: "2A78D6", accent3: "1BAF7A",
    accent4: "86B6EF", accent5: "1C5CAB", accent6: "0D366B",
    hlink: "1C5CAB", folHlink: "6B4E9B",
  },
};
const HEX = {
  cached: THEME.colors.accent1, original: THEME.colors.accent2, map: THEME.colors.accent3,
  ramp: ["86B6EF", "3987E5", "1C5CAB", "0D366B"],
  axis: "52514E", grid: "E1E0D9", ink: THEME.colors.dk1, white: "FFFFFF",
};
const MONO = "Courier New";

const pres = new pptxgen();
pres.layout = "LAYOUT_WIDE";            // 13.33 x 7.5 inches
pres.theme = { headFontFace: THEME.headFontFace, bodyFontFace: THEME.bodyFontFace };
pres.title = "Caching Finite Field Arithmetic and Distributing Determinants with MPI";
pres.author = "Diego Chequer, Bishoy Hana, Jacob Papu-Langdon, varshika";
pres.company = "University of Louisville";
pres.subject = "CSE 625 Parallel Programming";
const C = pres.SchemeColor;
const W = 13.333;
const LEFT = 0.6;
const WIDTH = W - 2 * LEFT;
const TOP = 1.8;                         // where the content of a slide starts

// ---------------------------------------------------------------------------
// Layouts
// ---------------------------------------------------------------------------
pres.defineSlideMaster({
  title: "Opening",
  background: { color: C.text2 },
  objects: [
    { placeholder: { options: { name: "title", type: "title", x: 0.9, y: 1.7, w: 11.5, h: 2.4,
        fontSize: 42, bold: true, color: C.background1, align: "left", valign: "bottom", margin: 0 },
      text: "" } },
    { placeholder: { options: { name: "body", type: "body", x: 0.9, y: 4.45, w: 11.5, h: 1.5,
        fontSize: 20, color: C.background2, align: "left", valign: "top", margin: 0 },
      text: "" } },
  ],
});
pres.defineSlideMaster({
  title: "Content",
  background: { color: C.background1 },
  objects: [
    { placeholder: { options: { name: "title", type: "title", x: LEFT, y: 0.45, w: WIDTH, h: 1.15,
        fontSize: 32, bold: true, color: C.text1, align: "left", valign: "top", margin: 0 },
      text: "" } },
    { text: { text: "Finite field determinants  ·  CSE 625",
        options: { x: LEFT, y: 6.95, w: 6, h: 0.3, fontSize: 10, color: C.text1, transparency: 45,
          margin: 0, isTextBox: true } } },
  ],
  slideNumber: { x: W - LEFT - 0.8, y: 6.95, w: 0.8, h: 0.3, fontSize: 10, color: C.text1,
    align: "right" },
});
pres.defineSlideMaster({
  title: "Closing",
  background: { color: C.text2 },
  objects: [
    { placeholder: { options: { name: "title", type: "title", x: LEFT, y: 0.45, w: WIDTH, h: 1.15,
        fontSize: 32, bold: true, color: C.background1, align: "left", valign: "top", margin: 0 },
      text: "" } },
  ],
  slideNumber: { x: W - LEFT - 0.8, y: 6.95, w: 0.8, h: 0.3, fontSize: 10, color: C.background2,
    align: "right" },
});

// ---------------------------------------------------------------------------
// Building blocks
// ---------------------------------------------------------------------------
let currentSection = "";
function section(title) {
  pres.addSection({ title });
  currentSection = title;
}
function contentSlide(title, notes, layout = "Content") {
  const slide = pres.addSlide({ masterName: layout, sectionTitle: currentSection });
  slide.addText(title, { placeholder: "title" });
  slide.addNotes(notes);
  return slide;
}
let shapeCount = 0;
function name(kind) {
  shapeCount += 1;
  return `${kind} ${shapeCount}`;
}
function text(slide, content, options) {
  slide.addText(content, { isTextBox: true, margin: 0, fontSize: 16, color: C.text1, valign: "top",
    objectName: name("Text"), ...options });
}
function card(slide, x, y, w, h, fill = C.background2) {
  slide.addShape(pres.shapes.ROUNDED_RECTANGLE, { x, y, w, h, rectRadius: 0.12,
    fill: { color: fill }, line: { type: "none" }, objectName: name("Card") });
}
// The largest size at which a figure still fits on one line of the given width.
function figureSize(figure, width) {
  const length = (typeof figure === "string" ? figure
    : figure.map((run) => run.text).join("")).length;
  for (const size of [34, 30, 26, 22]) {
    if (length * size * 0.0064 <= width) return size;
  }
  return 20;
}
// A card with a large figure and a line of explanation under it.
function stat(slide, x, y, w, h, figure, label, options = {}) {
  card(slide, x, y, w, h, options.fill || C.background2);
  const pad = 0.25;
  const figureHeight = options.figureHeight || 0.8;
  text(slide, figure, { x: x + pad, y: y + 0.2, w: w - 2 * pad, h: figureHeight,
    fontSize: options.figureSize || figureSize(figure, w - 2 * pad), bold: true,
    fontFace: THEME.headFontFace,
    color: options.color || C.accent1, valign: "mid" });
  text(slide, label, { x: x + pad, y: y + 0.2 + figureHeight, w: w - 2 * pad,
    h: h - figureHeight - 0.35, fontSize: options.labelSize || 14,
    color: options.labelColor || C.text1 });
}
// A card with a bold heading and a sentence.
function note(slide, x, y, w, h, heading, body, options = {}) {
  card(slide, x, y, w, h, options.fill || C.background2);
  const pad = 0.25;
  text(slide, heading, { x: x + pad, y: y + 0.2, w: w - 2 * pad, h: 0.4, fontSize: 16, bold: true,
    color: options.headingColor || C.text1 });
  text(slide, body, { x: x + pad, y: y + 0.65, w: w - 2 * pad, h: h - 0.8,
    fontSize: options.bodySize || 14, color: options.bodyColor || C.text1 });
}
// A numbered step: a filled circle with the number, then heading and sentence.
function step(slide, x, y, w, h, number, heading, body) {
  card(slide, x, y, w, h);
  slide.addShape(pres.shapes.OVAL, { x: x + 0.25, y: y + 0.25, w: 0.55, h: 0.55,
    fill: { color: C.accent1 }, line: { type: "none" }, objectName: name("Step") });
  text(slide, String(number), { x: x + 0.25, y: y + 0.25, w: 0.55, h: 0.55, fontSize: 18,
    bold: true, color: C.background1, align: "center", valign: "mid" });
  text(slide, heading, { x: x + 1.0, y: y + 0.2, w: w - 1.25, h: 0.4, fontSize: 16, bold: true });
  text(slide, body, { x: x + 1.0, y: y + 0.62, w: w - 1.25, h: h - 0.75, fontSize: 14 });
}
// A straight arrow from one point to another.
function arrow(slide, x1, y1, x2, y2, color = C.text1) {
  slide.addShape(pres.shapes.LINE, {
    x: Math.min(x1, x2), y: Math.min(y1, y2), w: Math.abs(x2 - x1), h: Math.abs(y2 - y1),
    flipH: x2 < x1, flipV: y2 < y1,
    line: { color, width: 1.5, endArrowType: "triangle", transparency: 35 },
    objectName: name("Arrow") });
}
function box(slide, x, y, w, h, label, options = {}) {
  slide.addShape(pres.shapes.ROUNDED_RECTANGLE, { x, y, w, h, rectRadius: 0.1,
    fill: { color: options.fill || C.background1 },
    line: { color: options.line || C.text1, width: options.lineWidth || 1,
      transparency: options.line ? 0 : 70 },
    objectName: name("Box") });
  text(slide, label, { x: x + 0.12, y, w: w - 0.24, h, fontSize: options.fontSize || 14,
    align: "center", valign: "mid", bold: !!options.bold, color: options.color || C.text1,
    fontFace: options.fontFace });
}

// Options shared by every chart, so axes and labels look the same on each.
const CHART = {
  catAxisLabelColor: HEX.axis, valAxisLabelColor: HEX.axis,
  catAxisLabelFontSize: 12, valAxisLabelFontSize: 12,
  catAxisLabelFontFace: "+mn-lt", valAxisLabelFontFace: "+mn-lt",
  catAxisTitleColor: HEX.axis, valAxisTitleColor: HEX.axis,
  catAxisTitleFontSize: 12, valAxisTitleFontSize: 12,
  catAxisTitleFontFace: "+mn-lt", valAxisTitleFontFace: "+mn-lt",
  legendFontFace: "+mn-lt", legendFontSize: 12, legendColor: HEX.axis,
  dataLabelFontFace: "+mn-lt", dataLabelFontSize: 12, dataLabelColor: HEX.ink,
  valGridLine: { color: HEX.grid, size: 0.75 }, catGridLine: { style: "none" },
};
// Horizontal bars with the value written at the end of each bar.
function barChart(slide, place, categories, series, options = {}) {
  slide.addChart(pres.charts.BAR,
    series.map((s) => ({ name: s.name, labels: categories, values: s.values })), {
      ...CHART, ...place, barDir: "bar", barGrouping: "clustered",
      barGapWidthPct: options.gap || 45, barOverlapPct: -8,
      chartColors: series.map((s) => s.color),
      catAxisOrientation: "maxMin", valAxisHidden: true, valGridLine: { style: "none" },
      valAxisMinVal: 0, valAxisMaxVal: options.max,
      showValue: true, dataLabelPosition: "outEnd", dataLabelFormatCode: options.format,
      showLegend: series.length > 1, legendPos: "t",
      objectName: name("Chart"),
    });
}
// Lines over matrix dimension, with the dimension on a logarithmic axis.
function sizeChart(slide, place, sizes, series, options = {}) {
  const rows = [{ name: "N", values: sizes }].concat(
    series.map((s) => ({ name: s.name, values: s.values })));
  slide.addChart(pres.charts.SCATTER, rows, {
    ...CHART, ...place,
    chartColors: series.map((s) => s.color),
    lineSize: 2.5, lineDataSymbol: "circle", lineDataSymbolSize: 8,
    lineDataSymbolLineColor: HEX.white, lineDataSymbolLineSize: 1,
    displayBlanksAs: "gap",
    catAxisMinVal: options.minSize, catAxisMaxVal: options.maxSize,
    valAxisMinVal: options.min, valAxisMaxVal: options.max,
    valAxisMajorUnit: options.unit, valAxisLogScaleBase: options.log ? 10 : undefined,
    valAxisLabelFormatCode: options.format || "General", catAxisLabelFormatCode: "General",
    showCatAxisTitle: true, catAxisTitle: "Matrix dimension N",
    showValAxisTitle: true, valAxisTitle: options.title,
    showLegend: series.length > 1, legendPos: "t",
    objectName: name("Chart"),
  });
}
// The power of ten at or below (above) a value, for the ends of a log axis.
const floor10 = (value) => Math.pow(10, Math.floor(Math.log10(value)));
const ceil10 = (value) => Math.pow(10, Math.ceil(Math.log10(value)));
// The right end of a size axis: a round number a little past the largest size.
function sizeLimit(sizes) {
  const target = Math.max(...sizes) * 1.25;
  const decade = floor10(target);
  for (const step of [1, 2, 2.5, 5, 10]) {
    if (step * decade >= target) return step * decade;
  }
  return 10 * decade;
}
const present = (values) => values.filter((value) => value !== null && value !== undefined);
const known = (value) => value !== undefined && value !== "n/a" && value !== "none" && value !== "";

// ---------------------------------------------------------------------------
// Slides
// ---------------------------------------------------------------------------
section("The problem");
{
  const slide = pres.addSlide({ masterName: "Opening", sectionTitle: currentSection });
  slide.addText("Caching Finite Field Arithmetic and Distributing Determinants with MPI",
    { placeholder: "title" });
  slide.addText([
    { text: "Diego Chequer  ·  Bishoy Hana  ·  Jacob Papu-Langdon  ·  varshika",
      options: { breakLine: true } },
    { text: "CSE 625 Parallel Programming, University of Louisville" },
  ], { placeholder: "body" });
  slide.addNotes(
    "Two parts. First we made the program faster on one core by caching the finite field " +
    "arithmetic. Then we used MPI for the determinants and measured when it pays off.");
}
{
  const slide = contentSlide("The same 1.77 million calculations, over and over",
    "The program builds two N by N matrices A and B, multiplies them, and takes three " +
    "determinants to check that det(AB) = det(A) det(B). Every matrix entry is an element of " +
    "the finite field with 11 cubed = 1331 elements. The library stores an element as a " +
    "polynomial of degree below 3 with coefficients modulo 11. To multiply two elements it " +
    "multiplies the polynomials and then divides by the fixed polynomial x^3 + x + 4 and keeps " +
    "the remainder. That is real work every time. The product needs N^3 multiplications and " +
    "N^3 additions, and each determinant about N^3/3 multiplications, negations and " +
    "additions, so about 5 N^3 operations in total: 3.2 x 10^11 for N = 4000. But there are " +
    "only 1331 elements, so only 1331 x 1331 = 1,771,561 different pairs can ever be " +
    "multiplied. Each pair is recomputed about 72,000 times. That is what caching is for.");
  text(slide, [
    { text: "C = A × B, then det(A), det(B) and det(C), over the field with 11", options: {} },
    { text: "3", options: { superscript: true } },
    { text: " = 1331 elements.", options: { breakLine: true } },
    { text: "An element is a polynomial. Every add and multiply is polynomial arithmetic, " +
        "ending with a division by x", options: {} },
    { text: "3", options: { superscript: true } },
    { text: "\u00a0+\u00a0x\u00a0+\u00a04.", options: { breakLine: true } },
    { text: "The inputs repeat, because only 1331 different values exist." },
  ], { x: LEFT, y: TOP + 0.1, w: 5.6, h: 3.1, fontSize: 18, paraSpaceAfter: 14 });
  card(slide, LEFT, TOP + 3.4, 5.6, 1.5, C.text2);
  text(slide, "det(A \u00d7 B) = det(A) \u00d7 det(B)", { x: LEFT + 0.3, y: TOP + 3.5, w: 5.0, h: 0.75,
    fontSize: 24, bold: true, fontFace: THEME.headFontFace, color: C.background1, valign: "mid" });
  text(slide, "the identity the program verifies at the end of every run",
    { x: LEFT + 0.3, y: TOP + 4.25, w: 5.0, h: 0.45, fontSize: 14, color: C.background1 });
  const x = 6.9;
  const w = W - LEFT - x;
  stat(slide, x, TOP, w, 1.5, [{ text: "3.2 × 10" }, { text: "11", options: { superscript: true } }],
    "field operations for N = 4000, about 5N³", { figureHeight: 0.7 });
  stat(slide, x, TOP + 1.7, w, 1.5, "1,771,561",
    "different pairs of operands, 1331 × 1331", { figureHeight: 0.7 });
  stat(slide, x, TOP + 3.4, w, 1.5, "72,000 times",
    "each pair is recomputed, on average, at N = 4000", { figureHeight: 0.7 });
}
{
  const slide = contentSlide("One class sits between the program and the arithmetic",
    "This is the dependency chain. The assignment program uses two libraries directly: " +
    "algebra-matrices for the matrix product and algebra-finite-fields for the element type. " +
    "The finite field class stores a polynomial from algebra-polynomials, whose coefficients " +
    "are residues from algebra-rings, built on the cyclic groups of algebra-groups. " +
    "Everything below the finite field class is reached only through four of its functions: " +
    "add, negate, multiply and reciprocal. So if we cache at that one class, the matrix " +
    "library and the program above it do not change, and the libraries below it do not " +
    "change either. They are only called when the cache has no answer yet.");
  const bw = 2.9;
  const bh = 0.72;
  const nodes = {
    assignment: [3.9, TOP, "algebra-assignment"],
    matrices: [1.55, TOP + 1.25, "algebra-matrices"],
    fields: [6.0, TOP + 1.25, "algebra-finite-fields"],
    polynomials: [4.3, TOP + 2.55, "algebra-polynomials"],
    rings: [7.55, TOP + 2.55, "algebra-rings"],
    core: [2.4, TOP + 3.85, "algebra-core"],
    groups: [7.55, TOP + 3.85, "algebra-groups"],
  };
  const centre = (key) => nodes[key][0] + bw / 2 - 0.9;
  const edge = (from, to) => {
    const [, y1] = nodes[from];
    const [, y2] = nodes[to];
    if (y1 === y2) {
      arrow(slide, nodes[from][0] - 0.9, y1 + bh / 2, nodes[to][0] - 0.9 + bw, y2 + bh / 2);
    } else {
      arrow(slide, centre(from), y1 + bh, centre(to), y2);
    }
  };
  [["assignment", "matrices"], ["assignment", "fields"], ["fields", "polynomials"],
    ["fields", "rings"], ["rings", "groups"], ["matrices", "core"], ["polynomials", "core"],
    ["groups", "core"]].forEach(([from, to]) => edge(from, to));
  Object.entries(nodes).forEach(([key, [x, y, label]]) => {
    const chosen = key === "fields";
    box(slide, x - 0.9, y, bw, bh, label, chosen
      ? { fill: C.accent1, line: C.accent1, color: C.background1, bold: true }
      : {});
  });
  const x = 9.75;
  note(slide, x, TOP, W - LEFT - x, 2.2, "The class we cache",
    "Everything below it is reached only through add, negate, multiply and reciprocal.",
    { bodySize: 16 });
  note(slide, x, TOP + 2.4, W - LEFT - x, 2.17, "Nothing else changes",
    "Not the program, not the matrix library, not the libraries underneath.",
    { bodySize: 16 });
}

section("The cached finite field");
{
  const profile = data.profile;
  const slide = contentSlide(`${T.ProfileField}% of the work is finite field arithmetic`,
    "We profiled the original program with Callgrind, which counts executed instructions, at " +
    `N = 60. Reducing a polynomial modulo x^3 + x + 4 takes ${T.ProfileReduction}% of the ` +
    `instructions. Allocating and freeing the vectors that hold polynomials takes ` +
    `${T.ProfileHeap}%, because every intermediate polynomial is a std::vector on the heap. ` +
    `Multiplying polynomials takes ${T.ProfileMultiply}%. The loops of the matrix product and ` +
    `of the elimination themselves are only ${T.ProfileMatrix}%. So ${T.ProfileField}% of the ` +
    "instructions belong to the field elements: their arithmetic and the memory it allocates. " +
    "Speeding up the matrix loops would gain almost nothing. The arithmetic is the target.");
  barChart(slide, { x: LEFT, y: TOP - 0.1, w: 7.6, h: 4.9 }, profile.categories,
    [{ name: "Share of executed instructions", values: profile.percent, color: HEX.original }],
    { format: '0.0"%"', max: Math.max(...profile.percent) * 1.18 });
  const x = 8.6;
  stat(slide, x, TOP, W - LEFT - x, 2.2, `${T.ProfileField}%`,
    "of the instructions belong to field elements: their arithmetic and the memory it allocates",
    { figureSize: 44 });
  stat(slide, x, TOP + 2.4, W - LEFT - x, 1.75, `${T.ProfileMatrix}%`,
    "are the loops of the product and the elimination", { color: C.text1 });
  text(slide, "Callgrind instruction counts, original program, N = 60",
    { x, y: TOP + 4.3, w: W - LEFT - x, h: 0.4, fontSize: 12, transparency: 35 });
}
{
  const slide = contentSlide("A cached operation is one table read",
    "A cached element is not a polynomial any more. It is a number from 0 to 1330, its index: " +
    "the three coefficients read as a base-11 number, c0 + 11 c1 + 121 c2. That is the " +
    "numbering the library already uses in from_index. Each operation has a table. For " +
    "multiply the table has one slot for every ordered pair, at position a times 1331 plus b. " +
    "A slot starts empty. To multiply, we read the slot. If it is filled, that is a cache hit " +
    "and we return it. If it is empty, that is a cache miss: we take the two original " +
    "polynomial elements, call the original multiply, turn the result into its index, store " +
    "it, and return it. Add works the same way with its own table. Negate and reciprocal have " +
    "one slot per element. A slot is filled once and never changes, so the original " +
    "arithmetic runs at most about 3.5 million times in total, however large the matrices " +
    "are. Slots are atomic, so several threads can use the field at once.");
  const y = TOP + 0.15;
  box(slide, LEFT, y + 0.65, 2.9, 1.1, "multiply(a, b)\na and b are indexes, 0 to 1330", {});
  box(slide, 4.35, y + 0.65, 3.7, 1.1, "Read slot  a × 1331 + b\nof the products table",
    { bold: true });
  box(slide, 8.95, y, 3.78, 1.0, "Filled: return it", { fill: C.accent1, line: C.accent1,
    color: C.background1, bold: true });
  box(slide, 8.95, y + 1.4, 3.78, 1.0,
    "Empty: run the original multiply once, store the result, return it",
    { fill: C.accent2, line: C.accent2, color: C.background1 });
  arrow(slide, LEFT + 2.9, y + 1.2, 4.35, y + 1.2);
  arrow(slide, 8.05, y + 1.05, 8.95, y + 0.5);
  arrow(slide, 8.05, y + 1.35, 8.95, y + 1.9);
  text(slide, "cache hit", { x: 8.95, y: y - 0.34, w: 3.78, h: 0.3, fontSize: 12, align: "center" });
  text(slide, "cache miss", { x: 8.95, y: y + 2.44, w: 3.78, h: 0.3, fontSize: 12, align: "center" });
  const cw = (WIDTH - 0.6) / 3;
  const cy = TOP + 3.15;
  stat(slide, LEFT, cy, cw, 1.75, "2 bytes", "per element: an index instead of a polynomial");
  stat(slide, LEFT + cw + 0.3, cy, cw, 1.75, "7.1 MB", "for all four tables, whatever the matrix size");
  stat(slide, LEFT + 2 * (cw + 0.3), cy, cw, 1.75, "3.5 million",
    "original operations at most, over the whole run");
}
{
  const slide = contentSlide("Switching libraries is one CMake entry",
    "The assignment asks for a drop-in replacement: callers switch by changing the dependency " +
    "in CMake and nothing else. We kept the header file names, the class names " +
    "algebra::FiniteField and algebra::FiniteFieldElement, all their public functions, and " +
    "the CMake target name algebra::finite_fields. The original header was renamed to " +
    "uncached_finite_field.hpp and one line in it changed: its namespace is now " +
    "algebra::uncached. The original classes are still compiled, and the new class calls " +
    "them on every cache miss. The modulus is not chosen by the cached class. It asks the " +
    "original class, so both use x^3 + x + 4. In the assignment repository the only edit is " +
    "the repository and tag of this one entry in cmake/Dependencies.cmake. main.cpp and the " +
    "matrix library are not touched.");
  const cw = 6.0;
  card(slide, LEFT, TOP, cw, 3.1, C.text2);
  text(slide, [
    { text: "FetchContent_Declare(", options: { breakLine: true } },
    { text: "    algebra_finite_fields", options: { breakLine: true } },
    { text: "    GIT_REPOSITORY <cached repository>", options: { breakLine: true, color: C.accent1, bold: true } },
    { text: "    GIT_TAG        <its tag>", options: { breakLine: true, color: C.accent1, bold: true } },
    { text: ")" },
  ], { x: LEFT + 0.35, y: TOP + 0.3, w: cw - 0.7, h: 2.5, fontFace: MONO, fontSize: 16,
    color: C.background1, valign: "mid", paraSpaceAfter: 4 });
  text(slide, "cmake/Dependencies.cmake: the two highlighted lines are the whole change.",
    { x: LEFT, y: TOP + 3.3, w: cw, h: 0.7, fontSize: 14 });
  const x = LEFT + cw + 0.5;
  const w = W - LEFT - x;
  text(slide, "What stays the same", { x, y: TOP, w, h: 0.4, fontSize: 18, bold: true });
  const kept = [
    ["Header paths", "algebra/finite_fields/finite_field.hpp"],
    ["Class names", "algebra::FiniteField and FiniteFieldElement"],
    ["CMake target", "algebra::finite_fields"],
    ["Callers", "main.cpp and algebra-matrices are not edited"],
    ["Original arithmetic", "still compiled, as algebra::uncached, and used on every miss"],
  ];
  kept.forEach(([heading, detail], index) => {
    const y = TOP + 0.6 + index * 0.82;
    slide.addShape(pres.shapes.OVAL, { x, y: y + 0.06, w: 0.36, h: 0.36, fill: { color: C.accent1 },
      line: { type: "none" }, objectName: name("Mark") });
    text(slide, "=", { x, y: y + 0.06, w: 0.36, h: 0.36, fontSize: 14, bold: true,
      color: C.background1, align: "center", valign: "mid" });
    text(slide, [
      { text: heading, options: { bold: true, breakLine: true } },
      { text: detail, options: { fontSize: 14 } },
    ], { x: x + 0.55, y, w: w - 0.55, h: 0.75, fontSize: 16 });
  });
}
{
  const identical = known(T.SeqIdenticalSizes) && T.SeqIdenticalVerdict === "identical";
  const slide = contentSlide("Every pair of elements is checked against the original",
    "The field is small enough to test everything, so we do not rely on samples. First, the " +
    "library's own test file runs unchanged against the cached class: 11 tests. Then 10 new " +
    "tests compare the cached class with the original. They build every one of the 1331 " +
    "elements both ways and compare them. They run add and multiply on all 1,771,561 " +
    "ordered pairs and negate and reciprocal on all elements. Every comparison is done " +
    "twice, because the first time through is answered by cache misses and the second time " +
    "by cache hits, and both paths have to be right. All 21 tests pass with GCC 13 and with " +
    "Clang 18, with both standard libraries, and under the address, undefined-behaviour and " +
    "thread sanitizers. To check that " +
    "the tests can fail, we put one wrong value into a table in a copy of the library: 6 of " +
    "the 10 new tests failed." + (identical
      ? ` Finally, the assignment program prints identical determinants with both libraries at N = ${T.SeqIdenticalSizes}.`
      : ""));
  const cw = (WIDTH - 0.3) / 2;
  const ch = 1.95;
  stat(slide, LEFT, TOP, cw, ch, "1,771,561 pairs, twice",
    "add and multiply on every ordered pair: the first pass is all misses, the second all hits");
  stat(slide, LEFT + cw + 0.3, TOP, cw, ch, "21 of 21 tests pass",
    "11 are the original library's own tests, unchanged. 10 are new and compare the two classes");
  stat(slide, LEFT, TOP + ch + 0.3, cw, ch, "2 compilers, 3 sanitizers",
    "GCC 13 and Clang 18 with both standard libraries; address, undefined-behaviour and thread sanitizers",
    { color: C.text1 });
  stat(slide, LEFT + cw + 0.3, TOP + ch + 0.3, cw, ch, "6 of 10 new tests fail",
    "when one stored table value is changed on purpose, so the tests can catch a wrong cache",
    { color: C.text1 });
  if (identical) {
    text(slide, `The assignment program prints identical determinants with both libraries at N = ${T.SeqIdenticalSizes}.`,
      { x: LEFT, y: TOP + 2 * ch + 0.5, w: WIDTH, h: 0.4, fontSize: 14 });
  }
}
{
  const lookup = data.lookup;
  const slide = contentSlide("A hash map was not enough",
    "The assignment text suggests std::unordered_map keyed by the operands, so we measured " +
    "it. The chart is the time for one operation after the cache is full. For independent " +
    `multiplications the hash map helps: ${T.LookupOriginalMultiply} ns down to ` +
    `${T.LookupMapMultiply} ns. But look at the third group. That is the inner loop of the ` +
    "matrix product: sum = sum + a times b, where each addition needs the previous sum before " +
    `it can start. There the hash map needs ${T.LookupMapChained} ns against ` +
    `${T.LookupOriginalChained} ns for the original arithmetic. The reason is memory. A hash ` +
    "map with 1.77 million entries keeps each entry in its own heap node, and a lookup reads " +
    "a bucket and then a node, each read waiting for the one before. When the additions are " +
    "chained, those waits line up one after another. Our elements are already numbers from 0 " +
    "to 1330, so the pair (a, b) is a perfect array position: one read from a 3.5 MB array, " +
    `nothing to hash. The table needs ${T.LookupTableChained} ns in the same loop.`);
  const all = present(lookup.series.flatMap((s) => s.values));
  barChart(slide, { x: LEFT, y: TOP - 0.15, w: 7.7, h: 5.1 }, lookup.groups, [
    { name: lookup.series[0].name, values: lookup.series[0].values, color: HEX.original },
    { name: lookup.series[1].name, values: lookup.series[1].values, color: HEX.map },
    { name: lookup.series[2].name, values: lookup.series[2].values, color: HEX.cached },
  ], { format: '[<10]0.0" ns";0" ns"', max: Math.max(...all) * 1.15, gap: 60 });
  const x = 8.7;
  const w = W - LEFT - x;
  note(slide, x, TOP, w, 2.3, "Chained: the matrix product",
    `Each add waits for the last sum. The hash map needs ${T.LookupMapChained} ns per step, ` +
    `the original arithmetic ${T.LookupOriginalChained} ns.`);
  stat(slide, x, TOP + 2.5, w, 2.25, `${T.LookupTableChained} ns`,
    "with the table: the two operands are already an array position, so there is nothing to hash");
}

section("Before and after");
{
  const seq = data.sequential;
  const have = present(seq.original_seconds).length > 0 && present(seq.cached_seconds).length > 0;
  const title = have && known(T.SeqLargestBoth)
    ? `N = ${T.SeqLargestBoth}: ${T.SeqOriginalAtLargest} becomes ${T.SeqCachedAtLargest}`
    : "Run time before and after caching";
  const slide = contentSlide(title,
    `These are run times of the whole program on ${T.SequentialMachine}, one core, built ` +
    "twice from the same source: once against the original library and once against the " +
    `cached one. Both axes are logarithmic. At N = ${T.SeqLargestBoth}, the largest size we ` +
    `ran with both, the original takes ${T.SeqOriginalAtLargest} and the cached version ` +
    `${T.SeqCachedAtLargest}, a factor of ${T.SeqSpeedupAtLargest}. The largest cached run, ` +
    `N = ${T.SeqLargestCached}, takes ${T.SeqCachedAtLargestCached}. The program verified ` +
    "det(C) = det(A) det(B) in every run, and the determinants are the same with both " +
    "libraries. Each point is the median of the runs at that size; the long runs were done once.");
  const times = present(seq.original_seconds.concat(seq.cached_seconds));
  if (times.length) {
    sizeChart(slide, { x: LEFT, y: TOP - 0.15, w: 7.7, h: 5.1 }, seq.sizes, [
      { name: "Original", values: seq.original_seconds, color: HEX.original },
      { name: "Cached", values: seq.cached_seconds, color: HEX.cached },
    ], { log: true, min: floor10(Math.min(...times)), max: ceil10(Math.max(...times)),
      minSize: floor10(Math.min(...seq.sizes)), maxSize: sizeLimit(seq.sizes),
      title: "Run time (s)" });
  }
  const x = 8.7;
  const w = W - LEFT - x;
  stat(slide, x, TOP, w, 1.5, `${T.SeqSpeedupAtLargest}\u00d7 faster`,
    `at N = ${T.SeqLargestBoth}, the largest size run with both libraries`, { figureHeight: 0.7 });
  stat(slide, x, TOP + 1.7, w, 1.5, T.SeqCachedAtLargestCached,
    `for N = ${T.SeqLargestCached}, the largest cached run`, { figureHeight: 0.7, color: C.text1 });
  note(slide, x, TOP + 3.4, w, 1.5, "Assignment text, Apple M3 Max",
    "N = 4000: 6 h 40 min original, 20 min 16 s cached.");
  text(slide, `Whole program, one core, ${T.SequentialMachine}. Median of the runs at each size.`,
    { x: LEFT, y: TOP + 4.95, w: 7.7, h: 0.3, fontSize: 12, transparency: 35 });
}
{
  const seq = data.sequential;
  const cache = data.cache;
  const slide = contentSlide("Small matrices gain little: the tables fill first",
    "The gain grows with the matrix. " + (known(T.SeqSmallestSentence)
      ? `On the left, ${T.SeqSmallestSentence}. ` : "") +
    "The reason is the first use of each pair: it still runs the original arithmetic, plus " +
    "the bookkeeping of storing the result. The right chart counts this. It is the share of " +
    "additions and multiplications that were answered from a table over one whole run. At " +
    `N = 100 only ${T.CacheHitAtHundred}% are answered from a table. The share passes 99% at ` +
    `N = ${T.CacheHitNinetyNineSize}. From there on nearly every operation is a table read.`);
  const half = (WIDTH - 0.4) / 2;
  const speedups = present(seq.speedup);
  if (speedups.length) {
    const sizes = seq.sizes.filter((_, index) => seq.speedup[index] !== null);
    sizeChart(slide, { x: LEFT, y: TOP + 0.35, w: half, h: 4.1 }, sizes,
      [{ name: "Original time / cached time", values: speedups, color: HEX.cached }],
      { min: 0, minSize: floor10(Math.min(...sizes)), maxSize: sizeLimit(sizes),
        title: "Original time / cached time" });
  }
  sizeChart(slide, { x: LEFT + half + 0.4, y: TOP + 0.35, w: half, h: 4.1 }, cache.sizes,
    [{ name: "Answered from a table", values: cache.answered, color: HEX.cached }],
    { min: 0, max: 100, unit: 25, minSize: floor10(Math.min(...cache.sizes)),
      maxSize: sizeLimit(cache.sizes), title: "Percent" });
  text(slide, "Speedup of the whole program", { x: LEFT, y: TOP - 0.05, w: half, h: 0.35,
    fontSize: 16, bold: true });
  text(slide, "Additions and multiplications answered from a table",
    { x: LEFT + half + 0.4, y: TOP - 0.05, w: half, h: 0.35, fontSize: 16, bold: true });
  text(slide, `At N = 100 only ${T.CacheHitAtHundred}% of the operations are table reads. ` +
    `From N = ${T.CacheHitNinetyNineSize} more than 99% are.`,
    { x: LEFT, y: TOP + 4.55, w: WIDTH, h: 0.4, fontSize: 14 });
}
{
  const seq = data.sequential;
  const have = present(seq.original_mib).length > 0;
  const title = have && known(T.SeqLargestBoth)
    ? `N = ${T.SeqLargestBoth}: peak memory ${T.SeqOriginalMemoryAtLargest} becomes ${T.SeqCachedMemoryAtLargest}`
    : "Peak memory before and after caching";
  const slide = contentSlide(title,
    "This is the peak resident memory of the whole program, measured by the operating " +
    "system. The original library stores every matrix entry as a vector object that points " +
    `to its own heap block, about ${T.SeqOriginalBytesPerEntry} bytes per entry on this ` +
    "system. A cached entry is two bytes. " +
    `At N = ${T.SeqLargestBoth} the peak falls from ${T.SeqOriginalMemoryAtLargest} to ` +
    `${T.SeqCachedMemoryAtLargest}. The tables are a fixed cost of about 7 MB, so for very ` +
    "small matrices the cached program uses more memory than the original. " +
    `At N = ${T.SeqLargestCached} the cached program peaks at ${T.SeqCachedMemoryAtLargestCached}.`);
  const memory = present(seq.original_mib.concat(seq.cached_mib));
  if (memory.length) {
    sizeChart(slide, { x: LEFT, y: TOP - 0.15, w: 7.7, h: 5.1 }, seq.sizes, [
      { name: "Original", values: seq.original_mib, color: HEX.original },
      { name: "Cached", values: seq.cached_mib, color: HEX.cached },
    ], { log: true, min: floor10(Math.min(...memory)), max: ceil10(Math.max(...memory)),
      minSize: floor10(Math.min(...seq.sizes)), maxSize: sizeLimit(seq.sizes),
      title: "Peak memory (MiB)" });
  }
  const x = 8.7;
  const w = W - LEFT - x;
  stat(slide, x, TOP, w, 1.5, "2 bytes",
    `per matrix entry, instead of about ${T.SeqOriginalBytesPerEntry} bytes for a polynomial on the heap`,
    { figureHeight: 0.7 });
  stat(slide, x, TOP + 1.7, w, 1.5, "7 MB",
    "of tables, a fixed cost: the smallest matrices use more memory than before",
    { figureHeight: 0.7, color: C.text1 });
  stat(slide, x, TOP + 3.4, w, 1.5, T.SeqCachedMemoryAtLargestCached,
    `peak for N = ${T.SeqLargestCached} with the cached library`,
    { figureHeight: 0.7, color: C.text1 });
}

section("Determinants with MPI");
{
  const slide = contentSlide("Deal out columns, so the pivot is a local choice",
    "The determinant comes from Gaussian elimination, which is a PLU factorization. At step k " +
    "we pick a nonzero pivot in column k, swap its row up, divide the entries below it by the " +
    "pivot to get the multipliers, and subtract multiplier times row k from every row below. " +
    "The determinant is the product of the pivots, with the sign flipped for every row swap. " +
    "Over a finite field there is no rounding, so any nonzero entry is a good pivot. " +
    "The key decision: step k needs the pivot and the multipliers, and both are in column k. " +
    "So every process owns whole columns. The process that owns column k finds the pivot and " +
    "the multipliers from its own memory, without asking anyone. If we split by rows instead, " +
    "column k would be spread over all processes and every step would need a reduction to " +
    "find a pivot. One message per column would be many small messages, so we group b columns " +
    "into a panel, 8 by default, and deal the panels out in turn like cards. The owner works " +
    "through its panel and then sends one broadcast for the whole panel: a flag for a zero " +
    "determinant, the pivot rows, and the multipliers. A cached element is a 2-byte number, " +
    "so this goes out as raw bytes. Every process then updates the columns it owns.");
  const size = 4.0;
  const mx = LEFT + 0.1;
  const my = TOP + 0.1;
  const panels = 8;
  const pw = size / panels;
  const owners = [C.accent4, C.accent2, C.accent5, C.accent6];
  for (let panel = 0; panel < panels; panel += 1) {
    slide.addShape(pres.shapes.RECTANGLE, { x: mx + panel * pw, y: my, w: pw - 0.04, h: size,
      fill: { color: owners[panel % 4] }, line: { type: "none" }, objectName: name("Panel") });
    text(slide, `P${panel % 4}`, { x: mx + panel * pw, y: my + size + 0.08, w: pw - 0.04, h: 0.3,
      fontSize: 12, align: "center" });
  }
  slide.addShape(pres.shapes.RECTANGLE, { x: mx + 2 * pw - 0.04, y: my - 0.06, w: pw + 0.04,
    h: size + 0.12, fill: { type: "none" }, line: { color: C.accent1, width: 3 },
    objectName: name("Current panel") });
  text(slide, "panel being eliminated", { x: mx + 2 * pw - 1.0, y: my - 0.42, w: pw + 2.0, h: 0.3,
    fontSize: 12, align: "center", color: C.text1 });
  text(slide, "Panels of b columns, dealt to the processes in turn",
    { x: mx, y: my + size + 0.45, w: size, h: 0.35, fontSize: 12, align: "center" });
  const x = 5.4;
  const w = W - LEFT - x;
  step(slide, x, TOP, w, 1.5, 1, "The panel's owner works alone",
    "It finds each pivot and the multipliers below it in its own columns. No messages.");
  step(slide, x, TOP + 1.7, w, 1.5, 2, "One broadcast per panel",
    "A zero flag, the pivot rows and the multipliers, sent as raw 2-byte values.");
  step(slide, x, TOP + 3.4, w, 1.5, 3, "Everyone updates its own columns",
    "The determinant is the product of the pivots, with the sign flipped for every row swap.");
}
{
  const mpi = data.mpi;
  const most = T.MpiMostProcesses;
  const single = T.MpiNodes === "1";
  const stays = known(T.MpiStaysFasterSize);
  const title = stays
    ? `With ${most} processes, MPI is faster from N = ${T.MpiStaysFasterSize} upward`
    : `With ${most} processes, MPI was not faster at the largest size`;
  const slide = contentSlide(title,
    `We tested N = ${T.MpiSizes} with ${T.MpiProcessCounts} processes and a panel width of ` +
    `${T.MpiBlock}. In every run rank 0 computes the determinant sequentially and with MPI ` +
    "one after the other on the same matrix, the assignment program's A and B, and the two " +
    `results always ${T.MpiAllMatch}. The two take turns going first, because the second one ` +
    `finds the caches warm. ${T.MpiRepeatsSentence}. The chart is the median of ` +
    "sequential time divided by MPI time, so above 1 MPI is faster. " +
    `${T.MpiBreakEvenSentence}. ${T.MpiWinsSentence} ` +
    `At N = ${T.MpiLargestSize} the ratio is ${T.MpiLargestRatio}. The MPI program with one ` +
    "process is not the same code as the sequential program: it sends nothing, but it stores " +
    "the matrix by columns and updates one column at a time. So we also ran it with one " +
    `process. ${T.MpiOneProcessSentence} The gain from the extra processes is the ` +
    `one-process time divided by the ${most}-process time: ${T.MpiParallelGain}. ` +
    (single
      ? "Important limit: all processes ran on one machine, so messages went through shared " +
        "memory. This is the smallest overhead the algorithm can have. Across real machines " +
        "the break-even point will be higher, and that run is still to be done."
      : `The processes ran on ${T.MpiNodes} machines.`));
  const ratios = present(mpi.series.flatMap((s) => s.ratio));
  if (ratios.length) {
    sizeChart(slide, { x: LEFT, y: TOP - 0.15, w: 7.7, h: 5.1 }, mpi.sizes,
      mpi.series.map((s, index) => ({
        name: s.processes === 1 ? "MPI, 1 process" : `MPI, ${s.processes} processes`,
        values: s.ratio, color: HEX.ramp[Math.min(index, HEX.ramp.length - 1)] })),
      { min: 0, max: Math.ceil(Math.max(...ratios) * 2) / 2, unit: 0.5, format: "0.0",
        // pptxgenjs gives both axes of a scatter chart the same number format.
        minSize: floor10(Math.min(...mpi.sizes)), maxSize: sizeLimit(mpi.sizes),
        title: "Sequential time / MPI time" });
  }
  const x = 8.7;
  const w = W - LEFT - x;
  stat(slide, x, TOP, w, 1.5, `${T.MpiLargestRatio}\u00d7 faster`,
    `at N = ${T.MpiLargestSize} with ${most} processes. In the chart, above 1.0 MPI is faster.`,
    { figureHeight: 0.7 });
  stat(slide, x, TOP + 1.7, w, 1.5, `${T.MpiParallelGain}\u00d7`,
    `from the ${most === "2" ? "second process" : "extra processes"}. One process alone: ` +
    `${T.MpiOneProcessRatio}\u00d7 the sequential speed.`,
    { figureHeight: 0.7, color: C.text1 });
  note(slide, x, TOP + 3.4, w, 1.5, single ? "One machine so far" : `${T.MpiNodes} machines`,
    single ? "Messages went through shared memory. Across machines the break-even will be higher."
      : "The broadcasts crossed the network between the machines.",
    { fill: C.text2, headingColor: C.background1, bodyColor: C.background1 });
}

section("Wrap-up");
{
  const single = T.MpiNodes === "1";
  const slide = contentSlide("What these numbers do not show yet",
    "Four limits. One: the before-and-after times come from one machine, " +
    `${T.SequentialMachine}, which is ${data.machines.sequential_description}, with ` +
    `${T.SeqRunsPhrase}. ${T.SeqRepeatSentence} Small differences mean nothing; the ` +
    "conclusions rest on much larger ratios. " + T.MpiNoiseSentence +
    " Two: " + T.MpiNodesLimitation + " Three: the matrix product is still sequential and with " +
    `the cached library it is ${T.SeqCachedProductShare}% of the run, so it is the next thing ` +
    "to parallelize. Four: the tables need about 4 q^2 bytes, so fields with more than 4096 " +
    "elements are not cached and fall back to the original arithmetic.");
  const cw = (WIDTH - 0.3) / 2;
  const ch = 1.9;
  const big = { bodySize: 16 };
  note(slide, LEFT, TOP, cw, ch, "One machine, few runs",
    `Before-and-after times come from one machine, ${T.SequentialMachine}, with few runs per ` +
    "size. Small differences mean nothing; the conclusions rest on large ratios.", big);
  note(slide, LEFT + cw + 0.3, TOP, cw, ch, single ? "MPI on one machine" : "One cluster",
    T.MpiNodesLimitation, big);
  note(slide, LEFT, TOP + ch + 0.3, cw, ch, "The product is still sequential",
    `With the cached library the matrix product is ${T.SeqCachedProductShare}% of the run. It ` +
    "is the next part to parallelize.", big);
  note(slide, LEFT + cw + 0.3, TOP + ch + 0.3, cw, ch, "Tables grow with the square of the field",
    "Fields with more than 4096 elements are not cached. They fall back to the original arithmetic.",
    big);
}
{
  const slide = contentSlide("What we found",
    "Three things. Caching at the one class that all the arithmetic passes through made the " +
    `program ${T.SeqSpeedupAtLargest} times faster at N = ${T.SeqLargestBoth} and cut its ` +
    "memory, without editing the program or the matrix library, and exhaustive tests show " +
    "the same results. A hash map was not enough for the matrix product; an array indexed by " +
    "the two operands was. And for the determinant, giving each process whole columns makes " +
    "pivot selection local and leaves one broadcast per panel. " + T.MpiBreakEvenSentence + ".",
    "Closing");
  const ch = 1.5;
  const rows = [
    [`${T.SeqSpeedupAtLargest}\u00d7 faster`,
      `at N = ${T.SeqLargestBoth}, by caching the one class the arithmetic passes through. ` +
      "Same results on all 1,771,561 pairs."],
    [`${T.LookupTableChained} ns, not ${T.LookupMapChained} ns`,
      "per step of the matrix product: an array indexed by the two operands instead of a hash map."],
    [known(T.MpiStaysFasterSize) ? `MPI wins from N = ${T.MpiStaysFasterSize}` : "MPI: no break-even yet",
      `with ${T.MpiMostProcesses} processes` + (T.MpiNodes === "1" ? " on one machine" : ` on ${T.MpiNodes} machines`) +
      ". Columns make the pivot a local choice: one broadcast per panel."],
  ];
  rows.forEach(([figure, label], index) => {
    const y = TOP + index * (ch + 0.2);
    slide.addShape(pres.shapes.ROUNDED_RECTANGLE, { x: LEFT, y, w: WIDTH, h: ch, rectRadius: 0.12,
      fill: { color: C.background1, transparency: 90 }, line: { type: "none" },
      objectName: name("Card") });
    text(slide, figure, { x: LEFT + 0.35, y, w: 4.9, h: ch, fontSize: 28, bold: true,
      fontFace: THEME.headFontFace, color: C.accent1, valign: "mid" });
    text(slide, label, { x: LEFT + 5.4, y, w: WIDTH - 5.75, h: ch, fontSize: 16,
      color: C.background1, valign: "mid" });
  });
}

// ---------------------------------------------------------------------------
// Writing the file
// ---------------------------------------------------------------------------
// pptxgenjs leaves three things undone, which are finished here in the saved file:
//   the theme colours (it always writes Office's own palette),
//   a logarithmic horizontal axis on the charts over matrix dimension,
//   blanks in a series, which it writes as points with an empty value.
async function finish(file) {
  const zip = await JSZip.loadAsync(fs.readFileSync(file));
  const escaped = THEME.name.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/"/g, "&quot;");
  const slots = ["dk1", "lt1", "dk2", "lt2", "accent1", "accent2", "accent3", "accent4",
    "accent5", "accent6", "hlink", "folHlink"];
  const scheme = `<a:clrScheme name="${escaped}">` + slots.map((slot) =>
    `<a:${slot}><a:srgbClr val="${THEME.colors[slot]}"/></a:${slot}>`).join("") + "</a:clrScheme>";
  const themePart = "ppt/theme/theme1.xml";
  let theme = await zip.file(themePart).async("string");
  theme = theme.replace(/<a:clrScheme\b[\s\S]*?<\/a:clrScheme>/, () => scheme)
    .replace(/(<a:(?:theme|fontScheme)\b[^>]*?\bname=")[^"]*"/g, (_, head) => `${head}${escaped}"`);
  zip.file(themePart, theme, { createFolders: false });

  for (const part of Object.keys(zip.files)) {
    if (!/^ppt\/charts\/chart\d+\.xml$/.test(part)) continue;
    let xml = await zip.file(part).async("string");
    if (!xml.includes("<c:scatterChart>")) continue;
    xml = xml.replace(/<c:pt idx="\d+"><c:v><\/c:v><\/c:pt>/g, "");
    xml = xml.replace(
      /(<c:valAx>\s*<c:axId val="\d+"\/>\s*<c:scaling>)(?!<c:logBase)((?:(?!<\/c:valAx>)[\s\S])*?<c:axPos val="b"\/>)/,
      '$1<c:logBase val="10"/>$2');
    // pptxgenjs gives both axes the same number format; matrix dimensions are whole numbers.
    xml = xml.replace(
      /(<c:axPos val="b"\/>(?:(?!<\/c:valAx>)[\s\S])*?<c:numFmt formatCode=")[^"]*(")/,
      "$1General$2");
    zip.file(part, xml, { createFolders: false });
  }
  // Entries for folders are not parts of the package and are left out.
  for (const part of Object.keys(zip.files)) {
    if (zip.files[part].dir) delete zip.files[part];
  }
  fs.writeFileSync(file, await zip.generateAsync({ type: "nodebuffer", compression: "DEFLATE" }));
}

pres.writeFile({ fileName: OUTPUT })
  .then(() => finish(OUTPUT))
  .then(() => console.log(`wrote ${OUTPUT}`))
  .catch((error) => {
    console.error(error);
    process.exit(1);
  });
