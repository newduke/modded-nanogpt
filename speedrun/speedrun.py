#!/usr/bin/env python3
"""Run, inspect, and compare modded-nanogpt speedrun records.

  python3 speedrun/speedrun.py list                     # all records + where their code comes from
  python3 speedrun/speedrun.py show 2024-10-14          # materialize a record's code, print its path
  python3 speedrun/speedrun.py diff 2024-10-14 2024-10-17  # unified diff of two records' train_gpt.py
  python3 speedrun/speedrun.py run 2024-10-14           # run a record on all GPUs, log the result
  python3 speedrun/speedrun.py run latest               # run the current HEAD trainer
  python3 speedrun/speedrun.py run 2024-11-19 --torch 'torch==2.6.0' -- <trainer args>
  python3 speedrun/speedrun.py run 2024-10-14 --code ~/my-edit   # your edited copy, same env

Records are matched by name prefix (date is enough when unique).

Where a record's code comes from:
  * git  - the full repo tree at the commit that added the record (multi-file
           trainers, with that commit's requirements.txt). Used when available.
  * log  - older records embed their single-file trainer at the top of the run
           log; it's recovered verbatim. These run on a "legacy" env with
           current stable torch; pass --torch 'torch==2.5.1' etc. if one breaks.
  * The two llm.c baselines (2024-06-06, 2024-10-13) were never in this repo.

Paths (override with env vars; defaults suit a RunPod network volume):
  DATA_DIR  /workspace/fineweb10B   tokenized FineWeb shards (bootstrap.sh fills it)
  RUNS_DIR  /workspace/runs         one folder per run + LOG.md
  VENVS_DIR /workspace/venvs        one venv per distinct requirements set
"""
import argparse, ast, datetime, difflib, hashlib, io, os, re, shutil, subprocess, sys, tarfile
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
RECORDS = REPO / "records" / "track_1_short"
DATA_DIR = Path(os.environ.get("DATA_DIR", "/workspace/fineweb10B"))
RUNS_DIR = Path(os.environ.get("RUNS_DIR", "/workspace/runs"))
VENVS_DIR = Path(os.environ.get("VENVS_DIR", "/workspace/venvs"))
REORG_COMMIT = "074a197"  # 2025-10-15 commit that moved every older record dir
LEGACY_REQS = "numpy\ntqdm\ntorch\nhuggingface-hub\n"
SEP = re.compile(r"^={20,}\s*$")


def git(*args, text=True):
    return subprocess.run(["git", "-C", str(REPO), *args], capture_output=True, text=text, check=False)


# ---------- locating a record's code ----------

def find_record(key):
    matches = sorted(d for d in RECORDS.iterdir() if d.is_dir() and d.name.startswith(key))
    if len(matches) != 1:
        names = [m.name for m in matches][:10]
        sys.exit(f"'{key}' matched {len(matches)} records{': ' + str(names) if names else ''}")
    return matches[0]


def code_from_log(path):
    lines = path.read_text(errors="replace").splitlines(keepends=True)
    i = 0
    while i < len(lines) and (SEP.match(lines[i]) or not lines[i].strip()):
        i += 1
    start = i
    while i < len(lines) and not SEP.match(lines[i]):
        i += 1
    if i == len(lines):
        return None
    code = "".join(lines[start:i])
    try:
        ast.parse(code)
    except SyntaxError:
        return None
    return code if ("torch" in code and len(code) > 2000) else None


def git_source(rec):
    rel = str(rec.relative_to(REPO))
    for sha in git("log", "--diff-filter=A", "--format=%H", "--reverse", "--", rel).stdout.split():
        if sha.startswith(REORG_COMMIT):
            continue
        for name in ("train_gpt.py", "train_gpt2.py"):
            r = git("show", f"{sha}:{name}")
            if r.returncode == 0:
                try:
                    ast.parse(r.stdout)
                    return sha, name
                except SyntaxError:
                    pass
    return None


def log_source(rec):
    for p in sorted(p for p in rec.rglob("*") if p.is_file() and p.suffix in (".txt", ".log")):
        code = code_from_log(p)
        if code:
            return p, code
    return None


