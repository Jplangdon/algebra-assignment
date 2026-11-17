// Compares three ways of getting a + b and a * b in the field of order 11^3:
//
//   original       the polynomial arithmetic of the original library
//   unordered_map  results kept in std::unordered_map, keyed by the operand pair
//   table          the cached field of this project (one array slot per pair)
//
// Each method is timed on the same stream of random operands, in two patterns:
//
//   independent    out[i] = x[i] op y[i]
//   chained        acc = acc + x[i] * y[i], the inner loop of a matrix product,
//                  where each addition has to wait for the one before it
//
// Both caches are filled before the clock starts, so the times are for hits.
//
// Usage: algebra_lookup_benchmark [CSV_FILE]

#include <chrono>
#include <cstddef>
#include <cstdint>
#include <fstream>
#include <iostream>
#include <random>
#include <string>
#include <unordered_map>
#include <vector>
#include <algebra/finite_fields/finite_fields.hpp>

namespace {

using Field = algebra::FiniteField<11, 3>;
using Element = Field::Element;
using Original = algebra::uncached::FiniteField<11, 3>::Element;
using Clock = std::chrono::steady_clock;
constexpr std::size_t order = 1331;

double seconds(Clock::time_point start) {
    return std::chrono::duration<double>(Clock::now() - start).count();
}

std::uint16_t index_of(const Original& value) {
    std::size_t index = 0;
    for (std::size_t i = Field::extension_degree; i > 0; --i) {
        index = index * Field::characteristic + value.coefficient(i - 1).representative();
    }
    return static_cast<std::uint16_t>(index);
}

// The cache the assignment text suggests: one hash map per operation.
class MapField {
    std::vector<Original> elements_;
    std::unordered_map<std::uint32_t, std::uint16_t> sums_;
    std::unordered_map<std::uint32_t, std::uint16_t> products_;

    static std::uint32_t key(std::uint16_t a, std::uint16_t b) {
        return (std::uint32_t{a} << 16) | b;
    }

public:
    MapField() {
        for (std::size_t index = 0; index < order; ++index) {
            elements_.push_back(Original::from_index(index));
        }
    }

    std::uint16_t add(std::uint16_t a, std::uint16_t b) {
        const auto found = sums_.find(key(a, b));
        if (found != sums_.end()) {
            return found->second;
        }
        const std::uint16_t result = index_of(elements_[a].add(elements_[b]));
        sums_.emplace(key(a, b), result);
        return result;
    }

    std::uint16_t multiply(std::uint16_t a, std::uint16_t b) {
        const auto found = products_.find(key(a, b));
        if (found != products_.end()) {
            return found->second;
        }
        const std::uint16_t result = index_of(elements_[a].multiply(elements_[b]));
        products_.emplace(key(a, b), result);
        return result;
    }
};

struct Row {
    std::string method;
    std::string operation;
    std::string pattern;
    std::size_t operations;
    double seconds;
};

std::vector<Row> rows;
std::uint64_t checksum = 0;

void record(const char* method, const char* operation, const char* pattern,
            std::size_t operations, double elapsed) {
    rows.push_back({method, operation, pattern, operations, elapsed});
    std::cout << method << ' ' << operation << ' ' << pattern << ": "
              << 1e9 * elapsed / static_cast<double>(operations) << " ns per operation\n";
}

}

