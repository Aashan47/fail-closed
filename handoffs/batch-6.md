# Handoff batch 6 — stage 2, the two entries that settle S-69 and S-76 by run

Seat: `@auditor`
Dispatched by: `@registrar`
Repository: `/Users/aashanjaved/band-work/result`

**WHY THIS IS A FILE AND NOT ONLY A ROOM MESSAGE.** This dispatch has now been sent twice in the
room — at `00eef6b99d95d1d1dd3dd9a3f5075f597ac40f40`, and re-stated at
`63e1de03de419d62c07dca8eb39d9beffb7e877b` in reply to `@auditor`'s own message — and
`verdicts/S-80.md` and `verdicts/S-81.md` still do not exist. In the same interval the room
re-delivered the same eleven stale messages twice, the second time after F-47 had already recorded
the first re-delivery. A transport that replays and may drop is not a channel a dispatch should
depend on. **The repository is the record and the room is the notification** — the same ordering the
gate already uses when it accepts a verdict from `verdicts/<claim-id>.md` rather than only from the
room. So the dispatch is committed here, where a restarted seat can read it and where a reader can
check it later. The room message that accompanies it names this path and nothing else is needed from
it.

## Revisions — both named, and they are different

    Audited revision     dc6879cdcb1094b0e75ecad2d5125741c6df31fe   build and serve stage-2/ from this
    Check-text revision  derive with: git log -1 --format=%H -- handoffs/batch-6.md

`LEDGER.md` is byte-identical at the Check-text revision to `d8ffcd6`, `1007a09`, `1277319`,
`00eef6b`, `b47bdf6`, `63e1de0` and `0b5132f`; confirm with an empty
`git diff --stat d8ffcd6 HEAD -- LEDGER.md`. **Nothing in `stage-2/` has changed since `dc6879c`**
and `@builder` has been told not to fix anything; confirm with an empty
`git diff --stat dc6879c HEAD -- stage-2/`.

## The two claims

    S-80   LEDGER.md:5284-5315   sha256 0639133c6d8ca24a4703c326631953452fba91fef3e28b8b864099444053d1c4   3735
    S-81   LEDGER.md:5317-5347   sha256 1bf454f1aa3a2f20de2e3bb8e6208ea5dbc8b7e7ec4500b144f2fe6945501e41   3657

Both are `Status: unclaimed` in `LEDGER.md`. **Neither is a probe of your invention** — that is the
whole reason they exist. You declined to run an ad-hoc command to identify the tag of S-69's
zero-box element, and declining was right; these are committed entries with Check text and a pass
condition, so they produce verdicts.

DETECTION, NOT PREVENTION. A digest mismatch means the Check moved between this dispatch and your
run; it does not stop it moving. Re-derive with
`sed -n '5284,5315p' LEDGER.md | shasum -a 256` and `sed -n '5317,5347p' LEDGER.md | shasum -a 256`.

## Preludes — three blocks, all read from the Check-text revision

    #PX-BEGIN  … #PX-END    (§17, $PX )  sha256 ab26a7c81555b741ae1c8df94371ef7946a4e9a78dc87126cb0e1061195934b9   9141
    #PX3-BEGIN … #PX3-END   (§20, $PX3)  sha256 a93c8b1727009ec244bbea2ddc6ffbe791fe38948a6b219bdf23f1775ec33d05  10220

Both digests are of the awk-extracted block as the export reads it, not of a line range. §19 is not
loaded by either Check. §20's own text, verbatim from `LEDGER.md`, including the confirm command:


**§17 and §19 are not touched.** Seventeen Checks load `$PX` and five load `$PX2`; changing either
would move the ground under Checks whose text is fixed, which is the F-11 shape §13 exists to make
visible. `$PX3` is a third additive block.

**Read every prelude from `LEDGER.md` at the Check-text revision**, which is the revision containing
this section — not from a clone of the audited revision, where `#PX3` does not exist. That is §19's
defect repeating, and the convention that fixes it properly is held for the next stage.

```sh
export PX3="$(awk '/^#PX3-BEGIN$/{f=1;next} /^#PX3-END$/{f=0} f' "$TK_LEDGER")"
export WPX3="$W
$PX
$PX3"
```

where `TK_LEDGER` is the path to a checkout at the Check-text revision, and `TK_REPO` remains the
clone of the audited revision that the service is built and served from. Confirm:

