#!/usr/bin/env python3
"""Build readable publication pages, validate privacy, and refresh file hashes."""
import argparse
import csv
import hashlib
import html
import json
from pathlib import Path
import re
import statistics as st
from urllib.parse import urlparse
import zipfile
import markdown

p=argparse.ArgumentParser()
p.add_argument('root',nargs='?',default='.')
p.add_argument('--site-url',help='Actual HTTPS Pages URL, including the project path')
p.add_argument('--repo-url',help='Actual HTTPS GitHub repository URL')
p.add_argument('--zip-output',help='Optional release archive outside the publication folder')
a=p.parse_args();root=Path(a.root).resolve()
settings=json.loads((root/'publication-settings.json').read_text())
if not settings.get('withhold_absolute_test_times'):raise RuntimeError('Public time privacy setting must remain enabled')
for arg,key in ((a.site_url,'site_url'),(a.repo_url,'repository_url')):
    if arg:
        u=urlparse(arg)
        if u.scheme!='https' or not u.netloc or u.query or u.fragment:raise ValueError('Use a real HTTPS URL without query/fragment')
        settings[key]=arg.rstrip('/')+('/' if key=='site_url' else '')
(root/'publication-settings.json').write_text(json.dumps(settings,indent=2)+'\n')
rows=json.loads((root/'configuration_summary.json').read_text())
confirmed=[r for r in rows if r['phase']=='confirm']
def get(gpu,n,t,variant):
    return next(r for r in confirmed if r['gpu']==gpu and r['concurrency']==n and r['threads_per_md']==t and r['variant']==variant)
blackwell=get('RTX PRO 6000 Blackwell',8,3,'gpu-graphs')
lean=get('RTX PRO 6000 Blackwell',12,1,'gpu-graphs')
a4000=get('RTX A4000',4,2,'gpu-graphs')
single=get('RTX PRO 6000 Blackwell',1,4,'gpu-graphs')
studies=[json.loads((root/'data'/f'{h}-study.json').read_text()) for h in ('local','remote')]
case_count=sum(len(s['records']) for s in studies)
process_count=sum(r['concurrency'] for s in studies for r in s['records'])
title=settings['title'];description=settings['description']
repo=settings.get('repository_url','');site=settings.get('site_url','')
lines=[f'# {title}','','**Measured RNase cubic performance · 24,040 atoms · GROMACS 2026.1 · CUDA MPS · CPU-thread allocation**','',
 'This benchmark measures total throughput from independent molecular dynamics simulations sharing one NVIDIA GPU. It compares two complete workstations: RTX PRO 6000 Blackwell with Core Ultra 9 285K, and RTX A4000 with Xeon w5-2455X. It explores NVIDIA CUDA Multi-Process Service (MPS), a combined GPU-bonded/CUDA-Graphs path, concurrency and OpenMP workers per simulation.', '',
 f'**{case_count} completed batches and {process_count} successful MD processes.** Selected settings received longer confirmation runs; all completed logs passed the execution audit before the requested MD-file cleanup.', '',
 '## Measured results at a glance', '',
 '`N × T` means N independent MD jobs, each with one thread-MPI rank and T OpenMP workers. All three rows below use MPS and GPU bonded + CUDA Graphs.', '',
 '| GPU / choice | N × T | Nominal CPU workers | Aggregate ns/day, mean ± sample SD | Batches | Full-batch ns/day | Task GPU peak MiB | Task RAM PSS peak MiB |',
 '|---|---:|---:|---:|---:|---:|---:|---:|']
for label,r in [('RTX PRO 6000 Blackwell / highest confirmed mean',blackwell),('RTX PRO 6000 Blackwell / fewer CPU workers',lean),('RTX A4000 / confirmed plateau',a4000)]:
    sd=f"{r['total_sd_ns_day']:.3f}" if 0<r['total_sd_ns_day']<.05 else f"{r['total_sd_ns_day']:.1f}"
    lines.append(f"| {label} | {r['concurrency']} × {r['threads_per_md']} | {r['openmp_budget']} | {r['total_mean_ns_day']:.1f} ± {sd} | {r['repeats']} | {r['batch_mean_ns_day']:.1f} | {r['sampled_task_gpu_peak_mib']:.0f} | {r['sampled_task_ram_pss_peak_mib']:.1f} |")
