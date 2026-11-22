# Independent MPI Correctness Validation

**Project:** Caching Finite Field Arithmetic and Distributing Determinants with MPI  
**Contributor:** Varshika Kotapati  
**Testing Environment:** Ubuntu on Windows Subsystem for Linux (WSL)  
**Validation Method:** Independent compilation, execution, and comparison of sequential and MPI determinant implementations

## 1. Objective

The objective of this testing activity was to independently verify the correctness and reproducibility of the MPI-based determinant implementation.

Testing focused on confirming that the MPI implementation produces results consistent with the sequential reference implementation across multiple matrix configurations and process counts.

## 2. Environment and Build Verification

The repository was cloned locally and configured using CMake in Release mode.

The following tools were used:

- GNU C++ compiler
- CMake
- Open MPI
- Git
- Ubuntu on WSL

The project was configured with `ALGEBRA_ASSIGNMENT_SIZE=100`.

All five CMake build targets compiled successfully:

- `algebra_determinants`
- `algebra_mpi_determinant`
- `algebra_cache_statistics`
- `algebra_measure`
- `algebra_lookup_benchmark`

MPI process launching was independently verified using two local processes.

## 3. Testing Methodology

The MPI determinant executable was run using two and four processes on a single machine.

For each test, the program calculated the determinant using the sequential reference implementation and the MPI implementation.

Correctness was evaluated using the program's reported comparison result, `Results match true`.

The following matrix configurations were evaluated:

1. Random matrices
2. Singular matrices
3. Matrices with a zero leading pivot
4. Permutation matrices

All tests used the program's reported seed of `123456` and a panel width of 8.

## 4. Test Cases and Results

| Test ID | Matrix Type | Matrix Size | MPI Processes | Result |
|---|---|---|---|---|
| TC-01 | Random | 10 × 10 | 2 | PASS |
| TC-02 | Random | 50 × 50 | 4 | PASS |
| TC-03 | Singular | 50 × 50 | 4 | PASS |
| TC-04 | Zero-leading | 50 × 50 | 4 | PASS |
| TC-05 | Permutation | 50 × 50 | 4 | PASS |

Five independent test runs completed successfully, with seven determinant comparisons reporting agreement between sequential and MPI execution.

### 4.1 Random Matrix Testing

Random matrices were tested at dimensions 10 × 10 and 50 × 50.

The tests used two and four MPI processes, respectively. Each run evaluated two determinant calculations, and both calculations reported matching sequential and MPI results.

### 4.2 Singular Matrix Testing

A 50 × 50 singular matrix was evaluated using four MPI processes.

The determinant was reported as zero, and the sequential and MPI results matched.

This test exercised the implementation's handling of a singular input.

### 4.3 Zero-Leading-Pivot Testing

A 50 × 50 zero-leading-pivot matrix was evaluated using four MPI processes.

The test completed successfully, with matching sequential and MPI determinant results.

This provided additional coverage for pivot-related edge-case behavior.

### 4.4 Permutation Matrix Testing

A 50 × 50 permutation matrix was evaluated using four MPI processes.

The MPI and sequential implementations reported matching determinant results.

This provided additional coverage for structured matrix inputs.

## 5. Performance Observations

Execution times were recorded during correctness testing.

For the tested small matrices, MPI execution was generally slower than sequential execution. This is consistent with parallel coordination and communication overhead being significant relative to the small computational workload.

These observations are based on individual local executions and are not intended to reproduce the project's full performance benchmarks.

## 6. Validation Limitations

The tests were performed on one Ubuntu/WSL machine, not a multi-node computing cluster.

The validation confirms agreement between the sequential and MPI implementations for the selected test cases. It does not constitute an exhaustive correctness proof or independent verification of the sequential algorithm against a separate mathematical oracle.

The full performance benchmark suite was not reproduced.

## 7. Conclusion

Independent testing successfully verified the compilation and local execution of the MPI determinant implementation.

All five selected test runs passed, and all seven determinant comparisons reported agreement between the sequential and MPI implementations.

The results provide supplementary correctness evidence covering random matrices, singular matrices, zero-leading-pivot inputs, permutation matrices, and multiple MPI process configurations.
