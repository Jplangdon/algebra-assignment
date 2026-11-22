# Running everything

Every command below is typed from inside the `algebra-assignment` folder unless the step says otherwise. Nothing here needs a GitHub account or an SSH key: the scripts read the public `nathanjrussell` repositories over HTTPS.

## 0. What you need

Two folders next to each other:

```
some-folder/
    algebra-assignment/              this repository
    algebra-finite-fields-cached/    the cached finite field library
```

Both are on GitHub. From the folder that should hold them:

```sh
git clone https://github.com/Jplangdon/algebra-assignment.git
git clone https://github.com/Jplangdon/algebra-finite-fields-cached.git
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
| `scripts/run_sequential.sh --label lemmen --preset quick` | 100, 200, 400 | 100 to 1000 | about a minute |
| `scripts/run_sequential.sh --label lemmen` | 100 to 800 | 100 to 2000 | about 7 minutes |
| `scripts/run_sequential.sh --label lemmen --preset overnight` | 100 to 4000 | 100 to 6000 | most of a day |
| `scripts/run_sequential.sh --label lemmen --original "" --cached "4000"` | none | 4000 | about 20 minutes |

The first, second and fourth times are worked out from the run times measured on Lemmen (Intel Core Ultra 9 275HX); a slower processor needs more. The overnight preset was not run, so its time is an estimate. The original program at 4000 is the long one (the assignment quotes 6 hours 40 minutes on an M3 Max).

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

The rows labelled `cluster` in `results/mpi.csv` were measured on the course cluster on the evening of 17 November 2026, in jobs 99 to 104, with the steps below. The cluster's clock runs on UTC, so its own records show 18 November. Three things about that cluster shape the steps:

- Its CMake is 3.22, and the algebra repositories need 3.24.
- MPI comes from a module, loaded with `module load openmpi`.
- The `demo` partition stops every job after 5 minutes, and it puts two jobs on the same machines unless a job asks for them with `--exclusive`.

1. Log in and get both repositories:

   ```sh
   ssh jplang01@mpi.nathan.cse.louisville.edu
   cd ~
   git clone https://github.com/Jplangdon/algebra-assignment.git
   git clone https://github.com/Jplangdon/algebra-finite-fields-cached.git
   ```

2. Put a newer CMake in the home folder, load MPI and build on the login node:

   ```sh
   curl -L -o cmake.tar.gz https://github.com/Kitware/CMake/releases/download/v3.28.3/cmake-3.28.3-linux-x86_64.tar.gz
   tar xzf cmake.tar.gz
   rm cmake.tar.gz
   export PATH=$HOME/cmake-3.28.3-linux-x86_64/bin:$PATH
   module load openmpi
   cd ~/algebra-assignment
   scripts/run_mpi.sh --build-only
   ```

   The `export` line lasts for one login. It is only needed for building.

3. Submit the sweep as six short jobs. Each one fits in the 5 minutes, and because the job script asks for its machines with `--exclusive`, they run one after another:

   ```sh
   sbatch scripts/cluster_mpi.sbatch --processes "2 4" --sizes "10 20 30 40 50 75 100 150 200 300 400 600 800 1000" --repeat 3
   sbatch scripts/cluster_mpi.sbatch --processes "2" --sizes "1500 2000" --repeat 3
   sbatch scripts/cluster_mpi.sbatch --processes "4" --sizes "1500 2000" --repeat 3
   sbatch scripts/cluster_mpi.sbatch --processes "1" --sizes "10 20 30 40 50 75 100 150 200 300 400 600 800 1000 1500" --repeat 3
   sbatch scripts/cluster_mpi.sbatch --processes "1" --sizes "2000" --repeat 3
   sbatch scripts/cluster_mpi.sbatch --processes "4" --blocks "1 4 32 128" --sizes "100 200 400 800 1000" --repeat 3
   ```

   The job script asks for 4 machines with one process on each, so a run with 2 processes uses 2 machines and a run with 4 uses 4. `--repeat 3` is given because the default is 5 and the committed `cluster` rows have 3. At N = 2000 one repeat of all process counts on both matrices takes close to 2 minutes, which is why the two largest sizes have jobs of their own. The last job is the panel-width comparison. Together the six took about 13 minutes.

4. Watch them with `squeue -u jplang01`. `PD` is waiting, `CF` is machines starting and `R` is running. The output of each job is in `slurm-<job number>.out` and should end with `Done. Results are in`. The results are in `results/mpi.csv`: 408 rows labelled `cluster`.

   A size that already has rows in the file for the label `cluster` is skipped. If the time limit stops a job in the middle of a size, delete that size's `cluster` rows from `results/mpi.csv` before submitting again, or the size stays short of its repeats.

5. Put the results in the repository. The login node has its own key on GitHub, so it can push:

   ```sh
   git remote set-url origin git@github.com:Jplangdon/algebra-assignment.git
   git add results/mpi.csv results/environments.csv
   git commit -m "Add the cluster measurements"
   git push
   ```

   If git asks who you are, set `git config user.name` and `git config user.email` first. Then `git pull` on your own computer.

The first attempt at sizes 1500 and 2000 went wrong and was thrown away. Two jobs were submitted together without `--exclusive`, the cluster ran them at the same time on the same machines, and both took about twice as long as they should have. All `cluster` rows were measured again with `--exclusive`. The discarded rows are in the history of this repository, in the commit before "Rerun the cluster measurements with exclusive nodes".

Result files that group members send from their own machines are combined with `python3 scripts/bench.py merge`, for example `python3 scripts/bench.py merge sequential-from-diego.csv results/sequential.csv`. Rows that are already there are not added twice.

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
- Left out, each defaults to the label with the most measurements. With the result files as they are now that is `cloud-vm` for both, so name the labels.

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
npm install pptxgenjs@4.0.1
node make_slides.js
```

`npm` leaves a `node_modules` folder and two `package` files in `slides`. Git ignores all three. This replaces `slides/presentation.pptx`, including anything edited in it by hand. If the deck has been edited in PowerPoint, keep that copy under another name first. The same figures the report uses are in `slides/figures` as pictures, in case pasting one is easier.

## 10. Building the assignment program by hand

The scripts above build against the library folder next to this one. Built exactly as the assignment's README does, with no extra options, CMake fetches the cached library from GitHub at the tag named in `cmake/Dependencies.cmake`:

```sh
cmake -S . -B build -DCMAKE_BUILD_TYPE=Release -DALGEBRA_ASSIGNMENT_SIZE=400
cmake --build build --parallel
./build/src/algebra_determinants
```

It should print `Identity verified true`. On Lemmen this size takes under 2 seconds with the cached library and about 23 seconds with the original.

That one file is the only place where the program chooses between the original and the cached library. To build against a local copy of the library instead, add `-DFETCHCONTENT_SOURCE_DIR_ALGEBRA_FINITE_FIELDS=../algebra-finite-fields-cached` to the first command.

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

`cmake/Dependencies.cmake` expects the library at `git@github.com:Jplangdon/algebra-finite-fields-cached.git` with the tag `cached-v1`, and it is published there. The steps below are how it was made, kept for reference. Forking the original keeps its history, so anyone can see exactly which files changed.

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