def resolve(key):
    """Return dict(name, kind, sha|log, entry)."""
    if key == "latest":
        sha = git("rev-parse", "HEAD").stdout.strip()
        return dict(name=f"latest-{sha[:7]}", kind="git", sha=sha, entry="train_gpt.py")
    rec = find_record(key)
    g = git_source(rec)
    if g:
        return dict(name=rec.name, kind="git", sha=g[0], entry=g[1])
    l = log_source(rec)
    if l:
        return dict(name=rec.name, kind="log", log=l[0], code=l[1], entry="train_gpt.py")
    sys.exit(f"{rec.name}: no recoverable trainer (the llm.c baselines live in karpathy/llm.c)")


def describe(src):
    if src["kind"] == "edit":
        return f"edited copy {src['edit']}"
    if src["kind"] == "git":
        return f"git {src['sha'][:7]}:{src['entry']}"
    return f"log {src['log'].relative_to(RECORDS)}"


def materialize(src, dest):
    """Write the record's runnable code tree into dest. Returns requirements text."""
    dest.mkdir(parents=True, exist_ok=True)
    if src["kind"] == "git":
        tar = subprocess.run(["git", "-C", str(REPO), "archive", src["sha"], "--", ".", ":(exclude)records"],
                             capture_output=True, check=True).stdout
        with tarfile.open(fileobj=io.BytesIO(tar)) as t:
            t.extractall(dest)
        req = dest / "requirements.txt"
        return req.read_text() if req.exists() else LEGACY_REQS
    (dest / "train_gpt.py").write_text(src["code"])
    return LEGACY_REQS


# ---------- environment ----------

def ensure_venv(reqs, torch_override=None):
    if torch_override:
        reqs = re.sub(r"(?m)^torch\b.*$", torch_override, reqs)
        if not re.search(r"(?m)^torch\b", reqs):
            reqs += torch_override + "\n"
    key = hashlib.sha256(reqs.encode()).hexdigest()[:12]
    venv = VENVS_DIR / key
    py = venv / "bin" / "python"
    if (venv / ".ready").exists():
        return py, key
    print(f"Building env {key} (first use of this requirements set)...", flush=True)
    shutil.rmtree(venv, ignore_errors=True)
    subprocess.run([sys.executable, "-m", "venv", str(venv)], check=True)
    pip = [str(py), "-m", "pip", "install", "-q"]
    subprocess.run(pip + ["--upgrade", "pip"], check=True)
    (venv / "requirements.txt").write_text(reqs)
    # requirements.txt may say torch must come from a specific wheel index (e.g. cu128)
    m = re.search(r"--index-url\s+(\S+)", reqs)
    torch_lines = re.findall(r"(?m)^torch\b\S*", reqs)
    if m and torch_lines:
        subprocess.run(pip + torch_lines + ["--index-url", m.group(1)], check=True)
    subprocess.run(pip + ["-r", str(venv / "requirements.txt")], check=True)
    (venv / ".ready").touch()
    return py, key


# ---------- commands ----------

def cmd_list(_):
    for d in sorted(p for p in RECORDS.iterdir() if p.is_dir()):
        g = git_source(d)
        if g:
            how = f"git {g[0][:7]}"
        elif log_source(d):
            how = "log"
        else:
            how = "n/a (llm.c)"
        print(f"{d.name:50s} {how}")


def cmd_show(a):
    src = resolve(a.record)
    dest = RUNS_DIR / "code" / src["name"]
    if not dest.exists():
        materialize(src, dest)
    print(f"{src['name']}  [{describe(src)}]\n{dest / src['entry']}")


def cmd_diff(a):
    out = []
    for key in (a.a, a.b):
        src = resolve(key)
        dest = RUNS_DIR / "code" / src["name"]
        if not dest.exists():
            materialize(src, dest)
        out.append((src["name"], (dest / src["entry"]).read_text().splitlines(keepends=True)))
    sys.stdout.writelines(difflib.unified_diff(out[0][1], out[1][1], out[0][0], out[1][0]))


def last_match(text, pattern):
    hits = re.findall(pattern, text)
    return hits[-1] if hits else "?"


