# Handoff batch 5 - stage 2, errata-4 replacements

Seat: @builder
Repository: /Users/aashanjaved/band-work/result

Parent revision: 62127f982143edbaaa2463744df044afa15d1ebe     - NOT the submitted revision
Submitted revision: derive with `git log -1 --format=%H -- handoffs/batch-5.md`

## Claims submitted (6)

    S-59 replaces S-41 · S-60 replaces S-47 · S-61 replaces S-49
    S-62 replaces S-50 · S-63 replaces S-51 · S-64 replaces S-58

## Check anchors (sections 11 and 13)

    S-59   5cd493d4f11ad8660650b01252c33b592edf97ef8a92433c5f82a2d3d0362ff9  998
    S-60   6bc38a58d7a9492a9e36afef3832b3a0dcf36c63c22837dd7fb84e6f0cc2f3d4  2275
    S-61   eb0ce09a194411e58db60c424ccf73e7d5eb25954d547d0054db1b39a03bd302  879
    S-62   685cd7dfca3d1bd4a1bdd157a4cff4f98f4882e0f407a5754ded48fbbc28bfc0  2399
    S-63   7925512ebdb4a80d2a518ebad1a4019411190793a9721f77dbc023139143f453  1234
    S-64   10f3ee43a299c58cf29cfcaebc6643d4365159011d8ed93185c07b96586237b5  1271

DETECTION, NOT PREVENTION. A mismatch means the Check moved between my read
and your run; it does not stop it moving.

## Blobs under test - UNCHANGED

    stage-2/Dockerfile     5d070e3f9d0cf833e476d1ec952a0f157a46469f
    stage-2/RUN.md         a460ecfe6b104efcefd9cf3a06f223fdab3ec32f
    stage-2/app.py         8a9182454355c789d6ca8380b80da4b6b58235f4

NO CODE CHANGE WAS MADE FOR THIS BATCH. These six entries replace Checks that
were defective, not behaviour that was wrong, so stage-2/app.py is the same
blob @auditor already audited across all 58 claims of batch 4. If any of the
six fails, that is new information about my implementation and I will treat it
as mine rather than as another check defect.

## What I ran myself

Not evidence. Your runs settle these. All six passed:

    S-59  PASS ('5ELLP9', None, True)
    S-60  PASS 58QK5X
    S-61  PASS Signed in as Ada
    S-62  PASS ZHOGTB
    S-63  PASS 6 states, 15 pairs distinct
    S-64  PASS ('Window + Corner at 19:00 on 2027-06-10 - Zum Anker',
                'Window + Corner', 'Window + Corner')

S-63 is the one worth naming: it is the first run anyone has seen of the seven
style vectors. S-51 always failed before reaching that measurement, so the
doubt @scribe flagged was never tested until now. 15 pairs across 6 states all
differ. The proxy label stands - differing vectors do not establish that a
person can tell the states apart, and the eight declared properties still have
no proxy at all.

## Section 8

Lock ACQUIRED before Docker and RELEASED after. Docker left clear: no tk-*
containers, no tk-* networks, nothing on 18080. Both preludes lifted from the
committed ledger: browser prelude 5722 bytes.
