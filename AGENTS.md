# AGENTS.md

## Project
Jordan's fork of KellerJordan/modded-nanogpt, the NanoGPT speedrun: train a 124M GPT-2 to 3.28 val loss on FineWeb as fast as possible on 8x H100.
Upstream code: `train_gpt.py`, `train_gpt_medium.py`, `track_1_short/` (current record trainer), `data/`, `evals/`, `records/`.
Jordan's own work: `speedrun/` (a lab that lists, diffs, shows and runs any historical record on RunPod; see `speedrun/README.md`).
Training needs 8x H100 and a RunPod network volume. Nothing here trains on a laptop.

## Commands (agents may run these without asking)
- syntax check: `python -m py_compile <file.py>`
- list records and their code source: `python speedrun/speedrun.py list`
- write a record's code to disk: `python speedrun/speedrun.py show <record>`
- diff two records: `python speedrun/speedrun.py diff <a> <b>`
These need full git history. In a shallow clone every record resolves to HEAD; run `git rev-parse --is-shallow-repository` first and say so if it prints `true`.

## Never (ask Jordan first)
- `python speedrun/speedrun.py run ...`, `run.sh`, `torchrun`, `speedrun/bootstrap.sh`, or anything that trains, downloads datasets, or rents GPUs. These cost real money.
- push, open PRs, or touch `.env*`, keys, or RunPod credentials
- edit anything under `records/`: they are historical logs and the lab reads trainer code out of them verbatim
- rewrite files outside your owned paths
- invent numbers: timings, losses and costs come from a log line or a command you ran, or you write "not measured"

## Ownership
- `speedrun/`                      -> lab work (Jordan's code; the usual place for changes)
- `track_1_short/`, `train_gpt*.py` -> upstream trainer; edit only for a named experiment, in a copy made with `speedrun.py show`
- `data/`, `evals/`, `Dockerfile`, `requirements.txt` -> upstream; read-only unless the brief names them
- `records/`                        -> read-only, always
- `README.md`                       -> upstream README; lab docs go in `speedrun/README.md`

## Done means
- every changed .py file passes `python -m py_compile`
- any lab change is exercised with `list`, `show` or `diff` on at least two records, output pasted
- every claim in a report has a repo-relative path + 1-based line number
- post "@verifier [done]" with a summary under 15 lines

## Gemini API CLI (`gemini-api`)
You have access to gemini-api through the shell.
Use it to call Gemini models, generate or edit media, analyze files, or launch managed agents.
1. Inspect --help or --usage to choose a command, and --schema when building a --body JSON payload.
2. Preview API calls with --dry-run (or --dry-run --output-format json).
3. For single JSON results, pass --stream=false --output-format json.
4. Capture returned file paths and interaction IDs to continue multi-step tasks.
Calls bill a paid Gemini API key: use --dry-run unless the brief asks for a real call.