lines += ['',
 f"- Blackwell 8 × 3 delivered **{blackwell['total_mean_ns_day']/single['total_mean_ns_day']:.2f}×** the fastest confirmed single-MD setting on that workstation. This gain combines concurrency, MPS and the chosen execution path; it is not an isolated MPS-only speedup.",
 f"- Blackwell 12 × 1 retained **{100*lean['total_mean_ns_day']/blackwell['total_mean_ns_day']:.1f}%** of that mean throughput with half the nominal OpenMP workers, with greater observed batch variability.",
 '- On A4000, auto bonded and GPU bonded + Graphs were effectively tied near 929 ns/day at 4 × 2. The 4 × 1 auto-bonded screen was already near the plateau, but did not receive longer confirmation before the requested early stop.', '',
 'The aggregate metric sums each process’s post-warm-up rate. Full-batch throughput includes startup, warm-up and completion-tail effects. Cross-workstation differences include CPU and build differences; they are not a GPU-only hardware comparison. These short performance runs do not establish scientific equilibration.', '',
 '![Repeated measurements of GROMACS GPU throughput](confirmed_throughput.png)', '',
 '## Questions this dataset helps answer', '',
 '### How many concurrent GROMACS jobs should I run on RTX PRO 6000 Blackwell?',
 'For this 24,040-atom RNase input, 8 jobs with 3 OpenMP workers each had the highest longer-run mean among tested settings. Twelve jobs with one worker each were a useful CPU-saving alternative. Other molecular systems may prefer different settings.', '',
 '### Does CUDA MPS help small GROMACS simulations?',
 'It can improve GPU sharing when one process leaves capacity unused. The matched Blackwell 8 × 3 screening control measured approximately 2.18× aggregate throughput with MPS versus without it. That control has one run per setting; the larger 2.97× ensemble-versus-single comparison changes more than MPS alone.', '',
 '### Should I always enable GPU bonded and CUDA Graphs?',
 'The combined path helped this Blackwell workload. It did not establish a throughput advantage over auto bonded on A4000. This extension changed GPU-bonded offload and CUDA Graphs together and does not isolate their individual effects.', '',
 '### Do GPU-wait timers prove a PCIe transfer bottleneck?',
 'No. They can include preceding GPU execution and synchronization. The report supports a CPU/offload/sharing interpretation, while distinguishing GPU arithmetic, device-memory bandwidth and PCIe traffic would require separate hardware profiling.', '',
 '## Full methodology, data and reproduction', '',
 '- [Full English benchmark report](REPORT.md)',
 '- [Configuration summary CSV](configuration_summary.csv) and [JSON](configuration_summary.json)',
 '- [Input provenance and reproduction commands](REPRODUCE.md)',
 '- [Extracted per-task Blackwell data](data/local-study.json) and [A4000 data](data/remote-study.json)',
 '- [Blackwell task-memory samples](data/local-task-memory.csv) and [A4000 task-memory samples](data/remote-task-memory.csv)',
 '- [Blackwell audit record](data/local-audit.json) and [A4000 audit record](data/remote-audit.json)',
 '- [Privacy and checksum notes](PUBLICATION_NOTES.md)',
 '- [Reuse and licensing guidance](LICENSE_GUIDANCE.md)', '',
 'Upstream input: [Páll, supplementary GROMACS benchmark dataset, DOI 10.5281/zenodo.3893789](https://zenodo.org/records/3893789). The exact input hash and build details are in the report. Original MD input copies, energies, trajectories, checkpoints and runtime logs were deleted after result extraction and successful audit, at the owner’s request. Extracted rates, command lines, timings and audit records remain available.', '',
 'Hardware and software versions are intentionally public. Absolute test timestamps and time zones are withheld; elapsed times and sampled intervals are retained. Publication-platform commit/release dates are separate from the withheld test times.', '']
if repo:lines += [f'[Repository and version history]({repo})','']
if site:lines += [f'[Readable benchmark website]({site})','']
if settings.get('public_author'):lines += ['Public attribution: '+settings['public_author'],'']
if settings.get('citation_doi'):
    doi=settings['citation_doi'].removeprefix('https://doi.org/')
    if not re.fullmatch(r'10\.\d{4,9}/[^\s<>]+',doi):raise ValueError('Enter the actual benchmark release DOI')
    lines += [f'[Archived benchmark release: {doi}](https://doi.org/{doi})','']
readme='\n'.join(lines);(root/'README.md').write_text(readme)
report=(root/'REPORT.md').read_text()
if (root/'REPRODUCE.md').exists():
    reproduction=(root/'REPRODUCE.md').read_text()
    reproduction=reproduction.replace('.venv/bin/pip install matplotlib numpy','.venv/bin/pip install -r analysis-requirements.txt -r publication-requirements.txt')
    if 'scripts/finalize_publication.py .' not in reproduction:
        reproduction=reproduction.replace('scripts/analyze_extended.py .','scripts/analyze_extended.py .\n.venv/bin/python scripts/finalize_publication.py .')
    (root/'REPRODUCE.md').write_text(reproduction)
body=markdown.markdown(readme,extensions=['tables','fenced_code','toc'])
full=markdown.markdown('\n'.join(report.splitlines()[1:]),extensions=['tables','fenced_code','toc'])
schema={'@context':'https://schema.org','@type':'Dataset','name':title,'description':description,
        'inLanguage':'en','keywords':settings['topics'],
        'citation':'https://doi.org/10.5281/zenodo.3893789',
        'measurementTechnique':'GROMACS 2026.1 mixed-precision RNase cubic MD; independent GPU-sharing jobs; per-process timing resets and longer confirmations'}
