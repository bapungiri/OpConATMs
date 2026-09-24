#!/usr/bin/env python
"""Deploy every rig in one pass, with a look before and a check after.

RemoteJobSubmission.py reads 'userInfo.in' from the current directory, so a
deploy has always meant cd-ing into each rig folder and running it by hand.
This drives that same script, unmodified, once per rig -- it only adds the
two things that are hard to do by hand across thirteen boxes: seeing the
state of all of them before committing, and confirming afterwards that every
one actually came back up.

Three phases:

  preflight  Read-only. For each rig: is it reachable, is ATM running and for
             which animal, does that match userInfo.in, and is there disk
             left. Nothing is touched.
  deploy     Sequential, one rig at a time, streaming output. Each rig gets
             RemoteJobSubmission.py run with cwd set to its folder, exactly
             as if you had cd-ed there, with 'y' fed to the overwrite prompt.
  verify     Re-check every rig: ATM running again, and started just now
             rather than left over from before.

Run it from the 'atm' conda environment, which is the one with paramiko:

    conda run -n atm python deploy_all.py --dry-run
    conda run -n atm python deploy_all.py
    conda run -n atm python deploy_all.py --rigs 10.36.22.12 10.36.22.13

Deploy before the animals start at 19:00, and not around 13:00, which is
when the logs rotate and the NAS transfer runs. Mid-afternoon leaves room to
react if a rig fails verification.
"""

import argparse
import re
import subprocess
import sys
import threading
import time
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent
LOG_DIR = ROOT / "deploy_logs"
SUBMIT = "RemoteJobSubmission.py"

# A retired rig folder keeps the IP of the box it used to be, so it now points
# at whatever replaced it. 10.36.22.11_old_Pi3 still says RPi_IP=10.36.22.11,
# which is the Pi5 running BGF11 -- deploying it would push the old Pi3 code
# and BGF4's config onto a live rig. Skipped unless asked for explicitly.
RETIRED = re.compile(r"_(old|retired|backup)", re.IGNORECASE)

# Bracketed so the pattern cannot match the shell running it: 'pgrep -f
# MainCode' finds its own command line, and reports a pid that has already
# exited by the time anything else looks at it -- which reads as "running"
# on a rig where nothing is.
PROC_PATTERN = r"[M]ainCode\.py"
# Started within this many seconds of the deploy counts as "came back up".
FRESH_SECONDS = 1800
# Refuse to deploy onto a card this full: the pre-upload backup needs room.
DISK_FULL_PCT = 90


def read_config(path):
    """Parse a 'key = value' userInfo.in into a dict."""
    cfg = {}
    for line in path.read_text(errors="replace").splitlines():
        line = line.split("#")[0]
        if "=" in line:
            k, v = line.split("=", 1)
            cfg[k.strip()] = v.strip()
    return cfg


def discover(selected=None, include_retired=False):
    """Find the rig folders to act on, refusing anything ambiguous."""
    rigs = []
    for cfg_path in sorted(ROOT.glob("10.36.22.*/AutoTrainerModular/userInfo.in")):
        folder = cfg_path.parent.parent
        if RETIRED.search(folder.name) and not include_retired:
            continue
        cfg = read_config(cfg_path)
        rigs.append(
            {
                "dir": cfg_path.parent,
                "name": folder.name,
                "ip": cfg.get("RPi_IP", ""),
                "user": cfg.get("RPi_ID", "pi"),
                "password": cfg.get("RPi_Pass", ""),
                "subject": cfg.get("Subject_Name", ""),
            }
        )

    if selected:
        want = set(selected)
        rigs = [r for r in rigs if r["name"] in want or r["ip"] in want]
        missing = want - {r["name"] for r in rigs} - {r["ip"] for r in rigs}
        if missing:
            sys.exit(f"No such rig: {', '.join(sorted(missing))}")

    # Two folders pointing at one box means one of them is stale, and there is
    # no safe way to guess which.
    seen = {}
    for r in rigs:
        seen.setdefault(r["ip"], []).append(r["name"])
    clashes = {ip: names for ip, names in seen.items() if len(names) > 1}
    if clashes:
        for ip, names in clashes.items():
            print(f"  {ip} is claimed by: {', '.join(names)}")
        sys.exit("Refusing to run: more than one folder targets the same rig.")

    return rigs


# ------------------------------------------------------------- preflight


def _ssh(rig, timeout=10):
    import paramiko

    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    client.connect(
        rig["ip"],
        username=rig["user"],
        password=rig["password"],
        timeout=timeout,
        banner_timeout=timeout,
        auth_timeout=timeout,
        look_for_keys=False,
        allow_agent=False,
    )
    return client


