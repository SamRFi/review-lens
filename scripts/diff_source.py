"""Reads the code a review page shows, straight from git or disk, never retyped.

A review source is one of:
  {"type": "worktree", "base": "HEAD"}      uncommitted changes (staged, unstaged, untracked) vs base
  {"type": "commit", "commit": "<sha>"}     one commit
  {"type": "range", "base": "<a>", "head": "<b>"}
"""
import pathlib
import re
import subprocess

HUNK = re.compile(r"^@@ -(\d+)(?:,\d+)? \+(\d+)(?:,\d+)? @@(.*)")


class GitError(RuntimeError):
    pass


def git(repo, *args):
    result = subprocess.run(["git", "-C", repo, *args], capture_output=True,
                            text=True, encoding="utf-8", errors="replace")
    if result.returncode != 0:
        raise GitError(f"git {' '.join(args)} failed in {repo}:\n{result.stderr.strip()}")
    return result.stdout


def parse_unified(text):
    """Turns unified diff text into display lines with old (o) and new (n) line numbers."""
    lines, old, new, started = [], 0, 0, False
    for raw in text.splitlines():
        match = HUNK.match(raw)
        if match:
            old, new, started = int(match.group(1)), int(match.group(2)), True
            lines.append({"t": "hunk", "s": raw})
            continue
        if raw.startswith("Binary files"):
            lines.append({"t": "hunk", "s": "Binary file changed; content not shown."})
            continue
        if not started or raw.startswith("\\"):
            continue
        kind, body = raw[:1], raw[1:]
        if kind == "+":
            lines.append({"t": "add", "n": new, "s": body}); new += 1
        elif kind == "-":
            lines.append({"t": "del", "o": old, "s": body}); old += 1
        else:
            lines.append({"t": "ctx", "o": old, "n": new, "s": body}); old += 1; new += 1
    return lines


def is_untracked(repo, path):
    return bool(git(repo, "ls-files", "--others", "--exclude-standard", "--", path).strip())


def read_disk(repo, path):
    return (pathlib.Path(repo) / path).read_text(encoding="utf-8", errors="replace").splitlines()


def diff_lines(repo, source, path, context=6):
    kind = source["type"]
    if kind == "commit":
        return parse_unified(git(repo, "show", "--format=", f"-U{context}", source["commit"], "--", path))
    if kind == "range":
        return parse_unified(git(repo, "diff", f"-U{context}", source["base"], source["head"], "--", path))
    if kind == "worktree":
        if is_untracked(repo, path):
            # git diff ignores untracked files, so a new file is shown as all-added
            body = read_disk(repo, path)
            return [{"t": "hunk", "s": f"@@ new untracked file, {len(body)} lines @@"}] + \
                   [{"t": "add", "n": i, "s": s} for i, s in enumerate(body, start=1)]
        return parse_unified(git(repo, "diff", f"-U{context}", source.get("base", "HEAD"), "--", path))
    raise ValueError(f"Unknown review source type: {kind!r}")


def context_lines(repo, source, path, first, last):
    """Unchanged code shown for orientation, as it is in the reviewed version."""
    kind = source["type"]
    if kind == "commit":
        body = git(repo, "show", f"{source['commit']}:{path}").splitlines()
    elif kind == "range":
        body = git(repo, "show", f"{source['head']}:{path}").splitlines()
    else:
        body = read_disk(repo, path)
    last = min(last, len(body))
    return [{"t": "ctx", "n": i, "s": body[i - 1]} for i in range(first, last + 1)]


def changed_files(repo, source):
    """Every file the source changes, so a review can't silently leave one out."""
    kind = source["type"]
    if kind == "commit":
        out = git(repo, "show", "--name-only", "--format=", source["commit"])
    elif kind == "range":
        out = git(repo, "diff", "--name-only", source["base"], source["head"])
    else:
        out = git(repo, "diff", "--name-only", source.get("base", "HEAD")) + \
              git(repo, "ls-files", "--others", "--exclude-standard")
    return sorted({line.strip() for line in out.splitlines() if line.strip()})


def describe(source):
    kind = source["type"]
    if kind == "commit":
        return f"commit {source['commit'][:7]}"
    if kind == "range":
        return f"{source['base'][:7]}..{source['head'][:7]}"
    return f"uncommitted changes vs {source.get('base', 'HEAD')}"
