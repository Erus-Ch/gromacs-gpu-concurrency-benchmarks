#!/usr/bin/env python3
"""Create English Markdown, CSV summaries and standalone scientific plots."""
import argparse
import csv
import datetime as dt
import json
from pathlib import Path
import statistics as st
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np

p = argparse.ArgumentParser()
p.add_argument('root')
a = p.parse_args()
root = Path(a.root)
data = root/'data' if (root/'data/local-study.json').exists() else root
public_settings = json.loads((root/'publication-settings.json').read_text()) if (root/'publication-settings.json').exists() else {}
studies = [json.loads((data / f'{host}-study.json').read_text()) for host in ('local', 'remote')]
labels = {studies[0]['hostname']: 'RTX PRO 6000 Blackwell', studies[1]['hostname']: 'RTX A4000'}
aggregates = []
all_records = []
for doc,short in zip(studies,('local','remote')):
    memory={}
    memfile=data/f'{short}-task-memory.csv'
    if memfile.exists():
        with memfile.open() as f:
            for sample in csv.DictReader(f):
                if not sample['case']:continue
                m=memory.setdefault(sample['case'],{'gpu':[],'ram':[]})
                if int(sample['gpu_memory_unavailable_processes'])==0:
                    m['gpu'].append(float(sample['task_gpu_mib']))
                if int(sample['ram_unreadable_processes'])==0:
                    m['ram'].append(float(sample['task_ram_pss_mib']))
    all_records.extend(doc['records'])
    grouped = {}
    for r in doc['records']:
        key = (r['phase'], r['variant'], r['concurrency'], r['threads'], r['mps'])
        grouped.setdefault(key, []).append(r)
    for key, records in grouped.items():
        phase, variant, n, t, mps = key
        values = [r['total_ns_day'] for r in records]
        gpu_samples=[x for r in records for x in memory.get(r['case'],{}).get('gpu',[])]
        ram_samples=[x for r in records for x in memory.get(r['case'],{}).get('ram',[])]
        aggregates.append({'hostname': doc['hostname'], 'gpu': labels[doc['hostname']],
            'phase': phase, 'variant': variant, 'concurrency': n, 'threads_per_md': t,
            'openmp_budget': n*t, 'mps': mps, 'repeats': len(records),
            'total_mean_ns_day': st.mean(values), 'total_sd_ns_day': st.stdev(values) if len(values)>1 else 0,
            'total_min_ns_day': min(values), 'total_max_ns_day': max(values),
            'per_md_mean_ns_day': st.mean(values)/n,
            'batch_mean_ns_day': st.mean(r['batch_ns_day'] for r in records),
            'wall_mean_s': st.mean(r['wall_s'] for r in records),
            'throughput_per_openmp_worker': st.mean(values)/(n*t),
            'sampled_task_gpu_peak_mib':max(gpu_samples) if gpu_samples else None,
            'sampled_task_ram_pss_peak_mib':max(ram_samples) if ram_samples else None})
with (root/'configuration_summary.csv').open('w', newline='') as f:
    w=csv.DictWriter(f,fieldnames=list(aggregates[0])); w.writeheader(); w.writerows(aggregates)
(root/'configuration_summary.json').write_text(json.dumps(aggregates,indent=2))

plt.rcParams.update({'font.size':10,'axes.spines.top':False,'axes.spines.right':False})
fig,axes=plt.subplots(1,2,figsize=(11,4.3),layout='constrained')
for ax,doc in zip(axes,studies):
    for variant,color,label in [('auto','#35639f','Auto bonded'),('gpu-graphs','#d26a37','GPU bonded + CUDA Graphs')]:
        rows=sorted([r for r in aggregates if r['hostname']==doc['hostname'] and r['phase']=='screen' and r['concurrency']==1 and r['variant']==variant],key=lambda r:r['threads_per_md'])
        ax.plot([r['threads_per_md'] for r in rows],[r['total_mean_ns_day'] for r in rows],marker='o',color=color,label=label)
    ax.set(title=labels[doc['hostname']],xlabel='OpenMP threads per MD',ylabel='Single-MD throughput (ns/day)',xticks=[1,2,4,8],ylim=(0,None))
    ax.grid(alpha=.2);ax.legend(frameon=False,fontsize=8)
