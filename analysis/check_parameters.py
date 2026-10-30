#!/usr/bin/env python3
"""Verification script to check consistency between simulations/omnetpp.ini,
docs/parameters.md, and the evidence-matrix characterization rules.

Detects parameter drift between configuration and documentation sheets.
Usage:
    python3 analysis/check_parameters.py
"""
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
INI_PATH = REPO_ROOT / "simulations" / "omnetpp.ini"
PARAMS_MD_PATH = REPO_ROOT / "docs" / "parameters.md"
CAPACITY_MD_PATH = REPO_ROOT / "docs" / "capacity.md"


def parse_ini_sections(ini_file):
    """Parse INI entries into {(section, key): value} with continuation-line support."""
    kv = {}
    section = "General"
    lines = ini_file.read_text(encoding="utf-8").splitlines()
    i = 0
    while i < len(lines):
        line = lines[i].split("#", 1)[0].strip()
        i += 1
        if not line:
            continue
        m = re.match(r"^\[(?:Config\s+)?(\w+)\]$", line)
        if m:
            section = m.group(1)
            continue
        while line.endswith("\\") and i < len(lines):
            line = line[:-1].rstrip() + " " + lines[i].split("#", 1)[0].strip()
            i += 1
        if "=" in line:
            k, v = line.split("=", 1)
            kv[(section, k.strip())] = v.strip()
    return kv


EVIDENCE_LABELS = ("Paper", "Derive", "Choice", "Standard", "Verify")
CLASS_ROWS = ("Orders", "State", "DDS", "Telemetry")
FIVE_PART_HEADERS = ("Role & Endpoints", "Message Schema & Size", "Generation Process",
                     "Transport, Framing & Middleware", "Application Deadline & Late Treatment")
# Per class, label(s) that must appear in the class's own table row, and facts that must stay in sync with the INI.
ROW_REQUIRED = {
    "Orders":    ("Choice", "Paper", "Verify", "600 B", "5051"),
    "State":     ("Choice", "Paper", "Verify", "1000 B", "5050"),
    "DDS":       ("Choice", "Paper", "Verify", "200 B", "5100", "88 B"),
    "Telemetry": ("Choice", "Verify", "1400 B", "5200"),
}
# Stale claims that earlier drafts contained; they must not reappear in the parameter sheet or capacity sheet.
FORBIDDEN = (
    ("56 B RTPS", "fabricated RTPS header breakdown (use Profanter 2019 88 B)"),
    ("co-located broker", "model has no broker process"),
    ("2.56", "wrong VDA path range (E = N - 1 gives 2124..11532 B)"),
    ("11.97 KB", "wrong VDA path range"),
)


def check_characterization_evidence(params_text):
    """Audit docs/parameters.md section 6.3 (5-part characterization + evidence labels) and docs/capacity.md."""
    ok = True
    m = re.search(r"### 6\.3 Evidence-Graded 5-Part Characterization.*?(?=\n---\n|\n## )", params_text, re.S)
    if not m:
        print("  [-] docs/parameters.md: section '6.3 Evidence-Graded 5-Part Characterization' not found")
        return False
    sec = m.group(0)
    header = next((l for l in sec.splitlines() if l.startswith("|") and "Role" in l), "")
    for h in FIVE_PART_HEADERS:
        if h not in header:
            print(f"  [-] 6.3 table header is missing part {h!r}")
            ok = False
    rows = {c: next((l for l in sec.splitlines() if l.startswith(f"| **{c}**")), None) for c in CLASS_ROWS}
    for cls, row in rows.items():
        if row is None:
            print(f"  [-] 6.3 has no row for class {cls!r}")
            ok = False
            continue
        for need in ROW_REQUIRED[cls]:
            if need not in row:
                print(f"  [-] 6.3 row {cls!r} lacks {need!r}")
                ok = False
        if row.count("|") < 7:
            print(f"  [-] 6.3 row {cls!r} does not have the six table cells")
            ok = False
    for label in EVIDENCE_LABELS:
        if f"**{label}**" not in sec and f"{label}" not in sec:
            print(f"  [-] evidence label {label!r} absent from 6.3")
            ok = False
    if CAPACITY_MD_PATH.exists():
        cap = CAPACITY_MD_PATH.read_text(encoding="utf-8")
        for label in EVIDENCE_LABELS:
            if label not in cap:
                print(f"  [-] evidence label {label!r} absent from docs/capacity.md (regenerate with analysis/capacity.py)")
                ok = False
        for cls in CLASS_ROWS:
            if f"**{cls}**" not in cap:
                print(f"  [-] docs/capacity.md section 5 has no {cls!r} row (regenerate with analysis/capacity.py)")
                ok = False
        for bad, why in FORBIDDEN:
            for name, txt in (("docs/capacity.md", cap), ("docs/parameters.md", params_text)):
                if bad in txt:
                    print(f"  [-] {name} still contains {bad!r}: {why}")
                    ok = False
    else:
        print("  [-] docs/capacity.md missing; run: python3 analysis/capacity.py --out docs/capacity.md")
        ok = False
    # Item 7 attribution must stay with the twin contract.
    if "Java" not in sec or "DeadlineSink" not in sec:
        print("  [-] 6.3 lacks the Item 7 attribution to the Java twin contract / DeadlineSink.cc")
        ok = False
    if ok:
        print("  [+] Verified 5-part characterization structure, evidence labels and Item 6/7 attribution")
    return ok


