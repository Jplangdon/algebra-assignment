add_executable(algebra_determinants main.cpp)
target_compile_features(algebra_determinants PRIVATE cxx_std_20)
target_compile_definitions(algebra_determinants PRIVATE
    ALGEBRA_ASSIGNMENT_SIZE=${ALGEBRA_ASSIGNMENT_SIZE}
)
target_link_libraries(algebra_determinants PRIVATE
    algebra::finite_fields
    algebra::matrices
)

if(ALGEBRA_ASSIGNMENT_BUILD_CACHED_TOOLS)
    find_package(MPI COMPONENTS CXX)
    if(MPI_CXX_FOUND)
        add_executable(algebra_mpi_determinant mpi_determinant.cpp)
        target_compile_features(algebra_mpi_determinant PRIVATE cxx_std_20)
        target_link_libraries(algebra_mpi_determinant PRIVATE
            algebra::finite_fields
            MPI::MPI_CXX
        )
    else()
        message(STATUS "MPI was not found, so algebra_mpi_determinant will not be built")
    endif()
endif()