fig.suptitle('RNase cubic · 24,040 atoms · single-task CPU scaling\nScreening measurements; one trajectory, one thread-MPI rank',fontsize=12)
fig.savefig(root/'single_task_cpu_scaling.png',dpi=180);plt.close(fig)

fig,axes=plt.subplots(1,2,figsize=(11,4.3),layout='constrained')
for ax,doc in zip(axes,studies):
    for variant,color,label in [('auto','#35639f','Auto bonded'),('gpu-graphs','#d26a37','GPU bonded + CUDA Graphs')]:
        rows=sorted([r for r in aggregates if r['hostname']==doc['hostname'] and r['phase']=='screen' and r['threads_per_md']==1 and r['variant']==variant],key=lambda r:r['concurrency'])
        ax.plot([r['concurrency'] for r in rows],[r['total_mean_ns_day'] for r in rows],marker='o',color=color,label=label)
    ax.set(title=labels[doc['hostname']],xlabel='Concurrent independent MD jobs',ylabel='Sum of task rates (ns/day)',xticks=[1,2,4,8,12,16,20],ylim=(0,None))
    ax.grid(alpha=.2);ax.legend(frameon=False,fontsize=8)
fig.suptitle('Concurrency scaling · one OpenMP worker per MD\nOne-task points: MPS off; multi-task points: MPS on',fontsize=12)
fig.savefig(root/'concurrency_scaling.png',dpi=180);plt.close(fig)

fig,axes=plt.subplots(2,2,figsize=(13,8),layout='constrained')
ns=[1,2,4,6,8,12,16,20];ts=[1,2,3,4,8]
for row,doc in enumerate(studies):
    hostrows=[r for r in aggregates if r['hostname']==doc['hostname'] and r['phase']=='screen']
    vmax=max(r['total_mean_ns_day'] for r in hostrows)
    for col,variant in enumerate(('auto','gpu-graphs')):
        ax=axes[row,col];matrix=np.full((len(ts),len(ns)),np.nan)
        for r in hostrows:
            if r['variant']==variant:
                matrix[ts.index(r['threads_per_md']),ns.index(r['concurrency'])]=r['total_mean_ns_day']
        im=ax.imshow(np.ma.masked_invalid(matrix),aspect='auto',vmin=0,vmax=vmax,cmap='YlGnBu')
        ax.set(xticks=range(len(ns)),xticklabels=ns,yticks=range(len(ts)),yticklabels=ts,
               xlabel='Concurrent MD jobs',ylabel='OpenMP workers per MD',
               title=labels[doc['hostname']]+' · '+('auto' if variant=='auto' else 'GPU bonded + Graphs'))
        for j in range(len(ts)):
            for i in range(len(ns)):
                if np.isfinite(matrix[j,i]):
                    ax.text(i,j,f'{matrix[j,i]:.0f}',ha='center',va='center',fontsize=8,
                            color='white' if matrix[j,i]>.6*vmax else 'black')
        fig.colorbar(im,ax=ax,label='Sum of task rates (ns/day)',shrink=.8)
fig.suptitle('CPU allocation × concurrency · adaptive screening\nBlank cells were not tested; nominal OpenMP budget ≤24',fontsize=12)
fig.savefig(root/'configuration_heatmaps.png',dpi=180);plt.close(fig)

fig,axes=plt.subplots(1,2,figsize=(12,5),layout='constrained')
for ax,doc in zip(axes,studies):
    rows=sorted([r for r in aggregates if r['hostname']==doc['hostname'] and r['phase']=='confirm'],
                key=lambda r:(r['concurrency']!=1,r['variant'],r['concurrency'],r['threads_per_md']))
    y=np.arange(len(rows))
    ax.barh(y,[r['total_mean_ns_day'] for r in rows],
            xerr=[r['total_sd_ns_day'] for r in rows],
            color=['#d26a37' if r['variant']=='gpu-graphs' else '#35639f' for r in rows],
            alpha=.65,error_kw={'capsize':4,'elinewidth':1})
    for i,r in enumerate(rows):
        points=[x['total_ns_day'] for x in doc['records'] if x['phase']=='confirm' and
                x['variant']==r['variant'] and x['concurrency']==r['concurrency'] and
                x['threads']==r['threads_per_md'] and x['mps']==r['mps']]
        ax.scatter(points,np.full(len(points),i),s=18,color='#24272b',zorder=3)
    ax.set(yticks=y,yticklabels=[f"{r['concurrency']} × {r['threads_per_md']} · "+
           ('GPU+Graphs' if r['variant']=='gpu-graphs' else 'auto')+
           (' · MPS' if r['mps'] else '') for r in rows],
           title=labels[doc['hostname']],xlabel='Aggregate throughput (ns/day)',xlim=(0,None))
    ax.invert_yaxis();ax.grid(axis='x',alpha=.2)