```sh
$PWPY -c "$WPX3"'
print("WPX3 OK",BASE,PX_AA,len(PX_SURF),len(PX3_ZB),len(PX3_CONT))'

## The Check text, verbatim from `LEDGER.md` at the Check-text revision

Copied by `sed -n '5284,5347p' LEDGER.md`, not transcribed. `LEDGER.md` remains authoritative; this
copy exists so a restarted seat is not dependent on the room.

### S-80: Every zero-box text-bearing element is identified by tag, and whether its zero box is intrinsic is settled by run.
Check: `$PWPY -c "$WPX3"'
ta,_=SETUP()
pre=OK(BOOK(ta,F+"T20:00","s80-seed",table_id="t_3",ps=4),201)
def f(pg):
    return PX_NAV(pg,pre["reference"],lambda n:pg.evaluate(PX3_ZB))
per=UI(f,route=None)
allf=[]; allfresh=[]
for n in sorted(per):
    for o in per[n]["found"]: allf.append(dict(o,surface=n))
    for o in per[n]["fresh"]: allfresh.append(dict(o,surface=n))
print("SURFACES VISITED:",len(per))
print("ZERO-BOX TEXT-BEARING ELEMENTS, WITH TAG:",json.dumps(allf,indent=1,sort_keys=True))
print("FRESH-SIBLING PROBES:",json.dumps(allfresh,indent=1,sort_keys=True))
assert len(per)==len(PX_SURF),"visited %d surfaces, not the %d PX_SURF names: %r"%(len(per),len(PX_SURF),sorted(per))
tags=sorted(set([o["tag"] for o in allf]))
print("DISTINCT TAGS:",json.dumps(tags))
print("PER TAG:",json.dumps({t:len([o for o in allf if o["tag"]==t]) for t in tags},sort_keys=True))
assert allf,"no zero-box text-bearing element was found on any of the %d surfaces, so S-69 third condition had nothing to refuse on and this entry cannot settle it"%len(per)
for o in allf:
    assert o["tag"],"an element was reported with no tag, which is the gap this entry exists to close: %r"%o
notint=[o for o in allf if not o["cssCannotGiveBox"]]
print("ZERO AT REST BUT GIVEN A BOX BY A FORCING STYLE:",json.dumps(notint,indent=1,sort_keys=True))
fz=[o for o in allfresh if o.get("made") and not o.get("freshAlsoZero")]
print("FRESH SIBLING THAT DID GET A BOX:",json.dumps(fz,indent=1,sort_keys=True))
print("VERDICT ON INTRINSIC-NESS: cssCannotGiveBox on all=%s ; freshAlsoZero on all made=%s"%(
  not notint, not fz))
assert not notint,"%d zero-box elements DID take a box from a forcing inline style, so their zero box is not intrinsic and S-69 third condition was refusing something the service controls: %s"%(len(notint),json.dumps(notint,indent=1,sort_keys=True))
assert not fz,"a fresh sibling of the same tag in the same parent DID get a box, so the zero box is not intrinsic to the element kind: %s"%json.dumps(fz,indent=1,sort_keys=True)
print("PASS",len(allf),"zero-box text-bearing elements identified by tag across",len(per),"surfaces; tags",tags,"; no forcing style and no fresh sibling of the same kind could obtain a box, so no stylesheet change in stage-2/ can give these elements one")'`
Passes when: exits 0 and ends `PASS <n> zero-box text-bearing elements identified by tag across 12 surfaces; tags [...]; no forcing style and no fresh sibling of the same kind could obtain a box, …`, having printed every such element with its **tag, parent tag, parent testid, display, visibility and three box measurements**, and the fresh-sibling probes. **This supersedes S-69's third condition only.** S-69's first two conditions printed empty at `fe543c4`, are not in question, and are not re-claimed here. **What a failing run means:** if `cssCannotGiveBox` is false for any element, its zero box is something `stage-2/`'s CSS controls, S-69's refusal was pointing at a real defect, and this entry fails — that is the outcome that would send it back to `@builder`. If every element resists both the forcing style and the fresh-sibling probe, the zero box is intrinsic to the element kind as the browser renders it. **What it does not establish:** that no *markup* change could give the element a box. Replacing a native control with a custom widget would, and that is a redesign aimed at an assertion rather than at a requirement — this entry reports the measurement and does not pretend it settles that design question. It also does not re-measure contrast; nothing here is a pixel claim.
Status: unclaimed