def cmd_run(a):
    shards = sorted(DATA_DIR.glob("fineweb_train_*.bin"))
    if not shards or not (DATA_DIR / "fineweb_val_000000.bin").exists():
        sys.exit(f"No data in {DATA_DIR}. Run: bash speedrun/bootstrap.sh")
    ngpu = int(os.environ.get("NGPU") or subprocess.run(["nvidia-smi", "-L"], capture_output=True, text=True)
               .stdout.count("GPU "))
    gpu = subprocess.run(["nvidia-smi", "--query-gpu=name", "--format=csv,noheader"],
                         capture_output=True, text=True).stdout.splitlines()[0].strip()
    src = resolve(a.record)
    stamp = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
    label = src["name"] + ("+" + Path(a.code).name if a.code else "")
    run_dir = RUNS_DIR / f"{stamp}_{label}"
    code = run_dir / "code"
    reqs = materialize(src, code)
    if a.code:  # overlay your edited tree on the record's code, keep the record's env
        shutil.copytree(a.code, code, dirs_exist_ok=True, symlinks=True,
                        ignore=shutil.ignore_patterns("fineweb10B", "logs", "__pycache__"))
        src = dict(src, kind="edit", edit=Path(a.code).resolve())
    py, env_key = ensure_venv(reqs, a.torch)
    data_link = code / "data" / "fineweb10B"
    data_link.parent.mkdir(exist_ok=True)
    if data_link.is_symlink() or data_link.exists():
        shutil.rmtree(data_link) if data_link.is_dir() and not data_link.is_symlink() else data_link.unlink()
    data_link.symlink_to(DATA_DIR)
    torch_ver = subprocess.run([str(py), "-c", "import torch;print(torch.__version__)"],
                               capture_output=True, text=True).stdout.strip()
    print(f"\n{src['name']}  [{describe(src)}]  torch {torch_ver}  {ngpu}x {gpu}\n{run_dir}\n", flush=True)
    if ngpu != 8:
        print(f"NOTE: records are tuned for 8 GPUs; with {ngpu} some will assert or change behavior.\n", flush=True)

    cmd = [str(py), "-m", "torch.distributed.run", "--standalone", f"--nproc_per_node={ngpu}", src["entry"], *a.extra]
    env = dict(os.environ, DATA_PATH=".", PATH=f"{py.parent}:{os.environ['PATH']}")
    log_path = run_dir / "train.log"
    with open(log_path, "w") as log:
        proc = subprocess.Popen(cmd, cwd=code, env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
        for line in proc.stdout:
            sys.stdout.write(line)
            log.write(line)
        rc = proc.wait()

    text = log_path.read_text(errors="replace")
    val = last_match(text, r"val_loss[:=\s]+([0-9.]+)")
    t = last_match(text, r"train_time[:=\s]+([0-9.]+\s*m?s)")
    status = "ok" if rc == 0 else f"exit {rc}"
    row = (f"| {stamp} | {src['name']} | {describe(src)} | {ngpu}x {gpu} | torch {torch_ver} "
           f"| {val} | {t} | {status} |\n")
    ledger = RUNS_DIR / "LOG.md"
    if not ledger.exists():
        ledger.write_text("| Run | Record | Source | GPUs | Env | Final val_loss | train_time | Status |\n"
                          "|---|---|---|---|---|---|---|---|\n")
    with open(ledger, "a") as f:
        f.write(row)
    print(f"\n{status}: val_loss {val}, train_time {t}\nLogged to {ledger}")
    sys.exit(rc)


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("list").set_defaults(fn=cmd_list)
    s = sub.add_parser("show"); s.add_argument("record"); s.set_defaults(fn=cmd_show)
    d = sub.add_parser("diff"); d.add_argument("a"); d.add_argument("b"); d.set_defaults(fn=cmd_diff)
    r = sub.add_parser("run")
    r.add_argument("record")
    r.add_argument("--torch", help="replace the torch requirement, e.g. 'torch==2.5.1'")
    r.add_argument("--code", help="run your edited copy of the record's code (e.g. from `show`)")
    r.set_defaults(fn=cmd_run)
    argv, extra = sys.argv[1:], []
    if "--" in argv:  # everything after a bare -- goes to the trainer
        i = argv.index("--")
        argv, extra = argv[:i], argv[i + 1:]
    a = p.parse_args(argv)
    a.extra = extra
    a.fn(a)


if __name__ == "__main__":
    main()
