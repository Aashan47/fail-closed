# Refusal ledger — stage 1

Owner: `@registrar`. This file is written as refusals happen, never reconstructed
afterwards. Entries are never deleted. A refusal that was later fixed is the most
informative record in this file, and an empty ledger is not a clean bill of health —
it is a sign nobody was looking.

Three situations are refusals and are treated identically:

1. A failing verdict.
2. A claim with no verdict at all.
3. A verdict whose output is empty, paraphrased, or describes code rather than a run.

The `Would it have failed the graded suite` line is copied from the `Graded suite at
this revision` line that `@auditor` records on every FAIL. It is never guessed, and
never recorded as `yes` merely because a graded run happened to fail for some other
reason at the same revision.

---

### R-1: C-0
Case: failing verdict
Revision: 90028fd5652ffca45e8b2fa395323484a89e9602
Verdict: `verdicts/C-0.md`, committed at 93baa8656af1310f3d4655920d5f67e5ed71007a

Citation corrected. This entry first cited `d30eebe`, which was `@auditor`'s first
verdict commit and rested on two runs that overlapped `@builder`'s `docker rm -f tk-s1`.
`@auditor` caught the stale citation and re-pointed it. Only `93baa86` carries the clean
third run and the liveness evidence that answers the contamination objection:

    $ docker ps -a --filter name=tk-s1 --format '{{.Names}}  {{.Status}}'
    tk-s1  Up About a minute

taken the instant the Check returned, so no run of `@auditor`'s was killed by anyone.
Three runs, exit 1 each time, 59/59/60 connection failures. Not flaky. The superseded
citation is recorded here rather than silently swapped, because a reader should be able
to see that the objection was raised and where it was answered.

Evidence, quoted from the verdict:

    Exit: 1

    curl: (7) Failed to connect to 127.0.0.1 port 18080 after 0 ms: Couldn't connect to server
    NOT HEALTHY WITHIN 60s
    EXIT=1

The image built cold — all seven steps after `docker builder prune -af` with
`--no-cache` — and the container started. The connection failure line was printed
59 times, once per second. Run twice from a full prune each time, identical output
both times. Not flaky.

Would it have failed the graded suite: **unknown — and this is a provenance case, not
a defect case.** The raw fact is that the graded suite also failed at this revision:

    Graded evidence: `26 failed, 1 passed, 93 errors in 1.39s`
    "revision": "90028fd...", "collected": 120, "passed": 1, "failed": 26, "errors": 93
    "mode": "host"

Recording that as `yes` would be wrong, and would credit this gate with catching a
defect it did not catch. The two failures have different causes, and `@auditor`
recorded both as output rather than inference:

- C-0 failed because nothing could reach the service at 127.0.0.1:18080 at all.
- The graded suite reached the service and failed on missing API surface —
  dominated by `POST /_test/reset -> 404 not_found`. It did not fail to connect.
  It ran in `"mode": "host"`, which publishes a port; C-0's Check uses a network
  created `--internal`, which does not.

So the graded run would not have caught what C-0's refusal caught, and C-0's refusal
did not catch a defect in the submitted work. It caught a defective check. The
service at this revision is a skeleton serving only `/health`, which is why the
graded suite fails, and that is a separate and expected fact about an early revision.

Why the check is defective, from the graded harness's own source rather than from any
seat's opinion — `harness/docker_driver.py`, module docstring:

    Two modes, because "no outbound network at run time" and "reachable from the host"
    cannot both hold on one Docker network:

and `harness/docker_driver.py:74`:

    Verified behaviour: container-to-container works, outbound is refused, and a
    published port does NOT reach it -- which is why `host` mode exists separately.

C-0's Check requires both conditions simultaneously. No `Dockerfile` can satisfy it.
The same construction is used by Conventions §1 (base URL pinned to
`http://127.0.0.1:18080`), Conventions §3 (container started on an `--internal`
network) and the embedded prelude (`B="http://127.0.0.1:18080"`), so it reaches all
142 checks, not only C-0.

Resolved: no. `@scribe` has issued C-142 as C-0's replacement at `4e49a7c`, but a
replacement entry is not a resolution — C-142 has no verdict yet. This entry is resolved
only when a PASS on C-142 is committed, and it will name that verdict when it happens.
C-0 is not edited and its FAIL stands against this revision permanently.

---

## Open findings not yet attached to a refusal

Recorded here when found, so they are not lost if the seat that found them is
restarted. None of these is a verdict and none has been refused yet.

**F-1 — the graded-suite claims run in the mode the harness says never to score from.**
`harness/cli.py:306` is `args.mode = args.mode or dd.HOST`. C-140 and C-141 name the
harness command with no `--mode` flag, so both run in host mode. The harness docstring
says of that mode: "Outbound is NOT blocked -- a service that fetches a CDN at run time
will pass here and fail grading, so never score a submission from this mode." Grading
uses `isolated`. `harness/cli.py:336` sets `args.build` from the stage folder before the
isolated-mode guard at `cli.py:360`, so `--repo --stage 1 --mode isolated` is a valid
invocation; the ledger simply does not ask for it. Confirmed independently by `@builder`.

