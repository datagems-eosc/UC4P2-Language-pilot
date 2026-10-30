# Pilot 2 benchmark: v1 vs v2

Files in this folder:

| File | Role |
|------|------|
| `pilot2_benchmark_english.v1.json` | Flat list (legacy layout) |
| `pilot2_benchmark_english.v2.json` | Nested parents + subquestions (**canonical** for the pilot) |

Both files need occasional missing commas between objects; the pilot loader inserts them (`load_benchmark`).

---

## Counts

| | **v1** | **v2** |
|---|---|---|
| Main (parent) questions | **8** | **8** |
| Subquestions | **28** | **28** |
| Total question rows | 36 (flat) | 8 + 28 nested (= 36) |
| Approximate size | ~127 KB | ~133 KB |

Parent `Question_ID`s (identical sets):

`0`, `4`, `9`, `15`, `19`, `23`, `27`, `31`

Concepts (identical): Dresden, Galileo, Marriage, Philosophy, Socialism, Odin, Love, multiple.

---

## Structure

**v1 — flat**

- Every question is a top-level array element with `Question_ID`.
- Parents point at children via `Subquestion_IDs: [...]`.
- Children are separate rows with `source_metadata`.

**v2 — nested**

- Only parents are top-level.
- Children live in `Subquestions[]` with `Subquestion_ID`.
- Children add `Simplified_Question` (all 28).

| | v1 parent | v1 child | v2 parent | v2 child |
|---|---|---|---|---|
| `Question_ID` / `Subquestion_ID` | ✓ | ✓ | ✓ | ✓ (`Subquestion_ID`) |
| `Question`, `Concept`, `Ground_Truth` | ✓ | ✓ | ✓ | ✓ |
| `Subquestion_IDs` | ✓ | | | |
| `Subquestions` | | | ✓ | |
| `source_metadata` | | ✓ | | ✓ |
| `Simplified_Question` | | | | ✓ |

---

## Content delta (aside from nesting)

Parent rows (`0`…`31` parents): **same** question text, concept, `Ground_Truth`, and child-id lists.

Child-level differences:

| ID | Parent | Change |
|----|--------|--------|
| `1` | Dresden (`0`) | Question: “How is Dresden **defined**?” → “How is Dresden **described**?” |
| `20` | Socialism (`19`) | `Ground_Truth` typo: `socialism` → `socialsim` |
| all 28 children | — | v2 adds `Simplified_Question` |

No parents or child IDs were added or removed between v1 and v2.

---

## How the pilot uses them

- Demo drawer / few-shots / local NLG: **`pilot2_benchmark_english.v2.json` only**.
- Remote IDD `/nlgEvaluate` gold (parents only): `in-dataset-discovery` `data/nlg/pilot2_nlg_gold.v2.json` — not a full copy of this benchmark.
