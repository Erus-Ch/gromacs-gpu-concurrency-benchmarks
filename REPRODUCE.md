# Reproducing the RNase GPU concurrency study

The measurements use GROMACS 2026.1, CUDA 13.1.115, mixed precision, thread-MPI, OpenMP and cuFFT. Each MD uses one rank. Consult the report for hardware-specific SIMD and CUDA architecture targets. Use a CUDA-enabled executable; verify `"$GMX" --version` before starting.

## Input provenance

Download the upstream benchmark archive from [Zenodo DOI 10.5281/zenodo.3893789](https://zenodo.org/records/3893789) and extract `rnase_cubic/topol.tpr`. This is the 24,040-atom RNase cubic system with a 2 fs time step. The expected SHA-256 of `topol.tpr` is:

```text
bd10c90ca230d76ef5fc1555dc24789f1162d18e36037007d9f325d9c760a54a
```

The sharing draft references the upstream input instead of bundling its binary files. Cite the upstream authors and review its applicable terms if redistributing inputs. Replicas in this performance study intentionally use the same input; production ensemble sampling needs independent scientific initial conditions or seeds.

## Full adaptive study

Set the executable and input paths for your installation. Use a fresh result directory with sufficient disk space. Run one study per physical GPU, with the GPU available to the benchmark. The script uses GPU 0 and private MPS pipes, validates MPS clients, and stops only its own MPS controller.

```bash
export GMX=/path/to/cuda-enabled/gmx
export TPR=/path/to/rnase_cubic/topol.tpr
export RESULT_DIR="$PWD/results-rnase-new"
export SCRIPTS="$PWD/scripts"  # public sharing draft

# If the executable needs nonstandard CUDA libraries, set LD_LIBRARY_PATH
# to that installation's runtime library directory before running.
"$GMX" --version
sha256sum "$TPR"

python3 "$SCRIPTS/extended_benchmark.py" \
  --gmx "$GMX" --tpr "$TPR" \
  --root "$RESULT_DIR" --hostname "my-workstation"
```

The main runner performs adaptive screening, three longer repetitions of selected baseline/single-MD/ensemble configurations, and a matched MPS-off control. It does not automatically run the optional CPU-saving follow-up below. Nominal OpenMP workers are bounded by 24 and concurrency by 20. Higher concurrency is added only when the screening curve meets the documented gain thresholds.

Optional task-memory recording can run in a second terminal while the study is active. Supply the actual runner PID. It records only the runner's GROMACS children and its private MPS server, using process GPU allocation and RAM PSS; it does not record whole-system occupancy.

```bash
python3 "$SCRIPTS/record_task_memory.py" \
  --study-pid RUNNER_PID --root "$RESULT_DIR"
```

For synchronized starts on separate workstations, pass the same future Unix timestamp to each runner with `--start-at TIMESTAMP`. The two machines then advance through their own adaptive schedules; individual configurations are not synchronized across hosts.

## Confirming an additional candidate

The study also confirmed the MPS screening candidate within 95% of the screening peak that used the fewest nominal OpenMP workers, breaking ties by fewer processes and then higher screening throughput. The saved `*-lean-selection.json` records that selection. To repeat an explicitly chosen candidate after the main runner finishes, supply case tokens `variant,N,T,mps,phase,repeat`:

```bash
# Example only: 12 MD processes, one worker each, graph path, MPS on.
# Remove COMPLETE.json only after confirming the previous runner has ended,
# if using the memory recorder for these additional cases.
python3 "$SCRIPTS/extended_benchmark.py" \
  --gmx "$GMX" --tpr "$TPR" \
  --root "$RESULT_DIR" --hostname "my-workstation" \
  --cases gpu-graphs,12,1,1,confirm,1 \
          gpu-graphs,12,1,1,confirm,2 \
          gpu-graphs,12,1,1,confirm,3
```

Existing successful cases are reused by case name; incomplete directories are not overwritten. Use a new root to obtain new repetitions of an already completed case. `confirm_lean_candidate.py` is the original follow-up supervisor used in this study; its arguments specify the owned main recorder PID so sampling can be handed over without duplication.

## Standalone production MPS pattern

The following pattern illustrates the scope of an isolated controller on a single-user workstation. On a managed shared machine, use the administrator's supported MPS/job scheduling arrangement. Each `run*` directory must already contain its own validated `md.tpr`; never share an output directory across processes.

```bash
export CUDA_VISIBLE_DEVICES=0
export CUDA_MPS_PIPE_DIRECTORY="$(mktemp -d /tmp/rnase-mps-pipe.XXXXXX)"
export CUDA_MPS_LOG_DIRECTORY="$(mktemp -d /tmp/rnase-mps-log.XXXXXX)"
unset CUDA_MPS_ACTIVE_THREAD_PERCENTAGE
nvidia-cuda-mps-control -d

# Example: CPU-saving configuration on the tested Blackwell workstation.
export GMX_CUDA_GRAPH=1
export OMP_NUM_THREADS=1
N=12
pids=()
for i in $(seq 1 "$N"); do
  (
    cd "run$i" || exit 1
    "$GMX" mdrun -s md.tpr -deffnm md -ntmpi 1 -ntomp 1 -pin off \
      -nb gpu -pme gpu -bonded gpu -update auto >md.stdout 2>&1
  ) &
  pids+=("$!")
done
status=0
for pid in "${pids[@]}"; do wait "$pid" || status=1; done

# The same private pipe environment targets this experiment's controller.
printf 'quit\n' | nvidia-cuda-mps-control
exit "$status"
```

GPU offload and CUDA Graphs require compatible simulation settings. The report's recommended combinations apply to this benchmark; retain scientifically validated production settings and check actual offload in each log.

## Rebuild figures and audit the shared data

The public draft stores extracted measurements and audit summaries in `data/` and scripts in `scripts/`. At the user's request, generated MD inputs, energy/trajectory/checkpoint files and original runtime logs were deleted after extraction and successful audits. No CUDA libraries or credentials are included.

```bash
python3 -m venv .venv
.venv/bin/pip install -r analysis-requirements.txt -r publication-requirements.txt
.venv/bin/python scripts/analyze_extended.py .
.venv/bin/python scripts/finalize_publication.py .

```

The retained `data/local-audit.json` and `data/remote-audit.json` describe successful checks completed before cleanup. To audit a new execution, use `scripts/audit_extended.py --study NEW_RESULTS/study.json --raw NEW_RESULTS --output new-audit.json` against its newly generated logs.

The local CUDA toolkit needed the four declaration-only compatibility edits shown in `cuda-glibc-compatibility.patch`. This file documents the tested build; it is not a general instruction to patch other CUDA versions or distributions.