fig.suptitle('Longer confirmation runs · means ± sample SD\nDots show individual batch results; axis scales differ between GPUs',fontsize=12)
fig.savefig(root/'confirmed_throughput.png',dpi=180);plt.close(fig)

def fmt(r):
    if r['repeats']<2:return f"{r['total_mean_ns_day']:.1f} (single run)"
    sd=r['total_sd_ns_day']
    sd_text=f'{sd:.3f}' if 0<sd<.05 else f'{sd:.1f}'
    return f"{r['total_mean_ns_day']:.1f} ± {sd_text}"

def config(r):
    return f"{r['concurrency']} × {r['threads_per_md']}"

def variant_name(r):
    return 'auto bonded' if r['variant']=='auto' else 'GPU bonded + CUDA Graphs'

date_note = 'Absolute test dates and time zones are withheld; durations and relative sampling times are retained.' if public_settings.get('withhold_absolute_test_times') else 'Test date: '+studies[0]['records'][0]['started_utc'][:10]+' (UTC).'
lines=['# '+public_settings.get('title','GROMACS GPU Concurrency and CPU Allocation Benchmark'),
       '', date_note, '',
       '## Executive findings', '',
       'This report compares independent RNase simulations on the two existing workstations. `N × T` means N concurrent MD processes, each using one thread-MPI rank and T OpenMP workers. Both studies started from the same scheduled time and then followed separate adaptive schedules.', '']
winners=[]
lean_recommendations=[]
for doc,short in zip(studies,('local','remote')):
    host=doc['hostname'];rs=[r for r in aggregates if r['hostname']==host and r['phase']=='confirm']
    base=next(r for r in rs if r['concurrency']==1 and r['threads_per_md']==1 and r['variant']=='auto')
    single=max([r for r in rs if r['concurrency']==1],key=lambda r:r['total_mean_ns_day'])
    winner=max([r for r in rs if r['mps']],key=lambda r:r['total_mean_ns_day'])
    winners.append(winner)
    lines += [f"- **{labels[host]}:** best confirmed ensemble = **{config(winner)}, MPS on, {variant_name(winner)}**, **{fmt(winner)} ns/day** (mean ± sample SD, n={winner['repeats']}). This is **{winner['total_mean_ns_day']/single['total_mean_ns_day']:.2f}×** the fastest confirmed single-MD configuration, or **{winner['total_mean_ns_day']/base['total_mean_ns_day']:.2f}×** the one-worker auto-bonded baseline. Full-batch throughput was **{winner['batch_mean_ns_day']:.1f} ns/day**."]
    leanfile=data/f'{short}-lean-selection.json'
    if leanfile.exists():
        choice=json.loads(leanfile.read_text())['selected']
        lean=next(r for r in rs if r['mps'] and r['variant']==choice['variant'] and
                  r['concurrency']==choice['concurrency'] and r['threads_per_md']==choice['threads'])
        lean_recommendations.append(lean)
        lines.append(f"  CPU-saving candidate: **{config(lean)}, {variant_name(lean)}**, {fmt(lean)} ns/day using **{lean['openmp_budget']} nominal OpenMP workers**, retaining **{100*lean['total_mean_ns_day']/winner['total_mean_ns_day']:.1f}%** of the confirmed peak. This candidate was selected within 95% of the screening peak and then independently confirmed.")
