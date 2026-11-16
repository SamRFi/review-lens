# content.json format

One file per review, UTF-8. Text fields may contain simple inline HTML (`<b>`, `<i>`, `<code>`).
Escape `<` as `&lt;` when you mean a literal angle bracket (e.g. `Func&lt;T&gt;`).

```jsonc
{
  "id": "2026-11-10-invoice-rounding",         // stable; also the browser storage key
  "title": "Invoice rounding review",      // 2–4 words
  "subject": "Round invoice totals per line instead of per invoice",
  "repo": "C:/Users/me/code/some-repo",     // absolute; forward slashes are fine
  "source": { "type": "worktree", "base": "HEAD" },
  //        { "type": "commit", "commit": "<sha>" }
  //        { "type": "range", "base": "<sha|ref>", "head": "<sha|ref>" }
  "context_lines": 6,                       // optional, default 6

  "files": {                                 // short keys used by every range below
    "A": { "path": "src/Service.cs" },                                   // reviewed diff
    "X": { "path": "src/Caller.cs", "kind": "context", "range": [94, 124] }  // unchanged code
  },
  "unrelated": [                             // changed files that are not part of this review
    { "pattern": "tmp/*", "reason": "pre-existing scratch output" }       // fnmatch; * crosses folders
  ],

  "intro": {                                 // the overview panel; every field optional
    "before": "…", "after": "…",
    "exampleTitle": "One page, step by step", "example": ["…", "…"],
    "verification": "What actually ran, or that nothing ran and why.",
    "commands": ["dotnet test … --filter …"]
  },

  "nodes": [
    {
      "id": "n5", "num": "⑤", "label": "The rounding rule", "sub": "LineRounding",
      "kind": "focused",                     // focused | routine | context | test
      "decision": true,                      // optional: holds a judgement call for the user
      "rev": 1,                              // optional, default 1; increment when its code or meaning changes
      "column": 2, "beside": "n4",           // optional layout hints (tests default to column 2 beside proves[-1])
      "proves": ["n5"],                      // tests only
      "cover": [ { "f": "A", "n": [11, 13] }, { "f": "A", "o": [108, 119] } ],
      "core": { "change": "…", "risk": "…", "evidence": "…" },
      "flow": [ { "f": "A", "o": [108, 113], "t": "<b>Before:</b> …" }, { "f": "A", "n": [99, 101], "t": "<b>After:</b> …" } ],
      "risks": [ { "lvl": "warn", "h": "Decision: …", "t": "…" } ],   // lvl: warn | info | assume | ok
      "lenses": {                            // written on request
        "syntax": {
          "1": { "intro": "…", "notes": [ { "f": "A", "n": [161, 161], "h": "Signature", "t": "…" } ] }
        },
        "flow": {
          "2": { "intro": "…", "steps": [ { "f": "A", "n": [25, 33], "t": "…" } ] }
        },
        "architecture": { "1": { "text": "…" } }
      }
    }
  ],
  "edges": [ ["n1", "n2", ""], ["n3", "n5", "per page"] ]   // optional; default chains column 1 in order
}
```

## Line ranges

- `"n": [a, b]`: lines in the **new** version (added or unchanged lines), inclusive.
- `"o": [a, b]`: **removed** lines, by their old line numbers.
- Untracked new files: every line is added, numbered from 1.
- Every added or removed line must be inside some node's `cover`; blank separator lines too.

## Lens level bodies

A level body may combine: `intro` (one or two sentences), `steps` (stepper, highlights lines),
`notes` (callouts above exact lines, each with "deeper here"), `items` (risk-style cards), `text`
(free HTML). Flow L1 and Risk L1 come from the node's `flow` and `risks`; don't repeat them under
`lenses`.

A level written only for some lines (a scoped request) also has `"partial": true` and
`"scope": "invoice.py lines 9–10"` (human-readable). The page shows it as ◐ and offers to ask for
the whole node. Its answers must be `notes` whose ranges overlap the requested lines, so the page
can find them when the same lines are right-clicked again.

## Data in motion (optional)

Add `motion` for a change where data visibly moves or changes shape (syncs, imports, mappings,
messages). The page gets a second tab: tokens move through columns, one step at a time, with
the exact lines of each step under it. Leave it out for control-flow changes and refactors.

```jsonc
"motion": {
  "examples": [ { "id": "normal", "label": "Normal invoice" },        // optional; scenarios to switch between
                { "id": "empty", "label": "+ an empty line" } ],
  "entities": [                                                      // ≤ 5; colour follows this order
    { "id": "line", "name": "Line", "shape": "row" },                // row | record | box | event | message
    { "id": "total", "name": "Total", "shape": "record" }
  ],
  "columns": [                                                       // left to right, in runtime order
    { "id": "lines", "after": "Invoice lines" },
    { "id": "round", "after": "② line_amount", "before": "line_amount" },  // "before" defaults to "after"
    { "id": "store", "after": "③ totals table", "before": null,            // null: not in the old code
      "missing": "no totals table", "width": 1.3 }                         // width: relative, default 1
  ],
  "legend": "Dashed border: …",                                       // optional extra legend text
  "tokens": {
    "l1": { "entity": "line", "l1": "3 × 0.335", "l2": "line 1" },     // two short lines of text
    "l3": { "entity": "line", "l1": "0 × 9.99", "l2": "line 3", "examples": ["empty"], "dashed": true }
  },
  "steps": [
    {
      "after": {
        "title": "Each line is rounded to cents", "node": "n2",
        "text": "Every line is rounded half up …",                    // or { "*": "…", "empty": "…" }
        "refs": [ { "f": "I", "n": [9, 10] } ],                       // the exact lines this step shows
        "notes": { "round": "rounded per line" },                      // small text under a column heading
        "do": [ { "move": ["l1", "l2"], "to": "round" },
                { "set": { "l1": { "l2": "1.005 → 1.01", "flash": true } } } ]
      },
      "before": {                                                      // optional; then every step has one
        "title": "Each line keeps every decimal",
        "refs": [ { "f": "I", "o": [6, 7] } ],                         // "o": the old version's line numbers
        "do": [ { "move": ["l1", "l2"], "to": "round" } ]
      }
    }
  ]
}
```

**Actions** (each step's `do`, replayed in order from step 1; the page works out the positions):

| Action | Meaning |
|---|---|
| `{"show": ids, "at": col, "from": token-or-col}` | appears in a column; `from` makes it slide out of a token or column |
| `{"move": ids, "to": col}` | moves to a column |
| `{"drop": ids, "to": col, "reason": "…"}` | left behind: goes to the strip under that column, with the reason |
| `{"group": ids, "label": "…"}` | a dashed frame around them, until they move |
| `{"pick": ids}` | yellow ring: what this step decides |
| `{"merge": ids, "into": token}` | flows into another token and disappears |
| `{"set": {id: {"l1": "…", "l2": "…", "flash": true}}}` | changes a token's text; `flash` draws attention |
| `{"order": ids}` | reorders tokens within their column |
| `{"hide": ids}` | fades out |

Rules the build enforces: every step cites lines (`refs`) or says why it has none (`none`); cited
lines exist in that version of the file; tokens, columns, examples and nodes exist; a token is
shown before it is used and not used after it left; when one step has `before`, all do.
Tokens that a step doesn't touch are dimmed, so what moves stands out. Any text value (`text`,
`notes`, `reason`, `l1`, `l2`) can be a string or `{ "*": default, "<example>": … }`.
