// Shows how the cached field's tables fill up during the assignment's workload.
//
// The program repeats what the assignment program does (generate A and B,
// compute C = A * B, then the three determinants) for one matrix size chosen
// at run time. It counts every field operation it asks for and reads how many
// table slots are filled afterwards. A filled slot is one cache miss, so
//   hits = operations - filled slots.
//
// Usage: algebra_cache_statistics SIZE [CSV_FILE]

#include <cstddef>
#include <cstdint>
#include <cstdlib>
#include <fstream>
#include <iostream>
#include <random>
#include <string>
#include <utility>
#include <vector>
#include <algebra/finite_fields/finite_fields.hpp>

namespace {

using Field = algebra::FiniteField<11, 3>;
using Element = Field::Element;
constexpr std::uint32_t seed = 123456u;

struct Counts {
    std::uint64_t adds = 0;
    std::uint64_t multiplies = 0;
    std::uint64_t negations = 0;
    std::uint64_t reciprocals = 0;
};

Counts counts;

std::uint32_t draw_coefficient(std::mt19937& generator, std::uint32_t prime) {
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

std::vector<Element> product(const std::vector<Element>& a, const std::vector<Element>& b,
                             std::size_t n) {
    std::vector<Element> result(n * n);
    for (std::size_t i = 0; i < n; ++i) {
        for (std::size_t j = 0; j < n; ++j) {
            Element sum = Element::zero();
            for (std::size_t k = 0; k < n; ++k) {
                sum = sum.add(a[i * n + k].multiply(b[k * n + j]));
            }
            result[i * n + j] = sum;
        }
    }
    counts.multiplies += static_cast<std::uint64_t>(n) * n * n;
    counts.adds += static_cast<std::uint64_t>(n) * n * n;
    return result;
}

Element determinant(std::vector<Element> matrix, std::size_t n) {
    Element result = Element::one();
    for (std::size_t k = 0; k < n; ++k) {
        std::size_t pivot_row = k;
        while (pivot_row < n && matrix[pivot_row * n + k].is_zero()) {
            ++pivot_row;
        }
        if (pivot_row == n) {
            return Element::zero();
        }
        if (pivot_row != k) {
            for (std::size_t j = 0; j < n; ++j) {
                std::swap(matrix[pivot_row * n + j], matrix[k * n + j]);
            }
            result = result.negate();
            ++counts.negations;
        }
        const Element pivot = matrix[k * n + k];
        result = result.multiply(pivot);
        ++counts.multiplies;
        Element inverse = Element::one();
        if (!pivot.is_one()) {
            inverse = pivot.reciprocal();
            ++counts.reciprocals;
        }
        for (std::size_t i = k + 1; i < n; ++i) {
            if (matrix[i * n + k].is_zero()) {
                continue;
            }
            const Element multiplier = matrix[i * n + k].multiply(inverse);
            ++counts.multiplies;
            matrix[i * n + k] = Element::zero();
            for (std::size_t j = k + 1; j < n; ++j) {
                const Element correction = multiplier.multiply(matrix[k * n + j]);
                matrix[i * n + j] = matrix[i * n + j].add(correction.negate());
            }
            const std::uint64_t width = n - k - 1;
            counts.multiplies += width;
            counts.negations += width;
            counts.adds += width;
        }
    }
    return result;
}

void report(std::ostream& out, std::size_t n, const char* phase) {
    const auto filled = Field::cache_statistics();
    out << n << ',' << phase << ',' << counts.adds << ',' << counts.multiplies << ','
        << counts.negations << ',' << counts.reciprocals << ',' << filled.sums << ','
        << filled.products << ',' << filled.negatives << ',' << filled.reciprocals << ','
        << filled.order * filled.order << '\n';
}

}

int main(int argc, char** argv) {
    if (argc < 2) {
        std::cerr << "Usage: " << argv[0] << " SIZE [CSV_FILE]\n";
        return 64;
    }
    const std::size_t n = std::strtoull(argv[1], nullptr, 10);
    const std::string csv_path = argc > 2 ? argv[2] : "";
    const char* header = "size,phase,adds,multiplies,negations,reciprocals,sums_filled,"
                         "products_filled,negatives_filled,reciprocals_filled,pair_slots\n";

    std::ofstream file;
    bool write_header = true;
    if (!csv_path.empty()) {
        write_header = !std::ifstream(csv_path).good();
        file.open(csv_path, std::ios::app);
    }
    std::ostream& out = csv_path.empty() ? std::cout : file;
    if (write_header) {
        out << header;
    }

    Field::initialize();
    std::mt19937 generator(seed);
    std::vector<Element> a(n * n);
    std::vector<Element> b(n * n);
    for (std::size_t i = 0; i < n; ++i) {
        for (std::size_t j = 0; j < n; ++j) {
            a[i * n + j] = next_element(generator);
            b[i * n + j] = next_element(generator);
        }
    }
    const std::vector<Element> c = product(a, b, n);
    report(out, n, "product");
    const Element det_a = determinant(a, n);
    const Element det_b = determinant(b, n);
    const Element det_c = determinant(c, n);
    report(out, n, "determinants");
    return det_c == det_a.multiply(det_b) ? 0 : 1;
}
