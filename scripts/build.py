"""Builds a self-contained, offline review page from a content.json.

    python build.py <path/to/content.json>           build review.html next to it
    python build.py <path/to/content.json> --check   build nothing; report whether the page is stale

Refuses (exit 1) when the review would silently miss something:
  - a changed line that no node explains (coverage)
  - a step or note that points at lines that don't exist (dangling)
  - a changed file that is neither reviewed nor listed as unrelated (undeclared)
  - a "Data in motion" step that cites lines that don't exist, or moves a token that isn't there
--check also reports STALE when the code changed after the page was built.
"""
import argparse
import datetime
import fnmatch
import hashlib
import json
import pathlib
import re
import sys

import motion
from diff_source import changed_files, context_lines, describe, diff_lines

SCRIPTS = pathlib.Path(__file__).parent
NODE_W, NODE_H, ROW, COLUMN_X, TOP = 152, 54, 74, (22, 196), 12

DEFAULT_LENSES = [
    {"id": "flow", "name": "Flow", "levels": ["The main path in tiny steps", "Branches and edge cases", "Exact execution order, including laziness"]},
    {"id": "risk", "name": "Risk", "levels": ["Main risks and decisions", "Failure scenarios with concrete inputs", "Evidence: what was checked and what would prove it"]},
    {"id": "syntax", "name": "Syntax", "levels": ["Load-bearing constructs", "Every line", "What the compiler and runtime do"]},
    {"id": "architecture", "name": "Architecture", "levels": ["Where it sits and why it's split this way", "Responsibilities and dependencies", "Alternatives and trade-offs"]},
    {"id": "context", "name": "Context", "levels": ["Callers and consumers", "Business rules behind them", "History: why it used to work this way"]},
]


def in_range(r, v):
    return r is not None and r[0] <= v <= r[1]


def load_files(content):
    repo, source = content["repo"], content["source"]
    files = {}
    for key, spec in content["files"].items():
        if spec.get("kind", "diff") == "diff":
            lines = diff_lines(repo, source, spec["path"], content.get("context_lines", 6))
        else:
            lines = context_lines(repo, source, spec["path"], *spec["range"])
        files[key] = {"path": spec["path"], "kind": spec.get("kind", "diff"), "lines": lines}
    return files


