#!/usr/bin/env python3
"""Adaptive local-GPU throughput study; no background-load telemetry is saved."""
import argparse
import csv
import datetime as dt
import hashlib
import json
import math
import os
from pathlib import Path
import random
import re
import shutil
import statistics as st
import subprocess as sp
import sys
import time

p = argparse.ArgumentParser()
p.add_argument('--gmx', required=True)
p.add_argument('--tpr', required=True)
p.add_argument('--root', required=True)
p.add_argument('--hostname', required=True)
p.add_argument('--start-at', type=float, default=0)
p.add_argument('--cases', nargs='*', help='Optional additions: variant,N,T,mps,phase,repeat')
a = p.parse_args()
root, gmx, tpr = Path(a.root).resolve(), Path(a.gmx).resolve(), Path(a.tpr).resolve()
root.mkdir(parents=True, exist_ok=True)
records = []
owned = []
env = os.environ.copy()
for k in ('CUDA_MPS_PIPE_DIRECTORY', 'CUDA_MPS_LOG_DIRECTORY',
          'CUDA_MPS_ACTIVE_THREAD_PERCENTAGE', 'GMX_CUDA_GRAPH'):
    env.pop(k, None)
env.update(CUDA_VISIBLE_DEVICES='0', OMP_DYNAMIC='FALSE', GMX_MAXBACKUP='-1')
pipe = Path('/tmp') / f'codex-ext-mps-{os.getuid()}-{root.name}'
logs = Path(str(pipe) + '-logs')
mps_env = env | {'CUDA_MPS_PIPE_DIRECTORY': str(pipe), 'CUDA_MPS_LOG_DIRECTORY': str(logs)}
control = shutil.which('nvidia-cuda-mps-control')

def checkpoint():
    doc = {'hostname': a.hostname, 'gmx': str(gmx), 'tpr_sha256': hashlib.sha256(tpr.read_bytes()).hexdigest(),
           'atoms': 24040, 'dt_ps': .002, 'cpu_budget_limit': 24,
           'screen_steps': 80000, 'screen_warmup': 20000,
           'confirmation_steps': 200000, 'confirmation_warmup': 40000,
           'records': records}
    tmp = root / 'study.json.tmp'
    tmp.write_text(json.dumps(doc, indent=2))
    tmp.replace(root / 'study.json')
    if records:
        keys = ['phase', 'variant', 'concurrency', 'threads', 'cpu_budget', 'mps', 'replicate',
                'steps', 'warmup', 'total_ns_day', 'per_task_mean_ns_day',
                'per_task_min_ns_day', 'per_task_max_ns_day', 'batch_ns_day', 'wall_s']
        with (root / 'results.csv').open('w', newline='') as f:
            w = csv.DictWriter(f, fieldnames=keys)
            w.writeheader()
            for r in records:
                w.writerow({k: r[k] for k in keys})

def mps_start():
    pipe.mkdir(mode=0o700, exist_ok=True)
    logs.mkdir(mode=0o700, exist_ok=True)
    r = sp.run([control, '-d'], env=mps_env, capture_output=True, text=True, timeout=20)
    if r.returncode:
        raise RuntimeError('MPS start: ' + r.stdout + r.stderr)
    time.sleep(1)

def mps_stop():
    r = sp.run([control], input='quit\n', env=mps_env, capture_output=True, text=True, timeout=20)
    if r.returncode:
        raise RuntimeError('MPS stop: ' + r.stdout + r.stderr)
    time.sleep(.3)
    shutil.rmtree(pipe, ignore_errors=True)
    shutil.rmtree(logs, ignore_errors=True)

