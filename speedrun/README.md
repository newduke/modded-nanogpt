# Speedrun lab (RunPod)

The tools in `speedrun/` let you run any historical record of the speedrun, diff two records, and run your own edited copy. Each record runs with its own code and dependencies, and every result is logged.

The record list and history are in the [main README](../README.md). Every record trains the same 124M GPT-2 model to 3.28 validation loss on FineWeb.

## One-time setup

1. **Create a network volume** in RunPod, under Storage → Network Volume. Use the Secure Cloud tier, which is the only one with network volumes. Size it at about **100 GB**: roughly 21 GB of data plus about 5 GB for each Python environment. Pick a data center that has **H100 SXM** availability. The volume is tied to that data center.
2. **Deploy a cheap pod** in the same data center with the volume attached. It mounts at `/workspace`. Then run:
   ```bash
   cd /workspace
   git clone https://github.com/newduke/modded-nanogpt.git
   cd modded-nanogpt
   bash speedrun/bootstrap.sh        # downloads ~21 GB once, onto the volume
   ```
   Stop this pod when it's done. The data stays on the volume.

## Each session

1. Deploy an **8× H100 SXM** pod with the volume attached, using a PyTorch image.
   - For the newest records, set the CUDA filter to **13.0**. Upstream requires a CUDA 13 runtime from the ANVIL2 record onward, and a CUDA 13 host still runs the older records.
2. Run:
   ```bash
   cd /workspace/modded-nanogpt && git pull
   tmux new -s run
   python3 speedrun/speedrun.py run 2024-10-14
   ```
3. Stop the pod as soon as you're done. Results are kept in `/workspace/runs/LOG.md`, and each run gets its own folder with `train.log`.

The first run of a record builds its Python environment, which takes a few minutes. `torch.compile` also adds several minutes the first time. Repeat runs are faster.

## Commands

```bash
python3 speedrun/speedrun.py list                        # every record and where its code comes from
python3 speedrun/speedrun.py show 2024-10-14             # write a record's code to disk and print the path
python3 speedrun/speedrun.py diff 2024-10-14 2024-10-17  # what one record changed
python3 speedrun/speedrun.py run 2024-10-14              # train it
python3 speedrun/speedrun.py run latest                  # current upstream trainer
python3 speedrun/speedrun.py run 2024-10-14 --code ~/exp1          # your edited copy, same environment
python3 speedrun/speedrun.py run 2024-11-19 --torch 'torch==2.6.0' # pin torch if an old record breaks
```

A date prefix is enough to name a record, as long as only one record has that date.

**Where a record's code comes from:**
- **Newer records:** the code is the full repo at the commit that added the record, including any extra kernel files and that commit's `requirements.txt`.
- **Older records:** the code is the single-file trainer that is embedded word for word at the top of the record's log.
- **Two exceptions:** the two llm.c baselines can't be run here, because they live in karpathy/llm.c.

Older records run on current stable torch. If one breaks on a changed API, pin the torch version it was written for using `--torch`.

## Suggested path

Upstream wall-clock times on 8×H100:

| Step | Record | Time | Lesson |
|---|---|---|---|
| 1 | `2024-10-10_Muon` | 22.3 min | The Muon optimizer; read it next to nanoGPT's AdamW |
| 2 | `2024-10-14_ModernArch` | 15.2 min | ReLU², QK-norm, zero-init projections |
| 3 | `2024-10-17_DistributedMuon` | 13.1 min | Splitting optimizer work across GPUs |
| 4 | `2024-11-19_FlexAttention` | 5.03 min | Attention masks and long context |
| 5 | `2025-01-16_Sub3Min` | ~3 min | A stack of small wins |
| 6 | `latest` | ~40 s | Kernels, FP8, and everything else |

For each step, `diff` it against the previous record, guess what the change will do, run it, then change one thing in your own copy and run that too.

At about $26/hr for an 8× H100 pod, a 15-minute record costs about $7.
