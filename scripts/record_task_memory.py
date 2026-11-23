#!/usr/bin/env python3
"""Sample only study-owned MD and private MPS allocations; no system baseline."""
import argparse
import csv
import datetime as dt
import os
from pathlib import Path
import re
import shutil
import subprocess as sp
import time

p=argparse.ArgumentParser()
p.add_argument('--study-pid', type=int, required=True)
p.add_argument('--root', required=True)
a=p.parse_args()
root=Path(a.root)
pipe=Path('/tmp')/f'codex-ext-mps-{os.getuid()}-{root.name}'
env=os.environ.copy();env['CUDA_MPS_PIPE_DIRECTORY']=str(pipe)
control=shutil.which('nvidia-cuda-mps-control')
fields=['utc','case','md_count','md_gpu_mib','mps_gpu_mib','task_gpu_mib',
        'task_ram_pss_mib','ram_unreadable_processes','gpu_memory_unavailable_processes']
memfile=root/'task-memory.csv'
needs_header=not memfile.exists() or memfile.stat().st_size==0
with memfile.open('a',newline='',buffering=1) as f:
    writer=csv.DictWriter(f,fieldnames=fields)
    if needs_header:writer.writeheader()
    while True:
        try:
            os.kill(a.study_pid,0)
        except ProcessLookupError:
            break
        if (root/'COMPLETE.json').exists() or (root/'ERROR.txt').exists():
            break
        md=set();cases=set()
        ps=sp.run(['ps','-eo','pid=,ppid=,comm='],text=True,capture_output=True,timeout=5)
        for line in ps.stdout.splitlines():
            parts=line.split()
            if len(parts)==3 and parts[1]==str(a.study_pid) and parts[2]=='gmx':
                pid=int(parts[0]);md.add(pid)
                try: cases.add(Path(os.readlink(f'/proc/{pid}/cwd')).parent.name)
                except OSError: pass
        servers=set()
        if pipe.exists():
            q=sp.run([control],input='get_server_list\n',env=env,text=True,
                     capture_output=True,timeout=5)
            for line in q.stdout.splitlines():
                if re.fullmatch(r'\s*\d+\s*',line):servers.add(int(line.strip()))
        query=sp.run(['nvidia-smi','--query-compute-apps=pid,used_memory',
                      '--format=csv,noheader,nounits'],text=True,capture_output=True,timeout=5)
        gpu={};unknown=set()
        if query.returncode==0:
            for line in query.stdout.splitlines():
                parts=[x.strip() for x in line.split(',')]
                if len(parts)!=2:continue
                try:
                    pid=int(parts[0]);gpu[pid]=float(parts[1])
                except ValueError:
                    if parts[0].isdigit():unknown.add(int(parts[0]))
        pss_kib=0;unreadable=0
        for pid in md|servers:
            try:
                text=Path(f'/proc/{pid}/smaps_rollup').read_text()
                m=re.search(r'^Pss:\s+(\d+)\s+kB',text,re.M)
                if m:pss_kib+=int(m.group(1))
                else:unreadable+=1
            except OSError:unreadable+=1
        mg=sum(gpu.get(x,0) for x in md);sg=sum(gpu.get(x,0) for x in servers)
        writer.writerow({'utc':dt.datetime.now(dt.timezone.utc).isoformat(),
            'case':';'.join(sorted(cases)),'md_count':len(md),'md_gpu_mib':mg,
            'mps_gpu_mib':sg,'task_gpu_mib':mg+sg,'task_ram_pss_mib':round(pss_kib/1024,3),
            'ram_unreadable_processes':unreadable,
            'gpu_memory_unavailable_processes':len((md|servers)&unknown)})
        time.sleep(5)
