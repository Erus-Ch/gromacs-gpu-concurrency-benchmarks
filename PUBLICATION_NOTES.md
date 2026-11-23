# Publication, privacy and integrity

- Hardware models and software/build versions are intentionally retained for interpretation and reproduction.
- Workstation hostnames are replaced by role labels. Usernames, home paths, private IP addresses and GPU UUIDs are not distributed.
- Absolute recorded test dates, timestamps and time zones are withheld. Study and memory sampling times are elapsed seconds relative to each workstation's first batch. Durations, rates and numeric allocation measurements remain unchanged.
- Patch-file timestamps are omitted. ZIP entries use a fixed format timestamp. This does not remove publication dates created later by GitHub or Zenodo, and the hardware combination can still be distinctive.
- The original MD inputs/copies, energy files, trajectories, checkpoints and runtime logs were deleted at the owner's request after successful result extraction and audit. Extracted per-task data, timings and audit records remain.
- Upload the contents of this publication folder. Its parent contains private originals and is not the upload target.

## Regeneration

```bash
python3 -m venv .venv
.venv/bin/pip install -r analysis-requirements.txt -r publication-requirements.txt
.venv/bin/python scripts/analyze_extended.py .
.venv/bin/python scripts/finalize_publication.py .
sha256sum -c SHA256SUMS
```

The public analyzer reads publication-settings.json, supports elapsed timestamps, and writes REPORT.md. The finalizer refreshes README.md and index.html, checks every distributable text file for absolute test dates/private paths, then refreshes SHA256SUMS. Review the final folder again after any manual edit or script run. Checksums detect file changes; they do not independently prove benchmark validity.

To set actual publication URLs, append --repo-url https://github.com/YOUR_GITHUB_USERNAME/gromacs-gpu-concurrency-benchmarks and --site-url https://YOUR_GITHUB_USERNAME.github.io/gromacs-gpu-concurrency-benchmarks/ to the finalizer command. This adds canonical/preview URLs and sitemap.xml. Replace the username before running.

License and author/citation choices remain with the owner. Public accessibility and search submission cannot guarantee indexing, AI citations or model-training inclusion.
