# Kanban cards

The assignment asks for a GitHub Kanban board with tasks assigned to each group member, and says standalone cards are enough. These are the cards, ready to paste. On GitHub: **Projects → New project → Board**, then **Add item** in a column, paste the title, open the card and paste the description, and set the assignee.

The owner column is a suggestion so that every member has code, measurement and writing work. Change it to whatever the group agrees.

Status is the state of the files as they are now, not a column the card has to stay in.

## Cached finite field

| # | Title | Description | Suggested owner | Status |
| --- | --- | --- | --- | --- |
| 1 | Publish the cached finite field library | Create the repository `algebra-finite-fields-cached`, push the folder, add the tag `cached-v1`. The group repository's `cmake/Dependencies.cmake` names this repository and tag. | Jacob | Done: `Jplangdon/algebra-finite-fields-cached`, tag `cached-v1` |
| 2 | Walk through the cached class | Read `include/algebra/finite_fields/finite_field.hpp` with `docs/EXPLAINER.md` next to it. Be able to explain the index numbering, the four tables, a hit and a miss. Note anything unclear on the card. | Everyone | Not started |
| 3 | Run the unit tests on each machine | `scripts/test_library.sh` on every member's computer. Put the compiler version and the result on the card. Expected: 21 of 21 pass. | Everyone | Passes with GCC 13 and Clang 18 on the test machine, and with GCC 15.2 on lemmen (21 of 21). Other machines open |
| 4 | Confirm the CMake switch | After card 1, build the program exactly as the assignment README says, with no extra options, and check it fetches the cached library and prints `Identity verified true`. | Diego | Done by Jacob on lemmen on 17 November, at size 400 |

## MPI determinant

| # | Title | Description | Suggested owner | Status |
| --- | --- | --- | --- | --- |
| 5 | Walk through the MPI program | Read `src/mpi_determinant.cpp`: how columns are dealt out, what one panel broadcast contains, how the sign and a zero determinant are handled. | Bishoy, varshika | Not started |
| 6 | Run the MPI tests | `scripts/test_mpi.sh`. Expected: `222 passed, 0 failed`. | Bishoy | Passes on the test machine and on lemmen (222 passed, 0 failed) |
| 7 | Cluster sweep | On the course cluster: `scripts/run_mpi.sh --build-only`, then `sbatch scripts/cluster_mpi.sbatch`. Copy `results/mpi.csv` back. Steps are in `docs/RUNNING.md`, section 5. | Jacob | Done: label `cluster` in `results/mpi.csv`, 1, 2 and 4 nodes, 3 repeats |
| 8 | Panel width on the cluster | `sbatch scripts/cluster_mpi.sbatch --blocks "1 4 32 128" --sizes "100 200 400 800 1000 2000"`. Over a real network the best width may differ from the single-machine result. | Jacob | Done: Table VII of the report |

## Measurements

| # | Title | Description | Suggested owner | Status |
| --- | --- | --- | --- | --- |
| 9 | Before and after on our own machines | `scripts/run_sequential.sh --label <machine name>` on each member's computer, then send `results/sequential.csv` and `results/environments.csv`. Whoever collects them combines the files with `python3 scripts/bench.py merge` (see `docs/RUNNING.md`, section 5). | Diego, Bishoy, varshika, Jacob | Measured on cloud-vm and lemmen; the report uses lemmen |
| 10 | The long runs | One machine runs `scripts/run_sequential.sh --label <machine name> --preset overnight` for the 4000 × 4000 original and the 6000 × 6000 cached figures the assignment quotes. | Diego | Cached 4000 measured on lemmen. Original 4000 and cached 6000 not run |
| 11 | Profiles | `scripts/run_profile.sh --label <machine name>` on the machine used for the report. | varshika | Done by Jacob on lemmen; the three profile files in `results/` are from that run |

## Report

| # | Title | Description | Suggested owner | Status |
| --- | --- | --- | --- | --- |
| 12 | Regenerate figures and tables | After cards 7 to 11: `python3 scripts/make_report_assets.py --sequential-label <machine name> --mpi-label cluster`, then recompile. | Jacob | Done: generated from lemmen and cluster |
| 13 | Check the results text against the new numbers | The numbers update by themselves, the sentences that interpret them do not. Read sections VII and IX against the new tables, and the limitations section, which describes the test machine. | Bishoy | Not started |
| 14 | Proofread the report | Each member reads the whole PDF once. Sections I to VI: Diego and varshika. Sections VII to XI: Bishoy and Jacob. | Everyone | Compiles; the current PDF was checked against the results |
| 15 | Upload to Overleaf | Upload the `report` folder as it is and compile `ieee_report.tex`. | varshika | Done by Jacob on 17 November: folder `Jacob Report` in the group's Overleaf project, compiles to 7 pages |

## Presentation

| # | Title | Description | Suggested owner | Status |
| --- | --- | --- | --- | --- |
| 16 | Update the slides | After card 12, rebuild the deck with `node slides/make_slides.js` (see `docs/RUNNING.md`, section 9), or change the chart values and the numbers on the results slides by hand in PowerPoint. | varshika | Done: PowerPoint rebuilt from lemmen and cluster; Beamer version in `slides/presentation.tex` |
| 17 | Split the talk and rehearse | Decide who presents which part. Each presenter reads the speaker notes for their slides and the question list in `docs/EXPLAINER.md`. | Everyone | Not started |

## Board

| # | Title | Description | Suggested owner | Status |
| --- | --- | --- | --- | --- |
| 18 | Create the board | Make the GitHub project, add these cards, assign them, and keep the columns current as work is finished. | Jacob | Board `algebra-assignment board` created on 17 November and linked under this repository's Projects tab |
