# Running everything

Every command below is typed from inside the `algebra-assignment` folder unless the step says otherwise. Nothing here needs a GitHub account or an SSH key: the scripts read the public `nathanjrussell` repositories over HTTPS.

## 0. What you need

Two folders next to each other:

```
some-folder/
    algebra-assignment/              this repository
    algebra-finite-fields-cached/    the cached finite field library
```

The scripts look for the library at `../algebra-finite-fields-cached`. If it lives somewhere else, put the path in the `CACHED_FIELDS` variable, for example `CACHED_FIELDS=/home/jplangdon/libs/algebra-finite-fields-cached scripts/run_sequential.sh`.

On Ubuntu (including WSL), the tools are installed with:

```sh
sudo apt update
sudo apt install build-essential cmake git python3 python3-matplotlib openmpi-bin libopenmpi-dev valgrind
```

`valgrind` is only used for one profile and can be left out. CMake has to be 3.24 or newer (`cmake --version`).

Files that were downloaded one at a time or copied through Windows lose their executable mark, and a script then answers `Permission denied`. Run this once, from inside `algebra-assignment`, before anything else:

```sh
chmod +x scripts/*.sh
```

## 1. Check that the cached library is correct

```sh
scripts/test_library.sh
```

This builds the library's unit tests and runs them. It should end with `100% tests passed, 0 tests failed out of 21`. Eleven of those are the original library's own tests, unchanged. Ten are new and compare the cached class with the original.

## 2. Check that the MPI program is correct

```sh
scripts/test_mpi.sh
```

It should end with `222 passed, 0 failed`. Every one of those runs computes a determinant sequentially and with MPI and compares the two.

## 3. Before and after caching (runtime and peak memory)

```sh
scripts/run_sequential.sh --label lemmen
```

`--label` is the name this machine gets in the tables. Use any short name without spaces. Results go to `results/sequential.csv`.

| Command | Sizes, original | Sizes, cached | Rough time |
| --- | --- | --- | --- |
| `scripts/run_sequential.sh --label lemmen --preset quick` | 100, 200, 400 | 100 to 1000 | a few minutes |
| `scripts/run_sequential.sh --label lemmen` | 100 to 800 | 100 to 2000 | about 20 minutes |
| `scripts/run_sequential.sh --label lemmen --preset overnight` | 100 to 4000 | 100 to 6000 | most of a day |
| `scripts/run_sequential.sh --label lemmen --original "" --cached "4000"` | none | 4000 | under an hour |

The times are what the cloud test machine needed; a faster processor needs less. The original program at 4000 is the long one (the assignment quotes 6 hours 40 minutes on an M3 Max).

A size that is already in the file for that label is skipped, so a run that was stopped can be started again with the same command.

Each size is run once. `--repeat 5` runs each size five times, and the report then uses the median. That is worth doing for the sizes that take seconds, where one run can be off by a lot:

```sh
scripts/run_sequential.sh --label lemmen --original "100 200 400" --cached "100 200 400 800 1000" --repeat 5
```

## 4. MPI against sequential on one machine

```sh
scripts/run_mpi.sh --label lemmen
```

This uses 1, 2, 4, ... processes up to the number of processors, sizes from 10 to 2000, panel width 8, and five repeats. Results go to `results/mpi.csv`. To choose yourself:

```sh
scripts/run_mpi.sh --label lemmen --processes "1 2 4 8" --sizes "100 200 400 800 1000 2000"
scripts/run_mpi.sh --label lemmen --processes "4" --blocks "1 4 32 128" --sizes "100 200 400 800 1000 2000"
```

The second line is the panel-width comparison.

## 5. MPI across several machines (the course cluster)

The assignment asks for determinants "across multiple machines", so the numbers that count for the break-even point are these.

1. Copy both folders to the login node. From the folder that holds them, on your own computer:

   ```sh
   scp -r algebra-assignment algebra-finite-fields-cached jplang01@mpi.nathan.cse.louisville.edu:~/
   ```

2. Log in and build on the login node (the compute nodes may have no internet access, and the first build downloads the other algebra repositories):

   ```sh
   ssh jplang01@mpi.nathan.cse.louisville.edu
   cd ~/algebra-assignment
   scripts/run_mpi.sh --build-only
   ```

3. Submit the job:

   ```sh
   sbatch scripts/cluster_mpi.sbatch
   ```

   The job script asks for 4 nodes with one process on each and runs the sweep with 1, 2 and 4 processes under the label `cluster`. To use a different number of machines, change the `#SBATCH --nodes=4` line. If the cluster needs a `module load` line or a partition name, copy those lines from the job script that worked for the Pi assignment. If that script started its program with `srun` instead of `mpirun`, add the line `export MPI_LAUNCHER=srun` as well. The place for these lines is marked in `scripts/cluster_mpi.sbatch`.

4. Watch it with `squeue -u jplang01`. The output is in `slurm-<job number>.out` and the results in `results/mpi.csv`.

5. Copy the results back. On your own computer, from inside `algebra-assignment`:

   ```sh
   scp jplang01@mpi.nathan.cse.louisville.edu:~/algebra-assignment/results/mpi.csv results/mpi-cluster.csv
   scp jplang01@mpi.nathan.cse.louisville.edu:~/algebra-assignment/results/environments.csv results/environments-cluster.csv
   ```

   Then add their rows to the local files. Rows that are already there are not added twice:

   ```sh
   python3 scripts/bench.py merge results/mpi-cluster.csv results/mpi.csv
   python3 scripts/bench.py merge results/environments-cluster.csv results/environments.csv
   ```

   The two `-cluster` files can be deleted afterwards. The same command combines result files that group members send from their own machines, for example `python3 scripts/bench.py merge sequential-from-diego.csv results/sequential.csv`.