lines += ['', 'The A4000 paths are effectively tied at approximately 929 ns/day with 4 × 2; the tiny difference does not establish that GPU bonded + Graphs is faster. Auto bonded is also a sensible choice. Its 4 × 1 screen reached approximately 933 ns/day with only four nominal workers, but that CPU-saving option did not receive longer confirmation before the requested early stop.', '',
 'These are the best confirmed configurations within the tested search, not an exhaustive global optimum. The full-batch metric includes launch, warm-up and completion-tail effects; the sum of task rates excludes the specified warm-up in each process.', '',
 '## What MPS does', '',
 'NVIDIA CUDA Multi-Process Service (MPS) is a lightweight service that coordinates GPU access from multiple CUDA processes. A control daemon manages a server, and clients share the server’s GPU scheduling resources. Kernels from different processes can overlap and GPU context-switching overhead can fall. Each MD trajectory remains an independent process with its own files and CUDA address space. Benefits are strongest when one process alone leaves usable GPU capacity. [NVIDIA MPS overview](https://docs.nvidia.com/deploy/mps/latest/index.html), [When to use MPS](https://docs.nvidia.com/deploy/mps/latest/when-to-use-mps.html).', '',
 '```mermaid','flowchart LR','  MD1[MD process 1] --> MPS[MPS server]','  MD2[MD process 2] --> MPS','  MDN[MD process N] --> MPS','  MPS --> GPU[One physical NVIDIA GPU]','```','',
 '| Mechanism | Role in this study |','|---|---|',
 '| thread-MPI | One rank per independent MD |','| OpenMP | CPU workers inside each MD |','| CUDA MPS | GPU sharing across independent MD processes |','| CUDA Graphs | Replays a process’s GPU execution graph to reduce repeated launch overhead |','',
 '## Hardware and controlled setup','',
 '| Workstation | CPU topology | GPU |','|---|---|',
 '| `Blackwell-workstation` | Core Ultra 9 285K: 24 cores / 24 logical CPUs; 8 P-cores + 16 E-cores | RTX PRO 6000 Blackwell, approximately 96 GiB |',
 '| `A4000-workstation` | Xeon w5-2455X: 12 physical cores / 24 logical CPUs | RTX A4000, approximately 16 GiB |','',
 '| Platform detail | Blackwell workstation | A4000 workstation |','|---|---|---|',
 '| Operating system | Ubuntu 26.04.1 LTS | Ubuntu 24.04.4 LTS |',
 '| Linux kernel | 7.0.0-43-generic | 7.0.0-43-generic |',
 '| NVIDIA driver | 595.99.02 | 595.99.02 |',
 '| GCC host compiler | 13.4.0 | 13.3.0 |','',
 'The local CPU is heterogeneous; the remote CPU exposes SMT siblings. The same nominal worker budget therefore does not imply the same number or type of physical cores. Core placement was left to the OS (`-pin off`). [Intel 285K specifications](https://www.intel.com/content/www/us/en/products/sku/241060/intel-core-ultra-9-processor-285k-36m-cache-up-to-5-70-ghz/specifications.html), [Intel w5-2455X specifications](https://www.intel.com/content/www/us/en/products/sku/233420/intel-xeon-w52455x-processor-30m-cache-3-20-ghz/specifications.html).','',
 '- Input: RNase cubic, RNASE ZF-1A in water, **24,040 atoms**, from the [published benchmark dataset](https://zenodo.org/records/3893789).',
 '- Identical input SHA-256: `'+studies[0]['tpr_sha256']+'`.',
 '- GROMACS **2026.1**, CUDA toolkit **13.1.115**, FFTW **3.3.10**, mixed precision, cuFFT, thread-MPI and OpenMP.',
 '- Hardware-specific builds: AVX2 / sm_120 locally; AVX-512 / sm_86 remotely. Absolute cross-host differences are not a GPU-only hardware comparison.',
 '- The local CUDA 13.1 toolchain needed four declaration-only `noexcept` additions for compatibility with glibc 2.42. Arithmetic implementations were unchanged; see `cuda-glibc-compatibility.patch`. The remote build used the unmodified CUDA 13.1 headers.',
 '- One rank per MD; fixed 2 fs timestep; PME on GPU; PME tuning disabled; coordinate/constraint update on GPU when supported; final coordinate output suppressed.',
 '- Standard path: `-bonded auto`. Graph path: `-bonded gpu` and `GMX_CUDA_GRAPH=1`; actual graph execution was verified from MD Graph counters. This is a bundled path comparison, so its gain cannot be attributed to CUDA Graphs alone.',
 '- Nominal OpenMP budget N×T ≤24; search safety limit 20 processes. MPS/driver helper threads are additional to this nominal worker count.',
 '- Private MPS pipes, default MPS scheduling, no active-thread percentage partition. Only the experiment-owned controller is stopped.',
 '- Screening: 80,000 steps, first 20,000 excluded. Confirmation: 200,000 steps, first 40,000 excluded. The initial plan was three repetitions per selected configuration; actual completed repetition counts are reported in the tables.',
 '- Concurrency expanded through 2, 4, 8 and 12; 16 was added when 12 improved over lower counts by more than 3%; 20 was added if 16 improved by more than 5%. CPU-worker combinations were then explored around each path’s throughput peak.',
 '- Input copies are benchmark replicas and do not establish independent scientific samples. Earlier experiments are not pooled into these statistics.', '',
 'The CPU/GPU work balance and launch overhead depend on the system and offload settings; moving all work to the GPU is not universally best. [GROMACS performance guide](https://manual.gromacs.org/documentation/2026.1/user-guide/mdrun-performance.html).','',
 '## Metrics','',
 '`Aggregate rate = sum(P_i)`, where P_i is each process’s post-warm-up GROMACS Performance value in ns/day.','',
 '`Full-batch rate = N × simulated_ns_per_MD × 86400 / batch_wall_seconds`. This includes startup and warm-up. It is useful for fixed-length batches and can be lower when task speeds are imbalanced.','',
 'Confirmation variability is the sample standard deviation across batches, not a confidence interval. Screening points are single runs and are used for candidate selection. Three repeats do not establish a statistically significant ordering between close configurations. No background-load telemetry was saved.','',
 'Each process resets its own counters and reports over its own completion interval. These intervals are not a single globally synchronized steady-state window; faster jobs finishing can reduce contention for the remaining jobs. The full-batch metric complements the summed rates and should be considered when planning finite batches.','',
 '### Task-attributed memory', '',
 'Memory is sampled approximately every five seconds for the study-owned GROMACS processes and the private MPS server only. GPU allocation is summed from their NVML process-memory records; RAM is the sum of their proportional set sizes (PSS), which apportions shared pages instead of counting them once per process. Desktop applications and unrelated system occupancy are excluded. GPU figures include the CUDA context and MPS overhead attributable to these jobs. The small MPS control daemon and Python benchmark harness are outside this memory scope.', '',
 'Memory sampling was requested after screening had started. Missing earlier measurements remain unreported; available confirmation samples are included below. Reported peaks are sampled maxima, not a guarantee of the instantaneous absolute peak. Units are MiB (1024 MiB = 1 GiB).', '',
 '## Single-trajectory CPU scaling','', '![Single-task CPU scaling](single_task_cpu_scaling.png)','',
 '## Concurrency with one CPU worker per MD','', '![Concurrency scaling](concurrency_scaling.png)','',
 '## CPU allocation and concurrency together','', '![Configuration heatmaps](configuration_heatmaps.png)','',
 'Blank heatmap cells were not tested. Colors have a common scale across the two paths within each GPU; scales differ between GPUs.','',
 '## Longer confirmation runs','', '![Confirmed throughput](confirmed_throughput.png)','',
 'Dots show completed batches. A setting with only one dot has no estimated standard deviation. Repetition counts are given in the table.', '',
 '| GPU | Path | N × T | MPS | Repeats | Aggregate ns/day, mean ± SD | Per-MD ns/day | Full-batch ns/day | Task GPU peak MiB | Task RAM PSS peak MiB |','|---|---|---:|---|---:|---:|---:|---:|---:|---:|']
