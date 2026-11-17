// Distributed determinant over the finite field of order 11^3.
//
// The matrix is split by columns. Blocks of `block` neighbouring columns
// (panels) are dealt out to the processes in turn, so every process keeps a
// share of the work until the end.
//
// One elimination step needs two things: a pivot and the column of multipliers
// below it. Both live in a single column, and a column belongs to exactly one
// process. So the owner of a panel
//   1. finds each pivot by looking only at its own data,
//   2. divides the entries below the pivot by it (the multipliers),
//   3. broadcasts the pivot rows and the multipliers once per panel.
// Every process then applies those steps to the columns it owns. No process
// ever asks another one for a pivot, and the only messages during the
// elimination are those broadcasts.
//
// The determinant is the product of the pivots, negated once per row swap.
//
// The program also runs the assignment's sequential elimination on the same
// matrix so the two times and the two results can be compared directly.

#include <algorithm>
#include <chrono>
#include <cstddef>
#include <cstdint>
#include <cstdlib>
#include <cstring>
#include <exception>
#include <fstream>
#include <iomanip>
#include <iostream>
#include <limits>
#include <numeric>
#include <random>
#include <set>
#include <sstream>
#include <stdexcept>
#include <string>
#include <thread>
#include <type_traits>
#include <utility>
#include <vector>
#include <mpi.h>
#include <algebra/finite_fields/finite_fields.hpp>

