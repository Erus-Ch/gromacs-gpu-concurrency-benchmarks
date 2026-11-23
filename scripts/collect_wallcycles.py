#!/usr/bin/env python3
"""Extract GROMACS internal timing rows, excluding the overlapping PME subtable."""
import argparse
import csv
import json
from pathlib import Path
import re

p=argparse.ArgumentParser()
p.add_argument('--study',required=True)
p.add_argument('--raw',required=True)
p.add_argument('--output',required=True)
a=p.parse_args()
doc=json.loads(Path(a.study).read_text());raw=Path(a.raw)
rows=[]
for r in doc['records']:
    for task in r['tasks']:
        log=(raw/r['case']/task['run']/'md.log').read_text(errors='replace')
        table=log.split('R E A L   C Y C L E   A N D   T I M E   A C C O U N T I N G',1)[1]
        table=table.split('Breakdown of PME mesh activities',1)[0]
        for line in table.splitlines():
            m=re.fullmatch(r'\s*(.+?)\s+(\d+)\s+(\d+)\s+(\d+)\s+([0-9.]+)\s+([0-9.]+)\s+([0-9.]+)\s*',line)
            if m:
                activity,ranks,threads,calls,wall_s,gcycles,pct=m.groups()
                rows.append({'hostname':doc['hostname'],'case':r['case'],'run':task['run'],
                    'phase':r['phase'],'variant':r['variant'],'concurrency':r['concurrency'],
                    'threads':r['threads'],'mps':r['mps'],'replicate':r['replicate'],
                    'activity':activity,'wall_s':float(wall_s),'giga_cycles':float(gcycles),
                    'reported_percent':float(pct),'calls':int(calls)})
with Path(a.output).open('w',newline='') as f:
    w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)
print('Extracted timing rows:',len(rows))