for r in sorted([x for x in aggregates if x['phase']=='confirm'],key=lambda x:(x['hostname'],x['variant'],x['concurrency'],x['threads_per_md'])):
    gm='n/a' if r['sampled_task_gpu_peak_mib'] is None else f"{r['sampled_task_gpu_peak_mib']:.0f}"
    rm='n/a' if r['sampled_task_ram_pss_peak_mib'] is None else f"{r['sampled_task_ram_pss_peak_mib']:.1f}"
    lines.append(f"| {r['gpu']} | {variant_name(r)} | {config(r)} | {'on' if r['mps'] else 'off'} | {r['repeats']} | {fmt(r)} | {r['per_md_mean_ns_day']:.1f} | {r['batch_mean_ns_day']:.1f} | {gm} | {rm} |")
lines += ['', '## Matched MPS control','',
 'The control uses the same configuration and 80,000-step / 20,000-step screening protocol as its matching MPS-on screening run. These are single-run controls. A workstation without a completed control is omitted.', '',
 '| GPU | Configuration | MPS on, ns/day | MPS off, ns/day | Ratio |','|---|---|---:|---:|---:|']
for off in [r for r in aggregates if r['phase']=='mps-control']:
    on=next(r for r in aggregates if r['hostname']==off['hostname'] and r['phase']=='screen' and r['variant']==off['variant'] and r['concurrency']==off['concurrency'] and r['threads_per_md']==off['threads_per_md'] and r['mps'])
    lines.append(f"| {off['gpu']} | {config(off)}, {variant_name(off)} | {on['total_mean_ns_day']:.1f} | {off['total_mean_ns_day']:.1f} | {on['total_mean_ns_day']/off['total_mean_ns_day']:.2f}× |")