namespace {

using Field = algebra::FiniteField<11, 3>;
using Element = Field::Element;
using Clock = std::chrono::steady_clock;

// Columns and multipliers travel between processes as raw bytes. That needs an
// element that is a plain value, which the cached finite field provides.
static_assert(std::is_trivially_copyable_v<Element>,
              "The MPI program needs the cached finite field");

constexpr int start_tag = 1;
constexpr int columns_tag = 2;

// The two routines that do the elimination work are compiled as functions of
// their own. Inlined into a large caller, a compiler can run short of
// registers and reload pointers from the stack inside the innermost loop,
// which would slow down one side of the comparison for no algorithmic reason.
#if defined(__GNUC__) || defined(__clang__)
#define ALGEBRA_KEEP_OUT_OF_LINE __attribute__((noinline))
#else
#define ALGEBRA_KEEP_OUT_OF_LINE
#endif

struct Options {
    std::size_t size = 0;
    std::size_t block = 8;
    std::uint32_t seed = 123456u;
    std::string matrix_case = "random";
    std::string csv;
    std::string label;
    int repeats = 1;
    bool warm = true;
    bool sequential = true;
};

struct Problem {
    std::string name;
    std::vector<Element> entries;   // row-major, size * size
};

struct Timing {
    double distribute = 0;   // rank 0: packing the columns and sending them out
    double eliminate = 0;    // rank 0: from the first panel until the determinant is known
    double factor = 0;       // per process: finding pivots and multipliers for its own panels
    double broadcast = 0;    // per process: inside MPI_Bcast, including waiting for the owner
    double update = 0;       // per process: applying panels to its own columns
};

double seconds(Clock::time_point start) {
    return std::chrono::duration<double>(Clock::now() - start).count();
}

[[noreturn]] void usage(const char* program) {
    int rank = 0;
    MPI_Comm_rank(MPI_COMM_WORLD, &rank);
    if (rank == 0) {
        std::cerr << "Usage: " << program << " --size N [options]\n"
                  << "  --size N          matrix dimension\n"
                  << "  --block B         columns per panel, one broadcast per panel (default 8)\n"
                  << "  --case NAME       random, sparse, permutation, singular or zero-leading\n"
                  << "  --seed S          generator seed (default 123456, as in the assignment)\n"
                  << "  --repeat R        timed repetitions per matrix (default 1)\n"
                  << "  --csv FILE        append one line per measurement to FILE\n"
                  << "  --label TEXT      free text copied into the CSV, for example the machine\n"
                  << "  --no-warm         do not fill the field's tables before timing\n"
                  << "  --no-sequential   skip the sequential reference run\n";
    }
    MPI_Abort(MPI_COMM_WORLD, 64);
    std::abort();
}

Options parse(int argc, char** argv) {
    Options options;
    for (int i = 1; i < argc; ++i) {
        const std::string argument = argv[i];
        auto value = [&]() -> std::string {
            if (i + 1 >= argc) {
                usage(argv[0]);
            }
            return argv[++i];
        };
        if (argument == "--size") {
            options.size = std::stoull(value());
        } else if (argument == "--block") {
            options.block = std::stoull(value());
        } else if (argument == "--case") {
            options.matrix_case = value();
        } else if (argument == "--seed") {
            options.seed = static_cast<std::uint32_t>(std::stoul(value()));
        } else if (argument == "--repeat") {
            options.repeats = std::stoi(value());
        } else if (argument == "--csv") {
            options.csv = value();
        } else if (argument == "--label") {
            options.label = value();
        } else if (argument == "--no-warm") {
            options.warm = false;
        } else if (argument == "--no-sequential") {
            options.sequential = false;
        } else {
            usage(argv[0]);
        }
    }
    const bool known_case = options.matrix_case == "random" || options.matrix_case == "sparse" ||
                            options.matrix_case == "permutation" ||
                            options.matrix_case == "singular" ||
                            options.matrix_case == "zero-leading";
    if (options.size == 0 || options.block == 0 || options.repeats < 1 || !known_case) {
        usage(argv[0]);
    }
    return options;
}

// The next two functions are the assignment program's generator, unchanged, so
// that the random case produces the same matrices A and B as that program.
std::uint32_t draw_coefficient(std::mt19937& generator, std::uint32_t prime) {
    if (prime < 2) {
        throw std::invalid_argument("The prime must be at least two");
    }
    constexpr std::uint64_t range = std::uint64_t{1} << 32;
    const std::uint64_t limit = range - range % prime;
    for (;;) {
        const std::uint64_t value = generator();
        if (value < limit) {
            return static_cast<std::uint32_t>(value % prime);
        }
    }
}

Element next_element(std::mt19937& generator) {
    Element::polynomial_type polynomial;
    for (std::size_t degree = 0; degree < Field::extension_degree; ++degree) {
        const auto coefficient = draw_coefficient(generator, Field::characteristic);
        polynomial.set_coefficient(degree, Element::coefficient_type::from_integer(coefficient));
    }
    return Element::from_polynomial(polynomial);
}

Element next_nonzero_element(std::mt19937& generator) {
    for (;;) {
        const Element value = next_element(generator);
        if (!value.is_zero()) {
            return value;
        }
    }
}

// The matrices to solve. "random" is the assignment's pair A and B. The other
// cases exist to exercise row swaps, zero multipliers and a zero determinant.
std::vector<Problem> build_problems(const Options& options) {
    const std::size_t n = options.size;
    std::mt19937 generator(options.seed);
    if (options.matrix_case == "random") {
        Problem a{"A", std::vector<Element>(n * n)};
        Problem b{"B", std::vector<Element>(n * n)};
        for (std::size_t i = 0; i < n; ++i) {
            for (std::size_t j = 0; j < n; ++j) {
                a.entries[i * n + j] = next_element(generator);
                b.entries[i * n + j] = next_element(generator);
            }
        }
        return {std::move(a), std::move(b)};
    }
    Problem problem{options.matrix_case, std::vector<Element>(n * n)};
    auto& entries = problem.entries;
    if (options.matrix_case == "permutation") {
        std::vector<std::size_t> column(n);
        std::iota(column.begin(), column.end(), std::size_t{0});
        std::shuffle(column.begin(), column.end(), generator);
        for (std::size_t i = 0; i < n; ++i) {
            entries[i * n + column[i]] = next_nonzero_element(generator);
        }
        return {std::move(problem)};
    }
    for (std::size_t i = 0; i < n * n; ++i) {
        const bool keep = options.matrix_case != "sparse" || generator() % 4 == 0;
        const Element value = next_element(generator);
        if (keep) {
            entries[i] = value;
        }
    }
    if (options.matrix_case == "singular") {
        // The last row repeats the first one.
        for (std::size_t j = 0; j < n; ++j) {
            entries[(n - 1) * n + j] = n > 1 ? entries[j] : Element::zero();
        }
    }
    if (options.matrix_case == "zero-leading") {
        // The only usable pivot for the first column is in the last row.
        for (std::size_t i = 0; i < n; ++i) {
            entries[i * n] = Element::zero();
        }
        entries[(n - 1) * n] = next_nonzero_element(generator);
    }
    return {std::move(problem)};
}

// Uses every table entry once so that later timings measure table reads and
// not the first-time fill. Returns the time it took.
double warm_field_tables() {
    const auto start = Clock::now();
    std::vector<Element> elements;
    const std::uint64_t order = Field::cardinality();
    elements.reserve(static_cast<std::size_t>(order));
    for (std::uint64_t index = 0; index < order; ++index) {
        elements.push_back(Element::from_index(index));
    }
    Element sink = Element::zero();
    for (const Element& a : elements) {
        sink = sink.add(a.negate());
        if (!a.is_zero()) {
            sink = sink.add(a.reciprocal());
        }
        for (const Element& b : elements) {
            sink = sink.add(a.add(b));
            sink = sink.add(a.multiply(b));
        }
    }
    static_cast<void>(sink);
    return seconds(start);
}

// The elimination from the assignment program, on a row-major array whose
// size is chosen at run time. Same steps in the same order: first nonzero
// entry as the pivot, a row swap negates the result, rows with a zero entry
// under the pivot are skipped.
ALGEBRA_KEEP_OUT_OF_LINE
Element sequential_determinant(std::vector<Element> matrix, std::size_t n) {
    Element result = Element::one();
    Element* const entries = matrix.data();
    for (std::size_t k = 0; k < n; ++k) {
        std::size_t pivot_row = k;
        while (pivot_row < n && entries[pivot_row * n + k].is_zero()) {
            ++pivot_row;
        }
        if (pivot_row == n) {
            return Element::zero();
        }
        Element* const pivot_entries = entries + k * n;
        if (pivot_row != k) {
            std::swap_ranges(pivot_entries, pivot_entries + n, entries + pivot_row * n);
            result = result.negate();
        }
        const Element pivot = pivot_entries[k];
        result = result.multiply(pivot);
        Element inverse = Element::one();
        if (!pivot.is_one()) {
            inverse = pivot.reciprocal();
        }
        for (std::size_t i = k + 1; i < n; ++i) {
            Element* const row = entries + i * n;
            if (row[k].is_zero()) {
                continue;
            }
            const Element multiplier = row[k].multiply(inverse);
            row[k] = Element::zero();
            for (std::size_t j = k + 1; j < n; ++j) {
                const Element correction = multiplier.multiply(pivot_entries[j]);
                row[j] = row[j].add(correction.negate());
            }
        }
    }
    return result;
}

// Which process owns which columns.
struct Layout {
    std::size_t n = 0;
    std::size_t block = 1;
    int processes = 1;