def _run(client, cmd):
    _, stdout, _ = client.exec_command(cmd, timeout=15)
    return stdout.read().decode(errors="replace").strip()


def inspect(rig):
    """Look at one rig without changing anything."""
    state = {"reachable": False, "running": False, "remote_subject": "",
             "elapsed": None, "disk": "", "disk_pct": None, "error": ""}
    try:
        client = _ssh(rig)
    except Exception as e:
        state["error"] = f"{type(e).__name__}: {e}"
        return state

    try:
        state["reachable"] = True
        pid = _run(client, f'pgrep -f "{PROC_PATTERN}" | head -1')
        if pid:
            state["running"] = True
            elapsed = _run(client, f"ps -o etimes= -p {pid}")
            state["elapsed"] = int(elapsed) if elapsed.isdigit() else None
            # The running job's own config says which animal it belongs to,
            # which is the one that matters -- userInfo.in on disk may already
            # have been edited for the next animal.
            info = _run(
                client,
                f"cat $(readlink -f /proc/{pid}/cwd)/userInfo.in 2>/dev/null"
                " | grep -m1 '^Subject_Name'",
            )
            if "=" in info:
                state["remote_subject"] = info.split("=", 1)[1].strip()
        state["disk"] = _run(client, "df -h /home/pi | awk 'NR==2{print $4\" free (\"$5\" used)\"}'")
        pct = _run(client, "df /home/pi | awk 'NR==2{gsub(\"%\",\"\",$5); print $5}'")
        state["disk_pct"] = int(pct) if pct.isdigit() else None
    except Exception as e:
        state["error"] = f"{type(e).__name__}: {e}"
    finally:
        client.close()
    return state