**F-2 — C-2, the only no-egress assertion in the ledger, can pass vacuously.**
Its Check is a chain of four fallbacks ending in `test $? -ne 0 && echo "NO EGRESS"`.
The chain takes the exit status of whichever command ran last, and a missing command
exits 127. Verified by inspection:

    $ sh -c 'nonexistent_a || nonexistent_b || nonexistent_c || nonexistent_d'
    all-absent exit=127
    -> C-2 would print NO EGRESS

On an image carrying none of `getent`, `nslookup`, `wget` or `curl`, C-2 prints
`NO EGRESS` with egress wide open, and an implementation could satisfy it by shipping
fewer tools. Reported by `@builder`, which found three of the four absent from
`python:3.12-slim`. Taken with F-1, nothing in this pipeline currently proves the §2
no-egress requirement that grading enforces.

**F-3 — fixed Docker names make concurrent seats collide.**
C-0's Check, Conventions §3 and Conventions §4 all use the literal names `tk-s1` and
`tk-s1-noout`, and C-0's Check opens with `docker rm -f tk-s1`. Docker is shared state
across seats even though the git trees are not. `@builder` disclosed killing a running
`tk-s1` that was not its own during `@auditor`'s run, and the verdict above was re-run
clean afterwards. Either seat can destroy the other's run.

Gate position on the replacement set, stated before it is written: a replacement that
reaches the service on a publishable network and drops the no-egress assertion will be
refused. Reaching the service and proving it cannot reach out are both required.


---

## Supersession authorised — 2026-09-29, at ledger revision 4e49a7c

`@scribe` issued an errata section and replacement entries C-142 to C-147 at
`4e49a7c13ee82aaa3c85a4f52a3816ae466be870`, and correctly left the `Status` change to me.
I authorise the following six entries to move to `superseded`:

| Original | Replaced by | Defect in the check, reproduced in the errata |
|---|---|---|
| C-0 | C-142 | a published port cannot reach an `--internal` network; also conflated two claims |
| C-2 | C-143 | same, plus the `\|\|` chain passes vacuously when probe tools are absent |
| C-3 | C-144 | started the container on a network that cannot publish |
| C-4 | C-145 | same |
| C-140 | C-147 | ran in host mode, where outbound is not blocked |
| C-141 | C-146 | same |

**What supersession does and does not mean.** A superseded entry does not need a pass and
does not hold the gate shut. It is not absolution. C-0's FAIL stands, R-1 above is never
deleted, and the replacement must earn its own verdict. I am authorising this only because
the errata reproduces a defect in each **check** from a run — not because the work was
inconvenient to fix. If a future request to supersede an entry rests on the work being hard
rather than the check being wrong, it will be refused.

The three findings recorded above are addressed by these entries, subject to verdicts:

- **F-1** — addressed by C-146 and C-147, which pass `--mode isolated`, the grading mode.
- **F-2** — addressed by C-143, which probes from a sibling `alpine:3` container whose tools
  are guaranteed present, and which must print the service's own `/health` body to pass.
  A positive assertion alongside the negative ones is what stops it passing by absence.
- **F-3** — addressed by Conventions §8, an atomic `mkdir /tmp/tk-docker.lock` mutex, plus
  per-claim container and network names. Verdicts should record which seat held the lock.

None of these is settled. Each is a claim awaiting a verdict like any other.

**F-4 — two seats have now interfered with a running audit.** `@builder` disclosed killing
a `tk-s1` that was not its own during `@auditor`'s C-0 run. `@scribe` then disclosed that it
too created and removed containers named `tk-s1` and networks `tk-s1-net` and `tk-noout`
while `@auditor` was running. Both disclosed unprompted and neither was asked to. The first
verdict was re-run clean and the refusal does not rest on a contaminated run. Recorded
because the near-miss is the finding: without those disclosures, R-1 would have cited
`d30eebe` and a reader would have had no way to know its provenance was in question.
Conventions §8 exists to stop this recurring and is itself unverified.


**F-5 — the checks read a mutable working tree, so a clean tree is part of every
verdict's provenance.** Found by `@auditor` at `655aef8`, and it caught an error of
mine before it did damage.

Every Check in this ledger hard-codes the absolute path
`/Users/aashanjaved/band-work/result/stage-1` — `@builder`'s live working tree, not the
auditor's clone. "Clone the named revision and work only there" and "run the Check
exactly as written" therefore coincide **only while that tree is clean**. Cloning does
not fix it: the Check builds from the live path whatever revision is checked out.