int main(int argc, char** argv) {
    Field::initialize();
    std::mt19937 generator(2026u);
    std::uniform_int_distribution<std::uint32_t> pick(0, order - 1);

    // Original arithmetic: fewer operations, because each one is slow.
    {
        constexpr std::size_t count = 2'000'000;
        std::vector<Original> x;
        std::vector<Original> y;
        for (std::size_t i = 0; i < 4096; ++i) {
            x.push_back(Original::from_index(pick(generator)));
            y.push_back(Original::from_index(pick(generator)));
        }
        auto start = Clock::now();
        for (std::size_t i = 0; i < count; ++i) {
            checksum += index_of(x[i % 4096].add(y[(i * 7) % 4096]));
        }
        record("original", "add", "independent", count, seconds(start));
        start = Clock::now();
        for (std::size_t i = 0; i < count; ++i) {
            checksum += index_of(x[i % 4096].multiply(y[(i * 7) % 4096]));
        }
        record("original", "multiply", "independent", count, seconds(start));
        start = Clock::now();
        Original accumulator = Original::zero();
        for (std::size_t i = 0; i < count; ++i) {
            accumulator = accumulator.add(x[i % 4096].multiply(y[(i * 7) % 4096]));
        }
        checksum += index_of(accumulator);
        record("original", "multiply-add", "chained", count, seconds(start));
    }

    constexpr std::size_t count = 20'000'000;
    std::vector<std::uint16_t> x(count);
    std::vector<std::uint16_t> y(count);
    for (std::size_t i = 0; i < count; ++i) {
        x[i] = static_cast<std::uint16_t>(pick(generator));
        y[i] = static_cast<std::uint16_t>(pick(generator));
    }

    // Hash maps keyed by the operand pair.
    {
        MapField field;
        for (std::size_t a = 0; a < order; ++a) {
            for (std::size_t b = 0; b < order; ++b) {
                field.add(static_cast<std::uint16_t>(a), static_cast<std::uint16_t>(b));
                field.multiply(static_cast<std::uint16_t>(a), static_cast<std::uint16_t>(b));
            }
        }
        auto start = Clock::now();
        for (std::size_t i = 0; i < count; ++i) {
            checksum += field.add(x[i], y[i]);
        }
        record("unordered_map", "add", "independent", count, seconds(start));
        start = Clock::now();
        for (std::size_t i = 0; i < count; ++i) {
            checksum += field.multiply(x[i], y[i]);
        }
        record("unordered_map", "multiply", "independent", count, seconds(start));
        start = Clock::now();
        std::uint16_t accumulator = 0;
        for (std::size_t i = 0; i < count; ++i) {
            accumulator = field.add(accumulator, field.multiply(x[i], y[i]));
        }
        checksum += accumulator;
        record("unordered_map", "multiply-add", "chained", count, seconds(start));
    }

    // The cached field.
    {
        std::vector<Element> elements;
        for (std::size_t index = 0; index < order; ++index) {
            elements.push_back(Element::from_index(index));
        }
        for (const Element& a : elements) {
            for (const Element& b : elements) {
                checksum += a.add(b).is_zero() ? 1 : 0;
                checksum += a.multiply(b).is_zero() ? 1 : 0;
            }
        }
        std::vector<Element> p(count);
        std::vector<Element> q(count);
        for (std::size_t i = 0; i < count; ++i) {
            p[i] = elements[x[i]];
            q[i] = elements[y[i]];
        }
        auto start = Clock::now();
        for (std::size_t i = 0; i < count; ++i) {
            checksum += p[i].add(q[i]).is_zero() ? 1 : 0;
        }
        record("table", "add", "independent", count, seconds(start));
        start = Clock::now();
        for (std::size_t i = 0; i < count; ++i) {
            checksum += p[i].multiply(q[i]).is_zero() ? 1 : 0;
        }
        record("table", "multiply", "independent", count, seconds(start));
        start = Clock::now();
        Element accumulator = Element::zero();
        for (std::size_t i = 0; i < count; ++i) {
            accumulator = accumulator.add(p[i].multiply(q[i]));
        }
        checksum += accumulator.is_zero() ? 1 : 0;
        record("table", "multiply-add", "chained", count, seconds(start));
    }

    std::cout << "checksum " << checksum << '\n';
    if (argc > 1) {
        const std::string path = argv[1];
        const bool exists = std::ifstream(path).good();
        std::ofstream csv(path, std::ios::app);
        if (!exists) {
            csv << "method,operation,pattern,operations,seconds,ns_per_operation\n";
        }
        for (const Row& row : rows) {
            csv << row.method << ',' << row.operation << ',' << row.pattern << ','
                << row.operations << ',' << row.seconds << ','
                << 1e9 * row.seconds / static_cast<double>(row.operations) << '\n';
        }
    }
    return 0;
}
