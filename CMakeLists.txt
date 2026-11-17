cmake_minimum_required(VERSION 3.24)
project(algebra_assignment VERSION 0.1.0 LANGUAGES CXX)

set(ALGEBRA_ASSIGNMENT_SIZE 4000 CACHE STRING "Square matrix dimension")
if(NOT ALGEBRA_ASSIGNMENT_SIZE MATCHES "^[1-9][0-9]*$")
    message(FATAL_ERROR "The matrix dimension must be a positive integer")
endif()

option(ALGEBRA_ASSIGNMENT_BUILD_CACHED_TOOLS "Build the programs that need the cached finite field" ON)

include(cmake/Dependencies.cmake)

# The MPI program and the benchmark tools use the cached finite field directly.
# When the dependency points at the original library they are left out, so that
# switching libraries stays a change to cmake/Dependencies.cmake and nothing else.
if(ALGEBRA_ASSIGNMENT_BUILD_CACHED_TOOLS AND DEFINED algebra_finite_fields_SOURCE_DIR AND NOT EXISTS
   "${algebra_finite_fields_SOURCE_DIR}/include/algebra/finite_fields/uncached_finite_field.hpp")
    message(STATUS "The finite field library is not the cached one: the MPI program and the benchmark tools are not built")
    set(ALGEBRA_ASSIGNMENT_BUILD_CACHED_TOOLS OFF)
endif()

add_subdirectory(src)
if(ALGEBRA_ASSIGNMENT_BUILD_CACHED_TOOLS)
    add_subdirectory(benchmarks)
endif()
