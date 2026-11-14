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
NED_PATH = REPO_ROOT / "simulations" / "MatrixFactoryNetwork.ned"
PARAMS_MD_PATH = REPO_ROOT / "docs" / "parameters.md"
CAPACITY_MD_PATH = REPO_ROOT / "docs" / "capacity.md"

WHITELIST_STAT_KEYS = (
    "**.app[*].source.packets.statistic-recording",
    "**.app[*].source.generationEvents.statistic-recording",
    "**.tsnSwitch.eth[*].macLayer.queue.transmissionGate[*].gateState.statistic-recording",
    "**.wlan[*].mac.dcf.packetSentToPeer.statistic-recording",
    "**.wlan[*].mac.dcf.packetSentToPeerWithRetry.statistic-recording",
    "**.wlan[*].mac.dcf.recoveryProcedure.retryLimitReached.statistic-recording",
    "**.wlan[*].mac.dcf.frameSequenceDuration.statistic-recording",
)


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


def _parse_ini_ordered(ini_file: Path) -> dict[str, list[tuple[str, str]]]:
    """Parse INI entries into {section: [(key, value), ...]} preserving order and continuations."""
    sections: dict[str, list[tuple[str, str]]] = {"General": []}
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
            sections.setdefault(section, [])
            continue
        while line.endswith("\\") and i < len(lines):
            line = line[:-1].rstrip() + " " + lines[i].split("#", 1)[0].strip()
            i += 1
        if "=" in line:
            k, v = line.split("=", 1)
            sections.setdefault(section, []).append((k.strip(), v.strip()))
    return sections


def check_statistic_whitelist_order(ini_file: Path = INI_PATH) -> bool:
    """Verify that all 7 whitelisted @statistic keys appear set to true BEFORE **.statistic-recording = false in [General]."""
    general_keys = _parse_ini_ordered(ini_file).get("General", [])
    idx_map = {k: idx for idx, (k, _v) in enumerate(general_keys)}
    val_map = {k: v for k, v in general_keys}
    if "**.statistic-recording" not in idx_map or val_map.get("**.statistic-recording") != "false":
        print("  [-] [General] missing **.statistic-recording = false")
        return False
    stop_idx = idx_map["**.statistic-recording"]
    ok = True
    for wk in WHITELIST_STAT_KEYS:
        if wk not in idx_map or val_map.get(wk) != "true":
            print(f"  [-] [General] missing whitelisted statistic key {wk} = true")
            ok = False
        elif idx_map[wk] >= stop_idx:
            print(f"  [-] [General] whitelisted key {wk} appears AFTER **.statistic-recording = false (first-match-wins would disable it)")
            ok = False
    if ok:
        print(f"  [+] Verified 7-key @statistic whitelist precedes **.statistic-recording = false in [General]")
    return ok


def check_no_production_recording_overrides(ini_file: Path = INI_PATH) -> bool:
    """Verify no production section or duplicate/wildcard [General] rule re-enables statistics, vectors, bins, or pcap."""
    sections = _parse_ini_ordered(ini_file)
    ok = True
    recording_suffixes = (
        "statistic-recording",
        "vector-recording",
        "bin-recording",
        "scalar-recording",
        "result-recording-modes",
    )

    general_entries = sections.get("General", [])
    seen_general_rec: set[str] = set()
    allowed_general_rec = set(WHITELIST_STAT_KEYS) | {
        "**.statistic-recording",
        "**.bin-recording",
        "**.vector-recording",
        "**.scalar-recording",
    }
    for key, val in general_entries:
        is_rec = key.endswith(recording_suffixes) or key.endswith("recordPcap") or key == "record-eventlog"
        if not is_rec:
            continue
        if key in seen_general_rec:
            print(f"  [-] [General] duplicate recording directive: {key} = {val}")
            ok = False
        seen_general_rec.add(key)
        if key not in allowed_general_rec:
            print(f"  [-] [General] unexpected recording directive {key} = {val} outside frozen 7-key whitelist")
            ok = False
    general_map = dict(general_entries)
    if general_map.get("**.vector-recording") != "false":
        print(f"  [-] [General] **.vector-recording must be false, got {general_map.get('**.vector-recording')!r}")
        ok = False
    if general_map.get("**.bin-recording") != "false":
        print(f"  [-] [General] **.bin-recording must be false, got {general_map.get('**.bin-recording')!r}")
        ok = False
    if general_map.get("**.scalar-recording") != "true":
        print(f"  [-] [General] **.scalar-recording must be true, got {general_map.get('**.scalar-recording')!r}")
        ok = False

    for sec_name, entries in sections.items():
        if sec_name in ("General", "Debug"):
            continue
        for key, val in entries:
            if key.endswith(recording_suffixes) or key.endswith("recordPcap") or key == "record-eventlog":
                print(f"  [-] [Config {sec_name}] forbidden recording override in non-Debug section: {key} = {val}")
                ok = False
            if key == "extends":
                bases = [b.strip() for b in val.split(",") if b.strip()]
                if "Debug" in bases:
                    print(f"  [-] [Config {sec_name}] extends Debug in production/sweep hierarchy: extends = {val}")
                    ok = False

    if ok:
        print("  [+] Verified no non-Debug section or duplicate/wildcard [General] entry overrides recording controls")
    return ok


