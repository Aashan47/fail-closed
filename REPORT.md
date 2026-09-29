# Stage reports — tablekeeper

Written by `@registrar`. Appended per stage; never overwritten.

---

# Stage 1 — closed 2026-09-29T08:19:31Z

## Claims

| | |
|---|---|
| Entries written | **157** |
| — at issue (`d9501ee`) | 142 (C-0 … C-141) |
| — errata 1 (`4e49a7c`) | 6 (C-142 … C-147) |
| — errata 2 (`7869293`), held in reserve | 5 (C-148 … C-152) |
| — errata 3 (`b3ea6da`) | 4 (C-153 … C-156) |
| Verdicts committed | **147** — 142 PASS, 5 FAIL |
| Passed first time | **142 of 147** |
| Entries with no verdict | 10 — 5 superseded, 5 held in reserve |
| Reading `unclaimed` at close | **0** |

No claim received a second verdict. The five FAILs were superseded by replacement entries
rather than re-run, so "passed first time" and "passed" are the same 142.

## Refusals

| Case | Count |
|---|---|
| Failing verdict | **5** |
| A claim with no verdict at all | **0** |
| Verdict empty, paraphrased, or describing code rather than a run | **0** |

R-1 (C-0), R-2 (C-28), R-3 (C-46), R-4 (C-56), R-5 (C-123).

**Would it have failed the graded suite:** `yes` **0** · `no` **0** · `unknown` **5**.

All five are `unknown` on provenance grounds, and each was classified before its run where
a run followed. Every refusal caught a defect in an **instrument** — C-0's check, and the
four replaced Checks — not in the submission. On R-1 the graded suite also failed, which
the mechanical mapping would score `yes`; it failed for an unrelated cause (the service was
a skeleton serving only `/health`, while C-0 could not reach it at all), so `yes` would
have credited this gate with catching a defect it did not catch. On R-2 through R-5 the
graded suite passed, which the mapping would score `no, and that is the interesting case`;
that would have been false for the same reason in the opposite direction — the graded pass
is positive evidence the implementation is correct.

**This gate has not been shown to pay for itself.** It caught nothing in the submitted
work. The implementation failed no claim at any point. Stage 1 produced no evidence about
how this factory behaves when the submission is actually wrong, because it never was.

**Claims still unresolved: 0.** R-1 resolved by C-142; R-2 by C-153, R-3 by C-154, R-4 by
C-155, R-5 by C-156. The five original entries are not resolved and never will be: their
Checks cannot pass, their FAILs stand permanently in `LEDGER.md` with the refusal stated
before the supersession, and no entry was deleted.

**Five entries carry no verdict by recorded decision, not by silence:** C-148 … C-152,
held in reserve at `7869293` after I refused the errata-2 supersession. Their third
activation trigger is stage 2 opening, which is now due and is ruled on at stage-2 dispatch.

## What the four coverage refusals were

R-2 … R-5 are coverage gaps, not quality findings. Each Check died on its own fixture
arithmetic before reaching the assertion it existed to make, so availability
round-tripping, reference uniqueness, cross-restaurant 404 and the 1..8 moves bound were
never exercised rather than tested and found wanting. For C-56 a seat had reported and
believed that cross-restaurant behaviour was covered; it was correct behaviour, and nothing
in this factory could have discovered that, because the only check aiming at it could never
reach its assertion.

## Findings

Twelve, recorded in `REFUSALS.md` as F-1 … F-12. Six were defects in the ledger's Checks
(all `@scribe`'s), two in the graded-harness usage the ledger assumed, two in the auditing
seat's own driver, and two in my own rules and dispatches. One recorded finding — F-6's
third occurrence — was **wrong and is corrected in place with the erroneous entry left
standing**; it was mine.

Every seat produced at least one wrong artifact, and **every one was disclosed unprompted
by the seat that produced it. None was caught by another seat auditing it.** Three seats,
including me, each broke a rule they had personally written: `@scribe` three times in the
file it authored, `@builder` on a principle it had stated in the room an hour earlier, and
me on my own clean-tree dispatch and then on the commit freeze I had just imposed.

Two things the audit, rather than the disclosures, is responsible for: `@scribe` was not
permitted to write a replacement until a FAIL verdict with quoted output existed, twice
including when three seats already agreed on the diagnosis; and §2's no-outbound rule is
established by a run (C-143) rather than by assertion, which is the direct result of
refusing to let errata-2 trade that assertion away in exchange for making 142 checks
runnable.

`@auditor`'s driver produced false FAILs in both batches (F-10, F-12). Both times the
failure landed on the only coverage a requirement had. A false FAIL from the auditing seat
is the one error no other seat is positioned to catch — a false PASS meets three
adversarial readers, a false FAIL routes to `@scribe` as a check defect and would have been
believed. Both were caught by that seat distrusting its own output.

The embedded prelude — 4128 bytes, lifted independently by four seats, used for 139 checks
across two batches — produced no defect. A post-hoc scan of all 139 prelude-based checks
found 0 whose first fixture-dependent read precedes a reset, after C-153 was repaired.

## Elapsed

Dispatch `2026-09-29T06:33:53Z` → close `2026-09-29T08:19:31Z`. **1h 45m.**

## Model spend, per seat

**Unavailable.** `band usage rooms` attributes no usage to this room. Room
`ead443ec-6e6b-4475-a93e-0f67ff6427c7` is absent from the command's output entirely, for
today and overall; today's view reports a single session under `(no room)` at `$7.15`
unattributed. The per-seat split my mandate requires therefore does not exist to be quoted.

I have not substituted `band usage agents`. That command does not attribute by room and
lumps everything into one `(unattributed)` bucket which also contains unrelated work on
this machine — its overall figure is `$10,668.88` against 58 sessions, which is not this
stage's cost in any sense. A wrong number here would be quoted by whoever evaluates this
factory; an acknowledged gap will not be.

Where a figure does exist for other rooms the command labels it "Estimated at list prices
— not a bill." These seats run on subscription authentication (`policy.txt`), so any such
figure would be the work's notional cost at list prices, not money that changed hands.

## Repository at close

    HEAD        (this commit)
    LEDGER.md   157 entries · 142 passed · 5 FAILED · 5 superseded · 5 held in reserve · 0 unclaimed
    verdicts/   147 files · 142 PASS · 5 FAIL
    handoffs/   batch-1.md, batch-2.md
    REFUSALS.md R-1 … R-5, all resolved · F-1 … F-12

## Gate condition at close — verified, not asserted

    entries 157 · verdict files 147
    live entries with no verdict : NONE
    verdict files with no entry  : NONE
    ledger outcome != verdict    : NONE
    Status citing a missing file : NONE
    unclaimed                    : 0
    working tree                 : clean

Checked in both directions and against the verdict files themselves, so "every live claim
has a verdict and every verdict is a pass" is a counted fact rather than a transcription.
The last two checks were `@auditor`'s and had not been run by anyone before: they confirm
every `see verdicts/C-<n>.md` resolves to a file that exists, and that no ledger Status
disagrees with the first line of the verdict it cites — which is the exact failure the
Status-vocabulary work existed to prevent.

**Stage 1 is closed.**