    std::size_t panels() const {
        return (n + block - 1) / block;
    }

    std::size_t panel_begin(std::size_t panel) const {
        return panel * block;
    }

    std::size_t panel_end(std::size_t panel) const {
        return std::min(n, (panel + 1) * block);
    }

    int owner(std::size_t panel) const {
        return static_cast<int>(panel % static_cast<std::size_t>(processes));
    }

    // Number of columns a process holds.
    std::size_t columns_of(int rank) const {
        std::size_t count = 0;
        for (std::size_t panel = static_cast<std::size_t>(rank); panel < panels();
             panel += static_cast<std::size_t>(processes)) {
            count += panel_end(panel) - panel_begin(panel);
        }
        return count;
    }

    // Where a panel's first column sits in its owner's storage. A process owns
    // every `processes`-th panel, and all of them are full except possibly the
    // very last panel of the matrix.
    std::size_t local_column(std::size_t panel) const {
        return (panel / static_cast<std::size_t>(processes)) * block;
    }
};

int byte_count(std::size_t elements) {
    const std::size_t bytes = elements * sizeof(Element);
    if (bytes > static_cast<std::size_t>(std::numeric_limits<int>::max())) {
        throw std::length_error("The matrix is too large for a single MPI message");
    }
    return static_cast<int>(bytes);
}

// Blocks without spinning until a message from `source` is available. The
// other processes sit here while rank 0 times the sequential run, so they do
// not compete with it for the processor.
void wait_for_message(int source, int tag) {
    for (;;) {
        int available = 0;
        MPI_Iprobe(source, tag, MPI_COMM_WORLD, &available, MPI_STATUS_IGNORE);
        if (available != 0) {
            return;
        }
        std::this_thread::sleep_for(std::chrono::microseconds(200));
    }
}

// Applies the elimination steps of one panel to one column.
//   column      all n entries of the column
//   first       first column (and first active row) of the panel
//   pivots      the row each step swapped into place
//   multipliers one column of multipliers per step; entry r is for row first + r
ALGEBRA_KEEP_OUT_OF_LINE
void apply_panel(Element* column, std::size_t n, std::size_t first, std::size_t steps,
                 const std::uint32_t* pivots, const Element* multipliers) {
    const std::size_t rows = n - first;
    for (std::size_t step = 0; step < steps; ++step) {
        const std::size_t k = first + step;
        const std::size_t pivot_row = pivots[step];
        if (pivot_row != k) {
            std::swap(column[k], column[pivot_row]);
        }
        const Element pivot_entry = column[k];
        if (pivot_entry.is_zero()) {
            continue;
        }
        const Element* multiplier = multipliers + step * rows;
        for (std::size_t i = k + 1; i < n; ++i) {
            const Element correction = pivot_entry.multiply(multiplier[i - first]);
            column[i] = column[i].add(correction.negate());
        }
    }
}

// Runs on every process. `source` is the full matrix on rank 0 and unused
// elsewhere. Returns the determinant on every process.
Element distributed_determinant(const Layout& layout, const std::vector<Element>& source,
                                Timing& timing, std::uint64_t& broadcast_bytes) {
    int rank = 0;
    MPI_Comm_rank(MPI_COMM_WORLD, &rank);
    const std::size_t n = layout.n;
    const std::size_t my_columns = layout.columns_of(rank);
    std::vector<Element> local(my_columns * n);   // column-major: column c starts at c * n

    // Rank 0 hands out the columns.
    const double distribute_start = MPI_Wtime();
    if (rank == 0) {
        std::vector<Element> outgoing;
        for (int target = layout.processes - 1; target >= 0; --target) {
            std::vector<Element>& destination = target == 0 ? local : outgoing;
            destination.resize(layout.columns_of(target) * n);
            std::size_t next = 0;
            for (std::size_t panel = static_cast<std::size_t>(target); panel < layout.panels();
                 panel += static_cast<std::size_t>(layout.processes)) {
                for (std::size_t column = layout.panel_begin(panel);
                     column < layout.panel_end(panel); ++column) {
                    for (std::size_t row = 0; row < n; ++row) {
                        destination[next++] = source[row * n + column];
                    }
                }
            }
            if (target != 0) {
                MPI_Send(outgoing.data(), byte_count(outgoing.size()), MPI_BYTE, target,
                         columns_tag, MPI_COMM_WORLD);
            }
        }
    } else {
        MPI_Recv(local.data(), byte_count(local.size()), MPI_BYTE, 0, columns_tag,
                 MPI_COMM_WORLD, MPI_STATUS_IGNORE);
    }
    const double eliminate_start = MPI_Wtime();
    timing.distribute = eliminate_start - distribute_start;

    Element determinant = Element::one();
    std::vector<std::uint32_t> pivots;
    std::vector<Element> multipliers;
    std::vector<unsigned char> wire;
    for (std::size_t panel = 0; panel < layout.panels(); ++panel) {
        const std::size_t first = layout.panel_begin(panel);
        const std::size_t steps = layout.panel_end(panel) - first;
        const std::size_t rows = n - first;
        const int owner = layout.owner(panel);
        std::uint32_t singular = 0;
        pivots.assign(steps, 0);
        multipliers.assign(steps * rows, Element::zero());

        // The owner turns its panel into pivots and multipliers.
        double mark = MPI_Wtime();
        if (rank == owner) {
            Element* panel_columns = local.data() + layout.local_column(panel) * n;
            for (std::size_t step = 0; step < steps && singular == 0; ++step) {
                Element* column = panel_columns + step * n;
                // Bring this column up to date with the earlier steps of the panel.
                apply_panel(column, n, first, step, pivots.data(), multipliers.data());
                const std::size_t k = first + step;
                std::size_t pivot_row = k;
                while (pivot_row < n && column[pivot_row].is_zero()) {
                    ++pivot_row;
                }
                if (pivot_row == n) {
                    singular = 1;
                    break;
                }
                std::swap(column[k], column[pivot_row]);
                pivots[step] = static_cast<std::uint32_t>(pivot_row);
                const Element pivot = column[k];
                Element inverse = Element::one();
                if (!pivot.is_one()) {
                    inverse = pivot.reciprocal();
                }
                Element* multiplier = multipliers.data() + step * rows;
                multiplier[step] = pivot;   // the diagonal slot carries the pivot itself
                for (std::size_t i = k + 1; i < n; ++i) {
                    multiplier[i - first] = column[i].multiply(inverse);
                }
            }
        }
        double now = MPI_Wtime();
        timing.factor += now - mark;
        mark = now;

        // One broadcast per panel: a flag, the pivot rows and the multipliers.
        const std::size_t header_bytes = (steps + 1) * sizeof(std::uint32_t);
        const std::size_t body_bytes = multipliers.size() * sizeof(Element);
        wire.resize(header_bytes + body_bytes);
        if (rank == owner) {
            std::memcpy(wire.data(), &singular, sizeof(singular));
            std::memcpy(wire.data() + sizeof(singular), pivots.data(),
                        steps * sizeof(std::uint32_t));
            std::memcpy(wire.data() + header_bytes, multipliers.data(), body_bytes);
        }
        if (wire.size() > static_cast<std::size_t>(std::numeric_limits<int>::max())) {
            throw std::length_error("The panel is too large for a single MPI message");
        }
        MPI_Bcast(wire.data(), static_cast<int>(wire.size()), MPI_BYTE, owner, MPI_COMM_WORLD);
        if (rank != owner) {
            std::memcpy(&singular, wire.data(), sizeof(singular));
            std::memcpy(pivots.data(), wire.data() + sizeof(singular),
                        steps * sizeof(std::uint32_t));
            std::memcpy(multipliers.data(), wire.data() + header_bytes, body_bytes);
        }
        broadcast_bytes += wire.size();
        now = MPI_Wtime();
        timing.broadcast += now - mark;
        mark = now;

        if (singular != 0) {
            determinant = Element::zero();
            break;
        }
        for (std::size_t step = 0; step < steps; ++step) {
            const std::size_t k = first + step;
            determinant = determinant.multiply(multipliers[step * rows + step]);
            if (pivots[step] != k) {
                determinant = determinant.negate();
            }
        }

        // Every process applies the panel to the columns it still has to its right.
        for (std::size_t later = panel + 1; later < layout.panels(); ++later) {
            if (layout.owner(later) != rank) {
                continue;
            }
            Element* later_columns = local.data() + layout.local_column(later) * n;
            const std::size_t width = layout.panel_end(later) - layout.panel_begin(later);
            for (std::size_t c = 0; c < width; ++c) {
                apply_panel(later_columns + c * n, n, first, steps, pivots.data(),
                            multipliers.data());
            }
        }
        timing.update += MPI_Wtime() - mark;
    }
    timing.eliminate = MPI_Wtime() - eliminate_start;
    return determinant;
}

// Free text that goes into the CSV must not contain the separator.
std::string csv_field(std::string text) {
    std::replace(text.begin(), text.end(), ',', ' ');
    return text;
}

std::string coefficients_text(const Element& value) {
    std::ostringstream out;
    for (std::size_t degree = 0; degree < Field::extension_degree; ++degree) {
        if (degree != 0) {
            out << ' ';
        }
        out << value.coefficient(degree);
    }
    return out.str();
}

// Number of different machines the processes run on.
int count_nodes(int rank, int processes, std::string& first_node) {
    char name[MPI_MAX_PROCESSOR_NAME] = {};
    int length = 0;
    MPI_Get_processor_name(name, &length);
    std::vector<char> all(static_cast<std::size_t>(processes) * MPI_MAX_PROCESSOR_NAME);
    MPI_Gather(name, MPI_MAX_PROCESSOR_NAME, MPI_CHAR, all.data(), MPI_MAX_PROCESSOR_NAME,
               MPI_CHAR, 0, MPI_COMM_WORLD);
    int nodes = 0;
    if (rank == 0) {
        std::set<std::string> names;
        for (int i = 0; i < processes; ++i) {
            names.insert(std::string(all.data() + static_cast<std::size_t>(i) *
                                                      MPI_MAX_PROCESSOR_NAME));
        }
        nodes = static_cast<int>(names.size());
        first_node = name;
    }
    return nodes;
}

int run(int argc, char** argv) {
    int rank = 0;
    int processes = 1;
    MPI_Comm_rank(MPI_COMM_WORLD, &rank);
    MPI_Comm_size(MPI_COMM_WORLD, &processes);
    const Options options = parse(argc, argv);
    const std::size_t n = options.size;
    const Layout layout{n, options.block, processes};

    Field::initialize();
    double warm_seconds = 0;
    if (options.warm) {
        const double mine = warm_field_tables();
        MPI_Reduce(&mine, &warm_seconds, 1, MPI_DOUBLE, MPI_MAX, 0, MPI_COMM_WORLD);
    }
    std::string node;
    const int nodes = count_nodes(rank, processes, node);

    std::vector<Problem> problems;
    if (rank == 0) {
        problems = build_problems(options);
        std::cout << std::fixed << std::setprecision(9) << "Matrix dimension " << n << '\n'
                  << "Processes " << processes << " on " << nodes << " node(s)\n"
                  << "Panel width " << options.block << '\n'
                  << "Case " << options.matrix_case << ", seed " << options.seed << '\n'
                  << "Table warm-up seconds " << warm_seconds << '\n';
    }
    const std::size_t problem_count = options.matrix_case == "random" ? 2 : 1;

    bool all_match = true;
    for (std::size_t p = 0; p < problem_count; ++p) {
        for (int repeat = 0; repeat < options.repeats; ++repeat) {
            // Rank 0 times the sequential run while the others sleep. The
            // sequential and the MPI run take turns going first: both work on
            // the same matrix, so whichever runs second finds the processor's
            // caches warmed by the first, and alternating keeps that from
            // favouring one of the two.
            const bool sequential_first = (p + static_cast<std::size_t>(repeat)) % 2 == 0;
            Element reference = Element::zero();
            double sequential_seconds = 0;
            const auto time_sequential = [&] {
                const auto start = Clock::now();
                reference = sequential_determinant(problems[p].entries, n);
                sequential_seconds = seconds(start);
            };
            if (rank == 0) {
                if (options.sequential && sequential_first) {
                    time_sequential();
                }
                for (int other = 1; other < processes; ++other) {
                    MPI_Send(nullptr, 0, MPI_BYTE, other, start_tag, MPI_COMM_WORLD);
                }
            } else {
                wait_for_message(0, start_tag);
                MPI_Recv(nullptr, 0, MPI_BYTE, 0, start_tag, MPI_COMM_WORLD, MPI_STATUS_IGNORE);
            }

            MPI_Barrier(MPI_COMM_WORLD);
            Timing timing;
            std::uint64_t broadcast_bytes = 0;
            static const std::vector<Element> nothing;
            const Element determinant = distributed_determinant(
                layout, rank == 0 ? problems[p].entries : nothing, timing, broadcast_bytes);

            // Collect the per-process phase times: the largest and the total.
            double mine[3] = {timing.factor, timing.broadcast, timing.update};
            double largest[3] = {};
            double total[3] = {};
            MPI_Reduce(mine, largest, 3, MPI_DOUBLE, MPI_MAX, 0, MPI_COMM_WORLD);
            MPI_Reduce(mine, total, 3, MPI_DOUBLE, MPI_SUM, 0, MPI_COMM_WORLD);

            if (rank != 0) {
                continue;
            }
            if (options.sequential && !sequential_first) {
                time_sequential();
            }
            const double mpi_seconds = timing.distribute + timing.eliminate;
            const bool match = !options.sequential || determinant == reference;
            all_match = all_match && match;
            std::cout << "det(" << problems[p].name << ") = " << determinant << '\n';
            if (options.sequential) {
                std::cout << "Sequential seconds " << sequential_seconds << '\n';
            }
            std::cout << "MPI seconds " << mpi_seconds << " (distribute " << timing.distribute
                      << ", eliminate " << timing.eliminate << ")\n";
            if (options.sequential) {
                std::cout << "Results match " << std::boolalpha << match << '\n';
            }
            std::cout << std::flush;

            if (!options.csv.empty()) {
                std::ifstream probe(options.csv);
                const bool exists = probe.good();
                probe.close();
                std::ofstream csv(options.csv, std::ios::app);
                if (!exists) {
                    csv << "label,node,nodes,processes,size,block,case,matrix,repeat,warm,"
                           "warm_seconds,sequential_seconds,mpi_seconds,distribute_seconds,"
                           "eliminate_seconds,factor_seconds_sum,broadcast_seconds_max,"
                           "update_seconds_max,update_seconds_sum,panels,broadcast_bytes,"
                           "distributed_bytes,match,determinant,order\n";
                }
                const std::size_t sent_columns = n - layout.columns_of(0);
                csv << std::fixed << std::setprecision(9) << csv_field(options.label) << ','
                    << csv_field(node) << ',' << nodes << ',' << processes << ',' << n << ','
                    << options.block << ',' << options.matrix_case << ','
                    << problems[p].name << ',' << repeat << ',' << (options.warm ? 1 : 0) << ','
                    << warm_seconds << ',';
                if (options.sequential) {
                    csv << sequential_seconds;
                }
                csv << ',' << mpi_seconds << ',' << timing.distribute << ',' << timing.eliminate
                    << ',' << total[0] << ',' << largest[1] << ',' << largest[2] << ','
                    << total[2] << ',' << layout.panels() << ',' << broadcast_bytes << ','
                    << sent_columns * n * sizeof(Element) << ','
                    << (options.sequential ? (match ? "yes" : "NO") : "") << ','
                    << coefficients_text(determinant) << ','
                    << (!options.sequential ? "" : sequential_first ? "sequential-first"
                                                                    : "mpi-first")
                    << '\n';
            }
        }
    }
    return all_match ? 0 : 2;
}

}

int main(int argc, char** argv) {
    MPI_Init(&argc, &argv);
    int status = 1;
    try {
        status = run(argc, argv);
    } catch (const std::exception& error) {
        std::cerr << error.what() << '\n';
        MPI_Abort(MPI_COMM_WORLD, 1);
    }
    MPI_Finalize();
    return status;
}
