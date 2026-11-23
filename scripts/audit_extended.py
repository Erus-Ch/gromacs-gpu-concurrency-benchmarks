#!/usr/bin/env python3
"""Independent checks against raw GROMACS logs for the extended study."""
import argparse
import json
import math
from pathlib import Path
import re

p=argparse.ArgumentParser()
p.add_argument('--study',required=True)
p.add_argument('--raw',required=True)
p.add_argument('--output',required=True)
a=p.parse_args();doc=json.loads(Path(a.study).read_text());raw=Path(a.raw)
details=[]
for r in doc['records']:
    errors=[];n=r['concurrency'];t=r['threads']
    if n*t>24:errors.append('OpenMP budget exceeded')
    if len(r['tasks'])!=n:errors.append('Incorrect task count')
    if r['mps'] and r['mps_clients_verified']<n:errors.append('MPS client count not verified')
    for task in r['tasks']:
        d=raw/r['case']/task['run'];log=(d/'md.log').read_text(errors='replace')
        stdout=(d/'md.stdout').read_text(errors='replace')
        if task['exit'] or not math.isfinite(task['ns_day']) or task['ns_day']<=0:
            errors.append(task['run']+': invalid exit/rate')
        if 'Finished mdrun' not in log:errors.append(task['run']+': missing completion')
        if 'resetting all time and cycle counters' not in stdout.lower():
            errors.append(task['run']+': missing timing reset')
        if re.search(r'WARNING|Fatal error|LINCS WARNING',log) or re.search(r'\bnan\b',log,re.I):
            errors.append(task['run']+': warning/error/NaN in log')
        if not re.search(rf'Using {t} OpenMP thread',stdout):
            errors.append(task['run']+': thread allocation differs')
        if r['variant']=='gpu-graphs' and not re.search(r'^\s*MD Graph\s+\d',log,re.M):
            errors.append(task['run']+': graphs not used')
        rate=re.findall(r'^Performance:\s+([0-9.]+)',log,re.M)
        if not rate or abs(float(rate[-1])-task['ns_day'])>.0005:
            errors.append(task['run']+': reported rate differs')
    details.append({'case':r['case'],'tasks':n,'passed':not errors,'errors':errors})
result={'hostname':doc['hostname'],'cases':len(details),
        'successful_md_runs':sum(r['concurrency'] for r in doc['records']),
        'all_passed':all(x['passed'] for x in details),'details':details}
Path(a.output).write_text(json.dumps(result,indent=2))
print({k:v for k,v in result.items() if k!='details'})
if not result['all_passed']:raise SystemExit(1)
