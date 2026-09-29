# Handoff batch 3 — stage 2

Seat: @builder
Repository: /Users/aashanjaved/band-work/result

Parent revision: e43ad8edf3fdcbc900979acbd804c58aa2a4939d

This file cannot name the commit that contains it, so no `Revision:` key
appears here. Derive this batch's revision on demand:

    git log -1 --format=%H -- handoffs/batch-3.md

## Claim submitted (1)

    S-0 — the stage-2 gate

## Check anchor (Conventions section 11 and section 13)

    S-0  sha256 afd44aa64b44732376e4dc5a65985f7db79c1e049a3ce29b953e34c327e5c855
         bytes  1050

Canonical form: the exact byte sequence between the backticks following
`Check: `, stripped, no trailing newline, no normalisation. This is DETECTION,
NOT PREVENTION: it makes the Check moving between my read and your run visible,
it does not stop it moving. Do not read a passing batch as F-11 being closed.

## Blobs under test

    stage-2/Dockerfile     5d070e3f9d0cf833e476d1ec952a0f157a46469f
    stage-2/RUN.md         a460ecfe6b104efcefd9cf3a06f223fdab3ec32f
    stage-2/app.py         b3afe577e6df6f0644c8c1758352d63066b6d5d3

stage-1/ is unchanged by this commit and stays byte-identical to the revision
it was audited at.

## What stage-2/ is at this revision

A faithful copy of the stage-1 service, with RUN.md retargeted to the tk-s2
container and tk-s2-net bridge of section 14. That is the dispatch's prescribed
starting point and it is all S-0 claims. It is NOT the widened stage-2 service:
there is no UI, no combinable handling, no available_options, and no table_ids.
S-1 through S-58 will fail against this revision and I am not submitting them.

## What I ran myself

Not evidence. Your run settles it.

    S-0   {"status": "ok"} HEALTHY IN 3s
          PORT PUBLISHED
          TREE CLEAN AND UNMOVED AT e43ad8edf3fdcbc900979acbd804c58aa2a4939d

All seven build steps ran cold after `docker builder prune -af`.
Section 8 lock: ACQUIRED before, RELEASED after. Docker left clear.
