---
name: review-lens
description: Review a code change with the user through a local, offline HTML review page (flow map + lenses with depth levels + exact code from git). Use after implementing a non-trivial change, when the user asks to review a commit, branch or uncommitted work, and whenever the user pastes a request starting with "Review <id> ·" (a lens/level request) or "Review <id>: decisions".
---

# Review page

The review happens in a local HTML page, not in chat. The page holds the explanation; chat carries
requests, discussion and decisions. Nothing is uploaded: the page and its data stay on this machine.

## When to use it

- **Use the page** for any change with behaviour, judgement, risk, or more than ~20 changed lines.
- **Chat only** for trivial changes (a few lines, no judgement call, no ⚠ decision): give a short
  summary of what changed and how it was verified, and say the page was skipped and why.
- Unsure? Use the page.

## Where things live

- Tools: `~/.claude/skills/review-lens/scripts/` (`build.py`, `diff_source.py`, `template.html`).
- Reviews: `~/.claude/reviews/<repo-folder-name>/<id>/content.json` → `review.html` next to it.
  `<id>` is short and stable, e.g. `2026-11-10-invoice-rounding` or `a1b2c3d-invoice-rounding`.
- Never write review files into the repository. Never commit them.

## Workflow

1. **Inspect the whole task-related diff yourself first.** Separate it from unrelated working-tree
   changes. Unrelated changes go under `unrelated` with a reason; they are never reviewed or touched.
2. **Slice the change into nodes** that follow the runtime flow (see *Slicing*), and write
   `content.json` (format: `reference/content-format.md`).
3. **Build:** `python ~/.claude/skills/review-lens/scripts/build.py <content.json>`
   It must exit 0. It refuses when a changed line belongs to no node, when a step or note points at
   nothing, or when a changed file is neither reviewed nor declared unrelated. Fix the content, never
   the check.
4. **Hand over in chat, briefly:** the page path, what the change does in one or two sentences,
   any ⚠ decisions waiting, and what verification actually ran (with exact commands for what didn't).
   Don't repeat the page's explanations in chat.
5. **Respond to what comes back** (see *Requests from the page*).
6. **Before calling it commit-ready**, run `build.py <content.json> --check`. It must say
   `UP TO DATE` with no problems.

## Slicing into nodes

- A node is one step in the flow of the change: something with its own input, output and purpose.
  Order nodes in execution order (column 1). Put things that support a node from the side, such as a
  strategy list or a helper, in column 2 with `"beside"`. Tests are nodes of kind `test` with `proves`.
- Include unchanged callers or consumers as `context` nodes when they explain where the output goes
  or why the change matters. Show only the relevant line range.
- Kinds: `focused` (behaviour, judgement, risk, contract, state, failure semantics), `routine`
  (mechanical support of an understood contract), `context`, `test`. When unsure: `focused`.
- Mark a node `"decision": true` when it holds a judgement call the user must make. Explain the
  options and their consequences in its Risk lens.
- Every node has the **core strip**: `change`, `risk`, `evidence`. Keep each to one or two sentences.
  Evidence states only what was actually observed. Say plainly when tests were not run.
- **Handoff-relevant concepts:** when the change introduces or reshapes a domain concept, model,
  service or ownership boundary a colleague could ask about, explain it once where it first
  appears (intro or that node's Flow): what it is, why it exists, who uses it, its main invariant,
  and one concrete example.
- Make the overview's `example` a realistic end-to-end trace through the nodes, including a
  revealing edge case when there is one. It's the picture everything else hangs on.

## Lenses and depth levels

| Lens | L1 | L2 | L3 |
|---|---|---|---|
| Flow | Main path in tiny steps | Branches and edge cases | Exact execution order, incl. laziness |
| Risk | Main risks and decisions | Failure scenarios with concrete inputs | Evidence: what was checked, what would prove it |
| Syntax | Load-bearing constructs | Every line | What the compiler and runtime do |
| Architecture | Where it sits and why it's split this way | Responsibilities and dependencies | Alternatives and trade-offs |
| Context | Callers and consumers | Business rules behind them | History: why it used to work this way |

- **Write up front:** Flow L1 (`flow`) and Risk L1 (`risks`) for every node. Nothing else.
- **Flow steps are tiny:** one idea and a few lines each. Start with "Before:" when the old code
  matters, then "After:".
- **Higher levels add depth; they never restate a lower level.** If a node genuinely has nothing more
  at a level, write that level with a one-line `text` saying so instead of inventing depth.
- **Syntax and other line-level explanations are `notes`**: each note is attached to an exact line
  range and shown just above those lines. Never insert teaching comments into code; the code panel
  always shows git's exact text.
- Don't re-teach a construct already explained in another node of the same review; write "see ②"
  with a one-clause reminder.
- Verify version-sensitive or runtime claims (library docs, source) before writing them, and state
  what you checked, e.g. which package version's docs.

## Requests from the page

The page copies requests to the clipboard; the user pastes them into chat.

**`Review <id> · <node> · Lens: <lens> · Level <n> (...)`**, optionally with `Focus:` (a specific
note and line range), `Scope:` (only these lines, from a right-clicked line, step or code
selection), `Selected code:` and `What's unclear:`:
1. Open that review's `content.json`, add `nodes[i].lenses.<lens>.<n>`, aimed at the focus and
   the unclear part when given.
   - **With `Scope:`** answer only for those lines, as `notes` attached to them (a note's range must
     overlap the scope, or the page won't find it). If that level didn't exist yet, create it with
     `"partial": true` and `"scope": "<the scope text>"`. If it already was partial, add the notes
     and extend `scope`. If it was complete, just add the notes. When `Selected code:` names an
     expression, explain that expression, not the whole line.
   - **Without `Scope:`** write the level for the whole node and remove `partial`/`scope`.
2. Rebuild (must exit 0).
3. Reply in **one line**: what was added, and "refresh the page (F5)". Don't put the explanation
   in chat.

**`Review <id>: decisions (diff <fingerprint>)`** followed by one line per node:
- Run `--check` first. If the fingerprint is stale, say so before anything else.
- `accepted`, `deferred`, `skipped`: acknowledge briefly. Deferred and skipped are resolved with
  exceptions, never "examined and accepted".
- `question`: answer in chat if it's a discussion; record the outcome in the page (Risk item, core
  strip, or a note) and rebuild.
- `change requested`: follow the normal correction flow (diagnose → smallest safe change →
  verify). Then update the affected nodes' content, **increment `rev`** on every node whose code,
  contract or explanation changed (this reopens its decision in the page), rebuild, and run `--check`.
- `reopened`: the user's decision predates a code change; it needs a fresh decision.

Chat is for discussion and decisions. Explanations, answers that matter later, and changed
conclusions belong in the page.

## Commit-readiness

Report these separately: implementation complete · page built and `--check` up to date · automated
verification run (or exactly what wasn't and why) · every node decided (accepted, deferred or
skipped, none reopened) · remaining risks and unrelated changes. Only when all hold is the change
commit-ready. Suggest a commit message then. Never commit, push or open a PR unless asked.

Never imply the user read code they didn't open. The page shows what was explained; decisions show
what was accepted.

## Known limits

- The page can't reach Claude: requests and decisions travel by copy-paste, answers by rebuild + F5.
  If clipboard access is blocked on `file://`, the page shows the text to copy by hand.
- Decisions and progress are stored in the browser's localStorage for that page; clearing site data
  loses them. The `--check` and the pasted decisions are the durable record.
- Renamed files appear as their new path only. Binary files are listed as changed but not shown.