lines += ['', '## Recommended commands','', 'Use the tested executable rather than assuming the default `gmx` command has CUDA support.', '',
 '| Workstation | Tested executable |','|---|---|']
for d in studies: lines.append(f"| `{d['hostname']}` | `{d['gmx']}` |")
lines += ['', 'Start a private MPS controller once, then launch each trajectory in a separate directory. Retain the same MPS pipe environment for the controller and its clients. For each selected configuration, use the following core options:', '']
for r in winners:
    lines += [f"**{r['gpu']}: {config(r)}**", '', '```bash',
              ('export GMX_CUDA_GRAPH=1' if r['variant']=='gpu-graphs' else 'unset GMX_CUDA_GRAPH'),
              f"# Run {r['concurrency']} independent jobs, one output directory per job.",
              f"\"$GMX\" mdrun -s md.tpr -deffnm md -ntmpi 1 -ntomp {r['threads_per_md']} -pin off \\",
              f"  -nb gpu -pme gpu -bonded {'gpu' if r['variant']=='gpu-graphs' else 'auto'} -update auto", '```', '']
lines += ['`$GMX` should be set to the executable in the table. The benchmark’s `-notunepme`, output suppression and counter resets were measurement controls; production choices should follow the actual system’s validated simulation settings. See `REPRODUCE.md` for an isolated MPS launch and full runner invocation.', '',
 '## Bottleneck assessment','',
 'The useful distinction is between CPU preparation/launch work, sharing between GPU processes, and the remaining device execution path. The following evidence comes from configuration changes, rather than from a GPU-utilization percentage:', '',
 '| GPU | Observation | Supported interpretation |','|---|---|---|']
for doc in studies:
    hs=[r for r in aggregates if r['hostname']==doc['hostname'] and r['phase']=='screen']
    one=next(r for r in hs if r['variant']=='auto' and r['concurrency']==1 and r['threads_per_md']==1)
    single=max([r for r in hs if r['variant']=='auto' and r['concurrency']==1],key=lambda r:r['total_mean_ns_day'])
    graph=next(r for r in hs if r['variant']=='gpu-graphs' and r['concurrency']==1 and r['threads_per_md']==1)
    lines.append(f"| {labels[doc['hostname']]} | Auto-bonded single MD: {one['total_mean_ns_day']:.0f} ns/day at one worker; best screened CPU allocation {single['threads_per_md']} workers: {single['total_mean_ns_day']:.0f} ns/day. GPU-bonded + Graphs at one worker: {graph['total_mean_ns_day']:.0f} ns/day. | CPU allocation and the offload/launch path can affect latency. The graph path changes two options together, so this extension does not isolate their individual contributions. |")
    ones=sorted([r for r in hs if r['variant']=='auto' and r['threads_per_md']==1 and r['mps']],key=lambda r:r['concurrency'])
    rates='; '.join(f"{r['concurrency']} jobs: {r['total_mean_ns_day']:.0f}" for r in ones)
    lines.append(f"| {labels[doc['hostname']]} | MPS, auto bonded, one worker per MD: {rates} ns/day. | The curve identifies where adding independent jobs stops providing much throughput. A plateau is consistent with saturation of the shared execution path; it does not identify a specific GPU hardware unit. |")
for off in [r for r in aggregates if r['phase']=='mps-control']:
    on=next(r for r in aggregates if r['hostname']==off['hostname'] and r['phase']=='screen' and r['variant']==off['variant'] and r['concurrency']==off['concurrency'] and r['threads_per_md']==off['threads_per_md'] and r['mps'])
    lines.append(f"| {off['gpu']} | Matched {config(off)} control: MPS on/off ratio {on['total_mean_ns_day']/off['total_mean_ns_day']:.2f}×. | A large ratio supports GPU process-sharing/scheduling overhead as a material limit without MPS. A near-unity ratio indicates little benefit for this configuration. This control has one run per setting. |")