At the time `@auditor` checked:

    $ git status --porcelain
     M stage-1/app.py
    $ git diff --stat -- stage-1/
     stage-1/app.py | 997 +++++++++++++++++++++++++++++++++++++++++++++-
     1 file changed, 982 insertions(+), 15 deletions(-)
    HEAD bytes: 1908   live bytes: 42127

Verified independently here at `655aef8`: same porcelain line, same 982 insertions,
`git cat-file -s HEAD:stage-1/app.py` = 1908 against 42127 bytes live.

**My error, recorded because it is mine.** I dispatched `@builder` to confirm a
revision and told it that "if you have committed nothing since, that is `66e7967` and
`stage-1/` is unchanged from what was already audited." That conflated *no new commits*
with *clean tree*. The two are not the same and the difference is exactly where this
hazard lives. Had `@builder` answered verbatim — which would have been reasonable, since
I supplied the wording — `@auditor` would have received a handoff naming a revision whose
`stage-1/` bore no resemblance to what the Check would have built, and a PASS would have
certified 42127 bytes that exist in nobody's history. `@auditor` refused to run on it and
was right to. Nothing was damaged; the near-miss is the finding.

**Standing gate requirement, effective now and applying to every remaining verdict.**
A handoff is not open, and I will not accept a verdict against it, unless it carries
literal `git status --porcelain` output showing an empty tree alongside the revision.
`@auditor` must re-verify the tree is clean immediately before and immediately after the
run, and record both in the verdict. A verdict whose run straddled a working-tree change
is unevidenced under case 3 and will be refused regardless of what it reports.

This is a distinct hazard from F-3. Conventions §8's `mkdir` lock serialises Docker and
does not touch this one: the collision here is git state, not Docker state, so a check
can be correct, the lock uncontended, and the audit still meaningless because the bytes
moved between commit and run. Both earlier interference incidents were Docker. This one
would not have been.

Supersession from the section above took effect at `655aef8`: `grep -c "^Status:
superseded"` returns 6, matching the six entries I authorised.


---

## Errata-2 supersession REFUSED — 2026-09-29, at ledger revision 7869293

`@scribe` requested authorisation to supersede C-1 -> C-148, C-142 -> C-149,
C-143 -> C-150, C-146 -> C-151, C-147 -> C-152, and — to its credit — argued against
its own request in the same message. **I refuse it, for now.** The gate stays C-142.

**Reason 1: it does not meet the bar I set at `66e7967`.** I authorised the first six
supersessions only because the errata reproduced a defect in each superseded *Check*
from a run. `@scribe`'s own words on this round are that "C-142 is not unsound; it is
only weaker than C-149." Weaker is not defective. If I supersede on *weaker*, the bar
I wrote one round ago means nothing, and supersession becomes what I said it must never
be: a way for entries to be replaced rather than settled.

**Reason 2: the numbers say the churn is now the risk.** 56 minutes from dispatch,
153 ledger entries, 5 reproduced check defects, **1 verdict**. Every round of
replacement has been justified on its own terms and the ledger is genuinely better for
each. But a gate that keeps improving its checks and never runs them produces exactly
as much assurance as no gate at all. C-148 through C-152 have been run by nobody —
`@scribe` deliberately did not execute them, correctly, to avoid taking the Docker lock
mid-implementation. Swapping five entries of proven shape for five unexecuted ones, to
close a gap that is already closed externally, trades evidence for tidiness.

**Reason 3: F-5 already supplies the guard.** My standing rule requires the handoff to
carry an empty `git status --porcelain`, and requires `@auditor` to verify the tree
clean immediately before and after the run and record both. `@auditor` did exactly this
on C-0 before anyone required it. The protection C-149 provides in-Check is the
protection F-5 already mandates out-of-Check. The in-Check version is better
engineering; it is not more assurance today.

**What I am giving up, stated plainly so it is not discovered later.** C-149's `TK_REPO`
indirection would let `@auditor` genuinely isolate in its own clone, which the
hard-coded path prevents. That is a real loss and I am accepting it knowingly, because
F-5's before-and-after proof makes auditing the live tree safe *provided the proof is
recorded*. If any verdict from here arrives without that proof, the trade was wrong and
I will authorise the Errata-2 set immediately.

**Disposition of C-148 to C-152.** They are not withdrawn and they are not decoration.
They are held in reserve at `7869293`, and they activate automatically, without further
argument from `@scribe`, on **any** of these:

1. A verdict arrives whose clean-tree proof is missing, partial, or straddles a change.
2. `@builder` or `@auditor` reports that the hard-coded path prevented an audit.
3. Stage 2 opens. The stage-2 folder is a copy of stage-1, two trees exist, and
   `TK_REPO` stops being a convenience at that point.

Until one of those fires, the gate is C-142 and the next thing this factory produces is
a verdict, not an entry.

`@scribe` has done nothing wrong here and this refusal costs it nothing. It found a real
defect, fixed it properly, and then told me the fix might not be worth the churn. That
last part is why I trust the first part.
