#!/usr/bin/env python3
"""After the primary study, confirm a near-peak configuration using fewer CPUs."""
import argparse
import json
import os
from pathlib import Path
import signal
import subprocess as sp
import time

p=argparse.ArgumentParser()
p.add_argument('--root',required=True)
p.add_argument('--runner',required=True)
p.add_argument('--recorder',required=True)
p.add_argument('--old-recorder-pid',type=int,required=True)
a=p.parse_args();root=Path(a.root)
try:
    while not (root/'COMPLETE.json').exists():
        if (root/'ERROR.txt').exists():raise RuntimeError((root/'ERROR.txt').read_text())
        time.sleep(5)
    # Let the previous sampler observe COMPLETE before a new append-mode sampler.
    time.sleep(6)
    old=Path(f'/proc/{a.old_recorder_pid}/cmdline')
    if old.exists() and b'record_task_memory.py' in old.read_bytes():
        os.kill(a.old_recorder_pid,signal.SIGTERM)
    study=json.loads((root/'study.json').read_text())
    screens=[r for r in study['records'] if r['phase']=='screen' and r['mps']]
    peak=max(r['total_ns_day'] for r in screens)
    near=[r for r in screens if r['total_ns_day']>=peak*.95]
    lean=min(near,key=lambda r:(r['cpu_budget'],r['concurrency'],-r['total_ns_day']))
    key=(lean['variant'],lean['concurrency'],lean['threads'],lean['mps'])
    done={r['replicate'] for r in study['records'] if r['phase']=='confirm'
          and (r['variant'],r['concurrency'],r['threads'],r['mps'])==key}
    tokens=[f'{key[0]},{key[1]},{key[2]},{int(key[3])},confirm,{i}' for i in (1,2,3) if i not in done]
    (root/'lean-selection.json').write_text(json.dumps({'screen_peak_ns_day':peak,
        'criterion':'within 95% of screening peak; fewest OpenMP workers, then fewer MD processes',
        'selected':{k:lean[k] for k in ('variant','concurrency','threads','cpu_budget','total_ns_day')},
        'additional_cases':tokens},indent=2))
    if tokens:
        (root/'COMPLETE.json').replace(root/'PRIMARY_COMPLETE.json')
        # The .tpr location is available in any stored case's independent input.
        tpr=root/study['records'][0]['case']/'run01/md.tpr'
        cmd=['/usr/bin/python3',a.runner,'--gmx',study['gmx'],'--tpr',str(tpr),
             '--root',str(root),'--hostname',study['hostname'],'--cases']+tokens
        with (root.parent/'lean-progress.log').open('w') as log:
            child=sp.Popen(cmd,stdin=sp.DEVNULL,stdout=log,stderr=sp.STDOUT)
            with (root.parent/'lean-memory-recorder.log').open('w') as memlog:
                sampler=sp.Popen(['/usr/bin/python3',a.recorder,'--study-pid',str(child.pid),
                                 '--root',str(root)],stdin=sp.DEVNULL,stdout=memlog,stderr=sp.STDOUT)
                code=child.wait()
                try:sampler.wait(timeout=8)
                except sp.TimeoutExpired:sampler.terminate();sampler.wait()
        if code:raise RuntimeError('Lean confirmation runner exited '+str(code))
    (root/'FOLLOWUP_COMPLETE.json').write_text(json.dumps({'completed_utc_seconds':time.time(),'selection':key}))
except Exception as exc:
    (root/'FOLLOWUP_ERROR.txt').write_text(str(exc))
    raise