def case(variant, n, threads, mps, phase='screen', repeat=1):
    if n < 1 or n > 20 or threads not in (1, 2, 3, 4, 8) or n * threads > 24:
        raise ValueError('Outside the approved bounded study: ' + str((n, threads)))
    steps, warmup = (80000, 20000) if phase in ('screen', 'mps-control') else (200000, 40000)
    name = f'{phase}-{variant}-{n}x{threads}-mps{int(mps)}-r{repeat}'
    d = root / name
    if (d / 'result.json').exists():
        r = json.loads((d / 'result.json').read_text())
        if not any(x['case'] == name for x in records):
            records.append(r)
        return r
    d.mkdir(exist_ok=False)
    active_mps = False
    procs = []
    print('START ' + name + ' ' + dt.datetime.now(dt.timezone.utc).isoformat(), flush=True)
    try:
        if mps:
            mps_start()
            active_mps = True
        taskenv = (mps_env if mps else env).copy()
        taskenv['OMP_NUM_THREADS'] = str(threads)
        if variant == 'gpu-graphs':
            taskenv['GMX_CUDA_GRAPH'] = '1'
        start_utc = dt.datetime.now(dt.timezone.utc).isoformat()
        started = time.monotonic()
        for i in range(n):
            rd = d / f'run{i+1:02d}'
            rd.mkdir()
            try:
                os.link(tpr, rd / 'md.tpr')
            except OSError:
                shutil.copy2(tpr, rd / 'md.tpr')
            cmd = [str(gmx), 'mdrun', '-s', 'md.tpr', '-deffnm', 'md', '-ntmpi', '1',
                   '-ntomp', str(threads), '-pin', 'off', '-nb', 'gpu', '-pme', 'gpu',
                   '-bonded', 'gpu' if variant == 'gpu-graphs' else 'auto', '-update', 'auto',
                   '-notunepme', '-noconfout', '-nsteps', str(steps), '-resetstep', str(warmup)]
            out = (rd / 'md.stdout').open('w')
            child = sp.Popen(cmd, cwd=rd, env=taskenv, stdin=sp.DEVNULL,
                             stdout=out, stderr=sp.STDOUT)
            procs.append((child, out, rd, cmd))
            owned.append(child)
        max_clients = 0
        next_query = started + 2
        ends = {}
        while len(ends) < len(procs):
            now = time.monotonic()
            for child, _, _, _ in procs:
                if child.pid not in ends and child.poll() is not None:
                    ends[child.pid] = now
            if mps and max_clients < n and now >= next_query:
                q = sp.run([control], input='ps\n', env=mps_env, text=True,
                           capture_output=True, timeout=10)
                max_clients = max(max_clients, sum(bool(re.match(r'\s*\d+\s+', s))
                                  for s in q.stdout.splitlines()))
                next_query = now + 2
            if now - started > 900:
                raise RuntimeError('Case exceeded 900-second wall-time bound')
            time.sleep(.2)
        wall = max(ends.values()) - started
        tasks = []
        for child, out, rd, cmd in procs:
            code = child.wait()
            out.close()
            log = (rd / 'md.log').read_text(errors='replace')
            stdout = (rd / 'md.stdout').read_text(errors='replace')
            perf = re.findall(r'^Performance:\s+([0-9.]+)', log, re.M)
            warnings = [s for s in log.splitlines() if re.search(r'WARNING|Fatal error|LINCS WARNING', s)]
            graphs = bool(re.search(r'^\s*MD Graph\s+\d', log, re.M))
            valid = (code == 0 and perf and 'Finished mdrun' in log and
                     'resetting all time and cycle counters' in stdout.lower() and
                     not re.search(r'\bnan\b', log, re.I) and not warnings)
            if not valid or (variant == 'gpu-graphs' and not graphs):
                raise RuntimeError('Invalid task or requested graphs not used: ' + str(rd) + '\n' + stdout[-2500:])
            tasks.append({'run': rd.name, 'ns_day': float(perf[-1]), 'exit': code,
                          'graphs_used': graphs, 'elapsed_s': ends[child.pid] - started, 'command': cmd})
        if mps and max_clients < n:
            raise RuntimeError(f'MPS client count {max_clients} < task count {n}')
        rates = [t['ns_day'] for t in tasks]
        r = {'case': name, 'hostname': a.hostname, 'phase': phase, 'variant': variant,
             'concurrency': n, 'threads': threads, 'cpu_budget': n * threads,
             'mps': mps, 'replicate': repeat, 'steps': steps, 'warmup': warmup,
             'started_utc': start_utc, 'finished_utc': dt.datetime.now(dt.timezone.utc).isoformat(),
             'wall_s': round(wall, 4), 'total_ns_day': sum(rates),
             'per_task_mean_ns_day': st.mean(rates), 'per_task_min_ns_day': min(rates),
             'per_task_max_ns_day': max(rates), 'batch_ns_day': n * steps * .002 / 1000 * 86400 / wall,
             'mps_clients_verified': max_clients, 'tasks': tasks}
        (d / 'result.json').write_text(json.dumps(r, indent=2))
        records.append(r)
        checkpoint()
        print(json.dumps({k: r[k] for k in ('case', 'total_ns_day', 'batch_ns_day', 'wall_s')}) , flush=True)
        return r
    finally:
        # Only children created by this study can be terminated here.
        for child, out, _, _ in procs:
            if child.poll() is None:
                child.terminate()
                try:
                    child.wait(timeout=15)
                except sp.TimeoutExpired:
                    child.kill()
                    child.wait()
            out.close()
        if active_mps:
            mps_stop()