def _parse_rate_bps(rate_str: str) -> float:
    m = re.match(r"^([0-9]+(?:\.[0-9]+)?)\s*(Gbps|Mbps|kbps|bps)$", rate_str.strip())
    if not m:
        raise ValueError(f"Unsupported bitrate literal: {rate_str!r}")
    val = float(m.group(1))
    unit = m.group(2)
    scale = {"bps": 1.0, "kbps": 1e3, "Mbps": 1e6, "Gbps": 1e9}[unit]
    return val * scale


def _parse_duration_sec(dur_str: str) -> float:
    m = re.match(r"^([0-9]+(?:\.[0-9]+)?)\s*(ns|us|ms|s)$", dur_str.strip())
    if not m:
        raise ValueError(f"Unsupported duration literal: {dur_str!r}")
    val = float(m.group(1))
    unit = m.group(2)
    scale = {"ns": 1e-9, "us": 1e-6, "ms": 1e-3, "s": 1.0}[unit]
    return val * scale


def check_wired_link_ifg_consistency(ini_kv: dict, ned_file: Path = NED_PATH) -> bool:
    """Verify that MatrixFactoryNetwork.ned wired bitrate, connections, and INI interFrameGapInserter.duration all match 96b / bitrate."""
    if not ned_file.exists():
        print(f"  [-] NED file not found: {ned_file}")
        return False
    ned_text = ned_file.read_text(encoding="utf-8")
    # Remove single-line comments
    clean_lines = [line.split("//", 1)[0].strip() for line in ned_text.splitlines()]
    clean_ned = "\n".join(clean_lines)

    m_rate = re.search(r"\*\.eth\[\*\]\.bitrate\s*=\s*default\(([^)]+)\)", clean_ned)
    if not m_rate:
        print("  [-] MatrixFactoryNetwork.ned missing *.eth[*].bitrate = default(...)")
        return False
    ned_bitrate_bps = _parse_rate_bps(m_rate.group(1))

    # Inspect every bidirectional connection in connections:
    conn_matches = list(re.finditer(r"([^\s;]+)\s*<-->\s*([^\s;{]+)\s*(\{[^}]*\})?\s*<-->\s*([^\s;]+)\s*;", clean_ned))
    if len(conn_matches) < 3:
        print(f"  [-] MatrixFactoryNetwork.ned: expected >= 3 wired connections, found {len(conn_matches)}")
        return False
    for cm in conn_matches:
        chan_type = cm.group(2)
        chan_body = cm.group(3) or ""
        if chan_type != "EthernetLink":
            print(f"  [-] Non-EthernetLink wired channel {chan_type!r} in MatrixFactoryNetwork.ned")
            return False
        if "datarate" in chan_body or "bitrate" in chan_body:
            print(f"  [-] Connection-specific bitrate/datarate override in MatrixFactoryNetwork.ned: {cm.group(0)!r}")
            return False

    # Ensure no INI section overrides eth bitrate or channel datarate
    for (sec, key), val in ini_kv.items():
        if ("eth" in key and "bitrate" in key) or ("datarate" in key):
            if _parse_rate_bps(val) != ned_bitrate_bps:
                print(f"  [-] INI [{sec}] {key} = {val} overrides NED wired bitrate {m_rate.group(1)}")
                return False

    ifg_str = ini_kv.get(("General", "**.eth[*].phyLayer.interFrameGapInserter.duration"))
    if not ifg_str:
        print("  [-] [General] missing **.eth[*].phyLayer.interFrameGapInserter.duration")
        return False
    ifg_sec = _parse_duration_sec(ifg_str)
    expected_ifg_sec = 96.0 / ned_bitrate_bps
    if abs(ifg_sec - expected_ifg_sec) > 1e-15:
        print(
            f"  [-] IFG duration mismatch: INI has {ifg_str} ({ifg_sec:.9e} s), "
            f"but 96 bits / {m_rate.group(1)} = {expected_ifg_sec:.9e} s"
        )
        return False

    print(
        f"  [+] Verified wired IFG consistency: {len(conn_matches)} NED EthernetLink connections at "
        f"{m_rate.group(1)} match 96b / {m_rate.group(1)} = {ifg_str}"
    )
    return True


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
        ("General", "**.app[*].source.packetNameFormat", '"pkt"', r"`\*\*\.app\[\*\]\.source\.packetNameFormat`\s*\|\s*`\"pkt\"`"),
        ("General", "**.statistic-recording", "false", r"`\*\*\.statistic-recording`\s*\|\s*`false`"),
        ("General", "**.bin-recording", "false", r"`\*\*\.bin-recording`\s*\|\s*`false`"),
        ("General", "**.vector-recording", "false", r"`\*\*\.vector-recording`\s*\|\s*`false`"),
        ("General", "**.scalar-recording", "true", r"`\*\*\.scalar-recording`\s*\|\s*`true`"),
        ("General", "**.eth[*].phyLayer.interFrameGapInserter.duration", "0.96us", r"`\*\*\.eth\[\*\]\.phyLayer\.interFrameGapInserter\.duration`\s*\|\s*`0\.96us`"),
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

    if not check_statistic_whitelist_order(INI_PATH):
        all_passed = False
    if not check_no_production_recording_overrides(INI_PATH):
        all_passed = False
    if not check_wired_link_ifg_consistency(ini_kv, NED_PATH):
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

