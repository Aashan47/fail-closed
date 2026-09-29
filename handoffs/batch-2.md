# Handoff batch 2

Seat: @builder
Repository: /Users/aashanjaved/band-work/result

Parent revision: 9013eefc83fe5a84ba78a369cf524bb185a3b9d2

This file cannot name the commit that contains it -- at write time only the
pre-commit HEAD is knowable, so a `Revision:` line here would be born stale.
Derive this batch's own revision on demand:

    git log -1 --format=%H -- handoffs/batch-2.md

## Blobs under test

Unchanged since 5cc1c31 (app.py) and ce80f21 (RUN.md). No code change was
needed for this batch; the four entries replace defective checks, not defects
in the implementation.

    stage-1/Dockerfile   5d070e3f9d0cf833e476d1ec952a0f157a46469f
    stage-1/RUN.md       54da4e9bae9e66fcc3f12179a89d5c4fbc241ade
    stage-1/app.py       b3afe577e6df6f0644c8c1758352d63066b6d5d3

## Claims submitted (4)

    C-153  replaces C-28   starts_at_local from availability accepted unchanged
    C-154  replaces C-46   references unique across all reservations
    C-155  replaces C-56   unknown/foreign restaurant or table is 404
    C-156  replaces C-123  moves list outside 1..8 is 422

## What I ran myself

Not evidence. @auditor's runs settle these.

    C-154   PASS 9
    C-155   PASS
    C-156   PASS
    C-153   FAILED for me -- see below

## C-153 is ORDER-DEPENDENT, which is why I am flagging it rather than
## reporting a plain defect

C-153's first statement reads availability before the check seeds anything:

    slots=[... for s in OK(AV("r_anker",F,4),200)["slots"]]
    assert len(slots)==9,slots
    for at,want in slots:
        t,_=SETUP()          <- the reset is INSIDE the loop, after the read

Conventions section 5 states every check resets state itself, so entries are
order-independent and repeatable in any order. C-153 does not reset before that
first read, so its outcome depends on what ran before it:

  * On a freshly started service it FAILS. I observed:
        GET /availability on unseeded service -> 404 not_found
        restaurants present: []
        AssertionError: status 404 want (200,)  {'code': 'not_found'}
    That 404 is correct behaviour -- an unknown restaurant is 404 per section 8,
    which C-27 asserts and which passed in batch 1.

  * Run after any check that leaves the default fixture seeded, it should PASS.

I ran C-153's body verbatim with a single reset ahead of the first read and
changed nothing else:

        PASS 9

So every assertion C-153 exists to make holds against this implementation. The
only thing standing between the check and a pass is the missing reset.

I have NOT edited C-153. I am submitting it per @registrar's ruling that omitting
a claim settles it by assurance. @auditor's run is what settles it, and its
result may differ from mine depending on execution order -- which is itself the
finding worth recording.

## Section 8 lock

Found HELD BY scribe on my first acquire. I waited and did not remove it, per
section 8. It freed moments later. First contention this factory has seen; the
rule held.
