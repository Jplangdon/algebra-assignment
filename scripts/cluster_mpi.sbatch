#!/bin/bash -l
#SBATCH --job-name=algebra-mpi
#SBATCH --nodes=4
#SBATCH --ntasks-per-node=1
#SBATCH --time=00:05:00
#SBATCH --partition=demo
#SBATCH --output=slurm-%j.out
#
# Runs the MPI sweep with one process per node, so that every process is on a
# different machine. From the repository folder on the login node:
#
#     scripts/run_mpi.sh --build-only
#     sbatch scripts/cluster_mpi.sbatch
#
# Change --nodes above to the number of machines to use. The sweep runs with
# 1, 2, 4, ... processes up to that number. Extra options are passed on, for
# example:  sbatch scripts/cluster_mpi.sbatch --blocks "1 4 16 64"
#
# If jobs on this cluster need a "module load" line, put it below this comment.
# If they start MPI programs with srun instead of mpirun, also add:
#     export MPI_LAUNCHER=srun
module load openmpi
set -euo pipefail
cd "${SLURM_SUBMIT_DIR:-.}"
bash scripts/run_mpi.sh --skip-build --label "${ALGEBRA_LABEL:-cluster}" "$@"