def preflight(rigs):
    """Report the state of every rig. Returns (states, blocking_problems)."""
    print(f"\nPREFLIGHT  {datetime.now():%Y-%m-%d %H:%M:%S}\n")
    print(f"  {'rig':<15}{'animal':<9}{'ATM':<9}{'running for':<13}{'disk':<26}note")
    print("  " + "-" * 86)

    states, blocking = {}, []
    for rig in rigs:
        st = inspect(rig)
        states[rig["name"]] = st

        notes = []
        if not st["reachable"]:
            notes.append(f"UNREACHABLE -- {st['error'][:40]}")
            blocking.append(f"{rig['name']} unreachable")
        elif st["error"]:
            notes.append(f"error: {st['error'][:40]}")
        if st["running"] and st["remote_subject"] and st["remote_subject"] != rig["subject"]:
            # Expected right after swapping animals; worth seeing, not fatal.
            notes.append(f"WARN running={st['remote_subject']} local={rig['subject']}")
        if st["reachable"] and not st["running"]:
            # Not an error -- there is simply no job to overwrite -- but if you
            # did not stop it yourself, something took it down.
            notes.append("ATM not running")
        if st["disk_pct"] is not None and st["disk_pct"] >= DISK_FULL_PCT:
            # The deploy backs up the remote directory before uploading, so a
            # nearly full card fails midway and leaves the rig half updated.
            notes.append("DISK %d%% FULL" % st["disk_pct"])
            blocking.append("%s disk %d%% full" % (rig["name"], st["disk_pct"]))

        uptime = ""
        if st["elapsed"] is not None:
            h, m = divmod(st["elapsed"] // 60, 60)
            uptime = f"{h}h{m:02d}m"

        print(
            f"  {rig['name']:<15}{rig['subject']:<9}"
            f"{('running' if st['running'] else '-'):<9}{uptime:<13}"
            f"{st['disk'][:25]:<26}{'; '.join(notes)}"
        )

    return states, blocking


# ---------------------------------------------------------------- deploy


def deploy_one(rig, timeout, echo=True):
    """Run RemoteJobSubmission.py for one rig, as if cd-ed into its folder."""
    LOG_DIR.mkdir(exist_ok=True)
    log_path = LOG_DIR / f"{rig['name']}.log"
    lines = []

    proc = subprocess.Popen(
        [sys.executable, SUBMIT],
        cwd=str(rig["dir"]),
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1,
    )

    def pump():
        for line in proc.stdout:
            lines.append(line)
            if echo:
                print(f"    | {line.rstrip()}")

    reader = threading.Thread(target=pump, daemon=True)
    reader.start()
    try:
        # The only prompt on this path is "overwrite the current job?", and an
        # empty answer means no. Answer it once, then close stdin; a second
        # prompt would be an anomaly and should surface rather than be fed.
        proc.stdin.write("y\n")
        proc.stdin.flush()
        proc.stdin.close()
    except Exception:
        pass

    try:
        proc.wait(timeout=timeout)
    except subprocess.TimeoutExpired:
        proc.kill()
        lines.append(f"\n*** killed after {timeout}s ***\n")
    reader.join(timeout=10)

    with open(log_path, "w") as f:
        f.write(f"# {rig['name']} ({rig['subject']}) {datetime.now():%Y-%m-%d %H:%M:%S}\n")
        f.writelines(lines)

    return proc.returncode, log_path


# ---------------------------------------------------------------- verify


def verify(rigs, started_at):
    """Confirm every rig is running ATM again, started by this deploy."""
    print(f"\nVERIFY  {datetime.now():%Y-%m-%d %H:%M:%S}\n")
    print(f"  {'rig':<15}{'animal':<9}{'ATM':<11}{'started':<14}verdict")
    print("  " + "-" * 66)

    failed = []
    for rig in rigs:
        st = inspect(rig)
        if not st["reachable"]:
            verdict, started = "FAIL unreachable", ""
        elif not st["running"]:
            verdict, started = "FAIL not running", ""
        else:
            age = st["elapsed"]
            started = f"{age // 60}m ago" if age is not None else "?"
            if age is None:
                verdict = "OK (age unknown)"
            elif age <= max(FRESH_SECONDS, int(time.time() - started_at) + 300):
                verdict = "OK"
            else:
                # Still the old process: the deploy did not restart this one.
                verdict = "FAIL stale process"
        if verdict.startswith("FAIL"):
            failed.append(rig["name"])
        print(
            f"  {rig['name']:<15}{rig['subject']:<9}"
            f"{('running' if st['running'] else '-'):<11}{started:<14}{verdict}"
        )
    return failed


# ------------------------------------------------------------------- cli


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--rigs", nargs="+", help="folder names or IPs; default all")
    ap.add_argument("--dry-run", action="store_true", help="preflight only")
    ap.add_argument("--yes", action="store_true", help="skip the confirmation")
    ap.add_argument("--force", action="store_true", help="deploy despite preflight problems")
    ap.add_argument("--include-retired", action="store_true")
    ap.add_argument("--timeout", type=int, default=900, help="per-rig seconds")
    ap.add_argument("--stop-on-error", action="store_true")
    args = ap.parse_args()

    try:
        import paramiko  # noqa: F401
    except ImportError:
        sys.exit("paramiko is missing -- run this from the 'atm' environment:\n"
                 "    conda run -n atm python deploy_all.py ...")

    rigs = discover(args.rigs, args.include_retired)
    if not rigs:
        sys.exit("No rigs found.")

    states, blocking = preflight(rigs)

    if args.dry_run:
        return 0

    if blocking and not args.force:
        # One sick rig should not silently hold up the other eleven, but it
        # should not be skipped without you deciding to skip it either.
        print(f"\nStopping: {'; '.join(blocking)}.")
        bad = {b.split()[0] for b in blocking}
        healthy = [r["name"] for r in rigs if r["name"] not in bad]
        if healthy:
            print("Fix those, or deploy just the healthy rigs with:")
            print("    python deploy_all.py --rigs " + " ".join(healthy))
        print("--force deploys everything regardless.")
        return 1

    live = [r["subject"] for r in rigs if states[r["name"]]["running"]]
    print(f"\nAbout to deploy to {len(rigs)} rig(s), overwriting the running job on "
          f"{len(live)}: {', '.join(live) if live else 'none'}")
    if not args.yes and input("Proceed? [n]|y: ").strip().lower() not in ("y", "yes"):
        print("Aborted.")
        return 1

    started_at = time.time()
    results = {}
    for i, rig in enumerate(rigs, 1):
        print(f"\n[{i}/{len(rigs)}] {rig['name']}  ({rig['subject']})")
        rc, log_path = deploy_one(rig, args.timeout)
        results[rig["name"]] = rc
        print(f"    -> exit {rc}, log: {log_path.relative_to(ROOT)}")
        if rc != 0 and args.stop_on_error:
            print("Stopping on error.")
            break

    failed = verify(rigs, started_at)

    bad_rc = [n for n, rc in results.items() if rc != 0]
    print(f"\nDeployed {len(results)}/{len(rigs)}.  "
          f"Non-zero exit: {', '.join(bad_rc) if bad_rc else 'none'}.  "
          f"Failed verification: {', '.join(failed) if failed else 'none'}.")
    return 1 if (bad_rc or failed) else 0


if __name__ == "__main__":
    raise SystemExit(main())
