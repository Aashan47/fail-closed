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
Verdict: `verdicts/C-0.md`, committed at d30eebe0cafadfc000b7769b988fb1e0a753b0a0

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

Resolved: no — awaiting a replacement entry from `@scribe`. C-0 is not edited and its
FAIL stands against this revision.

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