def fingerprint(source, files):
    reviewed = {k: f["lines"] for k, f in files.items() if f["kind"] == "diff"}
    raw = json.dumps({"source": source, "files": reviewed}, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def coverage_report(nodes, files):
    report = []
    for key, f in files.items():
        if f["kind"] != "diff":
            continue
        changed = [l for l in f["lines"] if l["t"] in ("add", "del")]
        uncovered = []
        for l in changed:
            side, num = ("n", l["n"]) if l["t"] == "add" else ("o", l["o"])
            if not any(c["f"] == key and in_range(c.get(side), num) for nd in nodes for c in nd["cover"]):
                uncovered.append(f"{side}{num}")
        report.append({
            "f": key, "path": f["path"], "changed": len(changed), "uncovered": uncovered,
            "binary": any(l["t"] == "hunk" and l["s"].startswith("Binary") for l in f["lines"]),
            "nodes": sorted({nd["num"] for nd in nodes for c in nd["cover"] if c["f"] == key}),
        })
    return report


def dangling_references(nodes, files):
    def hits(spec):
        if spec["f"] not in files:
            return False
        side = "o" if "o" in spec else "n"
        return any(l["t"] != "hunk" and l.get(side) is not None and in_range(spec[side], l[side])
                   and (side == "n" or l["t"] == "del") for l in files[spec["f"]]["lines"])

    found = []
    for nd in nodes:
        for spec in nd["cover"]:
            if not hits(spec): found.append(f'{nd["num"]} cover {spec}')
        for step in nd.get("flow", []):
            if not hits(step): found.append(f'{nd["num"]} flow step {step}')
        for lens_id, levels in nd.get("lenses", {}).items():
            for level, body in levels.items():
                for spec in body.get("steps", []) + body.get("notes", []):
                    if not hits(spec): found.append(f'{nd["num"]} {lens_id} L{level} {spec.get("h", spec)}')
    return found


def undeclared_changes(content):
    reviewed = {f["path"] for f in content["files"].values() if f.get("kind", "diff") == "diff"}
    patterns = [u["pattern"] for u in content.get("unrelated", [])]
    return [p for p in changed_files(content["repo"], content["source"])
            if p not in reviewed and not any(fnmatch.fnmatch(p, pat) for pat in patterns)]


def layout(nodes):
    """Column 1 holds the main flow in order; tests and side nodes sit beside what they relate to."""
    by_id = {n["id"]: n for n in nodes}
    side = lambda n: n.get("column") == 2 or (n.get("kind") == "test" and n.get("column") != 1)
    for i, n in enumerate([n for n in nodes if not side(n)]):
        n.setdefault("pos", [COLUMN_X[0], TOP + i * ROW])
    last_y = None
    for n in [n for n in nodes if side(n)]:
        if "pos" in n:
            last_y = n["pos"][1]; continue
        anchor = n.get("beside") or (n.get("proves") or [None])[-1]
        wanted = by_id[anchor]["pos"][1] if anchor in by_id else (TOP if last_y is None else last_y + ROW)
        y = wanted if last_y is None else max(wanted, last_y + ROW)
        n["pos"] = [COLUMN_X[1], y]
        last_y = y
    return max(n["pos"][1] for n in nodes) + NODE_H + TOP


def default_edges(nodes):
    main = [n["id"] for n in nodes if n["pos"][0] == COLUMN_X[0]]
    return [[a, b, ""] for a, b in zip(main, main[1:])]


def build(content_path, check):
    content_path = pathlib.Path(content_path).resolve()
    content = json.loads(content_path.read_text(encoding="utf-8"))
    out_path = content_path.with_name("review.html")
    files = load_files(content)
    nodes = content["nodes"]
    fp = fingerprint(content["source"], files)

    problems = []
    coverage = coverage_report(nodes, files)
    for c in coverage:
        if c["uncovered"]:
            problems.append(f'UNCOVERED {c["path"]}: {", ".join(c["uncovered"])}')
    problems += [f"POINTS AT NOTHING: {d}" for d in dangling_references(nodes, files)]
    undeclared = undeclared_changes(content)
    problems += [f"UNDECLARED CHANGE (review it or list it under 'unrelated'): {p}" for p in undeclared]
    problems += [f"MOTION: {m}" for m in motion.validate(content, files)]

    if check:
        built = re.search(r'"fingerprint": "([0-9a-f]+)"', out_path.read_text(encoding="utf-8")) if out_path.exists() else None
        if not built:
            problems.append("NOT BUILT: no review.html yet")
        elif built.group(1) != fp:
            problems.append("STALE: the code changed after the page was built. Update the affected nodes, bump their 'rev', rebuild.")
        else:
            print("UP TO DATE: the page matches the current code.")
    elif problems:
        print(f"NOT WRITTEN: {out_path.name} keeps its previous version until the problems below are fixed.")
    else:
        map_height = layout(nodes)
        data = {
            "meta": {
                "title": content["title"], "subject": content.get("subject", content["title"]),
                "source": describe(content["source"]), "id": content["id"],
                "storageKey": f'review-{content["id"]}', "fingerprint": fp,
                "built": datetime.datetime.now().strftime("%Y-%m-%d %H:%M"), "mapHeight": map_height,
            },
            "intro": content.get("intro", {}), "files": files, "nodes": nodes,
            "edges": content.get("edges") or default_edges(nodes),
            "lenses": content.get("lenses", DEFAULT_LENSES), "coverage": coverage,
            "unrelated": content.get("unrelated", []),
            "motion": motion.resolve(content, files),
        }
        template = (SCRIPTS / "template.html").read_text(encoding="utf-8")
        payload = json.dumps(data, ensure_ascii=False).replace("</", "<\\/")
        out_path.write_text(template.replace("__TITLE__", content["title"]).replace("__DATA__", payload), encoding="utf-8")
        print(f"written: {out_path}")

    for c in coverage:
        state = "binary, not shown" if c["binary"] else ("OK" if not c["uncovered"] else "UNCOVERED")
        print(f'  {c["changed"]:5} changed lines  {state:10} {c["path"]}')
    for p in problems:
        print(p)
    return 1 if problems else 0


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description="Build or check a local code review page.")
    parser.add_argument("content")
    parser.add_argument("--check", action="store_true", help="report staleness and gaps without writing")
    args = parser.parse_args()
    sys.exit(build(args.content, args.check))