def check_parameters():
    print(f"[*] Checking {INI_PATH.relative_to(REPO_ROOT)} against {PARAMS_MD_PATH.relative_to(REPO_ROOT)}...")
    if not INI_PATH.exists():
        print(f"[!] Error: {INI_PATH} not found.")
        sys.exit(1)
    if not PARAMS_MD_PATH.exists():
        print(f"[!] Error: {PARAMS_MD_PATH} not found.")
        sys.exit(1)

    ini_kv = parse_ini_sections(INI_PATH)
    params_text = PARAMS_MD_PATH.read_text(encoding="utf-8")

    # (section, key, expected_ini_value, doc_regex_pattern)
    critical_checks = [
        ("General", "sim-time-limit", "60s", r"`sim-time-limit`\s*\|\s*`60`"),
        ("General", "warmup-period", "5s", r"`warmup-period`\s*\|\s*`5`"),
        ("General", "num-rngs", "3", r"`num-rngs`\s*\|\s*`3`"),
        ("Sweep", "repeat", "22", r"`repeat`\s*\|\s*`22`"),
        ("Point", "*.numAmrs", "${nAmr=10}", r"`\*\.numAmrs`\s*\|\s*`10`"),
        ("Sweep", "*.numAmrs", "${nAmr=5, 10, 20, 40, 80}", r"`5,\s*10,\s*20,\s*40,\s*80`"),
        ("Sweep", "*.wirelessPhyRate", "${phyRate=54Mbps, 12Mbps}", r"Sweep:\s*`54,\s*12`"),
        ("General", "*.amr[*].app[0].source.packetLength", "1000B", r"State.*`1000`\s*B"),
        ("General", "*.fms.app[3..].source.packetLength", "600B", r"Orders.*`600`\s*B"),
        ("General", "*.station[*].app[0].source.packetLength", "200B", r"DDS.*`200`\s*B"),
        ("General", "*.station[*].app[1].source.packetLength", "1400B", r"Telemetry.*`1400`\s*B"),
        ("Wired_FIFO", "**.tsnSwitch.eth[*].macLayer.queue.packetCapacity", "80", r"`DropTailQueue`\s*\|\s*`80`\s*packets"),
        ("Wired_Prio", "**.tsnSwitch.eth[*].macLayer.queue.queue[*].packetCapacity", "20", r"`20`\s*packets\s*/\s*class"),
        ("Wired_TAS", "**.tsnSwitch.eth[*].macLayer.queue.queue[*].packetCapacity", "20", r"`20`\s*packets\s*/\s*class"),
    ]

    all_passed = True
    for section, key, expected_ini, pattern in critical_checks:
        val = ini_kv.get((section, key))
        ini_ok = (val == expected_ini)
        doc_ok = bool(re.search(pattern, params_text))
        if ini_ok and doc_ok:
            print(f"  [+] Verified [{section}] {key} = {val}")
        else:
            print(f"  [-] Mismatch [{section}] {key}: INI={val!r} (expected {expected_ini!r}), doc_match={doc_ok}")
            all_passed = False

    if not check_characterization_evidence(params_text):
        all_passed = False

    if all_passed:
        print("[✓] Consistency check passed: all checked baseline parameters are documented in docs/parameters.md.")
    else:
        print("[!] Some parameter mismatches or missing entries detected.")
        return False
    return True


if __name__ == "__main__":
    sys.exit(0 if check_parameters() else 1)

