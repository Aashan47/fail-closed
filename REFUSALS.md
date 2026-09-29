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
