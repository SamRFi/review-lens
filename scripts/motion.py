"""The "Data in motion" tab: a steppable illustration of data moving through the change.

The author describes each step as a few actions on named tokens; the page works out where
everything sits. This module checks that description before the page is built, and attaches
the exact code lines every step cites (read from git or disk, never retyped).
"""
from diff_source import file_version

VERBS = ("show", "move", "drop", "group", "pick", "merge", "set", "order", "hide")
SHAPES = ("row", "record", "box", "event", "message")
LANES = ("after", "before")


def _examples(motion):
    return [e["id"] for e in motion.get("examples") or []] or ["main"]


def _versions(content, files):
    cache = {}

    def lines(file_key, side):
        if (file_key, side) not in cache:
            cache[(file_key, side)] = file_version(content["repo"], content["source"], files[file_key]["path"], side)
        return cache[(file_key, side)]
    return lines


def _ids(action, verb):
    return list(action["set"].keys()) if verb == "set" else ([action[verb]] if isinstance(action[verb], str) else list(action[verb]))


def validate(content, files):
    """Every problem that would make the illustration point at nothing or quietly skip something."""
    motion = content.get("motion")
    if not motion:
        return []
    problems, where = [], "motion"
    examples = _examples(motion)
    columns = [c["id"] for c in motion.get("columns", [])]
    entities = [e["id"] for e in motion.get("entities", [])]
    tokens = motion.get("tokens", {})
    nodes = {n["id"] for n in content["nodes"]}
    lines = _versions(content, files)

    for name, ids in (("column", columns), ("entity", entities), ("example", examples)):
        dupes = {i for i in ids if ids.count(i) > 1}
        if dupes:
            problems.append(f"{where}: duplicate {name} id(s) {sorted(dupes)}")
    for e in motion.get("entities", []):
        if e.get("shape", "row") not in SHAPES:
            problems.append(f"{where}: entity {e['id']} has shape {e.get('shape')!r}; use one of {SHAPES}")
    for tid, t in tokens.items():
        if t.get("entity") not in entities:
            problems.append(f"{where}: token {tid} has unknown entity {t.get('entity')!r}")
        for ex in t.get("examples", []):
            if ex not in examples:
                problems.append(f"{where}: token {tid} names unknown example {ex!r}")
    steps = motion.get("steps", [])
    if not steps:
        problems.append(f"{where}: no steps")
    with_before = [i for i, s in enumerate(steps) if s.get("before")]
    if with_before and len(with_before) != len(steps):
        missing = [i + 1 for i, s in enumerate(steps) if not s.get("before")]
        problems.append(f"{where}: steps {missing} have no 'before' while others do; give every step one (use 'none' when the old code has nothing here)")

    for i, step in enumerate(steps, start=1):
        if not step.get("after"):
            problems.append(f"{where} step {i}: missing 'after'")
        for lane in LANES:
            body = step.get(lane)
            if not body:
                continue
            at = f"{where} step {i} {lane}"
            if not body.get("title"):
                problems.append(f"{at}: missing title")
            if body.get("node") and body["node"] not in nodes:
                problems.append(f"{at}: node {body['node']!r} doesn't exist")
            if not body.get("refs") and not body.get("none"):
                problems.append(f"{at}: cite the lines it shows ('refs'), or say why there are none ('none')")
            for ref in body.get("refs", []):
                side = "o" if "o" in ref else "n"
                if ref.get("f") not in files:
                    problems.append(f"{at}: ref to unknown file key {ref.get('f')!r}"); continue
                body_lines = lines(ref["f"], "old" if side == "o" else "new")
                a, b = ref.get(side, [0, 0])
                if body_lines is None:
                    problems.append(f"{at}: {files[ref['f']]['path']} has no {'old' if side == 'o' else 'new'} version to cite")
                elif not (1 <= a <= b <= len(body_lines)):
                    problems.append(f"{at}: {files[ref['f']]['path']} {side}{a}-{b} is outside the file ({len(body_lines)} lines)")
            for col in (body.get("notes") or {}):
                if col not in columns:
                    problems.append(f"{at}: note for unknown column {col!r}")
            for action in body.get("do", []):
                verbs = [v for v in VERBS if v in action]
                if len(verbs) != 1:
                    problems.append(f"{at}: action {action} needs exactly one of {VERBS}"); continue
                verb = verbs[0]
                for tid in _ids(action, verb):
                    if tid not in tokens:
                        problems.append(f"{at}: {verb} names unknown token {tid!r}")
                for key in ("at", "to"):
                    if key in action and action[key] not in columns:
                        problems.append(f"{at}: {verb} {key} unknown column {action[key]!r}")
                if verb == "show" and "at" not in action:
                    problems.append(f"{at}: show needs 'at' (a column)")
                if verb == "move" and "to" not in action:
                    problems.append(f"{at}: move needs 'to' (a column)")
                if verb == "merge" and action.get("into") not in tokens:
                    problems.append(f"{at}: merge needs 'into' (a token)")
                if "from" in action and action["from"] not in tokens and action["from"] not in columns:
                    problems.append(f"{at}: show from unknown token or column {action['from']!r}")

    if not problems:
        problems += _replay(motion, examples)
    return problems


def _replay(motion, examples):
    """Plays every lane for every example and reports tokens used before they appear or after they leave."""
    problems = []
    tokens = motion["tokens"]
    for lane in LANES:
        for ex in examples:
            exists = lambda t: not tokens[t].get("examples") or ex in tokens[t]["examples"]
            present, leaving = set(), set()
            for i, step in enumerate(motion["steps"], start=1):
                present -= leaving
                leaving = set()
                for action in (step.get(lane) or {}).get("do", []):
                    verb = next(v for v in VERBS if v in action)
                    for tid in filter(exists, _ids(action, verb)):
                        if verb == "show":
                            if tid in present:
                                problems.append(f"motion step {i} {lane} ({ex}): {tid} is shown while already there")
                            present.add(tid)
                        elif tid not in present:
                            problems.append(f"motion step {i} {lane} ({ex}): {verb} {tid} before it is shown, or after it left")
                        elif verb in ("merge", "hide"):
                            leaving.add(tid)
                    if verb == "merge" and exists(action["into"]) and action["into"] not in present:
                        problems.append(f"motion step {i} {lane} ({ex}): merge into {action['into']}, which isn't there")
    return sorted(set(problems))


def resolve(content, files):
    """The motion data for the page, with every cited line range replaced by its exact text."""
    motion = content.get("motion")
    if not motion:
        return None
    lines = _versions(content, files)
    steps = []
    for step in motion["steps"]:
        out = {}
        for lane in LANES:
            body = step.get(lane)
            if not body:
                continue
            refs = []
            for ref in body.get("refs", []):
                side = "o" if "o" in ref else "n"
                a, b = ref[side]
                refs.append({"file": files[ref["f"]]["path"].split("/")[-1], "path": files[ref["f"]]["path"],
                             "side": "old" if side == "o" else "new", "a": a, "b": b,
                             "lines": lines(ref["f"], "old" if side == "o" else "new")[a - 1:b]})
            out[lane] = {**body, "refs": refs}
        steps.append(out)
    return {**motion, "examples": motion.get("examples") or [{"id": "main", "label": ""}], "steps": steps}