## 6. The profiles

```sh
scripts/run_profile.sh --label lemmen
```

About two minutes. It writes `results/profile_original.csv` (where the original program spends its instructions), `results/cache_statistics.csv` (how the tables fill up) and `results/lookup_benchmark.csv` (cost of one operation three ways).

## 7. Figures, tables and numbers for the report

```sh
python3 scripts/make_report_assets.py --sequential-label lemmen --mpi-label cluster
```

- `--sequential-label` is the machine whose before-and-after numbers go in the report.
- `--mpi-label` is the machine or cluster whose MPI numbers go in the report.
- Left out, each one defaults to the label with the most measurements.

It writes `report/figures/*.pdf`, `report/generated/*.tex`, `slides/figures/*.png` and `slides/data.json`. Every measured number in the report comes from those files, so after new measurements run this again and recompile. The text itself does not have to be edited for the numbers to change, but read the results paragraphs again afterwards, because sentences that interpret the numbers were written against the first set of measurements.

## 8. The report

On Overleaf: upload the whole `report` folder (including `figures`, `generated` and `sections`) and compile `ieee_report.tex`.

On your own computer:

```sh
sudo apt install texlive-latex-recommended texlive-latex-extra texlive-publishers texlive-fonts-recommended texlive-bibtex-extra
cd report
pdflatex ieee_report && bibtex ieee_report && pdflatex ieee_report && pdflatex ieee_report
```

## 9. The slides

`slides/presentation.pptx` opens in PowerPoint as it is. Its charts are ordinary PowerPoint charts, so a value can also be changed by hand with **Edit Data**.

To rebuild the deck from new measurements, after step 7:

```sh
sudo apt install nodejs npm
cd slides
npm install pptxgenjs
node make_slides.js
```

This replaces `slides/presentation.pptx`, including anything edited in it by hand. If the deck has been edited in PowerPoint, keep that copy under another name first. The same figures the report uses are in `slides/figures` as pictures, in case pasting one is easier.

## 10. Building the assignment program by hand

The scripts above pick the library folder for you. To build exactly as the assignment's README does, CMake needs to know where the cached library is. Until the library is on GitHub, point it at the folder:

```sh
cmake -S . -B build -DCMAKE_BUILD_TYPE=Release -DALGEBRA_ASSIGNMENT_SIZE=400 \
    -DFETCHCONTENT_SOURCE_DIR_ALGEBRA_FINITE_FIELDS=../algebra-finite-fields-cached
cmake --build build --parallel
./build/src/algebra_determinants
```

Once the library is on GitHub with the tag named in `cmake/Dependencies.cmake`, the `-DFETCHCONTENT_SOURCE_DIR...` line is no longer needed. That one file is the only place where the program chooses between the original and the cached library.

If the first `cmake` command stops with `Permission denied (publickey)`, the machine has no SSH key registered with GitHub. Either add one, or run this once, which makes git use HTTPS for GitHub:

```sh
git config --global url."https://github.com/".insteadOf "git@github.com:"
```

The MPI program by hand:

```sh
mpirun -n 4 ./build/src/algebra_mpi_determinant --size 1000
mpirun -n 4 ./build/src/algebra_mpi_determinant --size 1000 --block 32 --repeat 5
```

Options: `--size N`, `--block B` (panel width, default 8), `--repeat R`, `--case random|sparse|permutation|singular|zero-leading`, `--seed S`, `--csv FILE`, `--label TEXT`, `--no-warm` (do not fill the tables before timing), `--no-sequential` (skip the sequential reference).

## 11. Putting the cached library on GitHub

`cmake/Dependencies.cmake` expects the library at `git@github.com:Jplangdon/algebra-finite-fields-cached.git` with the tag `cached-v1`. Nothing exists there yet. Forking the original keeps its history, so anyone can see exactly which files changed.

1. On GitHub, open `https://github.com/nathanjrussell/algebra-finite-fields`, press **Fork**, and name the fork `algebra-finite-fields-cached`.

2. Put the cached files on top of the commit the assignment uses, and tag the result. From the folder that holds `algebra-finite-fields-cached`:

   ```sh
   git clone git@github.com:Jplangdon/algebra-finite-fields-cached.git fork
   cd fork
   git checkout -b cached 74b3d569fb48818f4c10f3c32889f2128485f1a7
   cp -r ../algebra-finite-fields-cached/. .
   git add -A
   git commit -m "Add a cached finite field as a drop-in replacement"
   git tag cached-v1
   git push -u origin cached --tags
   ```

   `git status` before the commit should list five files: `README.md`, `test/CMakeLists.txt`, the new `finite_field.hpp`, `uncached_finite_field.hpp` and `test/cached_finite_field_test.cpp`.

3. Check the switch. In `algebra-assignment`, build with no extra options, as the assignment README does:

   ```sh
   cmake -S . -B build-check -DCMAKE_BUILD_TYPE=Release -DALGEBRA_ASSIGNMENT_SIZE=400
   cmake --build build-check --parallel
   ./build-check/src/algebra_determinants
   ```

   It should print `Identity verified true` after a few seconds. With the original library the same size takes about a minute.

If the fork lives under another account or name, change the `GIT_REPOSITORY` line in `cmake/Dependencies.cmake` to match. That line and `GIT_TAG` are the only two that select the library.