try:
    if (root / 'study.json').exists():
        records.extend(json.loads((root / 'study.json').read_text())['records'])
    if a.cases:
        for token in a.cases:
            variant, n, threads, mps, phase, repeat = token.split(',')
            case(variant, int(n), int(threads), bool(int(mps)), phase, int(repeat))
        (root / 'COMPLETE.json').write_text(json.dumps({'finished_utc':dt.datetime.now(dt.timezone.utc).isoformat(),
            'case_count':len(records), 'md_count':sum(r['concurrency'] for r in records)}, indent=2))
        print('ADDITIONAL_CASES_COMPLETE', flush=True)
        sys.exit(0)
    while time.time() < a.start_at:
        time.sleep(min(1, a.start_at - time.time()))
    for variant in ('auto', 'gpu-graphs'):
        for threads in (1, 2, 4, 8):
            case(variant, 1, threads, False)
    for variant in ('auto', 'gpu-graphs'):
        scaling = []
        for n in (2, 4, 8, 12):
            scaling.append(case(variant, n, 1, True))
        if scaling[-1]['total_ns_day'] > max(r['total_ns_day'] for r in scaling[:-1]) * 1.03:
            scaling.append(case(variant, 16, 1, True))
            if scaling[-1]['total_ns_day'] > max(r['total_ns_day'] for r in scaling[:-1]) * 1.05:
                scaling.append(case(variant, 20, 1, True))
        best_n = max(scaling, key=lambda r: r['total_ns_day'])['concurrency']
        low_n = max(2, min(8, best_n // 2))
        low_n = min((2, 4, 6, 8), key=lambda x: abs(x - low_n))
        cpu_grid = {(low_n, 2), (best_n, 2), (low_n, 3), (min(best_n, 8), 3),
                    (low_n, 4), (min(best_n, 6), 4), (4, 4)}
        if best_n >= 8:
            cpu_grid.add((12, 2))
        for n, threads in sorted(cpu_grid):
            if n * threads <= 24:
                case(variant, n, threads, True)
    screens = [r for r in records if r['phase'] == 'screen']
    selected = {('auto', 1, 1, False)}
    singles = [r for r in screens if r['concurrency'] == 1]
    best_single = max(singles, key=lambda r: r['total_ns_day'])
    selected.add((best_single['variant'], 1, best_single['threads'], False))
    for variant in ('auto', 'gpu-graphs'):
        best = max([r for r in screens if r['variant'] == variant and r['mps']], key=lambda r: r['total_ns_day'])
        selected.add((variant, best['concurrency'], best['threads'], True))
    # Interleave independent longer runs to avoid confirming each setting in one block.
    for repeat in (1, 2, 3):
        order = sorted(selected)
        random.Random(0x1352903 + repeat).shuffle(order)
        for variant, n, threads, mps in order:
            case(variant, n, threads, mps, 'confirm', repeat)
    # A matched no-MPS control for the winning concurrent configuration.
    confirms = [r for r in records if r['phase'] == 'confirm' and r['mps']]
    groups = {}
    for r in confirms:
        groups.setdefault((r['variant'], r['concurrency'], r['threads']), []).append(r['total_ns_day'])
    winner = max(groups, key=lambda k: st.mean(groups[k]))
    case(*winner, False, 'mps-control', 1)
    (root / 'COMPLETE.json').write_text(json.dumps({'finished_utc':dt.datetime.now(dt.timezone.utc).isoformat(),
        'case_count':len(records), 'md_count':sum(r['concurrency'] for r in records)}, indent=2))
    print('STUDY_COMPLETE', flush=True)
except Exception as exc:
    checkpoint()
    (root / 'ERROR.txt').write_text(str(exc))
    raise