if any((data/f'{short}-wallcycles.csv').exists() for short in ('local','remote')):
    lines += ['', '### Internal GROMACS timing evidence', '',
        'The following are arithmetic means of the reported per-process timing percentages across the indicated confirmation batches. They describe GROMACS host-side cycle accounting, not GPU hardware utilization or PCIe bandwidth. The overlapping PME breakdown is excluded.', '',
        '| GPU | Configuration | Force % | Neighbor search % | Wait GPU state copy % | MD Graph % |',
        '|---|---|---:|---:|---:|---:|']
    for doc,short in zip(studies,('local','remote')):
        path=data/f'{short}-wallcycles.csv'
        if not path.exists():continue
        with path.open() as f:timing=list(csv.DictReader(f))
        confirms=[r for r in aggregates if r['hostname']==doc['hostname'] and r['phase']=='confirm']
        picks=[next(r for r in confirms if r['variant']=='auto' and r['concurrency']==1 and r['threads_per_md']==1),
               max([r for r in confirms if r['concurrency']==1],key=lambda r:r['total_mean_ns_day']),
               next(r for r in winners if r['hostname']==doc['hostname'])]
        seen=set()
        for r in picks:
            key=(r['variant'],r['concurrency'],r['threads_per_md'],r['mps'])
            if key in seen:continue
            seen.add(key)
            rows=[x for x in timing if x['phase']=='confirm' and x['variant']==key[0] and
                  int(x['concurrency'])==key[1] and int(x['threads'])==key[2] and (x['mps']=='True')==key[3]]
            values=[]
            for activity in ('Force','Neighbor search','Wait GPU state copy','MD Graph'):
                v=[float(x['reported_percent']) for x in rows if x['activity']==activity]
                values.append(f'{st.mean(v):.1f}' if v else 'n/a')
            lines.append(f"| {r['gpu']} | {config(r)}, {variant_name(r)} | "+' | '.join(values)+' |')
lines += ['', 'Task-attributed VRAM and RAM peaks describe allocation, not bandwidth. They cannot by themselves diagnose PCIe transfer or device-memory bandwidth. Likewise, a GROMACS GPU-wait timer can include waiting for preceding device work and synchronization; its label alone does not establish a data-transfer bottleneck.', '',
 'Distinguishing GPU arithmetic from device-memory traffic, PCIe transfer and synchronization would require a representative kernel/API timeline and hardware counters (for example, a separate Nsight Systems/Compute experiment). This extension establishes useful settings and sharing effects, but does not claim that level of hardware attribution.', '',
 '## Interpretation and limits','',
 '- More OpenMP workers can help CPU-side work, but extra synchronization and hybrid-core/SMT placement can limit gains. Use measured throughput rather than assuming speed increases linearly with worker count.',
 '- Select for total ensemble throughput when many trajectories are needed; use the fastest single-MD setting when trajectory completion latency is the priority.',
 '- This adaptive search does not cover every N×T combination, affinity policy, MPS SM partition, neighbor-list setting or GPU kernel implementation. Small screening differences require confirmation.',
 '- No kernel-level hardware profile was collected in this extension. Throughput curves alone do not separate GPU arithmetic limits from device-memory bandwidth or synchronization latency.',
 '- The result applies to this 24,040-atom RNase benchmark. Different force fields, constraints, pressure coupling and output frequencies can change the best settings.', '',
 '## Complete screening table','',
 '| GPU | Path | N × T | Worker budget | MPS | Aggregate ns/day | Full-batch ns/day |','|---|---|---:|---:|---|---:|---:|']
for r in sorted([x for x in aggregates if x['phase']=='screen'],key=lambda x:(x['hostname'],x['variant'],x['concurrency'],x['threads_per_md'])):
    lines.append(f"| {r['gpu']} | {variant_name(r)} | {config(r)} | {r['openmp_budget']} | {'on' if r['mps'] else 'off'} | {r['total_mean_ns_day']:.1f} | {r['batch_mean_ns_day']:.1f} |")