### S-81: Off-scrollport content at 375 pixels is measured by scrolling to it, not excluded, and meets the declared threshold.
Check: `$PWPY -c "$WPX3"'
ta,_=SETUP()
pre=OK(BOOK(ta,F+"T20:00","s81-seed",table_id="t_3",ps=4),201)
def f(pg):
    acc={"cons":[],"rows":[],"inv":{}}
    def one(n):
        c,r,i=PX_SCROLLSCAN(pg,n)
        acc["cons"].extend([dict(x,surface=n) for x in c]); acc["rows"].extend(r); acc["inv"].update(i)
        return len(i)
    cen=PX_NAV(pg,pre["reference"],one)
    return acc,cen
acc,cen=UI(f,w=375,h=812,route=None)
cons=acc["cons"]; rows=acc["rows"]; inv=acc["inv"]
best=PX3_BEST(rows)
never=sorted([k for k in inv if k not in best])
bad=[best[k] for k in sorted(best) if best[k]["verdict"]!="OK"]
print("VIEWPORT 375x812")
print("INVENTORY PER SURFACE:",json.dumps(cen,indent=1,sort_keys=True))
print("SCROLLABLE CONTAINERS:",json.dumps(cons,indent=1,sort_keys=True))
print("MEASUREMENTS TAKEN:",len(rows),"DISTINCT ELEMENTS MEASURED:",len(best),"IN INVENTORY:",len(inv))
print("NEVER MEASURED AT ANY SCROLL POSITION:",json.dumps([inv[k] for k in never],indent=1,sort_keys=True))
print("BEST RESULT BELOW THRESHOLD:",json.dumps(bad,indent=1,sort_keys=True))
assert len(cen)==len(PX_SURF),"visited %d surfaces, not the %d PX_SURF names: %r"%(len(cen),len(PX_SURF),sorted(cen))
assert cons,"no scrollable container was found on any surface at 375 pixels, so the content S-76 refused on does not exist here and this entry cannot settle it"
assert inv,"no element inventory was built inside any scrollable container"
assert not never,"%d elements inside a scrollable container were never measured at any scroll position, which is the silent coverage hole this entry exists to close: %s"%(len(never),json.dumps([inv[k] for k in never],indent=1,sort_keys=True))
assert not bad,"%d of %d elements inside scrollable containers are below the declared threshold at their best scroll position, so they are illegible rather than merely off-scrollport:\n%s"%(len(bad),len(best),json.dumps(bad,indent=1,sort_keys=True))
print("PASS",len(best),"elements inside",len(cons),"scrollable containers measured by scrolling to them at 375x812,",len(rows),"measurements,0 never measured, none below threshold at its best position")'`
Passes when: exits 0 and ends `PASS <n> elements inside <m> scrollable containers measured by scrolling to them at 375x812, …`, having printed the per-surface inventory, every scrollable container with its scroll and client dimensions, the count of measurements, and empty lists for both never-measured and below-threshold. **This supersedes S-76 entirely.** It answers the question S-76 could not: content is measured on its **painted intersection with the scrollport** at every 80%-step across the container's scroll range, so the clamp of Defect 13 is never reached and `distinct: 1` can no longer arise from sampling a one-pixel column off the edge of the raster. Per element the **best** result across positions is what is asserted, because the requirement is that content be legible when a diner scrolls to it. **Two distinct failures are therefore separable in the output:** an element whose best result is below threshold at every position is illegible and a real defect; an element that never appears in any scrollport is a coverage hole, and it fails too rather than passing quietly. **What it does not establish:** anything about elements outside a scrollable container — S-67 covers the resting raster at 1280 and this entry does not re-claim it — nor hover, focus or disabled appearance, nor whether scrolling is discoverable, which is judgement and stays with the human.
Status: unclaimed

## What these two settle, and what the gate does with the answer

`verdicts/S-69.md` and `verdicts/S-76.md` hold two real FAILs at `dc6879c`, refused as F-45 and
F-46, both with `Would it have failed the graded suite: unknown`. Three seats then agreed by reading
that the cause is defective Check text rather than a defect in the service. **Agreement by reading
is not a verdict**, which is why the counterfactual column still says `unknown` and why these two
entries were written.

- If **both pass**, the zero box is intrinsic and the off-scrollport content is legible when
  scrolled to, and F-45 and F-46 resolve as defects in Checks this factory wrote rather than in
  `dc6879c`.
- If **either fails**, the refusal was pointing at something real in the service, and it goes back
  to `@builder` under the original claim identifier.

Either outcome closes the gate's open question. A third re-reading of the code does not.

Do not propose a fix and do not improvise a command. Run these two, quote the real stdout, commit
`verdicts/S-80.md` and `verdicts/S-81.md`, and name both revisions in each file. If either fails,
run the graded suite at `dc6879c` in the same clone and record the result as
`Graded suite at this revision`, as you did for S-69 and S-76 — that line is what the refusal ledger
cannot otherwise fill in without guessing.
