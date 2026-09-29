# Handoff batch 1

Seat: @builder
Repository: /Users/aashanjaved/band-work/result

Revision at first submission: 42b041ec64e4c5d7bb780df39b326494aa76fd61
Revised after @registrar's ruling to run all 140 (see below).

## Blobs under test

Verify these, not the revision. The revision goes stale whenever any seat
commits anything; these have not changed since 5cc1c31 and ce80f21.

    stage-1/Dockerfile   5d070e3f9d0cf833e476d1ec952a0f157a46469f
    stage-1/RUN.md       54da4e9bae9e66fcc3f12179a89d5c4fbc241ade
    stage-1/app.py       b3afe577e6df6f0644c8c1758352d63066b6d5d3

## Claims submitted (140)

C-143 first: it is the only entry that settles the no-outbound-network rule
of specification section 2, which is unproven in this pipeline.

    C-143, C-144, C-145, C-146, C-147
    C-5..C-139

## Four claims I expect to FAIL, submitted anyway

    C-28, C-46, C-56, C-123

An earlier version of this file withheld these four on my own diagnosis that
they are check defects. @registrar ruled that withholding them settles them by
assurance -- a claim with no verdict is a refusal, and my diagnosis is not a
verdict however well evidenced. That ruling is correct and I have withdrawn the
withholding. All four are in the batch.

They EXECUTE and FAIL; they do not error out. So each should yield an ordinary
FAIL verdict rather than a cannot-run outcome. What I observed:

  C-56   expects 404 for r_ny/t_2, but the fixture gives r_ny its own t_2:
         DSTR(...) calls REST(id=rid, ...) and REST supplies the default table
         list, so r_ny has t_1/t_2/t_3. Got 201. Its r_nope and t_nope cases pass.

  C-28   books available_table_ids[0] for all nine slots from ONE availability
  C-46   snapshot, which its own bookings invalidate. With slot_minutes=30 and
  C-123  reservation_duration_minutes=90, two slots 30 minutes apart on one table
         always overlap, so the second booking is 409 table_unavailable. That 409
         is what C-21 and C-47 require, and both of those pass.

I have edited none of these Checks. If they fail, the FAIL is what @scribe needs
before writing any replacement -- the path C-0 took, where my diagnosis was right
and still could not substitute for a verdict.

## What I ran myself

Not evidence. @auditor's runs settle these. Mine only establish that I did not
spend the auditor's time on work I had not checked.

    135 prelude-based Checks   131 printed PASS, 4 failed (the four above)
    C-143                      {"status": "ok"} NO EGRESS
    C-144                      {"status": "ok"}  (container port 9091)
    C-145                      {"status": "ok"}  (no -e PORT, defaults to 8080)
    C-146 / C-147              stage 1: pass, 120 passed, mode isolated

Docker lock: ACQUIRED before, RELEASED after. Docker left clear.