lines += ['', '## Validation','']
for doc,short in zip(studies,('local','remote')):
    if doc.get('stopping_reason'):
        lines.append(f"- **{labels[doc['hostname']]} stopping rule:** {doc['stopping_reason']} All scheduled screening was already complete. Redundant remaining confirmations, the MPS-off control and the extra CPU-saving follow-up were cancelled. Completed batches were retained; the active batch finished normally before shutdown. Single-run confirmations have no estimated standard deviation.")
    auditfile=data/f'{short}-audit.json'
    if auditfile.exists():
        audit=json.loads(auditfile.read_text())
        lines.append(f"- {labels[doc['hostname']]}: **{audit['cases']} completed batches, {audit['successful_md_runs']} successful MD processes**; independent raw-log audit {'passed' if audit['all_passed'] else 'FAILED'}.")
    else:
        lines.append(f"- {labels[doc['hostname']]}: {len(doc['records'])} completed batches, {sum(r['concurrency'] for r in doc['records'])} successful MD processes recorded by the runner.")
    if public_settings.get('withhold_absolute_test_times'):
        first=min(r['started_elapsed_s'] for r in doc['records'])
        last=max(r['finished_elapsed_s'] for r in doc['records'])
        lines.append(f"  Observed concurrency reached {max(r['concurrency'] for r in doc['records'])}; measurement window {first:.3f}–{last:.3f} seconds relative to this workstation’s first batch. Absolute dates and time zones are withheld.")
    else:
        lines.append(f"  Observed concurrency reached {max(r['concurrency'] for r in doc['records'])}; first batch started {min(r['started_utc'] for r in doc['records'])}, final batch finished {max(r['finished_utc'] for r in doc['records'])} (UTC).")
lines += ['', 'The audit checks normal completion, zero exit status, positive finite rates matching raw logs, requested OpenMP count, timing reset, graph execution where requested, MPS client count, worker budget and absence of NaN/fatal/LINCS warnings. These checks validate benchmark execution; they do not establish physical equilibration or production scientific convergence.', '',
 '## Reproducibility files','',
 '- `configuration_summary.csv` / `.json`: all grouped measurements.',
 '- `local-study.json` and `remote-study.json`: per-task rates, command lines, timing and MPS client validation.',
 '- `extended_benchmark.py`: bounded adaptive runner, including screening, confirmations and matched controls.',
 '- `local-task-memory.csv` / `remote-task-memory.csv`: task-attributed GPU and PSS memory samples.',
 '- Per-task rates, timings and command lines: retained in the study JSON. Extracted internal timing rows: `local-wallcycles.csv` / `remote-wallcycles.csv`.',
 '- Original MD input copies, energy/trajectory/checkpoint files and runtime logs were deleted at the user’s request after extraction and successful raw-log audits. The audit records are retained; the original logs are no longer distributed.',
 '- `analyze_extended.py`: this report and figure generator.',
 '- `audit_extended.py` and per-host audit JSON: independent raw-log validation.',
 '- `REPRODUCE.md`: environment, input and invocation guide.', '']
lines += ['## Sharing and citation', '',
 'A GitHub repository is suitable for versioned scripts, CSV data, figures and reproduction instructions. A tagged release can be archived in Zenodo to obtain a DOI; subsequent archived releases receive versioned records. This combines a practical collaboration surface with a stable research citation. [GitHub citation guide](https://docs.github.com/en/repositories/archiving-a-github-repository/referencing-and-citing-content), [Zenodo GitHub integration](https://help.zenodo.org/docs/github/).', '',
 'For feedback from practitioners, share the repository link through the [GROMACS community forum](https://gromacs.bioexcel.eu/). Include the precise hardware models, software/build settings, input DOI and hash, reset/measurement lengths, individual task rates, batch timings, repetition counts and dispersion. Distinguish screening observations from confirmed measurements.', '',
 'Use the anonymized public copy when sharing. Keep workstation hostnames, private network addresses, usernames and credential paths out of a public upload. Reference the upstream input dataset and its terms rather than automatically redistributing its binary inputs. Add an appropriate license for original scripts and results when preparing the repository release.', '']
report_name='REPORT.md' if public_settings else 'GROMACS_Extended_Dual_GPU_Benchmark_Report.md'
(root/report_name).write_text('\n'.join(lines))
(root/'recommendations.json').write_text(json.dumps({'throughput':winners,'cpu_saving':lean_recommendations},indent=2))
print(json.dumps(winners,indent=2))
