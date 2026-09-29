# Handoff batch 1
Seat: @builder
Revision: dda4497c836831c120d4a5d98568f0bcd06bd9a7
Repository: /Users/aashanjaved/band-work/result

## Blobs under test

These are the identifiers to verify. The revision goes stale whenever any
seat commits anything; the blobs do not.

    stage-1/Dockerfile   5d070e3f9d0cf833e476d1ec952a0f157a46469f
    stage-1/RUN.md       54da4e9bae9e66fcc3f12179a89d5c4fbc241ade
    stage-1/app.py       b3afe577e6df6f0644c8c1758352d63066b6d5d3

Every claim in this batch is tested against those three blobs. No claim in
this batch depends on any other file.

## Claims submitted (136)

C-143 first, as instructed: it is the only entry that settles the §2
no-outbound-network rule, which is unproven in this pipeline.

    C-143, C-144, C-145, C-146, C-147
    C-5..C-27, C-29..C-45, C-47..C-55, C-57..C-122, C-124..C-139

## Not submitted (4)

    C-28, C-46, C-56, C-123

Reported to @scribe as check defects, with runs quoted, in the room message
accompanying this batch. They are NOT claimed to pass and NOT claimed to be
blocked on implementation. I have not edited them.

## What I ran myself

Not evidence. @auditor's runs settle these; mine only establish that I did
not spend the auditor's time on work I had not checked.

    all 135 prelude-based Checks   131 printed PASS, 4 failed (the four above)
    C-143                          {"status": "ok"} NO EGRESS
    C-144                          {"status": "ok"} on container port 9091
    C-145                          {"status": "ok"} with no -e PORT
    C-146 / C-147                  stage 1: pass, 120 passed, mode isolated

§8 lock: ACQUIRED before, RELEASED after. Docker left clear.
