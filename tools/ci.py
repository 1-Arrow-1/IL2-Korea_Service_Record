"""
Ask GitHub about this repository's builds, without installing anything.

    python tools/ci.py runs [N]        the last N workflow runs
    python tools/ci.py run <id>        one run, job by job
    python tools/ci.py log <id>        the failing job's log (or --job <id>)
    python tools/ci.py releases [N]    releases and their assets
    python tools/ci.py tag <name>      what a tag points at, and its run

The token comes from Git Credential Manager, the same one git itself uses
to push, so there is nothing to log in to and nothing new to store. It is
never printed. If you would rather use your own, set GH_TOKEN.
"""

import json
import os
import subprocess
import sys
import urllib.error
import urllib.request

REPO = "1-Arrow-1/IL2-Korea_Service_Record"
API = "https://api.github.com"


def token() -> str:
    for name in ("GH_TOKEN", "GITHUB_TOKEN"):
        if os.environ.get(name):
            return os.environ[name]
    try:
        out = subprocess.run(["git", "credential", "fill"],
                             input="protocol=https\nhost=github.com\n\n",
                             capture_output=True, text=True, timeout=30).stdout
    except Exception as exc:                                  # noqa: BLE001
        raise SystemExit(f"cannot reach the credential helper: {exc}")
    for line in out.splitlines():
        if line.startswith("password="):
            return line.split("=", 1)[1]
    raise SystemExit("no GitHub token stored. Push once, or set GH_TOKEN.")


def get(path: str, raw: bool = False):
    req = urllib.request.Request(
        path if path.startswith("http") else f"{API}/repos/{REPO}/{path}",
        headers={"Authorization": f"Bearer {token()}",
                 "Accept": "application/vnd.github+json",
                 "User-Agent": "il2k-ci"})
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            body = r.read()
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", "replace")[:300]
        raise SystemExit(f"GitHub said {exc.code}: {detail}")
    return body if raw else json.loads(body.decode())


def runs(n=10):
    for r in get(f"actions/runs?per_page={n}")["workflow_runs"]:
        mark = {"success": "ok", "failure": "FAILED", None: "..."}.get(r["conclusion"], r["conclusion"])
        print(f"{r['id']}  {r['created_at'][:19].replace('T', ' ')}  "
              f"{str(r['head_branch'])[:16]:16s} {r['head_sha'][:7]}  {mark}")


def run(run_id):
    r = get(f"actions/runs/{run_id}")
    print(f"{r['name']}  {r['head_branch']}  {r['head_sha'][:7]}  {r['status']}/{r['conclusion']}")
    for j in get(f"actions/runs/{run_id}/jobs")["jobs"]:
        print(f"  job {j['id']}  {j['name'][:40]:40s} {j['status']}/{j['conclusion']}")
        for s in j.get("steps", []):
            if s.get("conclusion") not in ("success", "skipped", None):
                print(f"      step failed: {s['name']}")


def log(run_id, job_id=None):
    if job_id is None:
        jobs = get(f"actions/runs/{run_id}/jobs")["jobs"]
        bad = [j for j in jobs if j["conclusion"] == "failure"]
        if not bad:
            print("no failing job; pass --job <id> for a particular one")
            return run(run_id)
        job_id = bad[0]["id"]
        print(f"--- log of the failing job {job_id} ---")
    text = get(f"actions/jobs/{job_id}/logs", raw=True).decode("utf-8", "replace")
    print(text[-12000:])


def releases(n=5):
    for r in get(f"releases?per_page={n}"):
        print(f"{r['tag_name']:10s} {r['created_at'][:16].replace('T', ' ')}  "
              f"draft={r['draft']}  prerelease={r['prerelease']}")
        for a in r.get("assets", []):
            print(f"    {a['name']:46s} {a['size'] / 1e6:6.1f} MB  "
                  f"{a['download_count']:4d} downloads  {a['updated_at'][:16].replace('T', ' ')}")


def tag(name):
    ref = get(f"git/ref/tags/{name}")
    sha = ref["object"]["sha"]
    if ref["object"]["type"] == "tag":
        sha = get(f"git/tags/{sha}")["object"]["sha"]
    print(f"{name} -> {sha[:7]}")
    for r in get("actions/runs?per_page=30")["workflow_runs"]:
        if r["head_sha"] == sha and r["head_branch"] == name:
            print(f"   built by run {r['id']}  {r['status']}/{r['conclusion']}")
            break
    else:
        print("   no run for that tag yet")


def main(argv):
    if not argv or argv[0] in ("-h", "--help"):
        print(__doc__)
        return 0
    cmd, rest = argv[0], argv[1:]
    if cmd == "runs":
        runs(int(rest[0]) if rest else 10)
    elif cmd == "run":
        run(rest[0])
    elif cmd == "log":
        job = rest[rest.index("--job") + 1] if "--job" in rest else None
        log(rest[0], job)
    elif cmd == "releases":
        releases(int(rest[0]) if rest else 5)
    elif cmd == "tag":
        tag(rest[0])
    else:
        print(__doc__)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
