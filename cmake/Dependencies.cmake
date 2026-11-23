include(FetchContent)

if(NOT TARGET algebra::finite_fields)
    FetchContent_Declare(
        algebra_finite_fields
        GIT_REPOSITORY git@github.com:Jplangdon/algebra-finite-fields-cached.git
        # The commit that is tagged cached-v1 there, pinned like every other dependency.
        GIT_TAG 6444da30dc44288c694e07a8811cf75a3ffcff2d
    )
    FetchContent_MakeAvailable(algebra_finite_fields)
endif()

if(NOT TARGET algebra::matrices)
    FetchContent_Declare(
        algebra_matrices
        GIT_REPOSITORY git@github.com:nathanjrussell/algebra-matrices.git
        GIT_TAG 84abddac26d2805072efcb1c44bbe7faac45fa6b
    )
    FetchContent_MakeAvailable(algebra_matrices)
endif()
