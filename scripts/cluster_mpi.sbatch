#!/bin/bash -l
#SBATCH --job-name=algebra-mpi
#SBATCH --nodes=4
#SBATCH --ntasks-per-node=1
#SBATCH --time=00:05:00
#SBATCH --partition=demo
#SBATCH --exclusive
#SBATCH --output=slurm-%j.out
#
# Runs part of the MPI sweep with one process per node, so that every process is
# on a different machine. The settings above are the ones the course cluster
# needs: the demo partition, its 5 minute limit, and --exclusive, without which
# the cluster runs two jobs on the same machines at the same time.
#
# From the repository folder on the login node, after the build described in
# docs/RUNNING.md, section 5:
#
#     sbatch scripts/cluster_mpi.sbatch --processes "2 4" --sizes "100 200 400" --repeat 3
#
# Everything after the script name is passed on to scripts/run_mpi.sh. Choose
# sizes and repeats that fit in the time limit. The six commands that produced
# the measurements in results/mpi.csv are listed in docs/RUNNING.md, section 5.
#
# On a cluster that starts MPI programs with srun instead of mpirun, add:
#     export MPI_LAUNCHER=srun
module load openmpi
set -euo pipefail
cd "${SLURM_SUBMIT_DIR:-.}"
bash scripts/run_mpi.sh --skip-build --label "${ALGEBRA_LABEL:-cluster}" "$@"