if settings.get('citation_doi'):schema['identifier']='https://doi.org/'+doi
canonical=''
if site:
    canonical=f'<link rel="canonical" href="{html.escape(site,quote=True)}">\n<meta property="og:url" content="{html.escape(site,quote=True)}">'
    schema['url']=site
    schema['distribution']={'@type':'DataDownload','encodingFormat':'text/csv','contentUrl':site+'configuration_summary.csv'}
    (root/'sitemap.xml').write_text('<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9"><url><loc>'+html.escape(site)+'</loc></url></urlset>\n')
style='''body{margin:0;background:#f5f7fa;color:#1b2938;font:17px/1.65 system-ui,sans-serif}main{max-width:1120px;margin:36px auto;padding:28px;background:#fff;border:1px solid #dce2e9;border-radius:12px}h1{font-size:2rem;line-height:1.25}h2{margin-top:2rem}a{color:#1859a0}table{display:block;overflow-x:auto;border-collapse:collapse;width:100%;font-size:.9rem}th,td{padding:9px;border:1px solid #d6dee7;text-align:left}th{background:#edf3f8}td:nth-child(2),th:nth-child(2){white-space:nowrap}img{max-width:100%;height:auto}pre{padding:16px;overflow:auto;background:#f0f3f6}code{font-family:ui-monospace,monospace;font-size:.88em}nav{padding:12px;background:#edf3f8;border-radius:6px}.mermaid{white-space:pre-wrap}@media(max-width:680px){main{margin:0;padding:18px;border:0;border-radius:0}h1{font-size:1.5rem}}'''
# No client-side code is required to reveal the benchmark text or tables.
document=f'''<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{html.escape(title)}</title><meta name="description" content="{html.escape(description,quote=True)}">
<meta name="robots" content="index,follow"><meta property="og:type" content="article">
<meta property="og:title" content="{html.escape(title,quote=True)}"><meta property="og:description" content="{html.escape(description,quote=True)}">
{canonical}<script type="application/ld+json">{json.dumps(schema,ensure_ascii=False).replace('<','&lt;')}</script><style>{style}</style></head>
<body><main><nav><a href="#full-report">Full methodology and results</a> · <a href="configuration_summary.csv">CSV data</a> · <a href="REPRODUCE.md">Reproduction</a></nav>
{body}<hr><section id="full-report"><h2>Full benchmark report</h2>{full}</section></main></body></html>'''
(root/'index.html').write_text(document)
(root/'.nojekyll').write_text('')
# A report generator may produce another Markdown report; inspect every final text file.
bad=[]
for path in root.rglob('*'):
    if not path.is_file() or any(x in path.relative_to(root).parts for x in ('.git','.venv','__pycache__')) or path.suffix not in ('.md','.json','.csv','.py','.html','.xml','.patch','.txt'):continue
    text=path.read_text(errors='replace')
    if re.search(r'/ho' r'me/|\b100\.70\.\d+\.\d+\b|GPU-[0-9a-fA-F]{8}-',text):bad.append(str(path.relative_to(root))+': private identifier')
    if re.search(r'\b20\d{2}-\d{2}-\d{2}(?:T|\b)',text):bad.append(str(path.relative_to(root))+': absolute test date/time zone')
if bad:raise RuntimeError('Publication validation failed: '+repr(bad))
hashes=[]
for path in sorted(root.rglob('*')):
    if path.is_file() and path.name!='SHA256SUMS' and '.git' not in path.parts and '__pycache__' not in path.parts and '.venv' not in path.parts:
        hashes.append(hashlib.sha256(path.read_bytes()).hexdigest()+'  '+path.relative_to(root).as_posix())
(root/'SHA256SUMS').write_text('\n'.join(hashes)+'\n')
if a.zip_output:
    archive=Path(a.zip_output).resolve()
    if root in archive.parents:raise ValueError('Keep the ZIP outside the publication folder')
    with zipfile.ZipFile(archive,'w',compression=zipfile.ZIP_DEFLATED,compresslevel=6) as z:
        for path in sorted(root.rglob('*')):
            if not path.is_file() or '.git' in path.parts or '__pycache__' in path.parts or '.venv' in path.parts:continue
            info=zipfile.ZipInfo(path.relative_to(root).as_posix(),date_time=(1980,1,1,0,0,0))
            info.compress_type=zipfile.ZIP_DEFLATED;info.external_attr=0o100644<<16
            z.writestr(info,path.read_bytes())
print(f'Validated {len(hashes)} publication files; refreshed README, HTML and SHA256SUMS.')
