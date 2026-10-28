# Data policy

This repository is public. These rules apply to every file, test fixture, prompt and example in it.

## What we use

1. **Synthetic invoices** from our own generator. They use fictional vendors and carry a visible
   "SYNTHETIC SAMPLE" marker, so they can't pass as real tax invoices. VAT numbers come only from a
   test-only pattern (the one ZATCA, the Saudi tax authority, uses in its sandbox), never numbers that
   could belong to a real taxpayer. The generator's dataset card documents the pattern.
2. **Public datasets** whose licence allows our use. Each one is recorded in the register below
   *before* it is used.

## What we never use

- Real invoices, receipts or documents from any company, client or employer.
- Any material from an employer, including code, designs, prompts or schemas.
- Personal data. Logs, traces and test fixtures contain no names, emails, phone numbers or IDs of real
  people.
- Any dataset whose origin or licence is unclear. If we can't say where it came from, we don't use it.

## Where data lives

Data files are never committed. Everything under `data/` except this file is git-ignored. Datasets are
downloaded by a script or published on Hugging Face, and their exact version is recorded here.

## Register

| Dataset | Source | Licence | Version or date | Used for | Lesson |
|---|---|---|---|---|---|
| *None yet* | | | | | |
