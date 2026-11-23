# 0009. Publish dataset releases on the Hugging Face Hub, as Parquet with time-based splits

- **Status:** Accepted
- **Date:** 2026-11-23

## Context

The generator makes any dataset on demand, but later modules need one fixed dataset they can all name:
Module 3 fine-tunes on it, Module 4 trains vision models, Modules 5 and 6 score reviewers against its
labels, and Module 10 watches it drift. A training run or an evaluation must load exactly the same data
months later, on another machine or in CI.

## Decision

- **A public dataset repo on the Hugging Face Hub,** one release per generator version, tagged
  `v<version>` (`v0.3.0` first). Code loads it with `load_dataset(repo, revision="v0.3.0")`, so a run
  names the data it used. The Hub repo is a git repo, so a tag can't move silently.
- **Parquet, one file per split,** built by `tools/hf-release/release.py` with `datasets` 5.2.0. A row
  holds the page as a PNG, a few columns to filter on (type, date, design, anomaly), and the page's whole
  ground-truth JSON as text. `records/` holds the buyers' records and the generator's `dataset.json`.
- **Splits by issue date:** train before May, validation May to June, test from the drift date (1 July).
- **Build, review, then upload:** the tool only writes a folder; `hf upload` publishes it after review.
- The dataset card is generated: the release's command, commit and counts, then `datagen/DATASET_CARD.md`
  with its links pinned to that commit.

## Rejected options

- **Random splits:** they mix drifted invoices into training and hide the drift Module 10 must catch. A
  time split is also how production works: train on the past, meet the future.
- **Uploading the generator's folder as it is** (6,000+ files): no row joins a page to its labels, and it is
  far past the Hub's recommended 100 files per commit. **ImageFolder with a metadata file** would work, but
  flattens the nested labels and still uploads 2,000 images.
- **`push_to_hub` from the script:** it publishes without a look at what goes public.
- **Including the PDFs:** they differ on every run (each records when it was made), so a release with them
  can't be rebuilt byte for byte; anyone who needs them runs the recorded command.
- **One `ground_truth` column per field:** the JSON has nested lines, boxes and orders; text keeps it
  exactly as the generator wrote it, and `json.loads` gives it back.

## Measurements

Release v0.3.0: `--seed 20261122 --count 2000 --drift-from 2026-07-01`, generator 0.3.0 at commit 35f31d8,
on WSL2 Ubuntu 24.04 (Ryzen 5 3600X), 2026-11-22 and 23.

| | Result |
|---|---|
| Drawing 2,000 pages | 455 s (228 ms a page), 549 MiB: PNG 432, PDF 82, JSON 35 |
| Building the release | 7.9 s; 435 MiB: Parquet 183, 182 and 88 MB, records 1.4 MB |
| Splits (train / validation / test) | 807 / 386 / 807 invoices |
| Anomalies | 39 / 32 / 75 (4.8% of train, 9.3% of test: drift doubles the rate) |
| Design b | 0 / 0 / 273 |
| Duplicates whose original is in an earlier split | 0 of 36 |
| Read back with `load_dataset("parquet", ...)` | 3 splits, PNG 1588 x 2246, full ground truth |
| Upload with the default Xet path (`hf` 2.3.0, hf_xet 1.7.0) | Stalled after an hour: each ~61 MB block timed out (Xet measured 115 KB/s to its servers), 2 blocks gave up after 5 tries, nothing committed |
| Upload with `HF_HUB_DISABLE_XET=1` (Git LFS) | 454 MB in 2 min 32 s, three files in parallel (about 1.2 MB/s each), one commit |

Hub storage for public repos is "best-effort" free with no stated cap (Hugging Face's storage-limits page,
read 2026-11-22); this release is under half a gigabyte.

## Consequences

- Later modules pin `revision="v0.3.0"` and record it next to their results.
- A new generator version means a new release and tag; old tags stay loadable.
- The release is public: everything in it is synthetic, carries the marker, and uses test VAT numbers.
- `datasets` and Pillow live in a `release` dependency group, outside CI and the API image.
- From this machine, uploads use `HF_HUB_DISABLE_XET=1`: the speed depends on the route, not only the
  line (a speed test to another host measured about 0.4 MB/s, the LFS upload about 3.4 MB/s in total).

## Revisit when

- A release outgrows one Parquet file per split (the Hub recommends files well under 200 GB, so not soon),
  or Module 4 needs the images as separate files.
- A module needs an in-distribution test set after July: today validation is the last pre-drift data.
