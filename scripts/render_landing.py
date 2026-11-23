"""Render the concise public benchmark page from grouped measurements."""
import html
import json

REPO = 'https://github.com/Erus-Ch/gromacs-gpu-concurrency-benchmarks'

def render_landing(settings, rows):
    def get(gpu, n, t, variant='gpu-graphs'):
        return next(r for r in rows if r['phase'] == 'confirm' and
                    r['gpu'] == gpu and r['concurrency'] == n and
                    r['threads_per_md'] == t and r['variant'] == variant)
    bw = get('RTX PRO 6000 Blackwell', 8, 3)
    lean = get('RTX PRO 6000 Blackwell', 12, 1)
    single = get('RTX PRO 6000 Blackwell', 1, 4)
    a4 = get('RTX A4000', 4, 2)
    auto = get('RTX A4000', 4, 2, 'auto')
    def result(r, label):
        sd = r['total_sd_ns_day']
        spread = f'{sd:.3f}' if 0 < sd < .05 else f'{sd:.1f}'
        return (f'<tr><th scope="row">{label}</th>'
                f'<td>{r["concurrency"]} × {r["threads_per_md"]}</td>'
                f'<td>{r["openmp_budget"]}</td>'
                f'<td><strong>{r["total_mean_ns_day"]:,.1f}</strong> ± {spread}</td>'
                f'<td>{r["batch_mean_ns_day"]:,.1f}</td><td>{r["repeats"]}</td></tr>')
    table_rows = ''.join([result(bw, 'RTX PRO 6000 Blackwell'),
                          result(lean, 'RTX PRO 6000 Blackwell · fewer CPU workers'),
                          result(a4, 'RTX A4000')])
    title = html.escape(settings['title'])
    description = html.escape(settings['description'], quote=True)
    site = settings.get('site_url') or 'https://erus-ch.github.io/gromacs-gpu-concurrency-benchmarks/'
    schema = {'@context': 'https://schema.org', '@type': 'Dataset',
              'name': settings['title'], 'description': settings['description'],
              'url': site, 'inLanguage': 'en', 'keywords': settings['topics'],
              'citation': 'https://doi.org/10.5281/zenodo.3893789',
              'distribution': {'@type': 'DataDownload', 'encodingFormat': 'text/csv',
                               'contentUrl': site + 'configuration_summary.csv'}}
    style = """
:root{color-scheme:light;--ink:#202420;--muted:#596159;--line:#dce1db;--accent:#477400}
*{box-sizing:border-box}html{scroll-behavior:smooth}body{margin:0;background:#fff;color:var(--ink);font:16px/1.65 -apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif}
main,footer{max-width:1100px;margin:auto;padding:0 32px}a{color:var(--accent);text-underline-offset:4px}a:hover{text-decoration-thickness:2px}a:focus-visible{outline:2px solid var(--accent);outline-offset:4px}
nav{display:flex;gap:24px;flex-wrap:wrap;padding:24px 0;border-bottom:1px solid var(--line);font-size:14px}nav a{color:var(--ink);text-decoration:none}
header{padding:48px 0 32px;border-bottom:1px solid var(--line)}.eyebrow{font-size:12px;letter-spacing:.12em;text-transform:uppercase;font-weight:650;color:var(--muted)}
h1{font-size:clamp(30px,4.5vw,46px);line-height:1.15;letter-spacing:-.035em;max-width:850px;margin:16px 0}header p{color:var(--muted);max-width:820px;margin:0}
section{padding:30px 0;border-bottom:1px solid var(--line);scroll-margin-top:20px}h2{font-size:24px;line-height:1.3;letter-spacing:-.02em;margin:0 0 18px}p{margin:12px 0}.table-wrap{overflow-x:auto}table{border-collapse:collapse;width:100%;font-size:14px}
caption{text-align:left;color:var(--muted);padding:0 0 12px}th,td{padding:13px 12px;border-bottom:1px solid var(--line);text-align:right;font-variant-numeric:tabular-nums;white-space:nowrap}thead th{font-weight:600;background:#f3f5f1;vertical-align:bottom}th:first-child,td:first-child{text-align:left;white-space:normal}tbody th{font-weight:500}thead small{font-weight:400;color:var(--muted)}
.note,figcaption{font-size:13px;color:var(--muted);line-height:1.6}.findings{padding-left:20px;margin:20px 0 0}.findings li{padding:4px 0}
figure{margin:20px 0 0}img{display:block;width:100%;height:auto}figcaption{margin-top:8px}.setup th:first-child{width:24%}.setup td{text-align:left;white-space:normal}.setup th{white-space:normal}.links{display:flex;gap:12px 26px;flex-wrap:wrap}code{font-size:.9em;background:#f3f5f1;padding:2px 4px;overflow-wrap:anywhere}footer{padding-top:24px;padding-bottom:36px;font-size:13px;color:var(--muted)}footer p{margin:5px 0}
@media(max-width:640px){main,footer{padding-left:18px;padding-right:18px}nav{gap:12px 20px}header{padding-top:32px}th,td{padding:10px}section{padding:24px 0}table{min-width:720px}.setup{min-width:570px}}
@media(prefers-reduced-motion:reduce){html{scroll-behavior:auto}}
"""
    return f'''<!doctype html>
<html lang="en">
<head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{title}</title><meta name="description" content="{description}">
<link rel="canonical" href="{html.escape(site, quote=True)}">
<meta property="og:type" content="article"><meta property="og:title" content="{title}">
<meta property="og:description" content="{description}"><meta property="og:url" content="{html.escape(site, quote=True)}">
<script type="application/ld+json">{json.dumps(schema).replace('<', '&lt;')}</script>
<style>{style}</style></head>
<body><main>
<nav aria-label="Main navigation"><a href="#results">Results</a><a href="#scaling">Scaling</a><a href="#configuration">Test configuration</a><a href="#data">Data &amp; methods</a><a href="{REPO}">GitHub ↗</a></nav>
<header><span class="eyebrow">Molecular dynamics · Performance benchmark</span>
<h1>GROMACS GPU concurrency</h1>
<p>RTX PRO 6000 Blackwell and RTX A4000 · RNase cubic, 24,040 atoms · GROMACS 2026.1</p>
</header>
<section id="results"><h2>Confirmed throughput</h2>
<div class="table-wrap" role="region" aria-label="Confirmed throughput table" tabindex="0"><table>
<caption>MPS enabled · GPU bonded + CUDA Graphs · Throughput in ns/day</caption>
<thead><tr><th scope="col">GPU</th><th scope="col">Jobs × threads</th><th scope="col">CPU workers</th><th scope="col">Aggregate<br><small>mean ± sample SD</small></th><th scope="col">Full batch<br><small>mean</small></th><th scope="col">Batches</th></tr></thead>
<tbody>{table_rows}</tbody></table></div>
<p class="note">Each job uses one thread-MPI rank. CPU workers = jobs × OpenMP threads per job; MPS and driver helper threads are additional. Aggregate throughput sums each job’s post-warm-up rate. Full-batch throughput includes startup, warm-up and completion tails.</p>
<ul class="findings">
<li><strong>Blackwell:</strong> 8 × 3 produced the highest confirmed mean, {bw['total_mean_ns_day']/single['total_mean_ns_day']:.2f}× the fastest confirmed single-job setting (1 × 4, {single['total_mean_ns_day']:,.1f} ± {single['total_sd_ns_day']:.1f} ns/day). The comparison combines concurrency and MPS.</li>
<li><strong>CPU allocation:</strong> 12 × 1 retained {100*lean['total_mean_ns_day']/bw['total_mean_ns_day']:.1f}% of Blackwell’s peak mean with half the nominal CPU workers; batch variability was higher.</li>
<li><strong>A4000:</strong> 4 × 2 reached approximately 929 ns/day with either auto bonded ({auto['total_mean_ns_day']:.1f} ± {auto['total_sd_ns_day']:.1f}) or GPU bonded + Graphs. The measurements show no clear advantage for the latter.</li>
</ul>
<figure><img src="confirmed_throughput.png" width="1400" alt="Confirmation batches for single-job and concurrent GROMACS configurations"><figcaption>Confirmation measurements. Dots represent individual batches; repetition counts for all configurations are in the <a href="{REPO}/blob/main/REPORT.md#longer-confirmation-runs">full results table</a>.</figcaption></figure>
</section>
<section id="scaling"><h2>Concurrency scaling</h2>
<figure><img src="concurrency_scaling.png" loading="lazy" width="1400" alt="Aggregate throughput against concurrent jobs, with one OpenMP thread per job"><figcaption>Screening runs with one OpenMP thread per job. Each point is one batch; confirmed results above use separately selected thread allocations.</figcaption></figure>
<p>A4000’s auto-bonded path plateaued at about 933–935 ns/day from 4 to 12 jobs. Blackwell’s GPU-bonded + Graphs path reached about 4,556 ns/day at 8 jobs and 4,781 ns/day at 12 jobs in screening.</p>
<p class="note">A matched Blackwell 8 × 3 screening control measured 4,851.3 ns/day with MPS and 2,229.2 without MPS (2.18×; one batch per setting). GPU bonded and CUDA Graphs were changed together throughout the path comparison.</p>
</section>
<section id="configuration"><h2>Test configuration</h2>
<div class="table-wrap" role="region" aria-label="Hardware configuration table" tabindex="0"><table class="setup">
<thead><tr><th scope="col">Platform</th><th scope="col">Blackwell workstation</th><th scope="col">A4000 workstation</th></tr></thead>
<tbody>
<tr><th scope="row">GPU</th><td>RTX PRO 6000 Blackwell · ~96 GiB</td><td>RTX A4000 · ~16 GiB</td></tr>
<tr><th scope="row">CPU</th><td>Core Ultra 9 285K<br>8 P-cores + 16 E-cores · 24 threads</td><td>Xeon w5-2455X<br>12 cores · 24 threads</td></tr>
<tr><th scope="row">OS / GCC</th><td>Ubuntu 26.04.1 LTS / 13.4.0</td><td>Ubuntu 24.04.4 LTS / 13.3.0</td></tr>
<tr><th scope="row">GROMACS build</th><td>AVX2 · sm_120</td><td>AVX-512 · sm_86</td></tr>
</tbody></table></div>
<p><strong>Software:</strong> GROMACS 2026.1, mixed precision; CUDA 13.1.115; FFTW 3.3.10; NVIDIA driver 595.99.02. Blackwell used a declaration-only CUDA/glibc compatibility patch, documented in the <a href="{REPO}/blob/main/REPORT.md#hardware-and-controlled-setup">build notes</a>.</p>
<p><strong>Run settings:</strong> 2 fs timestep; one thread-MPI rank per job; GPU nonbonded and PME; <code>-update auto -notunepme -pin off</code>. The two paths used <code>-bonded auto</code> or <code>-bonded gpu</code> with <code>GMX_CUDA_GRAPH=1</code>. MPS used default scheduling with private pipes and no active-thread partition.</p>
<p><strong>Protocol:</strong> screening, 80,000 steps with 20,000 excluded; confirmation, 200,000 steps with 40,000 excluded. All 79 completed batches (432 MD processes) passed the execution audit. Full search results and task memory measurements are available in the dataset.</p>
<p class="note">Results apply to this RNase workload and the tested configurations. Cross-workstation comparisons include CPU and build differences. Batch SD describes observed repeatability; the small sample counts do not establish an ordering between close configurations. A4000 4 × 1 auto bonded reached 933.4 ns/day in screening but did not receive longer confirmation.</p>
</section>
<section id="data"><h2>Data &amp; methods</h2>
<p class="links"><a href="{REPO}/blob/main/REPORT.md">Full report</a><a href="configuration_summary.csv" download>Results CSV ↓</a><a href="configuration_summary.json">Results JSON</a><a href="{REPO}/blob/main/REPRODUCE.md">Reproduction commands</a></p>
<p class="links"><a href="{REPO}/tree/main/data">Per-job data &amp; audits</a><a href="configuration_heatmaps.png">Configuration heatmaps</a><a href="single_task_cpu_scaling.png">Single-job CPU scaling</a></p>
</section></main>
<footer><p>Input: RNase cubic, RNASE ZF-1A in water · <a href="https://doi.org/10.5281/zenodo.3893789">Páll benchmark dataset</a>.</p>
<p><a href="{REPO}/blob/main/PUBLICATION_NOTES.md">Publication notes</a> · <a href="{REPO}/blob/main/LICENSE_GUIDANCE.md">Reuse &amp; licensing</a></p></footer>
</body></html>
'''

