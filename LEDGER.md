# Acceptance ledger — Tablekeeper, stage 1

Owner: `@scribe`. This file is the definition of "done" for stage 1. It is written before any
implementation begins and is the only place acceptance criteria live.

- Result repository: `/Users/aashanjaved/band-work/result`
- Ledger written at revision: `8aa5f782ef7afb5188b774359a3f49266465671b` (branch `main`)
- Implementation under test: `/Users/aashanjaved/band-work/result/stage-1/`
- Specification: `tablekeeper/spec/stage-1.md` of the kickoff checkout

Rules of the ledger, so a reader who only has this repository knows how it is used:

- `@builder` takes the lowest `unclaimed` entry. `@auditor` settles it. `@registrar` alone
  authorises a `Status` change, and `@scribe` alone edits this file.
- A `Check` is **never edited after `@builder` has taken the entry**. If a check turns out to be
  wrong, `@scribe` writes a **new entry** and says so in the room. The old entry stays. A ledger
  that shifts under `@auditor` is not evidence.
- A verdict is a pass only if it quotes real output from the `Check` command. An empty or
  paraphrased output is a refusal.
- Claims describe behaviour the specification requires, observed from outside the service. No claim
  encodes a test's internals, and no claim describes how to build anything.
- **C-0 is the gate.** Nothing else is audited until C-0 passes. A service that does not start
  scores nothing.
- This ledger makes **no claim that stage 2 passes**. The stage-2 suite is expected to fail against
  stage 1; a folder that passed the next stage's suite would claim nothing for its own.

---

## Conventions

Every `Check` below is a single command. Most are one `python3` invocation that talks HTTP to the
running container and prints `PASS`. They use only the Python standard library, so nothing needs
installing.

### 1. Base URL and container name

The service under test is reached at `http://127.0.0.1:18080`. The container is named `tk-s1` and
the no-egress network is named `tk-s1-noout`.

### 2. Materialise the prelude (once per shell)

Run this from the repository root. It lifts the prelude block out of this file, so the instrument
and the ledger can never drift apart:

```sh
export P="$(awk '/^#PRELUDE-BEGIN$/{f=1;next} /^#PRELUDE-END$/{f=0} f' /Users/aashanjaved/band-work/result/LEDGER.md)"
```

Confirm it loaded:

```sh
python3 -c "$P"'
print("PRELUDE OK", B)'
```

Note the newline after the opening quote. `$(...)` strips the trailing newline from the extracted
prelude, so every check's body begins on its own line — that is why each `Check` below is written
across several lines rather than as one long line.

### 3. Start the service (C-0 does this; other checks assume it is up)

```sh
docker rm -f tk-s1 >/dev/null 2>&1; docker network create --internal tk-s1-noout >/dev/null 2>&1; docker build -t tk-s1 /Users/aashanjaved/band-work/result/stage-1 && docker run -d --name tk-s1 --network tk-s1-noout -p 18080:8080 -e PORT=8080 tk-s1 && for i in $(seq 1 60); do curl -fsS http://127.0.0.1:18080/health >/dev/null 2>&1 && break; sleep 1; done
```

`--network tk-s1-noout` is an **internal** Docker network: the published port stays reachable from
the host while the container has no outbound access. That is how the no-egress requirement of §2 is
enforced for every check in this file, not only C-0.

### 4. Tear down when finished

Leave nothing bound to port 18080. Run this after self-verifying, every time:

```sh
docker rm -f tk-s1 >/dev/null 2>&1; docker network rm tk-s1-noout >/dev/null 2>&1; echo "torn down"
```

### 5. Every check resets state itself

Each check begins with its own `POST /_test/reset`, so checks are order-independent and repeatable.
Running one check never changes the outcome of another.

### 6. The prelude

```python
#PRELUDE-BEGIN
import json,re,threading,urllib.request as U
from urllib.parse import urlencode as QS
B="http://127.0.0.1:18080"
WD=["mon","tue","wed","thu","fri","sat","sun"]
ADA={"id":"u_ada","email":"ada@example.com","password":"correct horse","display_name":"Ada"}
BOB={"id":"u_bob","email":"bob@example.com","password":"correct horse","display_name":"Bob"}
F="2027-06-10"
def R(m,p,b=None,tok=None,key=None,hdr=None):
    h={"Content-Type":"application/json"}
    if tok: h["Authorization"]="Bearer "+tok
    if key is not None: h["Idempotency-Key"]=key
    if hdr: h.update(hdr)
    d=None if b is None else (b if isinstance(b,bytes) else json.dumps(b).encode())
    try:
        x=U.urlopen(U.Request(B+p,method=m,data=d,headers=h),timeout=12); raw=x.read()
    except U.HTTPError as e:
        raw=e.read()
        try: bd=json.loads(raw or b"null")
        except Exception: bd={"raw":raw.decode("utf-8","replace")}
        return e.code,bd,dict(e.headers)
    try: bd=json.loads(raw or b"null")
    except Exception: bd={"raw":raw.decode("utf-8","replace")}
    return x.status,bd,dict(x.headers)
def ERR(r,want,code):
    s,b,_=r
    assert s==want,"status %s want %s body %r"%(s,want,b)
    assert b.get("error",{}).get("code")==code,"code %r want %r"%(b.get("error"),code)
def OK(r,*want):
    s,b,_=r
    assert s in want,"status %s want %s body %r"%(s,want,b)
    return b
def REST(**o):
    r={"id":"r_anker","name":"Zum Anker","timezone":"Europe/Berlin","slot_minutes":30,
       "reservation_duration_minutes":90,"cancellation_cutoff_minutes":120,
       "opening_hours":[{"weekday":w,"opens":"18:00","closes":"23:30"} for w in WD],
       "tables":[{"id":"t_1","label":"1","capacity":2},{"id":"t_2","label":"2","capacity":4},
                 {"id":"t_3","label":"3","capacity":4}]}
    r.update(o); return r
def DSTR(tz,rid="r_dst",opens="01:00",closes="06:00",**o):
    return REST(id=rid,timezone=tz,opening_hours=[{"weekday":w,"opens":opens,"closes":closes} for w in WD],**o)
def FX(**o):
    f={"users":[ADA,BOB],"restaurants":[REST()],"reservations":[]}
    f.update(o); return f
def SEED(ref,at,rid="r_anker",tid="t_2",ps=4,uid="u_ada",rsid=None):
    return {"id":rsid or ("res_"+ref.lower()),"reference":ref,"user_id":uid,"restaurant_id":rid,
            "table_id":tid,"starts_at_local":at,"party_size":ps}
def RESET(f):
    s,b,_=R("POST","/_test/reset",f)
    assert s==204,"reset %s %r"%(s,b)
def LOGIN(u):
    return OK(R("POST","/auth/login",{"email":u["email"],"password":u["password"]}),200)["token"]
def SETUP(f=None):
    RESET(f or FX()); return LOGIN(ADA),LOGIN(BOB)
def BOOK(tok,at,key,rid="r_anker",tid="t_2",ps=4,**o):
    body={"restaurant_id":rid,"table_id":tid,"starts_at_local":at,"party_size":ps}; body.update(o)
    return R("POST","/reservations",body,tok=tok,key=key)
def LIST(tok): return R("GET","/reservations",tok=tok)
def GETR(tok,ref): return R("GET","/reservations/"+ref,tok=tok)
def CANCEL(tok,ref): return R("POST","/reservations/"+ref+"/cancel",tok=tok)
def PATCHR(tok,ref,body): return R("PATCH","/reservations/"+ref,body,tok=tok)
def MOVES(tok,key,moves): return R("POST","/reservation-moves",{"moves":moves},tok=tok,key=key)
def AV(rid,date,ps,tok=None):
    return R("GET","/availability?"+QS({"restaurant_id":rid,"date":date,"party_size":ps}),tok=tok)
def SLOTS(rid,date,ps): return [s["starts_at_local"] for s in OK(AV(rid,date,ps),200)["slots"]]
def FREE(rid,date,ps,at):
    for s in OK(AV(rid,date,ps),200)["slots"]:
        if s["starts_at_local"]==at: return s["available_table_ids"]
    return None
def EXPORT(): return OK(R("GET","/_test/export"),200)
def IMPORT(o): return R("POST","/_test/import",o)
def PAR(n,fn):
    out=[None]*n
    def w(i):
        try: out[i]=fn(i)
        except Exception as e: out[i]=("EXC",repr(e),{})
    ts=[threading.Thread(target=w,args=(i,)) for i in range(n)]
    for t in ts: t.start()
    for t in ts: t.join()
    return out
def CODES(rs): return sorted(r[0] for r in rs)
RFC=re.compile(r"^\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d([.]\d+)?([+-]\d\d:\d\d|Z)$")
REF=re.compile(r"^[A-Z0-9]{6,12}$")
LOC=re.compile(r"^\d{4}-\d\d-\d\dT\d\d:\d\d$")
#PRELUDE-END
```

---

## The gate

### C-0: The service builds and serves from a clean container with no outbound network, by following its RUN.md.
Check: `docker rm -f tk-s1 >/dev/null 2>&1; docker network rm tk-s1-noout >/dev/null 2>&1; docker builder prune -af >/dev/null 2>&1; test -f /Users/aashanjaved/band-work/result/stage-1/Dockerfile && test -f /Users/aashanjaved/band-work/result/stage-1/RUN.md && docker network create --internal tk-s1-noout && docker build --no-cache -t tk-s1 /Users/aashanjaved/band-work/result/stage-1 && docker run -d --name tk-s1 --network tk-s1-noout -p 18080:8080 -e PORT=8080 tk-s1 && start=$(date +%s) && until curl -fsS http://127.0.0.1:18080/health; do [ $(( $(date +%s) - start )) -lt 60 ] || { echo "NOT HEALTHY WITHIN 60s"; exit 1; }; sleep 1; done && echo "HEALTHY IN $(( $(date +%s) - start ))s"`
Passes when: exits 0, prints the `/health` body followed by `HEALTHY IN <n>s` with `n` at most 60. The build runs with `--no-cache` after a builder prune, so nothing carries over from an earlier attempt; the container runs on an internal network, so it has no outbound access while serving.
Status: FAILED at 90028fd — see verdicts/C-0.md; superseded by C-142

### C-1: RUN.md's own command builds and starts the service without manual setup.
Check: `cd /Users/aashanjaved/band-work/result/stage-1 && docker rm -f tk-s1 >/dev/null 2>&1; docker network create --internal tk-s1-noout >/dev/null 2>&1; awk '/^```/{f=!f;next} f' RUN.md > /tmp/tk-runmd.sh && test -s /tmp/tk-runmd.sh && sh -eux /tmp/tk-runmd.sh && start=$(date +%s) && until curl -fsS http://127.0.0.1:18080/health; do [ $(( $(date +%s) - start )) -lt 60 ] || { echo "NOT HEALTHY"; exit 1; }; sleep 1; done && echo "RUNMD OK"`
Passes when: exits 0 and prints `RUNMD OK`. The fenced code blocks of `RUN.md` must contain exactly the shell commands that build and start the service and nothing else, must require no editing, and must leave the service answering on port 18080.
Status: passed at ce80f21 — see verdicts/C-1.md

### C-2: The container has no outbound network access while serving.
Check: `docker exec tk-s1 sh -c 'getent hosts example.com || nslookup example.com || wget -q -T3 -O- http://example.com || curl -sS -m3 http://example.com' ; test $? -ne 0 && echo "NO EGRESS"`
Passes when: prints `NO EGRESS`. Every outbound attempt from inside the running container fails.
Status: superseded by C-143

---

## Runtime contract (§3)

### C-3: The service listens on the port given in the PORT environment variable.
Check: `docker rm -f tk-s1-port >/dev/null 2>&1; docker run -d --name tk-s1-port --network tk-s1-noout -p 18081:9091 -e PORT=9091 tk-s1 >/dev/null && for i in $(seq 1 60); do curl -fsS http://127.0.0.1:18081/health && break; sleep 1; done; r=$?; docker rm -f tk-s1-port >/dev/null 2>&1; exit $r`
Passes when: exits 0 and prints `{"status": "ok"}` (any equivalent JSON spelling). The service bound the port named in `PORT`, not a hard-coded one.
Status: superseded by C-144

### C-4: The service listens on port 8080 when PORT is not set.
Check: `docker rm -f tk-s1-dflt >/dev/null 2>&1; docker run -d --name tk-s1-dflt --network tk-s1-noout -p 18082:8080 tk-s1 >/dev/null && for i in $(seq 1 60); do curl -fsS http://127.0.0.1:18082/health && break; sleep 1; done; r=$?; docker rm -f tk-s1-dflt >/dev/null 2>&1; exit $r`
Passes when: exits 0 and prints the health body. With `PORT` absent the service defaulted to 8080.
Status: superseded by C-145

### C-5: GET /health returns 200 with status ok.
Check: `python3 -c "$P"'
s,b,h=R("GET","/health")
assert s==200,(s,b)
assert b=={"status":"ok"},b
print("PASS",b)'`
Passes when: prints `PASS {'status': 'ok'}`.
Status: passed at 9c8c115 — see verdicts/C-5.md

### C-6: JSON responses are application/json with charset utf-8.
Check: `python3 -c "$P"'
t,_=SETUP()
for m,p,bd,tk in [("GET","/health",None,None),("GET","/restaurants",None,None),("GET","/reservations",None,t)]:
    s,b,h=R(m,p,bd,tok=tk)
    ct=(h.get("Content-Type") or h.get("content-type") or "").lower().replace(" ","")
    assert s==200,(p,s,b)
    assert ct=="application/json;charset=utf-8",(p,ct)
s,b,h=R("GET","/restaurants/nope")
ct=(h.get("Content-Type") or h.get("content-type") or "").lower().replace(" ","")
assert s==404 and ct=="application/json;charset=utf-8",(s,ct)
print("PASS")'`
Passes when: prints `PASS`. Success and error responses alike carry `application/json; charset=utf-8`.
Status: passed at 9c8c115 — see verdicts/C-6.md

### C-7: POST /_test/reset replaces all state, returns 204, and needs no authentication.
Check: `python3 -c "$P"'
RESET(FX())
t=LOGIN(ADA)
OK(BOOK(t,F+"T19:00","k1"),201)
assert len(OK(LIST(t),200)["reservations"])==1
RESET(FX())
t2=LOGIN(ADA)
assert OK(LIST(t2),200)["reservations"]==[],"state survived reset"
assert len(OK(R("GET","/restaurants"),200)["restaurants"])==1
print("PASS")'`
Passes when: prints `PASS`. Reset returned 204 with no bearer token, and after it the caller sees only the new fixture.
Status: passed at 9c8c115 — see verdicts/C-7.md

### C-8: Repeated resets are supported and each one takes full effect.
Check: `python3 -c "$P"'
for i in range(4):
    RESET(FX(restaurants=[REST(id="r_%d"%i,name="Round %d"%i)]))
    rs=OK(R("GET","/restaurants"),200)["restaurants"]
    assert [r["id"] for r in rs]==["r_%d"%i],(i,rs)
print("PASS")'`
Passes when: prints `PASS`. After each of four consecutive resets only that fixture's restaurant is visible.
Status: passed at 9c8c115 — see verdicts/C-8.md

### C-9: A reset fixture carrying an ID longer than 64 characters is rejected.
Check: `python3 -c "$P"'
ERR(R("POST","/_test/reset",FX(users=[dict(ADA,id="u"*65)])),422,"validation_failed")
ERR(R("POST","/_test/reset",FX(restaurants=[REST(id="r"*65)])),422,"validation_failed")
ERR(R("POST","/_test/reset",FX(restaurants=[REST(tables=[{"id":"t"*65,"label":"1","capacity":2}])])),422,"validation_failed")
print("PASS")'`
Passes when: prints `PASS`. An over-long user, restaurant or table ID in a fixture is 422 `validation_failed`.
Status: passed at 9c8c115 — see verdicts/C-9.md

### C-10: A reset fixture carrying a reservation reference of invalid format is rejected.
Check: `python3 -c "$P"'
for bad in ["x","lower01","TOO-LONG-WITH-DASH","ABCDEFGHIJKLM",""]:
    ERR(R("POST","/_test/reset",FX(reservations=[SEED(bad,F+"T19:00")])),422,"validation_failed")
print("PASS")'`
Passes when: prints `PASS`. Each malformed seeded reference is 422 `validation_failed`.
Status: passed at 9c8c115 — see verdicts/C-10.md

### C-11: Unknown fields in a request body are ignored, never an error.
Check: `python3 -c "$P"'
t,_=SETUP()
b=OK(R("POST","/reservations",{"restaurant_id":"r_anker","table_id":"t_2","starts_at_local":F+"T19:00","party_size":4,"nonsense":[1,2,3],"vip":True},tok=t,key="k1"),201)
assert b["status"]=="confirmed" and "nonsense" not in b,b
OK(R("POST","/auth/signup",{"email":"zoe@example.com","password":"correct horse","display_name":"Zoe","extra":{"a":1}}),201)
OK(PATCHR(t,b["reference"],{"party_size":2,"junk":"ignored"}),200)
print("PASS")'`
Passes when: prints `PASS`. Extra body fields are accepted and do not appear in the response.
Status: passed at 9c8c115 — see verdicts/C-11.md

### C-12: Unknown query parameters are ignored.
Check: `python3 -c "$P"'
SETUP()
s,b,_=R("GET","/availability?restaurant_id=r_anker&date="+F+"&party_size=4&sort=whatever&page=3")
assert s==200,(s,b)
assert b["restaurant_id"]=="r_anker" and b["date"]==F,b
print("PASS")'`
Passes when: prints `PASS`.
Status: passed at 9c8c115 — see verdicts/C-12.md

### C-13: Timestamps in responses are RFC 3339 with an explicit offset.
Check: `python3 -c "$P"'
t,_=SETUP()
b=OK(BOOK(t,F+"T19:00","k1"),201)
for f in ["starts_at","ends_at","created_at"]:
    assert RFC.match(b[f]),(f,b[f])
assert LOC.match(b["starts_at_local"]),b["starts_at_local"]
sl=OK(AV("r_anker",F,2),200)["slots"][0]
assert RFC.match(sl["starts_at"]) and LOC.match(sl["starts_at_local"]),sl
print("PASS")'`
Passes when: prints `PASS`. `starts_at`, `ends_at` and `created_at` carry an explicit offset; `starts_at_local` carries none.
Status: passed at 9c8c115 — see verdicts/C-13.md

### C-14: IDs and references in responses are at most 64 characters.
Check: `python3 -c "$P"'
t,_=SETUP()
b=OK(BOOK(t,F+"T19:00","k1"),201)
for f in ["reservation_id","reference","restaurant_id","table_id"]:
    assert isinstance(b[f],str) and 0<len(b[f])<=64,(f,b[f])
u=OK(R("POST","/auth/signup",{"email":"zoe@example.com","password":"correct horse","display_name":"Zoe"}),201)
assert len(u["user_id"])<=64,u["user_id"]
print("PASS")'`
Passes when: prints `PASS`.
Status: passed at 9c8c115 — see verdicts/C-14.md

---

## Public endpoints (§8)

### C-15: GET /restaurants is public and returns each restaurant's id, name and timezone.
Check: `python3 -c "$P"'
RESET(FX(restaurants=[REST(),DSTR("America/New_York",rid="r_ny")]))
b=OK(R("GET","/restaurants"),200)
rs=b["restaurants"]
assert [r["id"] for r in rs]==["r_anker","r_ny"],rs
assert rs[0]["name"]=="Zum Anker" and rs[0]["timezone"]=="Europe/Berlin",rs[0]
assert rs[1]["timezone"]=="America/New_York",rs[1]
print("PASS")'`
Passes when: prints `PASS`. No bearer token was sent.
Status: passed at 9c8c115 — see verdicts/C-15.md

### C-16: GET /restaurants/{id} is public and returns the restaurant in the fixture's shape.
Check: `python3 -c "$P"'
SETUP()
b=OK(R("GET","/restaurants/r_anker"),200)
assert b["slot_minutes"]==30 and b["reservation_duration_minutes"]==90 and b["cancellation_cutoff_minutes"]==120,b
assert b["timezone"]=="Europe/Berlin" and b["name"]=="Zum Anker",b
oh=b["opening_hours"]
assert len(oh)==7 and {o["weekday"] for o in oh}==set(WD),oh
assert all(o["opens"]=="18:00" and o["closes"]=="23:30" for o in oh),oh
assert [tb["id"] for tb in b["tables"]]==["t_1","t_2","t_3"],b["tables"]
assert [tb["capacity"] for tb in b["tables"]]==[2,4,4],b["tables"]
assert all("label" in tb for tb in b["tables"]),b["tables"]
print("PASS")'`
Passes when: prints `PASS`. No bearer token was sent.
Status: passed at 9c8c115 — see verdicts/C-16.md

### C-17: GET /restaurants/{unknown} is 404 not_found.
Check: `python3 -c "$P"'
SETUP()
ERR(R("GET","/restaurants/r_nope"),404,"not_found")
print("PASS")'`
Passes when: prints `PASS`.
Status: passed at 9c8c115 — see verdicts/C-17.md

### C-18: GET /availability is public.
Check: `python3 -c "$P"'
SETUP()
b=OK(AV("r_anker",F,4),200)
assert b["restaurant_id"]=="r_anker" and b["date"]==F and b["timezone"]=="Europe/Berlin",b
assert isinstance(b["slots"],list) and b["slots"],b
print("PASS")'`
Passes when: prints `PASS`. No bearer token was sent.
Status: passed at 9c8c115 — see verdicts/C-18.md

---

## Availability (§8)

### C-19: A slot appears for every slot_minutes step from opens while slot plus duration is at or before closes.
Check: `python3 -c "$P"'
SETUP()
got=SLOTS("r_anker",F,2)
want=[F+"T"+t for t in ["18:00","18:30","19:00","19:30","20:00","20:30","21:00","21:30","22:00"]]
assert got==want,(got,want)
print("PASS",len(got))'`
Passes when: prints `PASS 9`. Opening 18:00, closing 23:30, 30-minute grid, 90-minute duration gives exactly the nine slots from 18:00 to 22:00; 22:30 would end at 24:00, after `closes`, so it must not appear.
Status: passed at 9c8c115 — see verdicts/C-19.md

### C-20: available_table_ids lists the tables with capacity at or above party_size, in fixture order.
Check: `python3 -c "$P"'
SETUP()
assert FREE("r_anker",F,2,F+"T19:00")==["t_1","t_2","t_3"],FREE("r_anker",F,2,F+"T19:00")
assert FREE("r_anker",F,4,F+"T19:00")==["t_2","t_3"],FREE("r_anker",F,4,F+"T19:00")
assert FREE("r_anker",F,5,F+"T19:00")==[],FREE("r_anker",F,5,F+"T19:00")
print("PASS")'`
Passes when: prints `PASS`. Order follows the fixture, not sorting.
Status: passed at 9c8c115 — see verdicts/C-20.md

### C-21: A booked table disappears from every overlapping slot and from no other.
Check: `python3 -c "$P"'
t,_=SETUP()
OK(BOOK(t,F+"T19:00","k1",tid="t_2"),201)
for at in ["18:00","18:30","19:00","19:30","20:00"]:
    assert "t_2" not in FREE("r_anker",F,4,F+"T"+at),("overlap kept t_2",at)
for at in ["20:30","21:00"]:
    assert "t_2" in FREE("r_anker",F,4,F+"T"+at),("non-overlap lost t_2",at)
print("PASS")'`
Passes when: prints `PASS`. A 90-minute booking at 19:00 blocks 18:00 through 20:00 and leaves 20:30 onward free, per the half-open interval rule.
Status: passed at 9c8c115 — see verdicts/C-21.md

### C-22: A slot with no available table still appears, with an empty list.
Check: `python3 -c "$P"'
t,_=SETUP()
for i,tid in enumerate(["t_1","t_2","t_3"]):
    OK(BOOK(t,F+"T19:00","k%d"%i,tid=tid,ps=2),201)
sl=[s for s in OK(AV("r_anker",F,2),200)["slots"] if s["starts_at_local"]==F+"T19:00"]
assert len(sl)==1,sl
assert sl[0]["available_table_ids"]==[],sl
print("PASS")'`
Passes when: prints `PASS`. The 19:00 slot is present with an empty `available_table_ids`, not omitted.
Status: passed at 9c8c115 — see verdicts/C-22.md

### C-23: A closed day returns an empty slots list.
Check: `python3 -c "$P"'
RESET(FX(restaurants=[REST(opening_hours=[{"weekday":"fri","opens":"18:00","closes":"23:30"}])]))
b=OK(AV("r_anker","2027-06-10",4),200)
assert b["slots"]==[],b
assert OK(AV("r_anker","2027-06-11",4),200)["slots"],"friday should be open"
print("PASS")'`
Passes when: prints `PASS`. 2027-06-10 is a Thursday, which the fixture leaves closed; 2027-06-11 is the Friday and is open.
Status: passed at 9c8c115 — see verdicts/C-23.md

### C-24: Each of restaurant_id, date and party_size is required on GET /availability.
Check: `python3 -c "$P"'
SETUP()
ERR(R("GET","/availability?date="+F+"&party_size=4"),422,"validation_failed")
ERR(R("GET","/availability?restaurant_id=r_anker&party_size=4"),422,"validation_failed")
ERR(R("GET","/availability?restaurant_id=r_anker&date="+F),422,"validation_failed")
ERR(R("GET","/availability"),422,"validation_failed")
print("PASS")'`
Passes when: prints `PASS`.
Status: passed at 9c8c115 — see verdicts/C-24.md

### C-25: An integer-valued query parameter must be plain decimal digits.
Check: `python3 -c "$P"'
SETUP()
for bad in ["4.0","+4"," 4","1e9","0x4","four","-1","0",""]:
    ERR(AV("r_anker",F,bad),422,"validation_failed")
print("PASS")'`
Passes when: prints `PASS`. Each spelling is 422 `validation_failed` whatever its numeric value.
Status: passed at 9c8c115 — see verdicts/C-25.md

### C-26: An unparseable or impossible date on GET /availability is rejected.
Check: `python3 -c "$P"'
SETUP()
for bad in ["2027-06-31","2027-02-30","2027-13-01","10/06/2027","2027-6-1","not-a-date","2027-06-10T19:00",""]:
    ERR(AV("r_anker",bad,4),422,"validation_failed")
print("PASS")'`
Passes when: prints `PASS`.
Status: passed at 9c8c115 — see verdicts/C-26.md

### C-27: An unknown restaurant_id on GET /availability is 404 not_found.
Check: `python3 -c "$P"'
SETUP()
ERR(AV("r_nope",F,4),404,"not_found")
print("PASS")'`
Passes when: prints `PASS`.
Status: passed at 9c8c115 — see verdicts/C-27.md

### C-28: A starts_at_local taken from availability is accepted unchanged by POST /reservations.
Check: `python3 -c "$P"'
t,_=SETUP()
for sl in OK(AV("r_anker",F,4),200)["slots"]:
    at=sl["starts_at_local"]
    b=OK(BOOK(t,at,"k-"+at,tid=sl["available_table_ids"][0]),201)
    assert b["starts_at_local"]==at,(at,b["starts_at_local"])
    assert b["starts_at"]==sl["starts_at"],(sl["starts_at"],b["starts_at"])
print("PASS")'`
Passes when: prints `PASS`. Every advertised slot is bookable verbatim and echoes back the same local and absolute start.
Status: FAILED at 9c8c115 — see verdicts/C-28.md; superseded by C-153

---

## Authentication (§6)

### C-29: POST /auth/signup returns 201 with user_id, display_name and a usable token.
Check: `python3 -c "$P"'
RESET(FX())
b=OK(R("POST","/auth/signup",{"email":"zoe@example.com","password":"correct horse","display_name":"Zoe"}),201)
assert set(["user_id","display_name","token"])<=set(b),b
assert b["display_name"]=="Zoe" and isinstance(b["token"],str) and b["token"],b
assert OK(LIST(b["token"]),200)["reservations"]==[],"token unusable"
print("PASS")'`
Passes when: prints `PASS`.
Status: passed at 9c8c115 — see verdicts/C-29.md

### C-30: POST /auth/login returns 200 with user_id, display_name and a usable token.
Check: `python3 -c "$P"'
RESET(FX())
b=OK(R("POST","/auth/login",{"email":ADA["email"],"password":ADA["password"]}),200)
assert set(["user_id","display_name","token"])<=set(b),b
assert b["display_name"]=="Ada",b
assert OK(LIST(b["token"]),200)["reservations"]==[],"token unusable"
print("PASS")'`
Passes when: prints `PASS`.
Status: passed at 9c8c115 — see verdicts/C-30.md

### C-31: Signing up with an already registered email is 409 email_taken.
Check: `python3 -c "$P"'
RESET(FX())
ERR(R("POST","/auth/signup",{"email":ADA["email"],"password":"correct horse","display_name":"X"}),409,"email_taken")
OK(R("POST","/auth/signup",{"email":"zoe@example.com","password":"correct horse","display_name":"Zoe"}),201)
ERR(R("POST","/auth/signup",{"email":"zoe@example.com","password":"another one","display_name":"Y"}),409,"email_taken")
print("PASS")'`
Passes when: prints `PASS`.
Status: passed at 9c8c115 — see verdicts/C-31.md

### C-32: A password shorter than 8 characters is 422 validation_failed.
Check: `python3 -c "$P"'
RESET(FX())
for pw in ["1234567","a",""]:
    ERR(R("POST","/auth/signup",{"email":"new@example.com","password":pw,"display_name":"X"}),422,"validation_failed")
OK(R("POST","/auth/signup",{"email":"new@example.com","password":"12345678","display_name":"X"}),201)
print("PASS")'`
Passes when: prints `PASS`. Seven characters is refused and eight is accepted.
Status: passed at 9c8c115 — see verdicts/C-32.md

### C-33: An email not of the form local@domain is 422 validation_failed.
Check: `python3 -c "$P"'
RESET(FX())
for em in ["not-an-email","@example.com","ada@","ada example.com","","ada@@example.com"]:
    ERR(R("POST","/auth/signup",{"email":em,"password":"correct horse","display_name":"X"}),422,"validation_failed")
print("PASS")'`
Passes when: prints `PASS`.
Status: passed at 9c8c115 — see verdicts/C-33.md

### C-34: A wrong password or an unknown email on login is 401 unauthenticated.
Check: `python3 -c "$P"'
RESET(FX())
ERR(R("POST","/auth/login",{"email":ADA["email"],"password":"wrong password"}),401,"unauthenticated")
ERR(R("POST","/auth/login",{"email":"nobody@example.com","password":"correct horse"}),401,"unauthenticated")
print("PASS")'`
Passes when: prints `PASS`. An unknown email is 401, not 404 — the service does not disclose which accounts exist.
Status: passed at 9c8c115 — see verdicts/C-34.md

### C-35: A body field of the wrong JSON type is 400 malformed_request.
Check: `python3 -c "$P"'
RESET(FX())
ERR(R("POST","/auth/signup",{"email":17,"password":"correct horse","display_name":"X"}),400,"malformed_request")
ERR(R("POST","/auth/signup",{"email":"a@example.com","password":["x"],"display_name":"X"}),400,"malformed_request")
ERR(R("POST","/auth/login",{"email":{"a":1},"password":"correct horse"}),400,"malformed_request")
print("PASS")'`
Passes when: prints `PASS`.
Status: passed at 9c8c115 — see verdicts/C-35.md

### C-36: A protected endpoint without a bearer token is 401 unauthenticated.
Check: `python3 -c "$P"'
t,_=SETUP()
ref=OK(BOOK(t,F+"T19:00","k1"),201)["reference"]
ERR(R("GET","/reservations"),401,"unauthenticated")
ERR(R("GET","/reservations/"+ref),401,"unauthenticated")
ERR(R("POST","/reservations",{"restaurant_id":"r_anker","table_id":"t_3","starts_at_local":F+"T19:00","party_size":4},key="k9"),401,"unauthenticated")
ERR(R("PATCH","/reservations/"+ref,{"party_size":2}),401,"unauthenticated")
ERR(R("POST","/reservations/"+ref+"/cancel"),401,"unauthenticated")
ERR(R("POST","/reservation-moves",{"moves":[{"reference":ref,"table_id":"t_3"}]},key="k9"),401,"unauthenticated")
print("PASS")'`
Passes when: prints `PASS`. Every protected path refuses an anonymous caller.
Status: passed at 9c8c115 — see verdicts/C-36.md

### C-37: An unknown bearer token is 401 unauthenticated.
Check: `python3 -c "$P"'
SETUP()
ERR(LIST("not-a-real-token"),401,"unauthenticated")
ERR(LIST("x"*200),401,"unauthenticated")
print("PASS")'`
Passes when: prints `PASS`.
Status: passed at 9c8c115 — see verdicts/C-37.md

### C-38: A malformed Authorization header is 401 unauthenticated.
Check: `python3 -c "$P"'
t,_=SETUP()
for h in ["","Bearer","Bearer ","bearer","Basic "+t,t,"Token "+t]:
    ERR(R("GET","/reservations",hdr={"Authorization":h}),401,"unauthenticated")
print("PASS")'`
Passes when: prints `PASS`. A header that is present but not a well-formed bearer credential is 401, never a 5xx and never treated as authenticated.
Status: passed at 9c8c115 — see verdicts/C-38.md

### C-39: A seeded user can log in with the fixture password immediately after reset.
Check: `python3 -c "$P"'
RESET(FX())
for u in [ADA,BOB]:
    b=OK(R("POST","/auth/login",{"email":u["email"],"password":u["password"]}),200)
    assert b["display_name"]==u["display_name"],b
print("PASS")'`
Passes when: prints `PASS`.
Status: passed at 9c8c115 — see verdicts/C-39.md

### C-40: One account may hold several valid tokens at once.
Check: `python3 -c "$P"'
RESET(FX())
ts=[LOGIN(ADA) for _ in range(4)]
assert len(set(ts))==4,"tokens not distinct: %r"%ts
ref=OK(BOOK(ts[0],F+"T19:00","k1"),201)["reference"]
for t in ts:
    assert [r["reference"] for r in OK(LIST(t),200)["reservations"]]==[ref],t
print("PASS")'`
Passes when: prints `PASS`. Four concurrent sessions all see the same account's booking, and none was invalidated by a later login.
Status: passed at 9c8c115 — see verdicts/C-40.md

### C-41: No plaintext password appears anywhere in the exported state.
Check: `python3 -c "$P"'
import base64
RESET(FX())
OK(R("POST","/auth/signup",{"email":"zoe@example.com","password":"hunter2hunter2","display_name":"Zoe"}),201)
blob=json.dumps(EXPORT())
for pw in ["correct horse","hunter2hunter2"]:
    assert pw not in blob,"plaintext password in export: %r"%pw
    assert base64.b64encode(pw.encode()).decode().rstrip("=") not in blob,"base64 password in export: %r"%pw
    assert pw.encode().hex() not in blob,"hex password in export: %r"%pw
print("PASS")'`
Passes when: prints `PASS`. Neither the seeded nor a signed-up password is recoverable from the export in plain, base64 or hex form.
Status: passed at 9c8c115 — see verdicts/C-41.md

### C-42: Stored credentials carry the marker of a recognised password-hashing function.
Check: `python3 -c "$P"'
RESET(FX())
blob=json.dumps(EXPORT()).lower()
marks=["$2a$","$2b$","$2y$","$argon2","scrypt","pbkdf2","bcrypt"]
hit=[m for m in marks if m in blob]
assert hit,"no recognised KDF marker in export; markers looked for: %r"%marks
print("PASS",hit)'`
Passes when: prints `PASS` and the marker found. If the implementation uses a different but genuine password-hashing function whose serialised form matches none of these markers, `@auditor` records a fail naming the function and `@scribe` writes a replacement entry — the check is not edited.
Status: passed at 9c8c115 — see verdicts/C-42.md

---

## Creating a reservation (§8)

### C-43: POST /reservations returns 201 with the documented fields and status confirmed.
Check: `python3 -c "$P"'
t,_=SETUP()
b=OK(BOOK(t,F+"T19:00","k1"),201)
want=["reservation_id","reference","restaurant_id","table_id","party_size","status","starts_at_local","starts_at","ends_at","created_at"]
assert set(want)<=set(b),set(want)-set(b)
assert b["restaurant_id"]=="r_anker" and b["table_id"]=="t_2" and b["party_size"]==4,b
assert b["status"]=="confirmed" and b["starts_at_local"]==F+"T19:00",b
print("PASS")'`
Passes when: prints `PASS`.
Status: passed at 9c8c115 — see verdicts/C-43.md

### C-44: ends_at is starts_at plus reservation_duration_minutes.
Check: `python3 -c "$P"'
import datetime as D
t,_=SETUP()
b=OK(BOOK(t,F+"T19:00","k1"),201)
s=D.datetime.fromisoformat(b["starts_at"]); e=D.datetime.fromisoformat(b["ends_at"])
assert (e-s)==D.timedelta(minutes=90),(b["starts_at"],b["ends_at"],e-s)
RESET(FX(restaurants=[REST(reservation_duration_minutes=45)]))
t=LOGIN(ADA)
b=OK(BOOK(t,F+"T19:00","k2"),201)
s=D.datetime.fromisoformat(b["starts_at"]); e=D.datetime.fromisoformat(b["ends_at"])
assert (e-s)==D.timedelta(minutes=45),(b["starts_at"],b["ends_at"])
print("PASS")'`
Passes when: prints `PASS`. The duration comes from the restaurant's configuration, not a constant.
Status: passed at 9c8c115 — see verdicts/C-44.md

### C-45: reference is 6 to 12 characters of A-Z and 0-9.
Check: `python3 -c "$P"'
t,_=SETUP()
refs=[OK(BOOK(t,F+"T"+at,"k-"+at+tid,tid=tid,ps=2),201)["reference"] for at,tid in [("18:00","t_1"),("18:00","t_2"),("19:30","t_3"),("21:00","t_1"),("22:00","t_2")]]
for r in refs:
    assert REF.match(r),"bad reference %r"%r
print("PASS",refs)'`
Passes when: prints `PASS` and the references, each matching `^[A-Z0-9]{6,12}$`.
Status: passed at 9c8c115 — see verdicts/C-45.md

### C-46: References are unique across all reservations.
Check: `python3 -c "$P"'
t,_=SETUP()
refs=[]
for at in ["18:00","18:30","19:00","19:30","20:00","20:30","21:00","21:30","22:00"]:
    for tid in ["t_1","t_2","t_3"]:
        refs.append(OK(BOOK(t,F+"T"+at,"k-%s-%s"%(at,tid),tid=tid,ps=2),201)["reference"])
assert len(refs)==27 and len(set(refs))==27,"duplicate reference among %r"%refs
print("PASS",len(set(refs)))'`
Passes when: prints `PASS 27`.
Status: FAILED at 9c8c115 — see verdicts/C-46.md; superseded by C-154

### C-47: A table already taken for an overlapping interval is 409 table_unavailable.
Check: `python3 -c "$P"'
t,_=SETUP()
OK(BOOK(t,F+"T19:00","k1",tid="t_2"),201)
for at in ["18:00","18:30","19:00","19:30","20:00"]:
    ERR(BOOK(t,F+"T"+at,"k-"+at,tid="t_2"),409,"table_unavailable")
print("PASS")'`
Passes when: prints `PASS`. Every start whose 90-minute interval meets the existing booking is refused, not only the identical one.
Status: passed at 9c8c115 — see verdicts/C-47.md

### C-48: Occupancy is half-open, so a booking starting exactly when another ends succeeds.
Check: `python3 -c "$P"'
t,_=SETUP()
a=OK(BOOK(t,F+"T19:00","k1",tid="t_2"),201)
b=OK(BOOK(t,F+"T20:30","k2",tid="t_2"),201)
assert a["ends_at"]==b["starts_at"],(a["ends_at"],b["starts_at"])
c=OK(BOOK(t,F+"T22:00","k3",tid="t_2"),201)
assert c["status"]=="confirmed"
print("PASS")'`
Passes when: prints `PASS`. The second booking starts at the exact instant the first ends and is accepted, confirming `[starts_at, starts_at + duration)`.
Status: passed at 9c8c115 — see verdicts/C-48.md

### C-49: The same time on a different table succeeds.
Check: `python3 -c "$P"'
t,_=SETUP()
a=OK(BOOK(t,F+"T19:00","k1",tid="t_2"),201)
b=OK(BOOK(t,F+"T19:00","k2",tid="t_3"),201)
assert a["starts_at"]==b["starts_at"] and a["table_id"]!=b["table_id"],(a,b)
print("PASS")'`
Passes when: prints `PASS`.
Status: passed at 9c8c115 — see verdicts/C-49.md

### C-50: A start that is not on the slot grid is 422 not_on_slot_grid.
Check: `python3 -c "$P"'
t,_=SETUP()
for at in ["19:15","18:01","19:45","22:15"]:
    ERR(BOOK(t,F+"T"+at,"k-"+at),422,"not_on_slot_grid")
print("PASS")'`
Passes when: prints `PASS`. The grid runs in 30-minute steps from the 18:00 opening.
Status: passed at 9c8c115 — see verdicts/C-50.md

### C-51: A start outside opening hours is 422 outside_opening_hours.
Check: `python3 -c "$P"'
t,_=SETUP()
for at in ["12:00","17:30","00:00"]:
    ERR(BOOK(t,F+"T"+at,"k-"+at),422,"outside_opening_hours")
RESET(FX(restaurants=[REST(opening_hours=[{"weekday":"fri","opens":"18:00","closes":"23:30"}])]))
t=LOGIN(ADA)
ERR(BOOK(t,"2027-06-10T19:00","k9"),422,"outside_opening_hours")
print("PASS")'`
Passes when: prints `PASS`. A time before opening, after closing and a booking on a day the restaurant has no opening-hours entry are all `outside_opening_hours`.
Status: passed at 9c8c115 — see verdicts/C-51.md

### C-52: A reservation that would end after closes is 422 outside_opening_hours.
Check: `python3 -c "$P"'
t,_=SETUP()
OK(BOOK(t,F+"T22:00","k1"),201)
for at in ["22:30","23:00"]:
    ERR(BOOK(t,F+"T"+at,"k-"+at,tid="t_3"),422,"outside_opening_hours")
print("PASS")'`
Passes when: prints `PASS`. 22:00 plus 90 minutes is exactly 23:30 and is allowed; 22:30 and 23:00 would end after the close and are refused even though both are on the grid.
Status: passed at 9c8c115 — see verdicts/C-52.md

### C-53: A party_size above the table's capacity is 422 party_exceeds_capacity.
Check: `python3 -c "$P"'
t,_=SETUP()
ERR(BOOK(t,F+"T19:00","k1",tid="t_1",ps=3),422,"party_exceeds_capacity")
ERR(BOOK(t,F+"T19:00","k2",tid="t_2",ps=5),422,"party_exceeds_capacity")
OK(BOOK(t,F+"T19:00","k3",tid="t_1",ps=2),201)
print("PASS")'`
Passes when: prints `PASS`. Exactly the capacity is allowed; one more is refused.
Status: passed at 9c8c115 — see verdicts/C-53.md

### C-54: A party_size below 1 or not an integer is 422 validation_failed.
Check: `python3 -c "$P"'
t,_=SETUP()
for i,ps in enumerate([0,-1,"4",4.5,True,False,None,[4],{"n":4},"four",""]):
    ERR(BOOK(t,F+"T19:00","k%d"%i,ps=ps),422,"validation_failed")
print("PASS")'`
Passes when: prints `PASS`. Strings and booleans are 422 `validation_failed` here, not 400 — the endpoint-specific rule of §5 takes precedence.
Status: passed at 9c8c115 — see verdicts/C-54.md

### C-55: A starts_at_local that is not a bare local YYYY-MM-DDTHH:MM is 422 validation_failed.
Check: `python3 -c "$P"'
t,_=SETUP()
bad=[F+"T19:00:00",F+"T19:00Z",F+"T19:00:00+02:00",F+" 19:00",F+"T19",F,"19:00",F+"T19:00:00.000",""]
for i,at in enumerate(bad):
    ERR(BOOK(t,at,"k%d"%i),422,"validation_failed")
print("PASS")'`
Passes when: prints `PASS`. Seconds, a `Z`, an explicit offset and a space separator are all refused.
Status: passed at 9c8c115 — see verdicts/C-55.md

### C-56: An unknown restaurant, an unknown table, or a table of another restaurant is 404 not_found.
Check: `python3 -c "$P"'
RESET(FX(restaurants=[REST(),DSTR("America/New_York",rid="r_ny",opens="18:00",closes="23:30")]))
t=LOGIN(ADA)
ERR(BOOK(t,F+"T19:00","k1",rid="r_nope"),404,"not_found")
ERR(BOOK(t,F+"T19:00","k2",tid="t_nope"),404,"not_found")
ERR(BOOK(t,F+"T19:00","k3",rid="r_ny",tid="t_2"),404,"not_found")
print("PASS")'`
Passes when: prints `PASS`. The third case names a table id that exists, but under a different restaurant.
Status: FAILED at 9c8c115 — see verdicts/C-56.md; superseded by C-155

### C-57: An unparseable request body is 400 malformed_request.
Check: `python3 -c "$P"'
t,_=SETUP()
for raw in [b"{not json",b"",b"[]",b"null",b"\"string\"",b"{\"a\":}"]:
    s,b,_=R("POST","/reservations",raw,tok=t,key="k1")
    assert s==400 and b.get("error",{}).get("code")=="malformed_request",(raw,s,b)
print("PASS")'`
Passes when: prints `PASS`. A body that does not parse, and a parsed value that is not a JSON object, are both 400 `malformed_request`.
Status: passed at 9c8c115 — see verdicts/C-57.md

### C-58: A booking is not refused merely because its start is in the past.
Check: `python3 -c "$P"'
t,_=SETUP()
b=OK(BOOK(t,"2020-06-10T19:00","k1"),201)
assert b["status"]=="confirmed" and b["starts_at_local"]=="2020-06-10T19:00",b
assert "2020-06-10T19:00" in SLOTS("r_anker","2020-06-10",4)
print("PASS")'`
Passes when: prints `PASS`. 2020-06-10 is a Wednesday and open in the fixture; the booking is confirmed despite being years in the past.
Status: passed at 9c8c115 — see verdicts/C-58.md

### C-59: No request produces a 5xx response.
Check: `python3 -c "$P"'
t,_=SETUP()
ref=OK(BOOK(t,F+"T19:00","k0"),201)["reference"]
probes=[("POST","/reservations",{"restaurant_id":"r_anker","table_id":"t_2","starts_at_local":F+"T19:00","party_size":p},t,"p%d"%i) for i,p in enumerate([0,-1,"4",4.5,True,None,[4],{"n":1},10**12,"four"])]
probes+=[("POST","/reservations",b"{bad",t,"x1"),("GET","/availability?restaurant_id=&date=&party_size=",None,None,None)]
probes+=[("PATCH","/reservations/"+ref,{"party_size":[1]},t,None),("GET","/reservations/"+"z"*300,None,t,None)]
probes+=[("POST","/reservation-moves",{"moves":"nope"},t,"m1"),("POST","/_test/import",{"track":"x"},None,None)]
probes+=[("POST","/_test/reset",b"{",None,None),("GET","/nope",None,None,None),("DELETE","/reservations/"+ref,None,t,None)]
bad=[]
for m,p,bd,tk,k in probes:
    s,b,_=R(m,p,bd,tok=tk,key=k)
    if s>=500: bad.append((m,p,s,b))
assert not bad,"5xx responses: %r"%bad
print("PASS")'`
Passes when: prints `PASS`. Every hostile input returns a 4xx or a success, never a 5xx.
Status: passed at 9c8c115 — see verdicts/C-59.md

---

## Reading reservations (§8)

### C-60: GET /reservations returns only the caller's reservations, starts_at descending, confirmed and cancelled alike.
Check: `python3 -c "$P"'
ta,tb=SETUP()
a1=OK(BOOK(ta,F+"T19:00","a1",tid="t_2"),201)
a2=OK(BOOK(ta,F+"T21:00","a2",tid="t_2"),201)
a3=OK(BOOK(ta,F+"T18:00","a3",tid="t_1",ps=2),201)
b1=OK(BOOK(tb,F+"T19:00","b1",tid="t_3"),201)
OK(CANCEL(ta,a3["reference"]),200)
rs=OK(LIST(ta),200)["reservations"]
assert [r["reference"] for r in rs]==[a2["reference"],a1["reference"],a3["reference"]],[r["starts_at"] for r in rs]
assert b1["reference"] not in [r["reference"] for r in rs],"leaked another caller"
assert [r["status"] for r in rs]==["confirmed","confirmed","cancelled"],rs
assert set(["reservation_id","reference","ends_at","created_at"])<=set(rs[0]),rs[0]
print("PASS")'`
Passes when: prints `PASS`. Ordering is by `starts_at` descending, the cancelled booking is still listed, and the other account's booking is absent.
Status: passed at 9c8c115 — see verdicts/C-60.md

### C-61: An empty reservation list is returned as an empty array.
Check: `python3 -c "$P"'
ta,_=SETUP()
b=OK(LIST(ta),200)
assert b=={"reservations":[]},b
print("PASS",b)'`
Passes when: prints `PASS {'reservations': []}` — the key is present with an empty array, not omitted and not null.
Status: passed at 9c8c115 — see verdicts/C-61.md

### C-62: GET /reservations/{reference} returns the caller's booking and 404 for anyone else's.
Check: `python3 -c "$P"'
ta,tb=SETUP()
a=OK(BOOK(ta,F+"T19:00","a1"),201)
got=OK(GETR(ta,a["reference"]),200)
assert got["reference"]==a["reference"] and got["reservation_id"]==a["reservation_id"],got
ERR(GETR(tb,a["reference"]),404,"not_found")
print("PASS")'`
Passes when: prints `PASS`. The other account gets 404 `not_found`, not 403 — the existence of the booking is not disclosed.
Status: passed at 9c8c115 — see verdicts/C-62.md

### C-63: An unknown reference is 404 not_found.
Check: `python3 -c "$P"'
ta,_=SETUP()
for ref in ["ZZZZZZ","ABC123","nope","z"*100]:
    ERR(GETR(ta,ref),404,"not_found")
print("PASS")'`
Passes when: prints `PASS`.
Status: passed at 9c8c115 — see verdicts/C-63.md

---

## Cancelling (§8)

### C-64: Cancelling sets status cancelled and frees the table immediately.
Check: `python3 -c "$P"'
ta,_=SETUP()
a=OK(BOOK(ta,F+"T19:00","a1",tid="t_2"),201)
assert "t_2" not in FREE("r_anker",F,4,F+"T19:00")
b=OK(CANCEL(ta,a["reference"]),200)
assert b["status"]=="cancelled" and b["reference"]==a["reference"],b
assert "t_2" in FREE("r_anker",F,4,F+"T19:00"),"slot not freed"
OK(BOOK(ta,F+"T19:00","a2",tid="t_2"),201)
print("PASS")'`
Passes when: prints `PASS`. The next availability offers the slot again and it is genuinely re-bookable.
Status: passed at 9c8c115 — see verdicts/C-64.md

### C-65: Cancelling twice is not an error.
Check: `python3 -c "$P"'
ta,_=SETUP()
a=OK(BOOK(ta,F+"T19:00","a1"),201)
one=OK(CANCEL(ta,a["reference"]),200)
two=OK(CANCEL(ta,a["reference"]),200)
assert two["status"]=="cancelled" and two["reference"]==a["reference"],two
assert two["reservation_id"]==a["reservation_id"],two
print("PASS")'`
Passes when: prints `PASS`. The second cancel is 200 with the current state, not a 409.
Status: passed at 9c8c115 — see verdicts/C-65.md

### C-66: Cancelling within cancellation_cutoff_minutes of the start is 409 cutoff_passed.
Check: `python3 -c "$P"'
RESET(FX(restaurants=[REST(cancellation_cutoff_minutes=60*24*3650)]))
ta=LOGIN(ADA)
a=OK(BOOK(ta,F+"T19:00","a1"),201)
ERR(CANCEL(ta,a["reference"]),409,"cutoff_passed")
assert OK(GETR(ta,a["reference"]),200)["status"]=="confirmed","refused cancel still changed state"
assert "t_2" not in FREE("r_anker",F,4,F+"T19:00"),"refused cancel freed the table"
print("PASS")'`
Passes when: prints `PASS`. A cutoff wide enough to cover the booking makes cancel 409, and the booking keeps both its status and its occupancy.
Status: passed at 9c8c115 — see verdicts/C-66.md

### C-67: Cancelling a reservation whose start has already passed is 409 cutoff_passed.
Check: `python3 -c "$P"'
RESET(FX(reservations=[SEED("SEED01","2020-06-10T19:00")]))
ta=LOGIN(ADA)
ERR(CANCEL(ta,"SEED01"),409,"cutoff_passed")
assert OK(GETR(ta,"SEED01"),200)["status"]=="confirmed"
print("PASS")'`
Passes when: prints `PASS`. "Within the cutoff of `starts_at`, or later" covers a start in the past.
Status: passed at 9c8c115 — see verdicts/C-67.md

### C-68: Cancelling someone else's reservation is 404 not_found.
Check: `python3 -c "$P"'
ta,tb=SETUP()
a=OK(BOOK(ta,F+"T19:00","a1"),201)
ERR(CANCEL(tb,a["reference"]),404,"not_found")
assert OK(GETR(ta,a["reference"]),200)["status"]=="confirmed"
print("PASS")'`
Passes when: prints `PASS`.
Status: passed at 9c8c115 — see verdicts/C-68.md

---

## Amending (§8)

### C-69: PATCH changes the table, frees the old one and occupies the new one.
Check: `python3 -c "$P"'
ta,_=SETUP()
a=OK(BOOK(ta,F+"T19:00","a1",tid="t_2"),201)
b=OK(PATCHR(ta,a["reference"],{"table_id":"t_3"}),200)
assert b["table_id"]=="t_3",b
fr=FREE("r_anker",F,4,F+"T19:00")
assert "t_2" in fr and "t_3" not in fr,fr
print("PASS")'`
Passes when: prints `PASS`.
Status: passed at 9c8c115 — see verdicts/C-69.md

### C-70: PATCH requires no idempotency key.
Check: `python3 -c "$P"'
ta,_=SETUP()
a=OK(BOOK(ta,F+"T19:00","a1"),201)
s,b,_=R("PATCH","/reservations/"+a["reference"],{"party_size":2},tok=ta)
assert s==200,(s,b)
print("PASS")'`
Passes when: prints `PASS`. No `Idempotency-Key` header was sent and the amendment still succeeded.
Status: passed at 9c8c115 — see verdicts/C-70.md

### C-71: reference and reservation_id survive a change.
Check: `python3 -c "$P"'
ta,_=SETUP()
a=OK(BOOK(ta,F+"T19:00","a1",tid="t_2"),201)
b=OK(PATCHR(ta,a["reference"],{"table_id":"t_3","starts_at_local":F+"T21:00","party_size":2}),200)
assert b["reference"]==a["reference"] and b["reservation_id"]==a["reservation_id"],(a,b)
assert b["created_at"]==a["created_at"],(a["created_at"],b["created_at"])
assert b["table_id"]=="t_3" and b["starts_at_local"]==F+"T21:00" and b["party_size"]==2,b
print("PASS")'`
Passes when: prints `PASS`. Identity and creation time are untouched while the changed fields take effect.
Status: passed at 9c8c115 — see verdicts/C-71.md

### C-72: PATCH validation is identical to POST /reservations.
Check: `python3 -c "$P"'
ta,_=SETUP()
a=OK(BOOK(ta,F+"T19:00","a1",tid="t_2"),201)
r=a["reference"]
ERR(PATCHR(ta,r,{"starts_at_local":F+"T19:15"}),422,"not_on_slot_grid")
ERR(PATCHR(ta,r,{"starts_at_local":F+"T12:00"}),422,"outside_opening_hours")
ERR(PATCHR(ta,r,{"starts_at_local":F+"T22:30"}),422,"outside_opening_hours")
ERR(PATCHR(ta,r,{"table_id":"t_1"}),422,"party_exceeds_capacity")
ERR(PATCHR(ta,r,{"party_size":0}),422,"validation_failed")
ERR(PATCHR(ta,r,{"party_size":"4"}),422,"validation_failed")
ERR(PATCHR(ta,r,{"starts_at_local":F+"T19:00:00"}),422,"validation_failed")
ERR(PATCHR(ta,r,{"table_id":"t_nope"}),404,"not_found")
print("PASS")'`
Passes when: prints `PASS`. Each create-side error code appears unchanged on the amendment path.
Status: passed at 9c8c115 — see verdicts/C-72.md

### C-73: PATCH onto a table taken for an overlapping interval is 409 table_unavailable.
Check: `python3 -c "$P"'
ta,_=SETUP()
a=OK(BOOK(ta,F+"T19:00","a1",tid="t_2"),201)
OK(BOOK(ta,F+"T19:00","a2",tid="t_3"),201)
ERR(PATCHR(ta,a["reference"],{"table_id":"t_3"}),409,"table_unavailable")
print("PASS")'`
Passes when: prints `PASS`.
Status: passed at 9c8c115 — see verdicts/C-73.md

### C-74: A failed amendment leaves the original booking and its occupancy unchanged.
Check: `python3 -c "$P"'
ta,_=SETUP()
a=OK(BOOK(ta,F+"T19:00","a1",tid="t_2"),201)
OK(BOOK(ta,F+"T21:00","a2",tid="t_3"),201)
before=OK(GETR(ta,a["reference"]),200)
for body,st,code in [({"table_id":"t_3","starts_at_local":F+"T21:00"},409,"table_unavailable"),
                     ({"starts_at_local":F+"T19:15"},422,"not_on_slot_grid"),
                     ({"table_id":"t_1"},422,"party_exceeds_capacity"),
                     ({"starts_at_local":F+"T12:00"},422,"outside_opening_hours"),
                     ({"table_id":"t_nope"},404,"not_found")]:
    ERR(PATCHR(ta,a["reference"],body),st,code)
    after=OK(GETR(ta,a["reference"]),200)
    assert after==before,"failed amendment changed the booking: %r -> %r"%(before,after)
fr=FREE("r_anker",F,4,F+"T19:00")
assert "t_2" not in fr and "t_3" in fr,fr
assert "t_3" not in FREE("r_anker",F,4,F+"T21:00")
print("PASS")'`
Passes when: prints `PASS`. After five different refused amendments the booking is identical to before and both the old table and the other table hold exactly their original occupancy.
Status: passed at 9c8c115 — see verdicts/C-74.md

### C-75: Amending a cancelled reservation is 409 reservation_cancelled.
Check: `python3 -c "$P"'
ta,_=SETUP()
a=OK(BOOK(ta,F+"T19:00","a1"),201)
OK(CANCEL(ta,a["reference"]),200)
ERR(PATCHR(ta,a["reference"],{"table_id":"t_3"}),409,"reservation_cancelled")
ERR(PATCHR(ta,a["reference"],{"party_size":2}),409,"reservation_cancelled")
print("PASS")'`
Passes when: prints `PASS`.
Status: passed at 9c8c115 — see verdicts/C-75.md

### C-76: The amendment cutoff is measured against the current start time, not the requested one.
Check: `python3 -c "$P"'
RESET(FX(restaurants=[REST(cancellation_cutoff_minutes=60*24*3650)]))
ta=LOGIN(ADA)
a=OK(BOOK(ta,F+"T19:00","a1",tid="t_2"),201)
ERR(PATCHR(ta,a["reference"],{"starts_at_local":"2037-06-11T19:00"}),409,"cutoff_passed")
ERR(PATCHR(ta,a["reference"],{"table_id":"t_3"}),409,"cutoff_passed")
ERR(PATCHR(ta,a["reference"],{"party_size":2}),409,"cutoff_passed")
assert OK(GETR(ta,a["reference"]),200)==a,"refused amendment changed the booking"
print("PASS")'`
Passes when: prints `PASS`. Moving the booking far beyond the cutoff is still refused, because the cutoff is judged on where the booking currently starts.
Status: passed at 9c8c115 — see verdicts/C-76.md

### C-77: Amending someone else's reservation is 404 not_found.
Check: `python3 -c "$P"'
ta,tb=SETUP()
a=OK(BOOK(ta,F+"T19:00","a1"),201)
ERR(PATCHR(tb,a["reference"],{"party_size":2}),404,"not_found")
ERR(PATCHR(tb,"ZZZZZZ",{"party_size":2}),404,"not_found")
print("PASS")'`
Passes when: prints `PASS`.
Status: passed at 9c8c115 — see verdicts/C-77.md

### C-78: Fields omitted from a PATCH keep their current values.
Check: `python3 -c "$P"'
ta,_=SETUP()
a=OK(BOOK(ta,F+"T19:00","a1",tid="t_2",ps=4),201)
b=OK(PATCHR(ta,a["reference"],{"party_size":2}),200)
assert b["party_size"]==2,b
assert b["table_id"]==a["table_id"] and b["starts_at_local"]==a["starts_at_local"],b
assert b["starts_at"]==a["starts_at"] and b["ends_at"]==a["ends_at"],b
c=OK(PATCHR(ta,a["reference"],{}),200)
assert c["party_size"]==2 and c["table_id"]=="t_2" and c["starts_at_local"]==F+"T19:00",c
print("PASS")'`
Passes when: prints `PASS`. An empty PATCH body changes nothing and is not an error.
Status: passed at 9c8c115 — see verdicts/C-78.md

---

## Idempotency (§7)

### C-79: The first use of a key is 201 and a replay with the same body is 200 with an identical body.
Check: `python3 -c "$P"'
ta,_=SETUP()
body={"restaurant_id":"r_anker","table_id":"t_2","starts_at_local":F+"T19:00","party_size":4}
s1,b1,_=R("POST","/reservations",body,tok=ta,key="key-1")
assert s1==201,(s1,b1)
for _ in range(3):
    s2,b2,_=R("POST","/reservations",body,tok=ta,key="key-1")
    assert s2==200,(s2,b2)
    assert b2==b1,"replay body differs: %r vs %r"%(b1,b2)
assert len(OK(LIST(ta),200)["reservations"])==1,"replay created a second booking"
print("PASS")'`
Passes when: prints `PASS`. Three replays all return 200 with the identical JSON value and exactly one booking exists.
Status: passed at 9c8c115 — see verdicts/C-79.md

### C-80: A missing or empty Idempotency-Key is 400 missing_idempotency_key.
Check: `python3 -c "$P"'
ta,_=SETUP()
body={"restaurant_id":"r_anker","table_id":"t_2","starts_at_local":F+"T19:00","party_size":4}
s,b,_=R("POST","/reservations",body,tok=ta)
assert s==400 and b["error"]["code"]=="missing_idempotency_key",(s,b)
ERR(R("POST","/reservations",body,tok=ta,key=""),400,"missing_idempotency_key")
ERR(R("POST","/reservation-moves",{"moves":[{"reference":"ZZZZZZ"}]},tok=ta),400,"missing_idempotency_key")
ERR(R("POST","/reservation-moves",{"moves":[{"reference":"ZZZZZZ"}]},tok=ta,key=""),400,"missing_idempotency_key")
print("PASS")'`
Passes when: prints `PASS`. Both keyed write paths refuse an absent and an empty key with 400, and the moves case is refused before its unknown reference would give 404.
Status: passed at 9c8c115 — see verdicts/C-80.md

### C-81: An Idempotency-Key longer than 255 characters is 422 validation_failed.
Check: `python3 -c "$P"'
ta,_=SETUP()
body={"restaurant_id":"r_anker","table_id":"t_2","starts_at_local":F+"T19:00","party_size":4}
ERR(R("POST","/reservations",body,tok=ta,key="k"*256),422,"validation_failed")
ERR(R("POST","/reservations",body,tok=ta,key="k"*4000),422,"validation_failed")
OK(R("POST","/reservations",body,tok=ta,key="k"*255),201)
print("PASS")'`
Passes when: prints `PASS`. Exactly 255 characters is accepted and 256 is refused.
Status: passed at 9c8c115 — see verdicts/C-81.md

### C-82: The same key with a different body is 409 idempotency_key_reuse.
Check: `python3 -c "$P"'
ta,_=SETUP()
body={"restaurant_id":"r_anker","table_id":"t_2","starts_at_local":F+"T19:00","party_size":4}
OK(R("POST","/reservations",body,tok=ta,key="key-1"),201)
ERR(R("POST","/reservations",dict(body,party_size=3),tok=ta,key="key-1"),409,"idempotency_key_reuse")
ERR(R("POST","/reservations",dict(body,table_id="t_3"),tok=ta,key="key-1"),409,"idempotency_key_reuse")
assert len(OK(LIST(ta),200)["reservations"])==1
print("PASS")'`
Passes when: prints `PASS`.
Status: passed at 9c8c115 — see verdicts/C-82.md

### C-83: Idempotency is resolved before field validation, so a used key with a different invalid body is still 409.
Check: `python3 -c "$P"'
ta,_=SETUP()
body={"restaurant_id":"r_anker","table_id":"t_2","starts_at_local":F+"T19:00","party_size":4}
OK(R("POST","/reservations",body,tok=ta,key="key-1"),201)
for alt in [dict(body,party_size=0),dict(body,party_size="four"),dict(body,starts_at_local=F+"T19:15"),
            dict(body,starts_at_local=F+"T12:00"),dict(body,table_id="t_nope"),dict(body,restaurant_id="r_nope"),
            dict(body,table_id="t_1"),{}]:
    ERR(R("POST","/reservations",alt,tok=ta,key="key-1"),409,"idempotency_key_reuse")
print("PASS")'`
Passes when: prints `PASS`. Each of these bodies would be 422 or 404 on a fresh key; with a used key the reuse conflict wins.
Status: passed at 9c8c115 — see verdicts/C-83.md

### C-84: The same key with the same body on a different path is a different request and succeeds.
Check: `python3 -c "$P"'
ta,_=SETUP()
a=OK(BOOK(ta,F+"T19:00","shared-key",tid="t_2"),201)
s,b,_=R("POST","/reservation-moves",{"moves":[{"reference":a["reference"],"table_id":"t_3"}]},tok=ta,key="shared-key")
assert s==201,"moves with a key already used by POST /reservations: %s %r"%(s,b)
assert b["reservations"][0]["table_id"]=="t_3",b
print("PASS")'`
Passes when: prints `PASS`. A key spent on `POST /reservations` does not block `POST /reservation-moves`.
Status: passed at 9c8c115 — see verdicts/C-84.md

### C-85: A key reused after the original request failed with 4xx is treated as a first use.
Check: `python3 -c "$P"'
ta,_=SETUP()
ERR(BOOK(ta,F+"T19:15","key-1"),422,"not_on_slot_grid")
b=OK(BOOK(ta,F+"T19:00","key-1"),201)
assert b["status"]=="confirmed",b
ERR(BOOK(ta,F+"T21:00","key-2",tid="t_1",ps=4),422,"party_exceeds_capacity")
OK(BOOK(ta,F+"T21:00","key-2",tid="t_3"),201)
ERR(BOOK(ta,F+"T19:00","key-3",tid="t_2"),409,"table_unavailable")
OK(BOOK(ta,F+"T22:00","key-3",tid="t_2"),201)
assert len(OK(LIST(ta),200)["reservations"])==3
print("PASS")'`
Passes when: prints `PASS`. A key burnt on a 422 and on a 409 is reusable, and the later different body is accepted rather than reported as reuse.
Status: passed at 9c8c115 — see verdicts/C-85.md

### C-86: An idempotency key is scoped to the authenticated user.
Check: `python3 -c "$P"'
ta,tb=SETUP()
a=OK(BOOK(ta,F+"T19:00","shared",tid="t_2"),201)
b=OK(BOOK(tb,F+"T19:00","shared",tid="t_3"),201)
assert b["reference"]!=a["reference"] and b["table_id"]=="t_3",(a,b)
s,c,_=R("POST","/reservations",{"restaurant_id":"r_anker","table_id":"t_1","starts_at_local":F+"T21:00","party_size":2},tok=tb,key="shared")
assert s==409 and c["error"]["code"]=="idempotency_key_reuse",(s,c)
print("PASS")'`
Passes when: prints `PASS`. The second account books normally with the same key string, and its own reuse of that key is then detected independently.
Status: passed at 9c8c115 — see verdicts/C-86.md

### C-87: A replay returns the original response even after the reservation is cancelled, and makes no further change.
Check: `python3 -c "$P"'
ta,_=SETUP()
body={"restaurant_id":"r_anker","table_id":"t_2","starts_at_local":F+"T19:00","party_size":4}
first=OK(R("POST","/reservations",body,tok=ta,key="key-1"),201)
OK(CANCEL(ta,first["reference"]),200)
replay=OK(R("POST","/reservations",body,tok=ta,key="key-1"),200)
assert replay==first,"replay differs from original: %r vs %r"%(first,replay)
assert replay["status"]=="confirmed","replay must echo the original confirmed body"
assert OK(GETR(ta,first["reference"]),200)["status"]=="cancelled","replay resurrected the booking"
assert "t_2" in FREE("r_anker",F,4,F+"T19:00"),"replay re-took the table"
assert len(OK(LIST(ta),200)["reservations"])==1
print("PASS")'`
Passes when: prints `PASS`. The replay echoes the stored `confirmed` response while the live booking stays cancelled and its table stays free.
Status: passed at 9c8c115 — see verdicts/C-87.md

### C-88: Key order and whitespace do not make a body different.
Check: `python3 -c "$P"'
ta,_=SETUP()
first=OK(R("POST","/reservations",{"restaurant_id":"r_anker","table_id":"t_2","starts_at_local":F+"T19:00","party_size":4},tok=ta,key="key-1"),201)
raw=("{  \"party_size\" : 4 ,\n \"starts_at_local\":\"%sT19:00\", \"table_id\" :\"t_2\",\n\n  \"restaurant_id\" : \"r_anker\"  }"%F).encode()
s,b,_=R("POST","/reservations",raw,tok=ta,key="key-1")
assert s==200,"reordered/whitespaced body not treated as a replay: %s %r"%(s,b)
assert b==first,b
print("PASS")'`
Passes when: prints `PASS`. The same JSON value written differently replays rather than conflicting.
Status: passed at 9c8c115 — see verdicts/C-88.md

### C-89: Concurrent identical requests with an unused key yield exactly one 201 and one booking.
Check: `python3 -c "$P"'
ta,_=SETUP()
body={"restaurant_id":"r_anker","table_id":"t_2","starts_at_local":F+"T19:00","party_size":4}
rs=PAR(20,lambda i:R("POST","/reservations",body,tok=ta,key="race-key"))
cs=CODES(rs)
assert all(isinstance(c,int) for c in cs),rs
assert cs.count(201)==1,"expected exactly one 201, got %r"%cs
assert cs.count(200)==19,cs
assert not [c for c in cs if c>=500],cs
bodies={json.dumps(r[1],sort_keys=True) for r in rs}
assert len(bodies)==1,"concurrent replies differ: %r"%bodies
assert len(OK(LIST(ta),200)["reservations"])==1,"operation took effect more than once"
print("PASS",cs.count(201),cs.count(200))'`
Passes when: prints `PASS 1 19`. Twenty simultaneous identical requests produce one 201, nineteen 200s, a single response body and exactly one reservation.
Status: passed at 9c8c115 — see verdicts/C-89.md

---

## Concurrency (§1, §2)

### C-90: Fifty concurrent requests for one table and slot produce exactly one confirmed booking and no 5xx.
Check: `python3 -c "$P"'
ta,_=SETUP()
rs=PAR(50,lambda i:BOOK(ta,F+"T19:00","distinct-%d"%i,tid="t_2"))
cs=CODES(rs)
assert not [c for c in cs if not isinstance(c,int) or c>=500],"5xx or transport failure: %r"%rs
assert cs.count(201)==1,"expected exactly one 201, got %r"%cs
assert cs.count(409)==49,"expected 49 conflicts, got %r"%cs
for r in rs:
    if r[0]==409: assert r[1]["error"]["code"]=="table_unavailable",r[1]
res=[x for x in OK(LIST(ta),200)["reservations"] if x["status"]=="confirmed"]
assert len(res)==1,"double booking: %r"%res
assert "t_2" not in FREE("r_anker",F,4,F+"T19:00")
print("PASS")'`
Passes when: prints `PASS`. Fifty in-flight requests with distinct keys leave one booking; the other forty-nine are 409 `table_unavailable` and none is a 5xx.
Status: passed at 9c8c115 — see verdicts/C-90.md

### C-91: Fifty concurrent mixed reads and writes produce no 5xx.
Check: `python3 -c "$P"'
ta,tb=SETUP()
seed=OK(BOOK(ta,F+"T18:00","seed",tid="t_1",ps=2),201)
ats=["19:00","19:30","20:00","21:00","22:00"]
def job(i):
    m=i%5
    if m==0: return AV("r_anker",F,4)
    if m==1: return LIST(ta)
    if m==2: return BOOK(ta,F+"T"+ats[(i//5)%5],"mix-%d"%i,tid=["t_2","t_3"][i%2])
    if m==3: return PATCHR(ta,seed["reference"],{"party_size":1+(i%2)})
    return R("GET","/restaurants/r_anker")
rs=PAR(50,job)
bad=[r for r in rs if not isinstance(r[0],int) or r[0]>=500]
assert not bad,"5xx or transport failure: %r"%bad
assert OK(R("GET","/health"),200)=={"status":"ok"},"service unhealthy after load"
print("PASS",sorted(set(r[0] for r in rs)))'`
Passes when: prints `PASS` and the set of observed statuses, all below 500, with the service still healthy afterwards.
Status: passed at 9c8c115 — see verdicts/C-91.md

---

## Time and daylight saving (§9)

### C-92: Booking a local time skipped by Europe/Berlin's spring-forward is 422 invalid_local_time.
Check: `python3 -c "$P"'
RESET(FX(restaurants=[DSTR("Europe/Berlin")]))
ta=LOGIN(ADA)
for at in ["02:00","02:30"]:
    ERR(BOOK(ta,"2026-03-29T"+at,"k-"+at,rid="r_dst"),422,"invalid_local_time")
OK(BOOK(ta,"2026-03-29T01:30","k-ok",rid="r_dst"),201)
print("PASS")'`
Passes when: prints `PASS`. 02:00 and 02:30 do not exist on 2026-03-29 in Berlin; 01:30 does and is bookable.
Status: passed at 9c8c115 — see verdicts/C-92.md

### C-93: Local times skipped by Europe/Berlin's spring-forward never appear in availability.
Check: `python3 -c "$P"'
RESET(FX(restaurants=[DSTR("Europe/Berlin")]))
got=SLOTS("r_dst","2026-03-29",4)
want=["2026-03-29T"+t for t in ["01:00","01:30","03:00","03:30","04:00","04:30"]]
assert got==want,(got,want)
print("PASS",len(got))'`
Passes when: prints `PASS 6`. The 01:00-to-06:00 window yields six slots: the 02:00 and 02:30 steps are absent because those local times do not exist.
Status: passed at 9c8c115 — see verdicts/C-93.md

### C-94: A local time repeated by Europe/Berlin's fall-back appears exactly once in availability.
Check: `python3 -c "$P"'
RESET(FX(restaurants=[DSTR("Europe/Berlin")]))
got=SLOTS("r_dst","2026-10-25",4)
want=["2026-10-25T"+t for t in ["01:00","01:30","02:00","02:30","03:00","03:30","04:00","04:30"]]
assert got==want,(got,want)
for at in want:
    assert got.count(at)==1,("repeated slot",at,got)
sl={s["starts_at_local"]:s["starts_at"] for s in OK(AV("r_dst","2026-10-25",4),200)["slots"]}
assert sl["2026-10-25T02:00"]=="2026-10-25T02:00:00+02:00",sl["2026-10-25T02:00"]
assert sl["2026-10-25T02:30"]=="2026-10-25T02:30:00+02:00",sl["2026-10-25T02:30"]
print("PASS",len(got))'`
Passes when: prints `PASS 8`. The repeated 02:00 and 02:30 each appear once, and the offset advertised is `+02:00`, the first occurrence.
Status: passed at 9c8c115 — see verdicts/C-94.md

### C-95: Europe/Berlin's repeated hour resolves to the first occurrence.
Check: `python3 -c "$P"'
RESET(FX(restaurants=[DSTR("Europe/Berlin")]))
ta=LOGIN(ADA)
b=OK(BOOK(ta,"2026-10-25T02:00","k1",rid="r_dst",tid="t_2"),201)
assert b["starts_at"]=="2026-10-25T02:00:00+02:00","expected the pre-change offset, got %r"%b["starts_at"]
assert "t_2" not in FREE("r_dst","2026-10-25",4,"2026-10-25T02:00")
print("PASS",b["starts_at"])'`
Passes when: prints `PASS 2026-10-25T02:00:00+02:00`. The booking landed on the instant before the clocks changed, not the one after.
Status: passed at 9c8c115 — see verdicts/C-95.md

### C-96: Booking a local time skipped by America/New_York's spring-forward is 422 invalid_local_time.
Check: `python3 -c "$P"'
RESET(FX(restaurants=[DSTR("America/New_York")]))
ta=LOGIN(ADA)
for at in ["02:00","02:30"]:
    ERR(BOOK(ta,"2026-03-08T"+at,"k-"+at,rid="r_dst"),422,"invalid_local_time")
OK(BOOK(ta,"2026-03-08T01:30","k-ok",rid="r_dst"),201)
print("PASS")'`
Passes when: prints `PASS`.
Status: passed at 9c8c115 — see verdicts/C-96.md

### C-97: Local times skipped by America/New_York's spring-forward never appear in availability.
Check: `python3 -c "$P"'
RESET(FX(restaurants=[DSTR("America/New_York")]))
got=SLOTS("r_dst","2026-03-08",4)
want=["2026-03-08T"+t for t in ["01:00","01:30","03:00","03:30","04:00","04:30"]]
assert got==want,(got,want)
print("PASS",len(got))'`
Passes when: prints `PASS 6`.
Status: passed at 9c8c115 — see verdicts/C-97.md

### C-98: A local time repeated by America/New_York's fall-back appears exactly once in availability.
Check: `python3 -c "$P"'
RESET(FX(restaurants=[DSTR("America/New_York")]))
got=SLOTS("r_dst","2026-11-01",4)
want=["2026-11-01T"+t for t in ["01:00","01:30","02:00","02:30","03:00","03:30","04:00","04:30"]]
assert got==want,(got,want)
sl={s["starts_at_local"]:s["starts_at"] for s in OK(AV("r_dst","2026-11-01",4),200)["slots"]}
assert sl["2026-11-01T01:00"]=="2026-11-01T01:00:00-04:00",sl["2026-11-01T01:00"]
assert sl["2026-11-01T01:30"]=="2026-11-01T01:30:00-04:00",sl["2026-11-01T01:30"]
print("PASS",len(got))'`
Passes when: prints `PASS 8`. The repeated 01:00 and 01:30 each appear once, advertised at `-04:00`, the first occurrence.
Status: passed at 9c8c115 — see verdicts/C-98.md

### C-99: America/New_York's repeated hour resolves to the first occurrence.
Check: `python3 -c "$P"'
RESET(FX(restaurants=[DSTR("America/New_York")]))
ta=LOGIN(ADA)
b=OK(BOOK(ta,"2026-11-01T01:30","k1",rid="r_dst",tid="t_2"),201)
assert b["starts_at"]=="2026-11-01T01:30:00-04:00","expected the pre-change offset, got %r"%b["starts_at"]
print("PASS",b["starts_at"])'`
Passes when: prints `PASS 2026-11-01T01:30:00-04:00`.
Status: passed at 9c8c115 — see verdicts/C-99.md

### C-100: reservation_duration_minutes is absolute time, so a booking across a fall-back ends 90 real minutes later.
Check: `python3 -c "$P"'
import datetime as D
RESET(FX(restaurants=[DSTR("America/New_York")]))
ta=LOGIN(ADA)
b=OK(BOOK(ta,"2026-11-01T01:30","k1",rid="r_dst",tid="t_2"),201)
assert b["starts_at"]=="2026-11-01T01:30:00-04:00",b["starts_at"]
assert b["ends_at"]=="2026-11-01T02:00:00-05:00","expected local 02:00 at -05:00, got %r"%b["ends_at"]
s=D.datetime.fromisoformat(b["starts_at"]); e=D.datetime.fromisoformat(b["ends_at"])
assert (e-s)==D.timedelta(minutes=90),(e-s)
print("PASS",b["ends_at"])'`
Passes when: prints `PASS 2026-11-01T02:00:00-05:00`. This is the specification's own example: the local `ends_at` reads 02:00, not 03:00, and the elapsed absolute time is exactly 90 minutes.
Status: passed at 9c8c115 — see verdicts/C-100.md

### C-101: A Europe/Berlin booking across the fall-back also ends 90 real minutes later.
Check: `python3 -c "$P"'
import datetime as D
RESET(FX(restaurants=[DSTR("Europe/Berlin")]))
ta=LOGIN(ADA)
b=OK(BOOK(ta,"2026-10-25T02:00","k1",rid="r_dst",tid="t_2"),201)
assert b["starts_at"]=="2026-10-25T02:00:00+02:00",b["starts_at"]
assert b["ends_at"]=="2026-10-25T02:30:00+01:00","expected local 02:30 at +01:00, got %r"%b["ends_at"]
s=D.datetime.fromisoformat(b["starts_at"]); e=D.datetime.fromisoformat(b["ends_at"])
assert (e-s)==D.timedelta(minutes=90),(e-s)
print("PASS",b["ends_at"])'`
Passes when: prints `PASS 2026-10-25T02:30:00+01:00`. Starting at 02:00 the wall clock reads 02:30 ninety real minutes later, because the hour repeated.
Status: passed at 9c8c115 — see verdicts/C-101.md

### C-102: Offsets follow the IANA rules on both sides of each transition, in both zones.
Check: `python3 -c "$P"'
RESET(FX(restaurants=[DSTR("Europe/Berlin",rid="r_de",opens="18:00",closes="23:30"),
                      DSTR("America/New_York",rid="r_us",opens="18:00",closes="23:30")]))
ta=LOGIN(ADA)
cases=[("r_de","2026-03-28","+01:00"),("r_de","2026-03-30","+02:00"),
       ("r_de","2026-10-24","+02:00"),("r_de","2026-10-26","+01:00"),
       ("r_us","2026-03-07","-05:00"),("r_us","2026-03-09","-04:00"),
       ("r_us","2026-10-31","-04:00"),("r_us","2026-11-02","-05:00")]
for rid,d,off in cases:
    b=OK(BOOK(ta,d+"T19:00","k-%s-%s"%(rid,d),rid=rid,tid="t_2"),201)
    assert b["starts_at"]==d+"T19:00:00"+off,"%s %s: got %r want offset %s"%(rid,d,b["starts_at"],off)
    sl={s["starts_at_local"]:s["starts_at"] for s in OK(AV(rid,d,4),200)["slots"]}
    assert sl[d+"T19:00"]==d+"T19:00:00"+off,(rid,d,sl[d+"T19:00"])
print("PASS")'`
Passes when: prints `PASS`. All eight dates, either side of both transitions in both zones, carry the offset the IANA rules give, consistently in bookings and in availability.
Status: passed at 9c8c115 — see verdicts/C-102.md

### C-103: A restaurant's times follow its own timezone, so two zones reach the same instant from different local times.
Check: `python3 -c "$P"'
import datetime as D
RESET(FX(restaurants=[DSTR("Europe/Berlin",rid="r_de",opens="12:00",closes="23:30"),
                      DSTR("America/New_York",rid="r_us",opens="06:00",closes="23:30")]))
ta=LOGIN(ADA)
de=OK(BOOK(ta,F+"T19:00","k1",rid="r_de",tid="t_2"),201)
us=OK(BOOK(ta,F+"T13:00","k2",rid="r_us",tid="t_2"),201)
assert D.datetime.fromisoformat(de["starts_at"])==D.datetime.fromisoformat(us["starts_at"]),(de["starts_at"],us["starts_at"])
assert de["starts_at"]!=us["starts_at"],"offsets should differ textually"
print("PASS",de["starts_at"],us["starts_at"])'`
Passes when: prints `PASS` with the two timestamps. 19:00 in Berlin and 13:00 in New York on 2027-06-10 are the same absolute instant written with different offsets.
Status: passed at 9c8c115 — see verdicts/C-103.md

---

## Export and import (§10)

### C-104: GET /_test/export returns 200 with track tablekeeper, format_version 1 and a state object, without authentication.
Check: `python3 -c "$P"'
SETUP()
s,b,_=R("GET","/_test/export")
assert s==200,(s,b)
assert b["track"]=="tablekeeper",b.get("track")
assert b["format_version"]==1,b.get("format_version")
assert isinstance(b["state"],dict),type(b.get("state"))
print("PASS")'`
Passes when: prints `PASS`. No bearer token was sent.
Status: passed at 9c8c115 — see verdicts/C-104.md

### C-105: POST /_test/import accepts an unchanged export and returns 204, without authentication.
Check: `python3 -c "$P"'
ta,_=SETUP()
OK(BOOK(ta,F+"T19:00","k1"),201)
snap=EXPORT()
s,b,_=R("POST","/_test/import",snap)
assert s==204,(s,b)
print("PASS")'`
Passes when: prints `PASS`.
Status: passed at 9c8c115 — see verdicts/C-105.md

### C-106: A round trip preserves reservations, references, identities, statuses and timestamps without regenerating them.
Check: `python3 -c "$P"'
ta,_=SETUP()
a=OK(BOOK(ta,F+"T19:00","k1",tid="t_2"),201)
b=OK(BOOK(ta,F+"T21:00","k2",tid="t_3"),201)
OK(CANCEL(ta,b["reference"]),200)
before=OK(LIST(ta),200)["reservations"]
snap=EXPORT()
assert IMPORT(snap)[0]==204
after=OK(LIST(ta),200)["reservations"]
assert after==before,"round trip changed the reservations:\n%r\n%r"%(before,after)
assert OK(GETR(ta,a["reference"]),200)["created_at"]==a["created_at"]
assert OK(GETR(ta,b["reference"]),200)["status"]=="cancelled"
print("PASS")'`
Passes when: prints `PASS`. Every field of both reservations, including `reservation_id`, `reference`, `created_at` and the cancelled status, is identical after the round trip.
Status: passed at 9c8c115 — see verdicts/C-106.md

### C-107: A round trip preserves existing bearer tokens.
Check: `python3 -c "$P"'
ta,tb=SETUP()
extra=LOGIN(ADA)
a=OK(BOOK(ta,F+"T19:00","k1"),201)
snap=EXPORT()
assert IMPORT(snap)[0]==204
assert [r["reference"] for r in OK(LIST(ta),200)["reservations"]]==[a["reference"]],"original token stopped working"
assert [r["reference"] for r in OK(LIST(extra),200)["reservations"]]==[a["reference"]],"second session token stopped working"
assert OK(LIST(tb),200)["reservations"]==[]
print("PASS")'`
Passes when: prints `PASS`. Tokens issued before the export still authenticate the same accounts after the import, so they were carried in the state and not reissued.
Status: passed at 9c8c115 — see verdicts/C-107.md

### C-108: A round trip preserves hashed-password login.
Check: `python3 -c "$P"'
RESET(FX())
OK(R("POST","/auth/signup",{"email":"zoe@example.com","password":"hunter2hunter2","display_name":"Zoe"}),201)
snap=EXPORT()
assert IMPORT(snap)[0]==204
OK(R("POST","/auth/login",{"email":ADA["email"],"password":ADA["password"]}),200)
OK(R("POST","/auth/login",{"email":"zoe@example.com","password":"hunter2hunter2"}),200)
ERR(R("POST","/auth/login",{"email":"zoe@example.com","password":"wrong password"}),401,"unauthenticated")
blob=json.dumps(snap)
assert "hunter2hunter2" not in blob and "correct horse" not in blob,"plaintext password in export"
print("PASS")'`
Passes when: prints `PASS`. Both the seeded and the signed-up account still log in after the import, a wrong password is still refused, and no plaintext password travelled in the snapshot.
Status: passed at 9c8c115 — see verdicts/C-108.md

### C-109: A round trip preserves completed idempotency receipts and their original responses.
Check: `python3 -c "$P"'
ta,_=SETUP()
body={"restaurant_id":"r_anker","table_id":"t_2","starts_at_local":F+"T19:00","party_size":4}
first=OK(R("POST","/reservations",body,tok=ta,key="key-1"),201)
snap=EXPORT()
assert IMPORT(snap)[0]==204
s,b,_=R("POST","/reservations",body,tok=ta,key="key-1")
assert s==200,"receipt lost across import: %s %r"%(s,b)
assert b==first,"replayed body differs from the original: %r vs %r"%(first,b)
ERR(R("POST","/reservations",dict(body,party_size=3),tok=ta,key="key-1"),409,"idempotency_key_reuse")
assert len(OK(LIST(ta),200)["reservations"])==1
print("PASS")'`
Passes when: prints `PASS`. After the import the key still replays the identical original response and still detects a changed body.
Status: passed at 9c8c115 — see verdicts/C-109.md

### C-110: Keys whose original request failed with 4xx remain reusable after a round trip.
Check: `python3 -c "$P"'
ta,_=SETUP()
ERR(BOOK(ta,F+"T19:15","key-1"),422,"not_on_slot_grid")
snap=EXPORT()
assert IMPORT(snap)[0]==204
b=OK(BOOK(ta,F+"T19:00","key-1"),201)
assert b["status"]=="confirmed",b
print("PASS")'`
Passes when: prints `PASS`. A key burnt on a 422 before the export is still a first use after the import.
Status: passed at 9c8c115 — see verdicts/C-110.md

### C-111: Import is replacement, not merge, and repeating it does not duplicate anything.
Check: `python3 -c "$P"'
ta,_=SETUP()
a=OK(BOOK(ta,F+"T19:00","k1",tid="t_2"),201)
snap=EXPORT()
OK(BOOK(ta,F+"T21:00","k2",tid="t_3"),201)
assert len(OK(LIST(ta),200)["reservations"])==2
for _ in range(3):
    assert IMPORT(snap)[0]==204
    rs=OK(LIST(ta),200)["reservations"]
    assert [r["reference"] for r in rs]==[a["reference"]],"import merged or duplicated: %r"%rs
    assert len(OK(R("GET","/restaurants"),200)["restaurants"])==1
print("PASS")'`
Passes when: prints `PASS`. The booking made after the export is gone, and three successive imports of the same snapshot leave exactly one reservation and one restaurant.
Status: passed at 9c8c115 — see verdicts/C-111.md

### C-112: Import removes all previous destination data and credentials.
Check: `python3 -c "$P"'
RESET(FX(users=[ADA]))
ta=LOGIN(ADA)
OK(BOOK(ta,F+"T19:00","k1"),201)
snap=EXPORT()
RESET(FX(users=[BOB],restaurants=[REST(id="r_other",name="Other")]))
tb=LOGIN(BOB)
OK(R("POST","/auth/signup",{"email":"zoe@example.com","password":"correct horse","display_name":"Zoe"}),201)
assert IMPORT(snap)[0]==204
ERR(R("POST","/auth/login",{"email":BOB["email"],"password":BOB["password"]}),401,"unauthenticated")
ERR(R("POST","/auth/login",{"email":"zoe@example.com","password":"correct horse"}),401,"unauthenticated")
ERR(LIST(tb),401,"unauthenticated")
assert [r["id"] for r in OK(R("GET","/restaurants"),200)["restaurants"]]==["r_anker"]
OK(R("POST","/auth/login",{"email":ADA["email"],"password":ADA["password"]}),200)
print("PASS")'`
Passes when: prints `PASS`. The destination's own accounts, tokens and restaurants are gone; only the imported state remains.
Status: passed at 9c8c115 — see verdicts/C-112.md

### C-113: An export is an atomic read-only snapshot that later writes do not change.
Check: `python3 -c "$P"'
ta,_=SETUP()
a=OK(BOOK(ta,F+"T19:00","k1",tid="t_2"),201)
snap=EXPORT()
frozen=json.dumps(snap,sort_keys=True)
OK(BOOK(ta,F+"T21:00","k2",tid="t_3"),201)
OK(CANCEL(ta,a["reference"]),200)
OK(R("POST","/auth/signup",{"email":"zoe@example.com","password":"correct horse","display_name":"Zoe"}),201)
assert json.dumps(snap,sort_keys=True)==frozen,"the snapshot object mutated"
assert IMPORT(snap)[0]==204
rs=OK(LIST(ta),200)["reservations"]
assert [r["reference"] for r in rs]==[a["reference"]],rs
assert rs[0]["status"]=="confirmed","the snapshot recorded a later cancellation"
ERR(R("POST","/auth/login",{"email":"zoe@example.com","password":"correct horse"}),401,"unauthenticated")
print("PASS")'`
Passes when: prints `PASS`. Restoring the snapshot brings back the state as it was at export time, without the later booking, cancellation or signup.
Status: passed at 9c8c115 — see verdicts/C-113.md

### C-114: An import naming the wrong track is 422 validation_failed and changes nothing.
Check: `python3 -c "$P"'
ta,_=SETUP()
OK(BOOK(ta,F+"T19:00","k1"),201)
snap=EXPORT()
before=OK(LIST(ta),200)["reservations"]
for tr in ["pocketful","toy","","TABLEKEEPER",None,1]:
    ERR(IMPORT(dict(snap,track=tr)),422,"validation_failed")
    assert OK(LIST(ta),200)["reservations"]==before,"destination changed by a rejected import"
print("PASS")'`
Passes when: prints `PASS`. Each rejected import leaves the destination unchanged.
Status: passed at 9c8c115 — see verdicts/C-114.md

### C-115: An import naming the wrong format_version is 422 validation_failed and changes nothing.
Check: `python3 -c "$P"'
ta,_=SETUP()
OK(BOOK(ta,F+"T19:00","k1"),201)
snap=EXPORT()
before=OK(LIST(ta),200)["reservations"]
for v in [0,2,99,"1",None]:
    ERR(IMPORT(dict(snap,format_version=v)),422,"validation_failed")
    assert OK(LIST(ta),200)["reservations"]==before,"destination changed by a rejected import"
print("PASS")'`
Passes when: prints `PASS`.
Status: passed at 9c8c115 — see verdicts/C-115.md

### C-116: An import with a missing field or an invalid state is 422 validation_failed and changes nothing.
Check: `python3 -c "$P"'
ta,_=SETUP()
OK(BOOK(ta,F+"T19:00","k1"),201)
snap=EXPORT()
before=OK(LIST(ta),200)["reservations"]
bad=[{},{"track":"tablekeeper"},{"format_version":1},{"track":"tablekeeper","format_version":1},
     {"track":"tablekeeper","state":snap["state"]},{"format_version":1,"state":snap["state"]},
     dict(snap,state=None),dict(snap,state="nope"),dict(snap,state=[]),dict(snap,state=42)]
for o in bad:
    ERR(IMPORT(o),422,"validation_failed")
    assert OK(LIST(ta),200)["reservations"]==before,"destination changed by a rejected import: %r"%sorted(o)
print("PASS")'`
Passes when: prints `PASS`. A missing `track`, `format_version` or `state`, and a `state` of the wrong JSON type, are all 422, and the destination is untouched each time.
Status: passed at 9c8c115 — see verdicts/C-116.md

### C-117: An import whose body does not parse is 400 malformed_request.
Check: `python3 -c "$P"'
ta,_=SETUP()
OK(BOOK(ta,F+"T19:00","k1"),201)
before=OK(LIST(ta),200)["reservations"]
for raw in [b"{not json",b"",b"[1,2,3]",b"\"text\"",b"null"]:
    s,b,_=R("POST","/_test/import",raw)
    assert s==400 and b.get("error",{}).get("code")=="malformed_request",(raw,s,b)
    assert OK(LIST(ta),200)["reservations"]==before
print("PASS")'`
Passes when: prints `PASS`.
Status: passed at 9c8c115 — see verdicts/C-117.md

### C-118: Reset clears imported state.
Check: `python3 -c "$P"'
ta,_=SETUP()
OK(BOOK(ta,F+"T19:00","k1"),201)
snap=EXPORT()
assert IMPORT(snap)[0]==204
RESET(FX())
t2=LOGIN(ADA)
assert OK(LIST(t2),200)["reservations"]==[],"imported reservations survived reset"
b=OK(BOOK(t2,F+"T19:00","k1"),201)
assert b["status"]=="confirmed","the imported idempotency receipt survived reset"
print("PASS")'`
Passes when: prints `PASS`. After a reset neither the imported reservations nor the imported idempotency receipts remain.
Status: passed at 9c8c115 — see verdicts/C-118.md

---

## Atomic reservation moves (§11)

### C-119: POST /reservation-moves without a valid bearer token is 401 unauthenticated.
Check: `python3 -c "$P"'
ta,_=SETUP()
a=OK(BOOK(ta,F+"T19:00","k1"),201)
mv={"moves":[{"reference":a["reference"],"table_id":"t_3"}]}
ERR(R("POST","/reservation-moves",mv,key="m1"),401,"unauthenticated")
ERR(R("POST","/reservation-moves",mv,key="m2",hdr={"Authorization":"Bearer nope"}),401,"unauthenticated")
assert OK(GETR(ta,a["reference"]),200)["table_id"]=="t_2"
print("PASS")'`
Passes when: prints `PASS`.
Status: passed at 9c8c115 — see verdicts/C-119.md

### C-120: POST /reservation-moves requires an idempotency key of 1 to 255 characters.
Check: `python3 -c "$P"'
ta,_=SETUP()
a=OK(BOOK(ta,F+"T19:00","k1"),201)
mv={"moves":[{"reference":a["reference"],"table_id":"t_3"}]}
s,b,_=R("POST","/reservation-moves",mv,tok=ta)
assert s==400 and b["error"]["code"]=="missing_idempotency_key",(s,b)
ERR(R("POST","/reservation-moves",mv,tok=ta,key=""),400,"missing_idempotency_key")
ERR(R("POST","/reservation-moves",mv,tok=ta,key="k"*256),422,"validation_failed")
assert OK(GETR(ta,a["reference"]),200)["table_id"]=="t_2"
print("PASS")'`
Passes when: prints `PASS`.
Status: passed at 9c8c115 — see verdicts/C-120.md

### C-121: A successful batch returns 201 with the reservations in input order, including unchanged items.
Check: `python3 -c "$P"'
ta,_=SETUP()
a=OK(BOOK(ta,F+"T19:00","k1",tid="t_1",ps=2),201)
b=OK(BOOK(ta,F+"T19:00","k2",tid="t_2"),201)
c=OK(BOOK(ta,F+"T21:00","k3",tid="t_3"),201)
r=OK(MOVES(ta,"m1",[{"reference":c["reference"]},{"reference":a["reference"],"party_size":1},{"reference":b["reference"],"table_id":"t_3"}]),201)
got=[x["reference"] for x in r["reservations"]]
assert got==[c["reference"],a["reference"],b["reference"]],got
assert r["reservations"][0]==c,"unchanged item was altered: %r"%r["reservations"][0]
assert r["reservations"][1]["party_size"]==1,r["reservations"][1]
assert r["reservations"][2]["table_id"]=="t_3",r["reservations"][2]
print("PASS")'`
Passes when: prints `PASS`. Response order follows the request, and the untouched booking comes back exactly as it was.
Status: passed at 9c8c115 — see verdicts/C-121.md

### C-122: Two bookings may exchange tables in one batch.
Check: `python3 -c "$P"'
ta,_=SETUP()
a=OK(BOOK(ta,F+"T19:00","k1",tid="t_2"),201)
b=OK(BOOK(ta,F+"T19:00","k2",tid="t_3"),201)
r=OK(MOVES(ta,"m1",[{"reference":a["reference"],"table_id":"t_3"},{"reference":b["reference"],"table_id":"t_2"}]),201)
assert [x["table_id"] for x in r["reservations"]]==["t_3","t_2"],r
assert OK(GETR(ta,a["reference"]),200)["table_id"]=="t_3"
assert OK(GETR(ta,b["reference"]),200)["table_id"]=="t_2"
assert FREE("r_anker",F,4,F+"T19:00")==[],FREE("r_anker",F,4,F+"T19:00")
print("PASS")'`
Passes when: prints `PASS`. A swap that would conflict if applied one move at a time succeeds, because the batch is judged on its resulting state.
Status: passed at 9c8c115 — see verdicts/C-122.md

### C-123: A moves list outside 1 to 8 entries is 422 validation_failed.
Check: `python3 -c "$P"'
ta,_=SETUP()
refs=[OK(BOOK(ta,F+"T"+at,"k-%s-%s"%(at,tid),tid=tid,ps=2),201)["reference"] for at in ["18:00","18:30","19:00"] for tid in ["t_1","t_2","t_3"]]
assert len(refs)==9
ERR(MOVES(ta,"m0",[]),422,"validation_failed")
ERR(MOVES(ta,"m9",[{"reference":r} for r in refs]),422,"validation_failed")
OK(MOVES(ta,"m8",[{"reference":r} for r in refs[:8]]),201)
print("PASS")'`
Passes when: prints `PASS`. Zero entries and nine entries are refused; eight are accepted.
Status: FAILED at 9c8c115 — see verdicts/C-123.md; superseded by C-156

### C-124: Duplicate references in a batch are 422 validation_failed.
Check: `python3 -c "$P"'
ta,_=SETUP()
a=OK(BOOK(ta,F+"T19:00","k1",tid="t_2"),201)
b=OK(BOOK(ta,F+"T21:00","k2",tid="t_3"),201)
ERR(MOVES(ta,"m1",[{"reference":a["reference"],"table_id":"t_3"},{"reference":a["reference"],"party_size":2}]),422,"validation_failed")
ERR(MOVES(ta,"m2",[{"reference":a["reference"]},{"reference":b["reference"]},{"reference":a["reference"]}]),422,"validation_failed")
assert OK(GETR(ta,a["reference"]),200)==a
print("PASS")'`
Passes when: prints `PASS`.
Status: passed at 9c8c115 — see verdicts/C-124.md

### C-125: A batch of an invalid shape is 422 validation_failed.
Check: `python3 -c "$P"'
ta,_=SETUP()
a=OK(BOOK(ta,F+"T19:00","k1"),201)
for i,mv in enumerate(["nope",{},[{}],[{"table_id":"t_3"}],[{"reference":None}],[{"reference":7}],[{"reference":["x"]}],[{"reference":{"a":1}}],["BOOK01"],[[{"reference":a["reference"]}]]]):
    s,b,_=R("POST","/reservation-moves",{"moves":mv},tok=ta,key="m%d"%i)
    assert s==422 and b.get("error",{}).get("code")=="validation_failed",(mv,s,b)
s,b,_=R("POST","/reservation-moves",{},tok=ta,key="mm")
assert s==422 and b["error"]["code"]=="validation_failed",(s,b)
print("PASS")'`
Passes when: prints `PASS`. A missing `moves`, a `moves` that is not a list of objects, a missing `reference` and a non-string `reference` are all 422 `validation_failed`.
Status: passed at 9c8c115 — see verdicts/C-125.md

### C-126: An unknown reference, or another account's, is 404 not_found.
Check: `python3 -c "$P"'
ta,tb=SETUP()
a=OK(BOOK(ta,F+"T19:00","k1",tid="t_2"),201)
theirs=OK(BOOK(tb,F+"T19:00","k2",tid="t_3"),201)
ERR(MOVES(ta,"m1",[{"reference":"ZZZZZZ","table_id":"t_3"}]),404,"not_found")
ERR(MOVES(ta,"m2",[{"reference":a["reference"]},{"reference":"ZZZZZZ"}]),404,"not_found")
ERR(MOVES(ta,"m3",[{"reference":theirs["reference"],"table_id":"t_1"}]),404,"not_found")
ERR(MOVES(ta,"m4",[{"reference":a["reference"]},{"reference":theirs["reference"]}]),404,"not_found")
assert OK(GETR(ta,a["reference"]),200)==a
assert OK(GETR(tb,theirs["reference"]),200)==theirs
print("PASS")'`
Passes when: prints `PASS`. Another account's reference is 404, not 403, and neither booking changed.
Status: passed at 9c8c115 — see verdicts/C-126.md

### C-127: References spanning different restaurants are 422 validation_failed.
Check: `python3 -c "$P"'
RESET(FX(restaurants=[REST(),REST(id="r_two",name="Two")]))
ta=LOGIN(ADA)
a=OK(BOOK(ta,F+"T19:00","k1",rid="r_anker",tid="t_2"),201)
b=OK(BOOK(ta,F+"T19:00","k2",rid="r_two",tid="t_2"),201)
ERR(MOVES(ta,"m1",[{"reference":a["reference"],"table_id":"t_3"},{"reference":b["reference"],"table_id":"t_3"}]),422,"validation_failed")
assert OK(GETR(ta,a["reference"]),200)==a and OK(GETR(ta,b["reference"]),200)==b
print("PASS")'`
Passes when: prints `PASS`. Both bookings belong to the caller and both references exist, so the failure is the cross-restaurant rule, not 404.
Status: passed at 9c8c115 — see verdicts/C-127.md

### C-128: A cancelled booking in a batch is 409 reservation_cancelled.
Check: `python3 -c "$P"'
ta,_=SETUP()
a=OK(BOOK(ta,F+"T19:00","k1",tid="t_2"),201)
b=OK(BOOK(ta,F+"T21:00","k2",tid="t_3"),201)
OK(CANCEL(ta,b["reference"]),200)
ERR(MOVES(ta,"m1",[{"reference":b["reference"],"table_id":"t_1"}]),409,"reservation_cancelled")
ERR(MOVES(ta,"m2",[{"reference":a["reference"],"table_id":"t_3"},{"reference":b["reference"]}]),409,"reservation_cancelled")
assert OK(GETR(ta,a["reference"]),200)==a,"rejected batch changed the other booking"
print("PASS")'`
Passes when: prints `PASS`.
Status: passed at 9c8c115 — see verdicts/C-128.md

### C-129: A booking inside its own cutoff is 409 cutoff_passed within a batch.
Check: `python3 -c "$P"'
RESET(FX(restaurants=[REST(cancellation_cutoff_minutes=60*24*3650)]))
ta=LOGIN(ADA)
a=OK(BOOK(ta,F+"T19:00","k1",tid="t_2"),201)
b=OK(BOOK(ta,F+"T21:00","k2",tid="t_3"),201)
ERR(MOVES(ta,"m1",[{"reference":a["reference"],"table_id":"t_1","party_size":2}]),409,"cutoff_passed")
ERR(MOVES(ta,"m2",[{"reference":a["reference"]},{"reference":b["reference"],"party_size":2}]),409,"cutoff_passed")
assert OK(GETR(ta,a["reference"]),200)==a and OK(GETR(ta,b["reference"]),200)==b
print("PASS")'`
Passes when: prints `PASS`. Each booking's own cutoff applies, and a batch containing one inside its cutoff is refused whole.
Status: passed at 9c8c115 — see verdicts/C-129.md

### C-130: For one booking, its cutoff error precedes its other errors.
Check: `python3 -c "$P"'
RESET(FX(restaurants=[REST(cancellation_cutoff_minutes=60*24*3650)]))
ta=LOGIN(ADA)
a=OK(BOOK(ta,F+"T19:00","k1",tid="t_2"),201)
ERR(MOVES(ta,"m1",[{"reference":a["reference"],"starts_at_local":F+"T19:15"}]),409,"cutoff_passed")
ERR(MOVES(ta,"m2",[{"reference":a["reference"],"table_id":"t_1","party_size":4}]),409,"cutoff_passed")
ERR(MOVES(ta,"m3",[{"reference":a["reference"],"starts_at_local":F+"T12:00"}]),409,"cutoff_passed")
ERR(MOVES(ta,"m4",[{"reference":a["reference"],"table_id":"t_nope"}]),409,"cutoff_passed")
print("PASS")'`
Passes when: prints `PASS`. Each of these items would otherwise be 422 `not_on_slot_grid`, 422 `party_exceeds_capacity`, 422 `outside_opening_hours` or 404 `not_found`; the cutoff error wins for that booking.
Status: passed at 9c8c115 — see verdicts/C-130.md

### C-131: Non-occupancy errors take precedence in input order.
Check: `python3 -c "$P"'
ta,_=SETUP()
a=OK(BOOK(ta,F+"T19:00","k1",tid="t_2"),201)
b=OK(BOOK(ta,F+"T21:00","k2",tid="t_3"),201)
ERR(MOVES(ta,"m1",[{"reference":a["reference"],"starts_at_local":F+"T19:15"},{"reference":b["reference"],"party_size":0}]),422,"not_on_slot_grid")
ERR(MOVES(ta,"m2",[{"reference":a["reference"],"party_size":0},{"reference":b["reference"],"starts_at_local":F+"T19:15"}]),422,"validation_failed")
ERR(MOVES(ta,"m3",[{"reference":a["reference"],"starts_at_local":F+"T12:00"},{"reference":b["reference"],"table_id":"t_nope"}]),422,"outside_opening_hours")
ERR(MOVES(ta,"m4",[{"reference":a["reference"],"table_id":"t_nope"},{"reference":b["reference"],"starts_at_local":F+"T12:00"}]),404,"not_found")
print("PASS")'`
Passes when: prints `PASS`. In each pair the reported code is the one belonging to the earlier item in the list, so swapping the order swaps the code.
Status: passed at 9c8c115 — see verdicts/C-131.md

### C-132: An overlap among the resulting bookings is 409 table_unavailable.
Check: `python3 -c "$P"'
ta,_=SETUP()
a=OK(BOOK(ta,F+"T19:00","k1",tid="t_2"),201)
b=OK(BOOK(ta,F+"T21:00","k2",tid="t_3"),201)
ERR(MOVES(ta,"m1",[{"reference":a["reference"],"table_id":"t_3","starts_at_local":F+"T21:00"},{"reference":b["reference"]}]),409,"table_unavailable")
ERR(MOVES(ta,"m2",[{"reference":a["reference"],"table_id":"t_1","starts_at_local":F+"T20:00","party_size":2},{"reference":b["reference"],"table_id":"t_1","starts_at_local":F+"T20:30","party_size":2}]),409,"table_unavailable")
assert OK(GETR(ta,a["reference"]),200)==a and OK(GETR(ta,b["reference"]),200)==b
print("PASS")'`
Passes when: prints `PASS`. Two moved bookings that would collide with each other are refused, including the case where neither collides with anything that exists today.
Status: passed at 9c8c115 — see verdicts/C-132.md

### C-133: An overlap with a booking not listed in the batch is 409 table_unavailable.
Check: `python3 -c "$P"'
ta,tb=SETUP()
a=OK(BOOK(ta,F+"T19:00","k1",tid="t_2"),201)
mine=OK(BOOK(ta,F+"T21:00","k2",tid="t_3"),201)
theirs=OK(BOOK(tb,F+"T19:00","k3",tid="t_1",ps=2),201)
ERR(MOVES(ta,"m1",[{"reference":a["reference"],"table_id":"t_3","starts_at_local":F+"T21:00"}]),409,"table_unavailable")
ERR(MOVES(ta,"m2",[{"reference":a["reference"],"table_id":"t_1","party_size":2}]),409,"table_unavailable")
assert OK(GETR(ta,a["reference"]),200)==a
assert OK(GETR(tb,theirs["reference"]),200)==theirs
print("PASS")'`
Passes when: prints `PASS`. An unlisted booking of the caller's and one belonging to another account both block the move.
Status: passed at 9c8c115 — see verdicts/C-133.md

### C-134: A rejected batch changes nothing: no occupancy, no reservation record.
Check: `python3 -c "$P"'
ta,_=SETUP()
a=OK(BOOK(ta,F+"T19:00","k1",tid="t_1",ps=2),201)
b=OK(BOOK(ta,F+"T19:00","k2",tid="t_2"),201)
c=OK(BOOK(ta,F+"T21:00","k3",tid="t_3"),201)
before=OK(LIST(ta),200)["reservations"]
av=[OK(AV("r_anker",F,p),200) for p in (2,4)]
bad=[[{"reference":a["reference"],"party_size":1},{"reference":b["reference"],"table_id":"t_3","starts_at_local":F+"T21:00"}],
     [{"reference":c["reference"],"table_id":"t_1","party_size":2},{"reference":a["reference"],"starts_at_local":F+"T19:15"}],
     [{"reference":b["reference"],"table_id":"t_3"},{"reference":"ZZZZZZ"}],
     [{"reference":a["reference"],"party_size":2},{"reference":b["reference"],"party_size":0}]]
for i,mv in enumerate(bad):
    s,r,_=MOVES(ta,"bad-%d"%i,mv)
    assert 400<=s<500,(mv,s,r)
    assert OK(LIST(ta),200)["reservations"]==before,"rejected batch %d changed a record"%i
    assert [OK(AV("r_anker",F,p),200) for p in (2,4)]==av,"rejected batch %d changed occupancy"%i
print("PASS")'`
Passes when: prints `PASS`. After four different refused batches every reservation record and the whole availability picture are identical to before.
Status: passed at 9c8c115 — see verdicts/C-134.md

### C-135: A rejected batch leaves its idempotency key reusable.
Check: `python3 -c "$P"'
ta,_=SETUP()
a=OK(BOOK(ta,F+"T19:00","k1",tid="t_2"),201)
ERR(MOVES(ta,"m1",[{"reference":a["reference"],"starts_at_local":F+"T19:15"}]),422,"not_on_slot_grid")
r=OK(MOVES(ta,"m1",[{"reference":a["reference"],"table_id":"t_3"}]),201)
assert r["reservations"][0]["table_id"]=="t_3",r
print("PASS")'`
Passes when: prints `PASS`. The key spent on a refused batch is a first use again, so the later different body is accepted rather than reported as reuse.
Status: passed at 9c8c115 — see verdicts/C-135.md

### C-136: A batch replay returns the original response with 200, even after later amendments or cancellations.
Check: `python3 -c "$P"'
ta,_=SETUP()
a=OK(BOOK(ta,F+"T19:00","k1",tid="t_2"),201)
mv=[{"reference":a["reference"],"table_id":"t_3"}]
first=OK(MOVES(ta,"m1",mv),201)
s,b,_=MOVES(ta,"m1",mv)
assert s==200 and b==first,"replay differs: %s %r"%(s,b)
OK(PATCHR(ta,a["reference"],{"party_size":2}),200)
s,b,_=MOVES(ta,"m1",mv)
assert s==200 and b==first,"replay after amendment differs: %s %r"%(s,b)
OK(CANCEL(ta,a["reference"]),200)
s,b,_=MOVES(ta,"m1",mv)
assert s==200 and b==first,"replay after cancellation differs: %s %r"%(s,b)
cur=OK(GETR(ta,a["reference"]),200)
assert cur["status"]=="cancelled","replay resurrected the booking"
assert cur["party_size"]==2,"replay undid the amendment"
ERR(MOVES(ta,"m1",[{"reference":a["reference"],"table_id":"t_1"}]),409,"idempotency_key_reuse")
print("PASS")'`
Passes when: prints `PASS`. All three replays return the stored 201 body as a 200 and make no state change; a different body under the same key is 409.
Status: passed at 9c8c115 — see verdicts/C-136.md

### C-137: A no-op batch retains every existing value, including identity and creation time.
Check: `python3 -c "$P"'
ta,_=SETUP()
a=OK(BOOK(ta,F+"T19:00","k1",tid="t_2"),201)
b=OK(BOOK(ta,F+"T21:00","k2",tid="t_3"),201)
r=OK(MOVES(ta,"m1",[{"reference":a["reference"]},{"reference":b["reference"],"nonsense":1}]),201)
assert r["reservations"]==[a,b],"no-op batch altered the bookings: %r"%r["reservations"]
assert OK(GETR(ta,a["reference"]),200)==a and OK(GETR(ta,b["reference"]),200)==b
assert "t_2" not in FREE("r_anker",F,4,F+"T19:00") and "t_3" not in FREE("r_anker",F,4,F+"T21:00")
print("PASS")'`
Passes when: prints `PASS`. Omitted fields keep their values, unknown fields are ignored, and both bookings keep their occupancy.
Status: passed at 9c8c115 — see verdicts/C-137.md

### C-138: Unchanged bookings listed in a batch retain their occupancy.
Check: `python3 -c "$P"'
ta,tb=SETUP()
a=OK(BOOK(ta,F+"T19:00","k1",tid="t_2"),201)
b=OK(BOOK(ta,F+"T21:00","k2",tid="t_3"),201)
OK(MOVES(ta,"m1",[{"reference":a["reference"],"party_size":2},{"reference":b["reference"]}]),201)
ERR(BOOK(tb,F+"T21:00","x1",tid="t_3"),409,"table_unavailable")
ERR(BOOK(tb,F+"T19:00","x2",tid="t_2"),409,"table_unavailable")
print("PASS")'`
Passes when: prints `PASS`. The listed-but-unchanged booking still holds its table against another account, so the batch did not release and forget it.
Status: passed at 9c8c115 — see verdicts/C-138.md

### C-139: Export and import preserve successful batch receipts as well as the resulting bookings.
Check: `python3 -c "$P"'
ta,_=SETUP()
a=OK(BOOK(ta,F+"T19:00","k1",tid="t_2"),201)
mv=[{"reference":a["reference"],"table_id":"t_3"}]
first=OK(MOVES(ta,"m1",mv),201)
snap=EXPORT()
assert IMPORT(snap)[0]==204
assert OK(GETR(ta,a["reference"]),200)["table_id"]=="t_3","the batch result did not survive the round trip"
s,b,_=MOVES(ta,"m1",mv)
assert s==200,"batch receipt lost across import: %s %r"%(s,b)
assert b==first,"replayed batch body differs: %r vs %r"%(first,b)
ERR(MOVES(ta,"m1",[{"reference":a["reference"],"table_id":"t_1"}]),409,"idempotency_key_reuse")
print("PASS")'`
Passes when: prints `PASS`.
Status: passed at 9c8c115 — see verdicts/C-139.md

---

## Whole-suite claims

### C-140: The shipped stage-1 checks all pass against the delivered image.
Check: `cd /Users/aashanjaved/dark-factory-wearedevs && ./.venv/bin/python -m harness run --track tablekeeper --repo /Users/aashanjaved/band-work/result --stage 1 --out /Users/aashanjaved/band-work/checks/s1-shipped-$(date +%s)`
Passes when: the harness exits 0 and its summary reports zero failures and zero errors for stage 1.
Status: superseded by C-147

### C-141: The graded stage-1 suite passes in full.
Check: `cd /Users/aashanjaved/dark-factory-wearedevs && ./.venv/bin/python -m harness run --track tablekeeper --repo /Users/aashanjaved/band-work/result --stage 1 --out /Users/aashanjaved/band-work/checks/s1-$(date +%s)`
Passes when: the harness exits 0 and its summary reports zero failures and zero errors for stage 1. The shipped checks are roughly 83% of this suite, so passing them is necessary and not sufficient; that is why C-1 through C-139 exist.
Status: superseded by C-146

---

## Coverage note: what the shipped checks never ask for

The shipped checks in `tablekeeper/test/stage_1/` are roughly 83% of graded suite 1. Read against the
specification, the entries below cover requirements that subset does not exercise at all, or
exercises in only one direction. They are the entries most likely to decide the grade, and they are
why this ledger is longer than the shipped suite.

**Runtime contract.** C-1 (RUN.md's own command works unedited), C-2 (no egress while serving),
C-3 and C-4 (`PORT` honoured, and 8080 when it is absent), C-6 (`application/json; charset=utf-8` on
success *and* error responses), C-8 (repeated resets each take full effect), C-14 (the 64-character
limit applied to the IDs the service itself mints).

**Availability and reservations.** C-19 (the exact slot set, including the last slot that fits and
the first that does not), C-28 (every advertised slot is bookable verbatim and echoes the same
instant back), C-26 (impossible dates such as 2027-02-30), C-45 (the `^[A-Z0-9]{6,12}$` reference
format — the shipped checks test uniqueness only), C-48 (the half-open boundary asserted against the
previous booking's own `ends_at`), C-52 (both 22:30 and 23:00 refused although both are on the grid),
C-58 (a past start is not refused for being past), C-61 (the empty-list shape),
C-59 (a sweep of hostile inputs across every endpoint for 5xx).

**Authentication.** C-38 (a malformed `Authorization` header, as distinct from a missing or unknown
one), C-40 (several concurrent tokens per account, none invalidated by a later login),
C-41 and C-42 (no plaintext password recoverable from the export in plain, base64 or hex form, and a
recognised password-hashing marker present). The shipped checks never look at how credentials are
stored.

**Amendment.** C-74 (a failed amendment leaves both the record and the occupancy unchanged, checked
across five different failure modes), C-76 (the cutoff is measured against the **current** start, so
moving a booking far beyond the cutoff is still refused), C-78 (omitted fields retained; an empty
PATCH body is not an error).

**Idempotency.** C-81 (the 255-character bound, with 255 accepted and 256 refused), C-83
(idempotency resolved before field validation, across eight otherwise-invalid bodies), C-84 (the same
key and body on a different path must succeed), C-85 (a key reused after a 422 and after a 409 is a
first use), C-86 (per-user scoping *and* independent reuse detection for the second user), C-88 (key
order and whitespace do not make a body different), C-89 (concurrent identical requests with one
unused key).

**Concurrency.** C-90 (fifty in flight, not ten, with all forty-nine losers checked for the right
code) and C-91 (fifty mixed reads and writes, with the service still healthy afterwards).

**Time and DST.** C-93 and C-97 (the skipped hour is absent from **availability** — the shipped
checks only test that booking it is refused), C-94 and C-98 (the repeated hour appears once *and* is
advertised at the pre-change offset), C-101 (absolute duration across Berlin's fall-back, alongside
the New York case in C-100), C-102 (all eight dates either side of both transitions in both zones,
consistent between booking and availability).

**Export and import.** The shipped subset has a single export test. C-104 through C-118 cover the
envelope shape, the unauthenticated contract, preservation of tokens (C-107), of hashed-password
login (C-108), of idempotency receipts and their original response bodies (C-109), reusability of
failed keys (C-110), replacement rather than merge (C-111), removal of the destination's own
credentials (C-112), the read-only atomic snapshot (C-113), rejection of a wrong track, a wrong
version, a missing field and an invalid state **without changing the destination** (C-114 to C-116),
malformed JSON (C-117), and reset clearing imported state including its receipts (C-118).

**Atomic reservation moves.** The shipped subset has a single one-item batch test. C-119 through
C-139 cover the auth and key requirements (C-119, C-120), input-order response including unchanged
items (C-121), the mutual swap that only works if the batch is judged on its resulting state (C-122),
the 1..8 bound (C-123), duplicates and invalid shapes (C-124, C-125), the 404-versus-422 split
between another owner's reference and a cross-restaurant batch (C-126, C-127), cancelled bookings
(C-128), per-booking cutoff (C-129) and its precedence over that booking's own other errors (C-130),
error precedence in input order with the order deliberately swapped (C-131), overlap among results
and with unlisted bookings (C-132, C-133), all-or-nothing rollback across four failure modes
(C-134), key reusability after a refused batch (C-135), replay after amendment and after cancellation
(C-136), no-op retention (C-137), retained occupancy for listed-but-unchanged bookings (C-138), and
receipt preservation across export/import (C-139).

---

# ERRATA — defects in this ledger, found after issue

Four defects have been found in this ledger since it was issued at `d9501ee`. All four are mine, not
the implementation's. They were found by `@builder` and `@registrar` reading the ledger against the
graded harness's own source, and each is reproduced below from a run rather than asserted.

**No original entry is edited.** C-0, C-2, C-3, C-4, C-140 and C-141 stand exactly as written, with
whatever verdict they earn. Replacements are new entries appended below. Whether a superseded entry's
`Status` changes is `@registrar`'s to authorise, not mine to assume.

The root cause of the first and worst defect is that C-0 broke this ledger's own stated rule — *one
claim, one entry; an "and" in a requirement is usually two claims*. C-0 said "builds and serves from
a clean container **with no outbound network**". That is two claims, and on one Docker network they
are mutually exclusive.

## Defect 1 — a published port cannot reach an `--internal` network

Reproduced here, with the port verified free beforehand so nothing else could answer:

```
$ docker network create --internal probe-net    # internal=true
$ docker run -d --name probe-int --network probe-net -p 18077:8080 -e PORT=8080 tk-s1
$ docker inspect probe-int --format '{{json .HostConfig.PortBindings}}'
{"8080/tcp":[{"HostIp":"","HostPort":"18077"}]}
$ docker inspect probe-int --format '{{json .NetworkSettings.Ports}}'
{}
$ docker port probe-int
(no output)
$ curl -fsS -m 5 http://127.0.0.1:18077/health
curl: (7) Failed to connect to 127.0.0.1 port 18077 after 0 ms
$ docker exec probe-int python -c '...urlopen("http://127.0.0.1:8080/health")...'
b'{"status": "ok"}'
```

Docker records the bind request and publishes nothing. The graded harness states the constraint in
its own words, at `harness/docker_driver.py:74`: *"container-to-container works, outbound is refused,
and a published port does NOT reach it -- which is why `host` mode exists separately."*

Affects **C-0, C-2, C-3, C-4** and **Conventions §1 and §3**. The prelude's
`B="http://127.0.0.1:18080"` is correct and is not the defect; the defect is starting the container
on a network that cannot publish.

I must also record that I reported the opposite to the room before issuing this ledger. My original
probe appeared to reach a published port on an internal network. It was a false positive — I did not
verify the port was free first, so another container from an earlier run almost certainly answered
that curl while my own container supplied the no-egress half. Two different containers, one
conclusion. That is why every check below verifies its own premise.

## Defect 2 — the whole-suite claims run in the wrong harness mode

```
$ sed -n '306p' harness/cli.py
    args.mode = args.mode or dd.HOST
$ sed -n '336p' harness/cli.py
        args.build = str(folder)
$ sed -n '360p' harness/cli.py
    if args.mode == dd.ISOLATED and not args.build:
```

The default is `host`. C-140 and C-141 pass no `--mode`, so both run in host mode, where the harness
warns outbound is **not** blocked and "never score a submission from this mode". Grading runs
`isolated`. Because `args.build` is set from the stage folder at line 336, before the guard at line
360, `--repo --stage 1 --mode isolated` is a valid invocation — the ledger simply never asked for it.

Consequence: a service that reached the network at run time would pass C-140 and C-141 and fail
grading. Affects **C-140, C-141**.

## Defect 3 — fixed Docker names make this ledger unsafe to run concurrently

Every entry uses the container name `tk-s1`, the network `tk-s1-noout` and host port 18080, and
several begin with `docker rm -f tk-s1`. Docker is shared state across all four seats even though our
git trees are not, so any two seats running checks at once destroy each other's containers. This has
already happened twice in this room, once to `@auditor` mid-run. Affects **every entry**.

I am one of the causes, not only the author of the defect. While verifying the replacements below I
created and removed containers named `tk-s1` and networks `tk-s1-net`, `tk-noout`, at a time when
`.auditor-clones/` shows `@auditor` was running C-0. Any C-0 run of `@auditor`'s that reported
`NOT HEALTHY` may have been killed by me rather than by the defect. `@auditor` should disregard any
run that overlapped and re-run clean. I have stopped touching Docker.

## Defect 4 — C-2 can pass vacuously

C-2's Check is `getent hosts example.com || nslookup ... || wget ... || curl ...` and then tests the
exit status of whichever ran last. A missing tool exits 127, which is indistinguishable from blocked
egress. In the delivered image three of the four are absent:

```
getent   present
nslookup ABSENT
wget     ABSENT
curl     ABSENT
```

So the status C-2 finally reads comes from `curl: not found`, not from refused egress. On an image
carrying none of the four, C-2 prints `NO EGRESS` with egress wide open, and an implementation could
satisfy it by shipping fewer tools. Affects **C-2**. The replacement probes from a sibling container
whose tools are guaranteed, and asserts a positive fact — that the service answers — alongside the
negative ones, so it cannot pass by absence.

## Conventions, corrected

Additive. §1 to §6 are unchanged and still describe the superseded entries.

### §7 Start-up, corrected (supersedes §3)

The service runs on a **publishable** user-defined bridge, so `B="http://127.0.0.1:18080"` in the
prelude stays correct and every prelude-based check works unaltered:

```sh
docker rm -f tk-s1 >/dev/null 2>&1; docker network rm tk-s1-net >/dev/null 2>&1; docker network create tk-s1-net >/dev/null 2>&1; docker build -t tk-s1 /Users/aashanjaved/band-work/result/stage-1 && docker run -d --name tk-s1 --network tk-s1-net -p 18080:8080 -e PORT=8080 tk-s1 && for i in $(seq 1 60); do curl -fsS http://127.0.0.1:18080/health >/dev/null 2>&1 && break; sleep 1; done
```

Teardown, unchanged in spirit from §4, with the corrected network name:

```sh
docker rm -f tk-s1 >/dev/null 2>&1; docker network rm tk-s1-net >/dev/null 2>&1; echo "torn down"
```

This network has outbound access. That is deliberate and it is why no-egress is now its own claim
(C-143) rather than a clause inside the gate. Reaching the service and proving it cannot reach out
are both required; they are simply not provable on one network.

### §8 Docker is shared state — take the lock first

Only one seat runs Docker-touching checks at a time. Acquire before, release after, both by
exact command:

```sh
mkdir /tmp/tk-docker.lock 2>/dev/null && { echo "$SEAT" > /tmp/tk-docker.lock/owner; echo ACQUIRED; } || { echo "HELD BY $(cat /tmp/tk-docker.lock/owner 2>/dev/null)"; exit 1; }
```

```sh
rm -rf /tmp/tk-docker.lock && echo RELEASED
```

`mkdir` is atomic, so two seats cannot both acquire. A seat that cannot acquire waits and says so in
the room; it does not remove the lock. Report in a verdict which seat held the lock during the run.

### §9 Prelude-2 (optional, default-identical)

Identical to the §6 prelude in every line except that the base URL may be overridden, so seats can
use different ports when the registrar authorises concurrent runs:

```python
#PRELUDE2-BEGIN
import os
B=os.environ.get("TK_BASE","http://127.0.0.1:18080")
#PRELUDE2-END
```

Export it after `$P` and it replaces only `B`:

```sh
export P="$P
$(awk '/^#PRELUDE2-BEGIN$/{f=1;next} /^#PRELUDE2-END$/{f=0} f' /Users/aashanjaved/band-work/result/LEDGER.md)"
```

With `TK_BASE` unset this is byte-identical in behaviour to the §6 prelude. No check's text changes.
Using it is `@registrar`'s call, and a verdict must record whether it was used and what `TK_BASE` was.

## Replacement entries

### C-142: The service builds from a clean container and serves /health within 60 seconds, following its RUN.md.
Check: `docker rm -f tk-s1 >/dev/null 2>&1; docker network rm tk-s1-net >/dev/null 2>&1; docker builder prune -af >/dev/null 2>&1; test -f /Users/aashanjaved/band-work/result/stage-1/Dockerfile && test -f /Users/aashanjaved/band-work/result/stage-1/RUN.md && docker network create tk-s1-net && docker build --no-cache -t tk-s1 /Users/aashanjaved/band-work/result/stage-1 && docker run -d --name tk-s1 --network tk-s1-net -p 18080:8080 -e PORT=8080 tk-s1 && start=$(date +%s) && until curl -fsS http://127.0.0.1:18080/health; do [ $(( $(date +%s) - start )) -lt 60 ] || { echo "NOT HEALTHY WITHIN 60s"; exit 1; }; sleep 1; done && echo " HEALTHY IN $(( $(date +%s) - start ))s" && test "$(docker inspect tk-s1 --format '{{json .NetworkSettings.Ports}}')" != "{}" && echo "PORT PUBLISHED"`
Passes when: exits 0 and prints the `/health` body, then `HEALTHY IN <n>s` with `n` at most 60, then `PORT PUBLISHED`. Replaces C-0 and is the gate in its place. The build runs `--no-cache` after a builder prune, so nothing carries over. The final assertion checks the check's own premise — that the port genuinely published — which is exactly what C-0 assumed and never verified.
Status: passed at da45651 — see verdicts/C-142.md

### C-143: At run time the service has no outbound network access, and still serves /health.
Check: `docker rm -f tk-c143 >/dev/null 2>&1; docker network rm tk-c143-noout >/dev/null 2>&1; docker network create --internal tk-c143-noout && test "$(docker network inspect tk-c143-noout --format '{{.Internal}}')" = "true" && docker build -q -t tk-s1 /Users/aashanjaved/band-work/result/stage-1 >/dev/null && docker run -d --name tk-c143 --network tk-c143-noout -e PORT=8080 tk-s1 >/dev/null && for i in $(seq 1 60); do docker run --rm --network tk-c143-noout alpine:3 wget -qO- -T3 http://tk-c143:8080/health >/dev/null 2>&1 && break; sleep 1; done; docker run --rm --network tk-c143-noout alpine:3 sh -c 'wget -qO- -T5 http://tk-c143:8080/health || exit 1; nslookup example.com >/dev/null 2>&1 && exit 2; nc -w4 -z 1.1.1.1 80 2>/dev/null && exit 3; wget -qO- -T4 http://example.com >/dev/null 2>&1 && exit 4; echo " NO EGRESS"'; r=$?; docker rm -f tk-c143 >/dev/null 2>&1; docker network rm tk-c143-noout >/dev/null 2>&1; exit $r`
Passes when: exits 0 and prints the `/health` body followed by `NO EGRESS`. Replaces C-2. The service is attached only to an internal network and publishes no port; it is reached by container name from a sibling `alpine:3` container, the way the graded harness reaches it in isolated mode. Exit 1 means the service did not answer, 2 that DNS resolved, 3 that a raw TCP connection opened, 4 that an HTTP fetch succeeded. Because the probe runs in a container whose tools are guaranteed and must print the service's own health body to pass, it cannot pass by a tool being absent. `alpine:3` is pulled once during setup; the no-outbound rule constrains the service, not the auditor's tooling.
Status: passed at 9c8c115 — see verdicts/C-143.md

### C-144: The service listens on the port given in the PORT environment variable.
Check: `docker rm -f tk-c144 >/dev/null 2>&1; docker network rm tk-c144-net >/dev/null 2>&1; docker network create tk-c144-net >/dev/null && docker run -d --name tk-c144 --network tk-c144-net -p 18081:9091 -e PORT=9091 tk-s1 >/dev/null && for i in $(seq 1 60); do curl -fsS http://127.0.0.1:18081/health && break; sleep 1; done; r=$?; docker rm -f tk-c144 >/dev/null 2>&1; docker network rm tk-c144-net >/dev/null 2>&1; exit $r`
Passes when: exits 0 and prints the `/health` body. Replaces C-3. The container port is 9091, not 8080, so a hard-coded port cannot pass.
Status: passed at 9c8c115 — see verdicts/C-144.md

### C-145: The service listens on port 8080 when PORT is not set.
Check: `docker rm -f tk-c145 >/dev/null 2>&1; docker network rm tk-c145-net >/dev/null 2>&1; docker network create tk-c145-net >/dev/null && docker run -d --name tk-c145 --network tk-c145-net -p 18082:8080 tk-s1 >/dev/null && for i in $(seq 1 60); do curl -fsS http://127.0.0.1:18082/health && break; sleep 1; done; r=$?; docker rm -f tk-c145 >/dev/null 2>&1; docker network rm tk-c145-net >/dev/null 2>&1; exit $r`
Passes when: exits 0 and prints the `/health` body. Replaces C-4. No `-e PORT` is passed, so the service must default to 8080.
Status: passed at 9c8c115 — see verdicts/C-145.md

### C-146: The graded stage-1 suite passes in the mode grading uses.
Check: `cd /Users/aashanjaved/dark-factory-wearedevs && ./.venv/bin/python -m harness run --track tablekeeper --repo /Users/aashanjaved/band-work/result --stage 1 --mode isolated --out /Users/aashanjaved/band-work/checks/s1-iso-$(date +%s)`
Passes when: the harness exits 0 and its summary reports zero failures and zero errors for stage 1. Replaces C-141. `--mode isolated` is the grading mode: the service gets no outbound access and is reached by container name. A pass here, unlike a pass in host mode, cannot be earned by a service that fetches something at run time.
Status: passed at 9c8c115 — see verdicts/C-146.md

### C-147: The shipped stage-1 checks pass in the mode grading uses.
Check: `cd /Users/aashanjaved/dark-factory-wearedevs && ./.venv/bin/python -m harness run --track tablekeeper --repo /Users/aashanjaved/band-work/result --stage 1 --mode isolated --out /Users/aashanjaved/band-work/checks/s1-iso-shipped-$(date +%s)`
Passes when: the harness exits 0 and its summary reports zero failures and zero errors for stage 1. Replaces C-140. Host mode is still useful while developing, but per the harness's own warning it must never be the basis of a pass, so no entry in this ledger claims anything from it.
Status: passed at 9c8c115 — see verdicts/C-147.md

## Superseded entries

| Original | Replaced by | Why |
|---|---|---|
| C-0 | C-142 | published port cannot reach an `--internal` network; also conflated two claims |
| C-2 | C-143 | same, plus the `\|\|` chain passes vacuously when probe tools are absent |
| C-3 | C-144 | started the container on a network that cannot publish |
| C-4 | C-145 | same |
| C-140 | C-147 | ran in host mode, where outbound is not blocked |
| C-141 | C-146 | same |

Supersession was authorised by `@registrar` and recorded in `REFUSALS.md` at
`66e7967fadcce831e7288564483116e1322cbd0b`. It was granted only because the errata above reproduces a
defect in each superseded **Check** from a run.

**What supersession does not mean.** A superseded entry is not absolved and is not forgiven. It does
not need a pass, and it does not hold the gate shut. C-0's FAIL at `90028fd` stands permanently, the
refusal R-1 recording it is never deleted, and each replacement must earn its own verdict from
`@auditor` — no replacement inherits anything from the entry it replaces. A request to supersede an
entry because the work turned out to be hard, rather than because the check is demonstrably wrong,
is refused. This paragraph exists because quietly retiring inconvenient entries is the mechanism by
which a factory makes its own failures disappear, and bounding it in advance is cheaper than arguing
about it later.

Three seats have now produced passing runs of C-142 and C-143 — `@scribe` while writing them and
`@builder` while investigating. **None of those is evidence.** A verdict is a run by the seat that
cannot change what it judges, so every entry below stays `unclaimed` until `verdicts/<claim-id>.md`
is committed by `@auditor`.

**Unaffected: C-1 and C-5 through C-139.** C-1 runs `RUN.md`'s own command, which does its own
`docker run`; its `docker network create --internal tk-s1-noout` line is vestigial and unused, so the
entry stands. C-5 through C-139 reach the service through the prelude's `B`, which was never the
defect — they need only the corrected start-up in §7 and the lock in §8. That is one setup defect,
not 137 broken checks.

---

# ERRATA 2 — the checks audited a working tree, not a revision

## Defect 5 — every path-bearing Check builds from a mutable shared working tree

Found by `@auditor`, which refused to run C-142 rather than audit uncommitted work. §8's Docker lock
does not touch this: the collision is **git state, not Docker state**. A Check can be correct, the
lock uncontended, and the audit still meaningless because the bytes moved between commit and run.

Every path-bearing Check hard-codes `/Users/aashanjaved/band-work/result` — the writing seat's live
working tree. So "clone the named revision and work only there" and "run the Check exactly as
written" coincide **only while that tree is clean**, and no amount of cloning fixes it, because the
Check builds from the live path whatever the auditor checks out. Demonstrated:

```
$ git -C /tmp/revprobe checkout 90028fd   # a clone at the named revision
  clone app.py : 1908 bytes  (blob 4b71552)
  live  app.py : 42127 bytes (blob b3afe57)
```

A PASS on those 42127 bytes would certify code that exists in nobody's history and that no graded
checkout would ever contain.

Affects the five live path-bearing entries: **C-1, C-142, C-143, C-146, C-147**. It does *not* affect
C-5 through C-139: none of them reads a repository path — they reach the running service over HTTP
through the prelude's `B`. The path enters only at build time, so repairing these five repairs the
whole chain.

## §10 Audit a revision, not a working tree

Replacement checks take the repository path from `TK_REPO`, defaulting to the canonical path, so with
`TK_REPO` unset they behave identically to the entries they replace:

```sh
export TK_REPO=/Users/aashanjaved/band-work/result/.auditor-clones/<claim>
```

`@auditor` clones the named revision, checks it out, and exports `TK_REPO` at that clone. A clone is
immutable while nobody writes to it, which the writing seats do not. Each replacement below then
asserts, **in the Check itself**, that the tree is clean before the run and clean and still at the
same revision after it — so a check cannot silently audit a tree that moved underneath it. Record the
revision printed by the final assertion in the verdict.

## Replacement entries

### C-148: RUN.md's own command builds and starts the service from a clean checkout, without manual setup.
Check: `R="${TK_REPO:-/Users/aashanjaved/band-work/result}"; test -z "$(git -C "$R" status --porcelain)" || { echo "TREE NOT CLEAN IN $R"; exit 1; }; before=$(git -C "$R" rev-parse HEAD); cd "$R/stage-1" && docker rm -f tk-s1 >/dev/null 2>&1; awk '/^```/{f=!f;next} f' RUN.md > /tmp/tk-runmd.sh && test -s /tmp/tk-runmd.sh && sh -eux /tmp/tk-runmd.sh && start=$(date +%s) && until curl -fsS http://127.0.0.1:18080/health; do [ $(( $(date +%s) - start )) -lt 60 ] || { echo "NOT HEALTHY"; exit 1; }; sleep 1; done && test -z "$(git -C "$R" status --porcelain)" && test "$(git -C "$R" rev-parse HEAD)" = "$before" && echo "RUNMD OK AT $before"`
Passes when: exits 0 and prints the `/health` body then `RUNMD OK AT <revision>`. Replaces C-1. The fenced code blocks of `RUN.md` must contain exactly the shell commands that build and start the service, must need no editing, and must work from the stage directory of **any** clean checkout — so a command that only works in one seat's home directory does not pass.
Status: held in reserve (activates per REFUSALS.md at da45651)

### C-149: The service builds from a clean container at a named revision and serves /health within 60 seconds.
Check: `R="${TK_REPO:-/Users/aashanjaved/band-work/result}"; test -z "$(git -C "$R" status --porcelain)" || { echo "TREE NOT CLEAN IN $R"; exit 1; }; before=$(git -C "$R" rev-parse HEAD); docker rm -f tk-s1 >/dev/null 2>&1; docker network rm tk-s1-net >/dev/null 2>&1; docker builder prune -af >/dev/null 2>&1; test -f "$R/stage-1/Dockerfile" && test -f "$R/stage-1/RUN.md" && docker network create tk-s1-net && docker build --no-cache -t tk-s1 "$R/stage-1" && docker run -d --name tk-s1 --network tk-s1-net -p 18080:8080 -e PORT=8080 tk-s1 && start=$(date +%s) && until curl -fsS http://127.0.0.1:18080/health; do [ $(( $(date +%s) - start )) -lt 60 ] || { echo "NOT HEALTHY WITHIN 60s"; exit 1; }; sleep 1; done && echo " HEALTHY IN $(( $(date +%s) - start ))s" && test "$(docker inspect tk-s1 --format '{{json .NetworkSettings.Ports}}')" != "{}" && echo "PORT PUBLISHED" && test -z "$(git -C "$R" status --porcelain)" && test "$(git -C "$R" rev-parse HEAD)" = "$before" && echo "TREE CLEAN AND UNMOVED AT $before"`
Passes when: exits 0 and prints the `/health` body, then `HEALTHY IN <n>s` with `n` at most 60, then `PORT PUBLISHED`, then `TREE CLEAN AND UNMOVED AT <revision>`. Replaces C-142 and is the gate in its place. It refuses to start against a dirty tree, and it proves afterwards that the tree neither changed nor moved during the run, so the revision it certifies is the revision it built.
Status: held in reserve (activates per REFUSALS.md at da45651)

### C-150: At run time the service has no outbound network access, and still serves /health.
Check: `R="${TK_REPO:-/Users/aashanjaved/band-work/result}"; test -z "$(git -C "$R" status --porcelain)" || { echo "TREE NOT CLEAN IN $R"; exit 1; }; before=$(git -C "$R" rev-parse HEAD); docker rm -f tk-c150 >/dev/null 2>&1; docker network rm tk-c150-noout >/dev/null 2>&1; docker network create --internal tk-c150-noout && test "$(docker network inspect tk-c150-noout --format '{{.Internal}}')" = "true" && docker build -q -t tk-s1 "$R/stage-1" >/dev/null && docker run -d --name tk-c150 --network tk-c150-noout -e PORT=8080 tk-s1 >/dev/null && for i in $(seq 1 60); do docker run --rm --network tk-c150-noout alpine:3 wget -qO- -T3 http://tk-c150:8080/health >/dev/null 2>&1 && break; sleep 1; done; docker run --rm --network tk-c150-noout alpine:3 sh -c 'wget -qO- -T5 http://tk-c150:8080/health || exit 1; nslookup example.com >/dev/null 2>&1 && exit 2; nc -w4 -z 1.1.1.1 80 2>/dev/null && exit 3; wget -qO- -T4 http://example.com >/dev/null 2>&1 && exit 4; echo " NO EGRESS"'; r=$?; docker rm -f tk-c150 >/dev/null 2>&1; docker network rm tk-c150-noout >/dev/null 2>&1; test $r -eq 0 && test -z "$(git -C "$R" status --porcelain)" && test "$(git -C "$R" rev-parse HEAD)" = "$before" && echo "TREE CLEAN AND UNMOVED AT $before"; exit $?`
Passes when: exits 0 and prints the `/health` body, then `NO EGRESS`, then `TREE CLEAN AND UNMOVED AT <revision>`. Replaces C-143. The service is attached only to an internal network and publishes no port; it is reached by container name from a sibling `alpine:3`, the way the graded harness reaches it in isolated mode. Exit 1 means the service did not answer, 2 that DNS resolved, 3 that raw TCP opened, 4 that an HTTP fetch succeeded. Because the probe must print the service's own health body to pass, it cannot pass by a tool being absent.
Status: held in reserve (activates per REFUSALS.md at da45651)

### C-151: The graded stage-1 suite passes in the mode grading uses, at a named revision.
Check: `R="${TK_REPO:-/Users/aashanjaved/band-work/result}"; test -z "$(git -C "$R" status --porcelain)" || { echo "TREE NOT CLEAN IN $R"; exit 1; }; before=$(git -C "$R" rev-parse HEAD); cd /Users/aashanjaved/dark-factory-wearedevs && ./.venv/bin/python -m harness run --track tablekeeper --repo "$R" --stage 1 --mode isolated --out /Users/aashanjaved/band-work/checks/s1-iso-$(date +%s); r=$?; test $r -eq 0 && test -z "$(git -C "$R" status --porcelain)" && test "$(git -C "$R" rev-parse HEAD)" = "$before" && echo "TREE CLEAN AND UNMOVED AT $before"; exit $?`
Passes when: the harness exits 0 reporting zero failures and zero errors for stage 1, then `TREE CLEAN AND UNMOVED AT <revision>` prints. Replaces C-146. `--mode isolated` is the grading mode: the service gets no outbound access and is reached by container name, so a pass cannot be earned by a service that fetches something at run time.
Status: held in reserve (activates per REFUSALS.md at da45651)

### C-152: The shipped stage-1 checks pass in the mode grading uses, at a named revision.
Check: `R="${TK_REPO:-/Users/aashanjaved/band-work/result}"; test -z "$(git -C "$R" status --porcelain)" || { echo "TREE NOT CLEAN IN $R"; exit 1; }; before=$(git -C "$R" rev-parse HEAD); cd /Users/aashanjaved/dark-factory-wearedevs && ./.venv/bin/python -m harness run --track tablekeeper --repo "$R" --stage 1 --mode isolated --out /Users/aashanjaved/band-work/checks/s1-iso-shipped-$(date +%s); r=$?; test $r -eq 0 && test -z "$(git -C "$R" status --porcelain)" && test "$(git -C "$R" rev-parse HEAD)" = "$before" && echo "TREE CLEAN AND UNMOVED AT $before"; exit $?`
Passes when: the harness exits 0 reporting zero failures and zero errors for stage 1, then `TREE CLEAN AND UNMOVED AT <revision>` prints. Replaces C-147. Host mode remains useful while developing, but per the harness's own warning it must never be the basis of a pass, so no live entry in this ledger claims anything from it.
Status: held in reserve (activates per REFUSALS.md at da45651)

## Superseded by Errata 2

| Original | Replaced by | Why |
|---|---|---|
| C-1 | C-148 | built from a mutable shared working tree, not a revision |
| C-142 | C-149 | same; was the gate, and C-149 is the gate in its place |
| C-143 | C-150 | same |
| C-146 | C-151 | same |
| C-147 | C-152 | same |

These supersessions need `@registrar`'s authorisation, exactly as the first six did, and the same
bound applies: supersession is not absolution. C-5 through C-139 are untouched by Defect 5.

---

# ERRATA 3 — four Checks contradict this ledger's own occupancy rule

Four Checks have FAIL verdicts at revision `9c8c1158`, each with a quoted run, and all four are
defects in the Check rather than the implementation. The bound set at `66e7967` is met: a defect
reproduced in the Check from a run by the seat that cannot change what it judges.

```
C-28   AssertionError: status 409 want (201,)  {'code': 'table_unavailable'}
C-46   AssertionError: status 409 want (201,)  {'code': 'table_unavailable'}
C-123  AssertionError: status 409 want (201,)  {'code': 'table_unavailable'}
C-56   AssertionError: status 201 want 404     {'restaurant_id': 'r_ny', 'table_id': 't_2'}
```

The graded suite **passed** at that revision — `120 passed, 0 failed, 0 errors`, mode isolated — so
the implementation is right and these four checks are wrong.

## Defect 6 — three Checks demand more simultaneous bookings than occupancy permits

With `slot_minutes=30` and `reservation_duration_minutes=90`, two starts thirty minutes apart on one
table always overlap. The fixture's real ceiling:

```
bookable starts:                    18:00 18:30 19:00 19:30 20:00 20:30 21:00 21:30 22:00
mutually non-overlapping per table: 18:00 19:30 21:00                      -> 3
ceiling across t_1, t_2, t_3:                                              -> 9
```

- **C-46** asks for 27 confirmed bookings where the ceiling is 9.
- **C-123** books 9 across `18:00/18:30/19:00 × 3 tables`, where those three times pairwise overlap
  on every table, so the ceiling for that slot set is 3.
- **C-28** takes one availability snapshot and then books `available_table_ids[0]` for all nine
  slots — always `t_2` — so its own first booking invalidates the snapshot it is still reading.

The `409 table_unavailable` all three treat as failure **is what C-21, C-47 and C-48 require**, and
those three pass. So this is the same class of error as C-0: a Check contradicting a rule stated
elsewhere in this same file. C-0 broke the one-claim-one-entry rule; these break the occupancy rule.

## Defect 7 — the fixture cannot express "a table of another restaurant"

C-56's third case books `restaurant_id=r_ny` with `table_id=t_2` and expects 404. But `DSTR(...)`
calls `REST(id=rid, ...)`, and `REST` supplies the default table list, so **`r_ny` has its own
`t_2`** at capacity 4. `201` is correct and `404` would be wrong. The claim's prose is sound; the
fixture never creates the situation it describes. C-56's other two cases — `r_nope` and `t_nope` —
are correct and pass.

## Replacement entries

**These four have NOT been executed against a running service.** The `/tmp/tk-docker.lock` was held
by `@builder` when they were written, so per §8 this seat waited rather than taking it. Their
arithmetic is verified against the fixture's ceiling and their bodies are syntax-checked, but that is
the same standing errata-2's replacements had when `@registrar` refused to supersede working checks
with unexecuted ones. **Supersession of C-28, C-46, C-56 and C-123 should not be authorised until
these four have been run.** `@scribe` will run them as soon as the lock frees and report the output.

### C-153: A starts_at_local taken from availability is accepted unchanged by POST /reservations.
Check: `python3 -c "$P"'
SETUP()
slots=[(s["starts_at_local"],s["starts_at"]) for s in OK(AV("r_anker",F,4),200)["slots"]]
assert len(slots)==9,slots
for at,want in slots:
    t,_=SETUP()
    fr=FREE("r_anker",F,4,at)
    assert fr,("no table free at "+at)
    b=OK(BOOK(t,at,"k-"+at,tid=fr[0]),201)
    assert b["starts_at_local"]==at,(at,b["starts_at_local"])
    assert b["starts_at"]==want,(want,b["starts_at"])
print("PASS",len(slots))'`
Passes when: prints `PASS 9`. Replaces C-28. Every advertised slot is bookable verbatim and echoes back the same local and absolute start. State is reset before each slot, so the availability snapshot is never invalidated by the check's own earlier bookings — which is what C-28 got wrong.
Status: passed at ec1fe94 — see verdicts/C-153.md

### C-154: References are unique across all reservations.
Check: `python3 -c "$P"'
t,_=SETUP()
refs=[]
for at in ["18:00","19:30","21:00"]:
    for tid in ["t_1","t_2","t_3"]:
        refs.append(OK(BOOK(t,F+"T"+at,"k-%s-%s"%(at,tid),tid=tid,ps=2),201)["reference"])
assert len(refs)==9,refs
assert len(set(refs))==9,"duplicate reference among %r"%refs
for r in refs: assert REF.match(r),"bad reference %r"%r
print("PASS",len(set(refs)))'`
Passes when: prints `PASS 9`. Replaces C-46. 18:00, 19:30 and 21:00 are the only mutually non-overlapping starts on this fixture, so nine coexisting confirmed bookings is the ceiling and every one is accepted; each reference is distinct and well-formed.
Status: passed at ec1fe94 — see verdicts/C-154.md

### C-155: An unknown restaurant, an unknown table, or a table of another restaurant is 404 not_found.
Check: `python3 -c "$P"'
RESET(FX(restaurants=[REST(),REST(id="r_two",name="Two",tables=[{"id":"t_x1","label":"1","capacity":4}])]))
t=LOGIN(ADA)
ERR(BOOK(t,F+"T19:00","k1",rid="r_nope"),404,"not_found")
ERR(BOOK(t,F+"T19:00","k2",tid="t_nope"),404,"not_found")
ERR(BOOK(t,F+"T19:00","k3",rid="r_anker",tid="t_x1"),404,"not_found")
ERR(BOOK(t,F+"T19:00","k4",rid="r_two",tid="t_2"),404,"not_found")
print("PASS")'`
Passes when: prints `PASS`. Replaces C-56. The two restaurants now have disjoint table ids, so the cross-restaurant case is genuinely expressible and is checked in both directions: `t_x1` exists but under `r_two`, and `t_2` exists but under `r_anker`.
Status: passed at ec1fe94 — see verdicts/C-155.md

### C-156: A moves list outside 1 to 8 entries is 422 validation_failed.
Check: `python3 -c "$P"'
ta,_=SETUP()
refs=[OK(BOOK(ta,F+"T"+at,"k-%s-%s"%(at,tid),tid=tid,ps=2),201)["reference"] for at in ["18:00","19:30","21:00"] for tid in ["t_1","t_2","t_3"]]
assert len(refs)==9,refs
ERR(MOVES(ta,"m0",[]),422,"validation_failed")
ERR(MOVES(ta,"m9",[{"reference":r} for r in refs]),422,"validation_failed")
OK(MOVES(ta,"m8",[{"reference":r} for r in refs[:8]]),201)
print("PASS")'`
Passes when: prints `PASS`. Replaces C-123. Zero entries and nine entries are refused; eight are accepted. The nine references are built on the non-overlapping starts, so all nine coexist — the fixture's ceiling is exactly nine and this claim needs exactly nine, with no slack for a spare booking.
Status: passed at ec1fe94 — see verdicts/C-156.md

## Superseded by Errata 3 — pending authorisation and a run

| Original | Replaced by | Why |
|---|---|---|
| C-28 | C-153 | booked against an availability snapshot its own bookings invalidated |
| C-46 | C-154 | demanded 27 coexisting bookings where the ceiling is 9 |
| C-56 | C-155 | fixture gave both restaurants the same table ids |
| C-123 | C-156 | booked 9 across three pairwise-overlapping starts |

`@registrar` authorises supersession, not `@scribe`, and the errata-2 precedent says entries of
unexecuted shape should not displace entries of proven shape. These four are unexecuted. The FAIL
verdicts establish the originals are defective; they do not establish that the replacements work.

---
---

# ═══ STAGE 2 LEDGER ═══

Owner: `@scribe`. This section defines "done" for **stage 2**. It is appended, not substituted:
**everything above this line is stage 1 and remains evidence.** Stage-1 entries keep their statuses,
their verdicts and their refusals, because `stage-2/` is graded against **suite 1 and suite 2** and a
regression in stage-1 behaviour loses both stages.

- Result repository: `/Users/aashanjaved/band-work/result`
- Implementation under test: `/Users/aashanjaved/band-work/result/stage-2/`
- Specification: `tablekeeper/spec/stage-2.md`, with `stage-1.md` continuing to apply
- Stage-2 claim ids are prefixed **`S-`** so no reader has to infer which stage a claim belongs to.
  Verdicts go to `verdicts/S-<n>.md`.

**S-0 is the gate.** Nothing else is audited until it passes. Per stage 1's D-1, the gate asserts the
port **genuinely published** — the thing C-0 assumed and never checked.

## Stage-2 Conventions

§1 to §10 of the stage-1 Conventions continue to apply, with the additions and corrections below.
Carried forward and unchanged: **§5** order-independence (every check seeds its own state), **§8**
the `mkdir`-atomic Docker lock, the **F-5** clean-tree bracket, the **commit freeze** from BATCH
START to BATCH END, and per-claim container and network names. §8 and the freeze were both exercised
in stage 1 and held.

### §11 The canonical form of a Check

> The canonical form of a Check is the exact byte sequence between the backticks following `Check: `
> — stripped of surrounding whitespace, with no trailing newline, and with no normalisation of
> internal whitespace or line endings. Anchor it as `sha256` of those bytes and record the byte
> count beside the digest. `Passes when:` and `Status:` are not part of it.

Stage 1 produced five different digests for one Check, from five correct computations of five
different readings. The byte count is the cheap guard: a digest tells a reader that something
differs, a byte count tells them what.

### §12 The repository path comes from the environment

Two stage folders now exist, so no Check hard-codes a repository path. Every path-bearing Check
reads `TK_REPO`, defaulting to the canonical location, which lets `@auditor` run against an
immutable clone instead of `@builder`'s live tree:

```sh
export TK_REPO="${TK_REPO:-/Users/aashanjaved/band-work/result}"
```

This replaces retired C-148..C-152, which were never activated.

### §13 A handoff anchors the Check text it was run against

A handoff names, per claim, the `sha256` and byte count of the canonical Check form it ran, alongside
the code blobs. **This is detection, not prevention.** It makes a Check moving between being read and
being run *visible*; it does not stop it moving. The window stays open, and stage 2 must not record a
passing batch as evidence that F-11 is closed.

### §14 Start-up for stage 2

```sh
docker rm -f tk-s2 >/dev/null 2>&1; docker network rm tk-s2-net >/dev/null 2>&1; docker network create tk-s2-net >/dev/null 2>&1; docker build -t tk-s2 "$TK_REPO/stage-2" && docker run -d --name tk-s2 --network tk-s2-net -p 18080:8080 -e PORT=8080 tk-s2 && for i in $(seq 1 60); do curl -fsS http://127.0.0.1:18080/health >/dev/null 2>&1 && break; sleep 1; done
```

Teardown, after every self-verification:

```sh
docker rm -f tk-s2 >/dev/null 2>&1; docker network rm tk-s2-net >/dev/null 2>&1; echo "torn down"
```

### §15 Two preludes: API and browser

The stage-1 §6 prelude is unchanged and remains the instrument for **re-running stage-1 claims** —
4128 bytes, lifted independently by four seats, 139 checks, zero defects.

**Every stage-2 claim, API and UI alike, uses one prelude: `$W` below.** It carries the API helpers
*and* the browser helpers over a single stage-2 fixture, so the two cannot diverge — a stage-1 fixture
has no `combinable` and labels its tables `1`,`2`,`3`, which would silently make a combination claim
untestable. It runs under the harness's interpreter, which carries Playwright and Chromium. That is
the auditor's tooling, not the service's, exactly as `alpine:3` was for C-143:

```sh
export PWPY=/Users/aashanjaved/dark-factory-wearedevs/.venv/bin/python
export W="$(awk '/^#PW-BEGIN$/{f=1;next} /^#PW-END$/{f=0} f' "$TK_REPO/LEDGER.md")"
```

Confirm both loaded:

```sh
$PWPY -c "$W"'
print("PW OK", BASE, REPO)'
```

Note the newline after the opening quote, as in §2.

```python
#PW-BEGIN
import json,os,re,threading,urllib.request as U
from urllib.parse import urlencode as QS
from playwright.sync_api import sync_playwright
BASE=os.environ.get("TK_BASE","http://127.0.0.1:18080")
REPO=os.environ.get("TK_REPO","/Users/aashanjaved/band-work/result")
WD=["mon","tue","wed","thu","fri","sat","sun"]
ADA={"id":"u_ada","email":"ada@example.com","password":"correct horse","display_name":"Ada"}
BOB={"id":"u_bob","email":"bob@example.com","password":"correct horse","display_name":"Bob"}
F="2027-06-10"
def R(m,p,b=None,tok=None,key=None,hdr=None):
    h={"Content-Type":"application/json"}
    if tok: h["Authorization"]="Bearer "+tok
    if key is not None: h["Idempotency-Key"]=key
    if hdr: h.update(hdr)
    d=None if b is None else (b if isinstance(b,bytes) else json.dumps(b).encode())
    try:
        x=U.urlopen(U.Request(BASE+p,method=m,data=d,headers=h),timeout=20); raw=x.read()
    except U.HTTPError as e:
        raw=e.read()
        try: bd=json.loads(raw or b"null")
        except Exception: bd={"raw":raw.decode("utf-8","replace")}
        return e.code,bd,dict(e.headers)
    try: bd=json.loads(raw or b"null")
    except Exception: bd={"raw":raw.decode("utf-8","replace")}
    return x.status,bd,dict(x.headers)
def OK(r,*w):
    s,b,_=r
    assert s in w,"status %s want %s body %r"%(s,w,b)
    return b
def ERR(r,w,code):
    s,b,_=r
    assert s==w,"status %s want %s body %r"%(s,w,b)
    assert b.get("error",{}).get("code")==code,"code %r want %r"%(b.get("error"),code)
def REST(**o):
    r={"id":"r_anker","name":"Zum Anker","timezone":"Europe/Berlin","slot_minutes":30,
       "reservation_duration_minutes":90,"cancellation_cutoff_minutes":120,
       "opening_hours":[{"weekday":w,"opens":"18:00","closes":"23:30"} for w in WD],
       "tables":[{"id":"t_1","label":"Window","capacity":2},{"id":"t_2","label":"Corner","capacity":4},
                 {"id":"t_3","label":"Terrace","capacity":4}],
       "combinable":[["t_1","t_2"],["t_2","t_3"]]}
    r.update(o); return r
def FX(**o):
    f={"users":[ADA,BOB],"restaurants":[REST()],"reservations":[]}
    f.update(o); return f
def RESET(f):
    s,b,_=R("POST","/_test/reset",f)
    assert s==204,"reset %s %r"%(s,b)
def LOGIN(u):
    return OK(R("POST","/auth/login",{"email":u["email"],"password":u["password"]}),200)["token"]
def SETUP(f=None):
    RESET(f or FX()); return LOGIN(ADA),LOGIN(BOB)
def AV(rid,date,ps,tok=None):
    return R("GET","/availability?"+QS({"restaurant_id":rid,"date":date,"party_size":ps}),tok=tok)
def SLOT(rid,date,ps,at):
    for s in OK(AV(rid,date,ps),200)["slots"]:
        if s["starts_at_local"]==at: return s
    return None
def BOOK(tok,at,key,rid="r_anker",ps=4,**o):
    body={"restaurant_id":rid,"starts_at_local":at,"party_size":ps}; body.update(o)
    return R("POST","/reservations",body,tok=tok,key=key)
def UI(fn,w=1280,h=900,route="/"):
    with sync_playwright() as p:
        br=p.chromium.launch()
        pg=br.new_page(viewport={"width":w,"height":h})
        try:
            if route is not None: pg.goto(BASE+route,wait_until="load")
            return fn(pg)
        finally: br.close()
def SEL(t): return '[data-testid="%s"]'%t
def SELSTART(pfx): return '[data-testid^="%s"]'%pfx
def TID(pg,t): return pg.query_selector(SEL(t))
def SEE(pg,t):
    e=TID(pg,t); return bool(e) and e.is_visible()
def TXT(pg,t):
    e=TID(pg,t)
    return e.inner_text().strip() if e else None
def FILL(pg,t,v): pg.fill('[data-testid="%s"]'%t,str(v))
def CLICK(pg,t): pg.click('[data-testid="%s"]'%t)
def STYLE(pg,t,props=("backgroundColor","borderTopColor","color","opacity","outlineStyle","textDecorationLine","fontWeight")):
    return pg.eval_on_selector('[data-testid="%s"]'%t,
      "e=>{const s=getComputedStyle(e);return "+json.dumps(list(props))+".map(k=>s[k])}")
def LUM(css):
    v=[int(x) for x in re.findall(r"\d+",css)[:3]]
    f=[]
    for c in v:
        c=c/255.0
        f.append(c/12.92 if c<=0.03928 else ((c+0.055)/1.055)**2.4)
    return 0.2126*f[0]+0.7152*f[1]+0.0722*f[2]
def RATIO(fg,bg):
    a,b=LUM(fg),LUM(bg)
    hi,lo=max(a,b),min(a,b)
    return (hi+0.05)/(lo+0.05)
def OVERFLOW(pg):
    return pg.evaluate("()=>({sw:document.documentElement.scrollWidth,cw:document.documentElement.clientWidth})")
def LABELOF(pg,t):
    return pg.evaluate("""(t)=>{const i=document.querySelector('[data-testid="'+t+'"]');
        if(!i) return null; if(i.labels&&i.labels.length&&i.labels[0].textContent.trim()) return i.labels[0].textContent.trim();
        const al=i.getAttribute('aria-label'); if(al&&al.trim()) return al.trim();
        const lb=i.getAttribute('aria-labelledby');
        if(lb){const e=document.getElementById(lb); if(e&&e.textContent.trim()) return e.textContent.trim();}
        return null}""",t)
def SIGNUP_UI(pg,email,pw,name):
    pg.goto(BASE+"/signup",wait_until="load")
    FILL(pg,"signup-email",email); FILL(pg,"signup-password",pw); FILL(pg,"signup-display-name",name)
    CLICK(pg,"signup-submit"); pg.wait_for_timeout(700)
def LOGIN_UI(pg,email=None,pw=None):
    pg.goto(BASE+"/login",wait_until="load")
    FILL(pg,"login-email",email or ADA["email"]); FILL(pg,"login-password",pw or ADA["password"])
    CLICK(pg,"login-submit"); pg.wait_for_timeout(700)
def SEARCH_UI(pg,rid="r_anker",date=None,ps=4):
    pg.goto(BASE+"/",wait_until="load")
    pg.select_option('[data-testid="restaurant-select"]',rid)
    FILL(pg,"date-input",date or F); FILL(pg,"party-size-input",ps)
    CLICK(pg,"search-button"); pg.wait_for_timeout(900)
def CELL(pg,ids,at):
    return TID(pg,"slot-%s-%s"%("+".join(ids) if isinstance(ids,list) else ids,at))
def AVAILATTR(pg,ids,at):
    c=CELL(pg,ids,at); return c.get_attribute("data-available") if c else None
#PW-END
```

### §16 Proxies are labelled, and unsettleable properties are declared

The UI is 25% of the score and a human judges it. Three rules, authorised as binding by `@registrar`
and stated by `@auditor` as its operational bar:

1. Where a human-judged property has a **faithful deterministic proxy**, the entry states the proxy
   *and* names what the proxy does not establish. A passing verdict then means exactly what it says.
2. Where it has **no faithful proxy**, the property is listed under **Declared human-judged** at the
   end of this section and **no entry is written for it**. A claim honestly marked unsettleable is
   worth more than one that can be passed without meaning anything, and per `@registrar` such a claim
   is *not* a case-2 refusal — case 2 is a claim that was supposed to be settled and silently was not.
3. An entry must never check the attribute a test can read *instead of* the property a human will
   judge. `aria-label` present is not the label being visible; seven `data-state` values existing is
   not seven visually distinct states. A proxy presented as the whole property is a **case-3 refusal**.

Stage 1 ended on an instrument reporting success about something it never tested. Five of the seven
ledger defects were checks that could not establish what their prose claimed. The UI is where that
mistake is cheapest to make and most expensive to find, because a green `data-testid` looks exactly
like a working interface until a person opens it.

## The gate

### S-0: The stage-2 service builds from a clean container, serves /health within 60 seconds, and genuinely publishes its port.
Check: `TK_REPO="${TK_REPO:-/Users/aashanjaved/band-work/result}"; test -z "$(git -C "$TK_REPO" status --porcelain)" || { echo "TREE NOT CLEAN"; exit 1; }; before=$(git -C "$TK_REPO" rev-parse HEAD); docker rm -f tk-s2 >/dev/null 2>&1; docker network rm tk-s2-net >/dev/null 2>&1; docker builder prune -af >/dev/null 2>&1; test -f "$TK_REPO/stage-2/Dockerfile" && test -f "$TK_REPO/stage-2/RUN.md" && docker network create tk-s2-net && docker build --no-cache -t tk-s2 "$TK_REPO/stage-2" && docker run -d --name tk-s2 --network tk-s2-net -p 18080:8080 -e PORT=8080 tk-s2 && start=$(date +%s) && until curl -fsS http://127.0.0.1:18080/health; do [ $(( $(date +%s) - start )) -lt 60 ] || { echo "NOT HEALTHY WITHIN 60s"; exit 1; }; sleep 1; done && echo " HEALTHY IN $(( $(date +%s) - start ))s" && test "$(docker inspect tk-s2 --format '{{json .NetworkSettings.Ports}}')" != "{}" && echo "PORT PUBLISHED" && test -z "$(git -C "$TK_REPO" status --porcelain)" && test "$(git -C "$TK_REPO" rev-parse HEAD)" = "$before" && echo "TREE CLEAN AND UNMOVED AT $before"`
Passes when: exits 0 and prints the `/health` body, then `HEALTHY IN <n>s` with `n` at most 60, then `PORT PUBLISHED`, then `TREE CLEAN AND UNMOVED AT <revision>`. This is the gate. `PORT PUBLISHED` is the assertion C-0 assumed and never checked, which cost stage 1 an hour; it is asserted here rather than inferred from the curl succeeding.
Status: unclaimed

### S-1: The stage-2 service has no outbound network access at run time and still serves.
Check: `TK_REPO="${TK_REPO:-/Users/aashanjaved/band-work/result}"; docker rm -f tk-s1x >/dev/null 2>&1; docker network rm tk-s1x-noout >/dev/null 2>&1; docker network create --internal tk-s1x-noout && test "$(docker network inspect tk-s1x-noout --format '{{.Internal}}')" = "true" && docker build -q -t tk-s2 "$TK_REPO/stage-2" >/dev/null && docker run -d --name tk-s1x --network tk-s1x-noout -e PORT=8080 tk-s2 >/dev/null && for i in $(seq 1 60); do docker run --rm --network tk-s1x-noout alpine:3 wget -qO- -T3 http://tk-s1x:8080/health >/dev/null 2>&1 && break; sleep 1; done; docker run --rm --network tk-s1x-noout alpine:3 sh -c 'wget -qO- -T5 http://tk-s1x:8080/health || exit 1; nslookup example.com >/dev/null 2>&1 && exit 2; nc -w4 -z 1.1.1.1 80 2>/dev/null && exit 3; wget -qO- -T4 http://example.com >/dev/null 2>&1 && exit 4; echo " NO EGRESS"'; r=$?; docker rm -f tk-s1x >/dev/null 2>&1; docker network rm tk-s1x-noout >/dev/null 2>&1; exit $r`
Passes when: exits 0 and prints the `/health` body then `NO EGRESS`. Replicates C-143 against stage 2, because §2's no-outbound rule applies to every stage and the UI adds fonts, scripts and stylesheets — the exact assets a service is tempted to fetch at run time. Exit 1 means the service did not answer, 2 DNS resolved, 3 raw TCP opened, 4 an HTTP fetch succeeded.
Status: unclaimed

### S-2: RUN.md's own command builds and starts the stage-2 service from a clean checkout.
Check: `TK_REPO="${TK_REPO:-/Users/aashanjaved/band-work/result}"; test -z "$(git -C "$TK_REPO" status --porcelain)" || { echo "TREE NOT CLEAN"; exit 1; }; before=$(git -C "$TK_REPO" rev-parse HEAD); cd "$TK_REPO/stage-2" && docker rm -f tk-s2 >/dev/null 2>&1; awk '/^```/{f=!f;next} f' RUN.md > /tmp/tk-s2-runmd.sh && test -s /tmp/tk-s2-runmd.sh && sh -eux /tmp/tk-s2-runmd.sh && start=$(date +%s) && until curl -fsS http://127.0.0.1:18080/health; do [ $(( $(date +%s) - start )) -lt 60 ] || { echo "NOT HEALTHY"; exit 1; }; sleep 1; done && test -z "$(git -C "$TK_REPO" status --porcelain)" && test "$(git -C "$TK_REPO" rev-parse HEAD)" = "$before" && echo "RUNMD OK AT $before"`
Passes when: exits 0 and prints the `/health` body then `RUNMD OK AT <revision>`. The fenced blocks of `stage-2/RUN.md` must hold exactly the build-and-start commands, need no editing, and work from the stage directory of any clean checkout. Stage 1's C-1 found a `RUN.md` that attached the container to an `--internal` network and published nothing; this asserts the replacement did not regress.
Status: unclaimed

## Stage 1 must still behave — stage-2/ is graded against suite 1

### S-3: The stage-1 graded suite passes against stage-2/ in the grading mode.
Check: `TK_REPO="${TK_REPO:-/Users/aashanjaved/band-work/result}"; test -z "$(git -C "$TK_REPO" status --porcelain)" || { echo "TREE NOT CLEAN"; exit 1; }; before=$(git -C "$TK_REPO" rev-parse HEAD); cd /Users/aashanjaved/dark-factory-wearedevs && ./.venv/bin/python -m harness run --track tablekeeper --repo "$TK_REPO" --stage 2 --mode isolated --out /Users/aashanjaved/band-work/checks/s2-iso-$(date +%s); r=$?; test $r -eq 0 && test -z "$(git -C "$TK_REPO" status --porcelain)" && test "$(git -C "$TK_REPO" rev-parse HEAD)" = "$before" && echo "TREE CLEAN AND UNMOVED AT $before"; exit $?`
Passes when: the harness exits 0 reporting zero failures and zero errors for **both** stage 1 and stage 2, then `TREE CLEAN AND UNMOVED AT <revision>` prints. `--stage 2` runs suite 1 and suite 2 against `stage-2/`, so a stage-1 regression fails here. A printed failure for stage 3 is expected and required; per `harness/cli.py:459` the next-stage probe's exit code is not this run's and the probe failing is the good case.
Status: unclaimed

### S-4: A single-table booking still works end to end after the copy and widening.
Check: `$PWPY -c "$W"'
ta,_=SETUP()
b=OK(BOOK(ta,F+"T19:00","s4",table_id="t_2",ps=4),201)
assert b["status"]=="confirmed" and b["table_id"]=="t_2",b
assert b["table_ids"]==["t_2"],b
assert b["starts_at"].endswith("+02:00") and b["ends_at"].endswith("+02:00"),b
got=OK(R("GET","/reservations/"+b["reference"],tok=ta),200)
assert got["reservation_id"]==b["reservation_id"],got
OK(R("POST","/reservations/"+b["reference"]+"/cancel",tok=ta),200)
assert OK(R("GET","/reservations/"+b["reference"],tok=ta),200)["status"]=="cancelled"
print("PASS")'`
Passes when: prints `PASS`. The stage-1 create/read/cancel path is intact, the legacy `table_id` request form still works, and the response carries both `table_id` and `table_ids` for a one-member set.
Status: unclaimed

### S-5: Stage-1 idempotency, export and import still behave after the widening.
Check: `$PWPY -c "$W"'
ta,_=SETUP()
body={"restaurant_id":"r_anker","table_id":"t_2","starts_at_local":F+"T19:00","party_size":4}
first=OK(R("POST","/reservations",body,tok=ta,key="s5"),201)
assert OK(R("POST","/reservations",body,tok=ta,key="s5"),200)==first,"replay differs"
ERR(R("POST","/reservations",dict(body,party_size=3),tok=ta,key="s5"),409,"idempotency_key_reuse")
snap=OK(R("GET","/_test/export"),200)
assert snap["track"]=="tablekeeper" and snap["format_version"]==1 and isinstance(snap["state"],dict),snap
s,_,_=R("POST","/_test/import",snap); assert s==204,s
assert OK(R("POST","/reservations",body,tok=ta,key="s5"),200)==first,"receipt lost across import"
assert OK(R("GET","/reservations/"+first["reference"],tok=ta),200)["reference"]==first["reference"]
ERR(R("POST","/_test/import",dict(snap,track="pocketful")),422,"validation_failed")
print("PASS")'`
Passes when: prints `PASS`. Replay returns the identical original response, a changed body is still 409, the export envelope is unchanged, an unchanged export still imports, receipts and bookings survive it, and a wrong track is still refused.
Status: unclaimed

### S-6: The stage-1 DST rules still hold, in both zones, with absolute-time duration.
Check: `$PWPY -c "$W"'
import datetime as D
NY=REST(id="r_us",timezone="America/New_York",opening_hours=[{"weekday":w,"opens":"01:00","closes":"06:00"} for w in WD],combinable=[])
DE=REST(id="r_de",opening_hours=[{"weekday":w,"opens":"01:00","closes":"06:00"} for w in WD],combinable=[])
RESET(FX(restaurants=[DE,NY])); ta=LOGIN(ADA)
ERR(BOOK(ta,"2026-03-29T02:30","d1",rid="r_de",table_id="t_2"),422,"invalid_local_time")
ERR(BOOK(ta,"2026-03-08T02:30","d2",rid="r_us",table_id="t_2"),422,"invalid_local_time")
b=OK(BOOK(ta,"2026-11-01T01:30","d3",rid="r_us",table_id="t_2"),201)
assert b["starts_at"]=="2026-11-01T01:30:00-04:00",b["starts_at"]
assert b["ends_at"]=="2026-11-01T02:00:00-05:00",b["ends_at"]
c=OK(BOOK(ta,"2026-10-25T02:00","d4",rid="r_de",table_id="t_2"),201)
assert c["starts_at"]=="2026-10-25T02:00:00+02:00",c["starts_at"]
assert c["ends_at"]=="2026-10-25T02:30:00+01:00",c["ends_at"]
assert [s["starts_at_local"] for s in OK(AV("r_de","2026-03-29",2),200)["slots"]]==["2026-03-29T"+t for t in ["01:00","01:30","03:00","03:30","04:00","04:30"]]
print("PASS")'`
Passes when: prints `PASS`. The skipped hour is still refused and absent from availability in both zones, the repeated hour still resolves to the first occurrence, and duration is still absolute — New York 01:30 ends at local 02:00 at `-05:00`, the specification's own example.
Status: unclaimed

## Model: combinable pairs (§Model)

### S-7: A declared pair is bookable and occupies both tables for the full duration.
Check: `$PWPY -c "$W"'
ta,tb=SETUP()
b=OK(BOOK(ta,F+"T19:00","s7",table_ids=["t_1","t_2"],ps=6),201)
assert b["table_ids"]==["t_1","t_2"],b
assert "table_id" not in b,"table_id must be omitted when the set has two members: %r"%b
for tid in ["t_1","t_2"]:
    ERR(BOOK(tb,F+"T19:00","s7-"+tid,table_id=tid,ps=2),409,"table_unavailable")
for at in ["18:00","18:30","19:30","20:00"]:
    ERR(BOOK(tb,F+"T"+at,"s7o-"+at,table_id="t_1",ps=2),409,"table_unavailable")
OK(BOOK(tb,F+"T20:30","s7free",table_id="t_1",ps=2),201)
print("PASS")'`
Passes when: prints `PASS`. Both members are occupied for the whole 90 minutes, every overlapping start on either table is refused, and the first non-overlapping start is free — the half-open rule applied to a pair.
Status: unclaimed

### S-8: A pair not listed in combinable is 422 combination_not_allowed.
Check: `$PWPY -c "$W"'
ta,_=SETUP()
ERR(BOOK(ta,F+"T19:00","s8a",table_ids=["t_1","t_3"],ps=6),422,"combination_not_allowed")
ERR(BOOK(ta,F+"T19:00","s8b",table_ids=["t_3","t_1"],ps=6),422,"combination_not_allowed")
OK(BOOK(ta,F+"T19:00","s8c",table_ids=["t_1","t_2"],ps=6),201)
print("PASS")'`
Passes when: prints `PASS`. `[t_1,t_3]` is refused in both orderings even though the two tables are free and their summed capacity is sufficient, while a declared pair at the same slot is accepted.
Status: unclaimed

### S-9: Combining is not transitive.
Check: `$PWPY -c "$W"'
ta,_=SETUP()
ERR(BOOK(ta,F+"T19:00","s9",table_ids=["t_1","t_3"],ps=6),422,"combination_not_allowed")
OK(BOOK(ta,F+"T19:00","s9a",table_ids=["t_1","t_2"],ps=6),201)
RESET(FX()); ta=LOGIN(ADA)
OK(BOOK(ta,F+"T19:00","s9b",table_ids=["t_2","t_3"],ps=8),201)
print("PASS")'`
Passes when: prints `PASS`. `[t_1,t_2]` and `[t_2,t_3]` are both declared and both bookable, and `{t_1,t_3}` is still refused — the specification says transitivity must not be inferred.
Status: unclaimed

### S-10: A combinable entry is an unordered pair.
Check: `$PWPY -c "$W"'
RESET(FX(restaurants=[REST(combinable=[["t_2","t_1"]])])); ta=LOGIN(ADA)
b=OK(BOOK(ta,F+"T19:00","s10",table_ids=["t_1","t_2"],ps=6),201)
assert sorted(b["table_ids"])==["t_1","t_2"],b
RESET(FX(restaurants=[REST(combinable=[["t_1","t_2"]])])); ta=LOGIN(ADA)
OK(BOOK(ta,F+"T19:00","s10b",table_ids=["t_2","t_1"],ps=6),201)
print("PASS")'`
Passes when: prints `PASS`. A pair declared `[t_2,t_1]` is bookable as `[t_1,t_2]` and a pair declared `[t_1,t_2]` is bookable as `[t_2,t_1]`. The fixture's ordering does not constrain the request's.
Status: unclaimed

### S-11: More than two tables is 422 combination_not_allowed.
Check: `$PWPY -c "$W"'
ta,_=SETUP()
ERR(BOOK(ta,F+"T19:00","s11a",table_ids=["t_1","t_2","t_3"],ps=10),422,"combination_not_allowed")
RESET(FX(restaurants=[REST(combinable=[["t_1","t_2"],["t_2","t_3"],["t_1","t_3"]])])); ta=LOGIN(ADA)
ERR(BOOK(ta,F+"T19:00","s11b",table_ids=["t_1","t_2","t_3"],ps=10),422,"combination_not_allowed")
print("PASS")'`
Passes when: prints `PASS`. Three tables is refused even when every constituent pair is declared — the rule is pairs only, not "any set whose pairs are all combinable".
Status: unclaimed

### S-12: A combination's capacity is the sum of its tables' capacities.
Check: `$PWPY -c "$W"'
ta,_=SETUP()
OK(BOOK(ta,F+"T19:00","s12a",table_ids=["t_1","t_2"],ps=6),201)
RESET(FX()); ta=LOGIN(ADA)
ERR(BOOK(ta,F+"T19:00","s12b",table_ids=["t_1","t_2"],ps=7),422,"party_exceeds_capacity")
RESET(FX()); ta=LOGIN(ADA)
OK(BOOK(ta,F+"T19:00","s12c",table_ids=["t_2","t_3"],ps=8),201)
RESET(FX()); ta=LOGIN(ADA)
ERR(BOOK(ta,F+"T19:00","s12d",table_ids=["t_2","t_3"],ps=9),422,"party_exceeds_capacity")
print("PASS")'`
Passes when: prints `PASS`. `t_1`+`t_2` seats exactly 6 and refuses 7; `t_2`+`t_3` seats exactly 8 and refuses 9. The boundary is asserted on both sides for both pairs rather than sampled.
Status: unclaimed

### S-13: A duplicate table id in the set is 422 validation_failed.
Check: `$PWPY -c "$W"'
ta,_=SETUP()
ERR(BOOK(ta,F+"T19:00","s13a",table_ids=["t_2","t_2"],ps=4),422,"validation_failed")
ERR(BOOK(ta,F+"T19:00","s13b",table_ids=["t_1","t_1"],ps=2),422,"validation_failed")
print("PASS")'`
Passes when: prints `PASS`. A duplicate is `validation_failed`, not `combination_not_allowed` — the specification separates a malformed set from an undeclared pair.
Status: unclaimed

### S-14: Any taken table in the set makes the combination 409 table_unavailable.
Check: `$PWPY -c "$W"'
ta,tb=SETUP()
OK(BOOK(ta,F+"T19:00","s14a",table_id="t_1",ps=2),201)
ERR(BOOK(tb,F+"T19:00","s14b",table_ids=["t_1","t_2"],ps=6),409,"table_unavailable")
RESET(FX()); ta,tb=LOGIN(ADA),LOGIN(BOB)
OK(BOOK(ta,F+"T19:00","s14c",table_id="t_2",ps=4),201)
ERR(BOOK(tb,F+"T19:00","s14d",table_ids=["t_1","t_2"],ps=6),409,"table_unavailable")
RESET(FX()); ta,tb=LOGIN(ADA),LOGIN(BOB)
OK(BOOK(ta,F+"T18:00","s14e",table_id="t_2",ps=4),201)
ERR(BOOK(tb,F+"T19:00","s14f",table_ids=["t_1","t_2"],ps=6),409,"table_unavailable")
print("PASS")'`
Passes when: prints `PASS`. Either member being taken refuses the pair, and an *overlapping* rather than identical booking on one member also refuses it.
Status: unclaimed

### S-15: A seeded reservation may hold table_ids, and a seeded cancelled reservation occupies nothing.
Check: `$PWPY -c "$W"'
seed=[{"id":"res_c","reference":"COMBO1","user_id":"u_ada","restaurant_id":"r_anker",
       "table_ids":["t_1","t_2"],"starts_at_local":F+"T19:00","party_size":6}]
RESET(FX(reservations=seed)); ta,tb=LOGIN(ADA),LOGIN(BOB)
g=OK(R("GET","/reservations/COMBO1",tok=ta),200)
assert g["table_ids"]==["t_1","t_2"] and "table_id" not in g,g
ERR(BOOK(tb,F+"T19:00","s15a",table_id="t_1",ps=2),409,"table_unavailable")
seed2=[dict(seed[0],status="cancelled")]
RESET(FX(reservations=seed2)); ta,tb=LOGIN(ADA),LOGIN(BOB)
assert OK(R("GET","/reservations/COMBO1",tok=ta),200)["status"]=="cancelled"
OK(BOOK(tb,F+"T19:00","s15b",table_id="t_1",ps=2),201)
print("PASS")'`
Passes when: prints `PASS`. A seeded combination blocks both its tables; a seeded reservation carrying `status: cancelled` blocks nothing and reads back as cancelled.
Status: unclaimed

## API: available_options (§API)

### S-16: Slots carry available_options listing every single table and every declared pair that fits.
Check: `$PWPY -c "$W"'
SETUP()
s=SLOT("r_anker",F,4,F+"T19:00")
assert s is not None,"no 19:00 slot"
opts=[(o["table_ids"],o["capacity"]) for o in s["available_options"]]
assert opts==[(["t_2"],4),(["t_3"],4),(["t_1","t_2"],6),(["t_2","t_3"],8)],opts
print("PASS",opts)'`
Passes when: prints `PASS` and the option list. For party 4: `t_1` is excluded (capacity 2), both capacity-4 singles appear in fixture order, then both declared pairs in `combinable` order, each with its summed capacity.
Status: unclaimed

### S-17: available_options orders singles in fixture order, then pairs in combinable order.
Check: `$PWPY -c "$W"'
RESET(FX(restaurants=[REST(tables=[{"id":"t_3","label":"Terrace","capacity":4},{"id":"t_1","label":"Window","capacity":4},{"id":"t_2","label":"Corner","capacity":4}],combinable=[["t_2","t_3"],["t_1","t_2"]])]))
s=SLOT("r_anker",F,4,F+"T19:00")
ids=[o["table_ids"] for o in s["available_options"]]
assert ids==[["t_3"],["t_1"],["t_2"],["t_2","t_3"],["t_1","t_2"]],ids
print("PASS",ids)'`
Passes when: prints `PASS` and the order. The fixture deliberately lists tables `t_3,t_1,t_2` and pairs `[t_2,t_3],[t_1,t_2]`, so alphabetical or id-sorted output fails. Singles precede pairs, each group in its own declared order, and `table_ids` within a pair follows `combinable` order.
Status: unclaimed

### S-18: available_table_ids still lists single tables only and is unchanged by combinations.
Check: `$PWPY -c "$W"'
SETUP()
s=SLOT("r_anker",F,4,F+"T19:00")
assert s["available_table_ids"]==["t_2","t_3"],s["available_table_ids"]
assert all(isinstance(x,str) for x in s["available_table_ids"]),s
s2=SLOT("r_anker",F,2,F+"T19:00")
assert s2["available_table_ids"]==["t_1","t_2","t_3"],s2["available_table_ids"]
print("PASS")'`
Passes when: prints `PASS`. `available_table_ids` remains a flat list of single table ids filtered by capacity in fixture order — stage 1's C-20 contract — and gains nothing from `available_options`.
Status: unclaimed

### S-19: An option disappears when any of its tables is taken.
Check: `$PWPY -c "$W"'
ta,_=SETUP()
OK(BOOK(ta,F+"T19:00","s19",table_id="t_1",ps=2),201)
s=SLOT("r_anker",F,4,F+"T19:00")
ids=[o["table_ids"] for o in s["available_options"]]
assert ["t_1","t_2"] not in ids,"pair containing the taken table still offered: %r"%ids
assert ["t_2","t_3"] in ids and ["t_2"] in ids,ids
s2=SLOT("r_anker",F,2,F+"T19:00")
assert ["t_1"] not in s2["available_table_ids"],s2
print("PASS")'`
Passes when: prints `PASS`. Booking `t_1` removes both the `t_1` single and the `[t_1,t_2]` pair, while `[t_2,t_3]` and the `t_2` single remain.
Status: unclaimed

### S-20: available_options respects party_size on the summed capacity.
Check: `$PWPY -c "$W"'
SETUP()
for ps,want in [(2,[["t_1"],["t_2"],["t_3"],["t_1","t_2"],["t_2","t_3"]]),
                (5,[["t_1","t_2"],["t_2","t_3"]]),
                (7,[["t_2","t_3"]]),
                (9,[])]:
    ids=[o["table_ids"] for o in SLOT("r_anker",F,ps,F+"T19:00")["available_options"]]
    assert ids==want,(ps,ids,want)
print("PASS")'`
Passes when: prints `PASS`. Party 5 drops every single because none seats 5 while both pairs remain; party 7 leaves only the capacity-8 pair; party 9 leaves nothing and the slot still appears.
Status: unclaimed

### S-21: A closed day and a no-option slot still appear correctly with combinations present.
Check: `$PWPY -c "$W"'
RESET(FX(restaurants=[REST(opening_hours=[{"weekday":"fri","opens":"18:00","closes":"23:30"}])]))
b=OK(AV("r_anker",F,4),200)
assert b["slots"]==[],b
RESET(FX()); ta=LOGIN(ADA)
for i,tid in enumerate(["t_1","t_2","t_3"]):
    OK(BOOK(ta,F+"T19:00","s21-%d"%i,table_id=tid,ps=2),201)
s=SLOT("r_anker",F,2,F+"T19:00")
assert s is not None and s["available_table_ids"]==[] and s["available_options"]==[],s
print("PASS")'`
Passes when: prints `PASS`. 2027-06-10 is a Thursday, closed in the first fixture, so `slots` is empty. With every table booked the 19:00 slot still appears with both lists empty rather than being omitted.
Status: unclaimed

## API: table_id and table_ids (§API)

### S-22: table_id and table_ids are both accepted, and sending both is 422 validation_failed.
Check: `$PWPY -c "$W"'
ta,_=SETUP()
a=OK(BOOK(ta,F+"T19:00","s22a",table_id="t_2",ps=4),201)
assert a["table_ids"]==["t_2"] and a["table_id"]=="t_2",a
RESET(FX()); ta=LOGIN(ADA)
b=OK(BOOK(ta,F+"T19:00","s22b",table_ids=["t_2"],ps=4),201)
assert b["table_ids"]==["t_2"] and b["table_id"]=="t_2",b
RESET(FX()); ta=LOGIN(ADA)
s,bd,_=R("POST","/reservations",{"restaurant_id":"r_anker","table_id":"t_2","table_ids":["t_2"],"starts_at_local":F+"T19:00","party_size":4},tok=ta,key="s22c")
assert s==422 and bd["error"]["code"]=="validation_failed",(s,bd)
s,bd,_=R("POST","/reservations",{"restaurant_id":"r_anker","table_id":"t_1","table_ids":["t_1","t_2"],"starts_at_local":F+"T19:00","party_size":6},tok=ta,key="s22d")
assert s==422 and bd["error"]["code"]=="validation_failed",(s,bd)
print("PASS")'`
Passes when: prints `PASS`. Either field alone works and means the same thing for a one-member set; both together is 422 even when they agree.
Status: unclaimed

### S-23: Responses carry table_id only when the set has exactly one member.
Check: `$PWPY -c "$W"'
ta,_=SETUP()
one=OK(BOOK(ta,F+"T19:00","s23a",table_ids=["t_2"],ps=4),201)
assert one["table_id"]=="t_2" and one["table_ids"]==["t_2"],one
two=OK(BOOK(ta,F+"T21:00","s23b",table_ids=["t_1","t_2"],ps=6),201)
assert "table_id" not in two,"table_id present on a two-member set: %r"%two
assert two["table_ids"]==["t_1","t_2"],two
for ref,want in [(one["reference"],True),(two["reference"],False)]:
    g=OK(R("GET","/reservations/"+ref,tok=ta),200)
    assert ("table_id" in g)==want,(ref,g)
rs=OK(R("GET","/reservations",tok=ta),200)["reservations"]
for r in rs:
    assert ("table_id" in r)==(len(r["table_ids"])==1),r
print("PASS")'`
Passes when: prints `PASS`. The rule holds on create, on read-by-reference and on the list — `table_ids` always present, `table_id` present exactly when the set is a singleton.
Status: unclaimed

### S-24: PATCH accepts table_ids under the same combination rules.
Check: `$PWPY -c "$W"'
ta,_=SETUP()
a=OK(BOOK(ta,F+"T19:00","s24",table_id="t_2",ps=4),201)
r=a["reference"]
b=OK(R("PATCH","/reservations/"+r,{"table_ids":["t_1","t_2"],"party_size":6},tok=ta),200)
assert b["table_ids"]==["t_1","t_2"] and "table_id" not in b,b
assert b["reference"]==r and b["reservation_id"]==a["reservation_id"],b
ERR(R("PATCH","/reservations/"+r,{"table_ids":["t_1","t_3"]},tok=ta),422,"combination_not_allowed")
ERR(R("PATCH","/reservations/"+r,{"table_ids":["t_1","t_2","t_3"]},tok=ta),422,"combination_not_allowed")
ERR(R("PATCH","/reservations/"+r,{"table_ids":["t_2","t_2"]},tok=ta),422,"validation_failed")
ERR(R("PATCH","/reservations/"+r,{"party_size":7},tok=ta),422,"party_exceeds_capacity")
after=OK(R("GET","/reservations/"+r,tok=ta),200)
assert after["table_ids"]==["t_1","t_2"] and after["party_size"]==6,after
print("PASS")'`
Passes when: prints `PASS`. A single booking widens to a declared pair keeping its identity, every combination rule applies on the amendment path, and the refused amendments leave the booking unchanged.
Status: unclaimed

### S-25: Cancelling a combination frees every table in the set.
Check: `$PWPY -c "$W"'
ta,tb=SETUP()
a=OK(BOOK(ta,F+"T19:00","s25",table_ids=["t_1","t_2"],ps=6),201)
s=SLOT("r_anker",F,2,F+"T19:00")
assert s["available_table_ids"]==["t_3"],s
OK(R("POST","/reservations/"+a["reference"]+"/cancel",tok=ta),200)
s=SLOT("r_anker",F,2,F+"T19:00")
assert s["available_table_ids"]==["t_1","t_2","t_3"],s
ids=[o["table_ids"] for o in SLOT("r_anker",F,6,F+"T19:00")["available_options"]]
assert ["t_1","t_2"] in ids,ids
OK(BOOK(tb,F+"T19:00","s25b",table_ids=["t_1","t_2"],ps=6),201)
print("PASS")'`
Passes when: prints `PASS`. After the cancel both tables return to `available_table_ids`, the pair returns to `available_options`, and another account can book the pair at the same slot.
Status: unclaimed

### S-26: Atomic reservation moves accept table_ids, and no table may end up in overlapping bookings.
Check: `$PWPY -c "$W"'
ta,_=SETUP()
a=OK(BOOK(ta,F+"T19:00","s26a",table_id="t_1",ps=2),201)
b=OK(BOOK(ta,F+"T19:00","s26b",table_id="t_3",ps=4),201)
r=OK(R("POST","/reservation-moves",{"moves":[{"reference":a["reference"],"table_ids":["t_1","t_2"],"party_size":6},{"reference":b["reference"]}]},tok=ta,key="s26m"),201)
assert r["reservations"][0]["table_ids"]==["t_1","t_2"],r
assert "table_id" not in r["reservations"][0],r
ERR(R("POST","/reservation-moves",{"moves":[{"reference":b["reference"],"table_ids":["t_1","t_2"],"party_size":6}]},tok=ta,key="s26n"),409,"table_unavailable")
RESET(FX()); ta=LOGIN(ADA)
c=OK(BOOK(ta,F+"T19:00","s26c",table_id="t_1",ps=2),201)
d=OK(BOOK(ta,F+"T21:00","s26d",table_id="t_2",ps=4),201)
ERR(R("POST","/reservation-moves",{"moves":[{"reference":c["reference"],"table_ids":["t_1","t_2"],"party_size":6},{"reference":d["reference"],"starts_at_local":F+"T19:00","table_id":"t_2","party_size":4}]},tok=ta,key="s26o"),409,"table_unavailable")
assert OK(R("GET","/reservations/"+c["reference"],tok=ta),200)==c,"rejected batch changed a record"
print("PASS")'`
Passes when: prints `PASS`. A move may widen a booking to a declared pair; a move onto a pair whose member is held by an unlisted booking is refused; and a batch whose *resulting* bookings would share `t_2` is refused with both records left untouched.
Status: unclaimed

### S-27: Concurrent bookings of a shared table produce a serialisable outcome with no 5xx.
Check: `$PWPY -c "$W"'
ta,_=SETUP()
def one(i):
    if i%2==0: return BOOK(ta,F+"T19:00","conc-%d"%i,table_ids=["t_1","t_2"],ps=6)
    return BOOK(ta,F+"T19:00","conc-%d"%i,table_id="t_2",ps=4)
out=[None]*40
def w(i):
    try: out[i]=one(i)
    except Exception as e: out[i]=("EXC",repr(e),{})
ts=[threading.Thread(target=w,args=(i,)) for i in range(40)]
for t in ts: t.start()
for t in ts: t.join()
codes=sorted(r[0] for r in out)
assert not [c for c in codes if not isinstance(c,int) or c>=500],"5xx or transport failure: %r"%out
assert codes.count(201)==1,"expected exactly one winner, got %r"%codes
assert codes.count(409)==39,codes
conf=[x for x in OK(R("GET","/reservations",tok=ta),200)["reservations"] if x["status"]=="confirmed"]
assert len(conf)==1,conf
held=set(conf[0]["table_ids"])
for tid in held:
    ERR(BOOK(ta,F+"T19:00","post-"+tid,table_id=tid,ps=2),409,"table_unavailable")
print("PASS",conf[0]["table_ids"])'`
Passes when: prints `PASS` and the winning set. Forty in-flight requests contend for `t_2` through both a single and a pair; exactly one commits, thirty-nine are 409 `table_unavailable`, none is a 5xx, and the surviving booking genuinely holds its tables — which is what "the same results as executing them one at a time in some order" requires at the read after.
Status: unclaimed

## UI: routes and authentication (§UI)

### S-28: The four required screens are reachable directly by URL and return HTML.
Check: `$PWPY -c "$W"'
SETUP()
def f(pg):
    seen={}
    for route,tid in [("/","search-button"),("/signup","signup-submit"),("/login","login-submit"),("/lookup","lookup-submit")]:
        r=pg.goto(BASE+route,wait_until="load")
        ct=(r.header_value("content-type") or "").lower()
        seen[route]=(r.status,ct.split(";")[0],SEE(pg,tid))
        assert r.status==200,(route,r.status)
        assert seen[route][1]=="text/html",(route,ct)
        assert seen[route][2],(route,"missing "+tid)
    return seen
print("PASS",UI(f,route=None))'`
Passes when: prints `PASS` and the four routes. Each returns HTTP 200 with `Content-Type: text/html`, and each renders its own distinguishing control — so a single-page app that serves one shell and cannot deep-link fails. §3.4's JSON convention governs the API, not these routes.
Status: unclaimed

### S-29: Signup signs the user in, and current-user shows the display name on every screen.
Check: `$PWPY -c "$W"'
SETUP()
def f(pg):
    SIGNUP_UI(pg,"zoe@example.com","hunter2hunter2","Zoe Aster")
    out={}
    for route in ["/","/lookup","/signup","/login"]:
        pg.goto(BASE+route,wait_until="load"); pg.wait_for_timeout(300)
        out[route]=TXT(pg,"current-user")
        assert out[route] and "Zoe Aster" in out[route],(route,out[route])
        assert SEE(pg,"logout-button"),(route,"no logout-button")
    CLICK(pg,"logout-button"); pg.wait_for_timeout(600)
    pg.goto(BASE+"/",wait_until="load"); pg.wait_for_timeout(300)
    assert not SEE(pg,"current-user"),"current-user still visible after logout"
    return out
print("PASS",UI(f))'`
Passes when: prints `PASS` and the display name seen on each route. The name appears on **every** screen while signed in, a logout control is present on each, and after logout `current-user` is gone.
Status: unclaimed

### S-30: Login signs in and a bad login shows auth-error, which is absent when there is none.
Check: `$PWPY -c "$W"'
SETUP()
def f(pg):
    pg.goto(BASE+"/login",wait_until="load")
    assert not SEE(pg,"auth-error"),"auth-error present before any attempt"
    LOGIN_UI(pg,ADA["email"],"wrong password")
    assert SEE(pg,"auth-error"),"no auth-error on a bad login"
    txt=TXT(pg,"auth-error")
    assert txt,"auth-error is empty"
    assert not SEE(pg,"current-user"),"signed in despite a bad password"
    LOGIN_UI(pg,ADA["email"],ADA["password"])
    assert not SEE(pg,"auth-error"),"auth-error persists after a good login"
    cu=TXT(pg,"current-user")
    assert cu and "Ada" in cu,cu
    return txt
print("PASS",UI(f,route=None))'`
Passes when: prints `PASS` and the error text. `auth-error` is absent before any attempt, present and non-empty on a bad login, and gone again after a good one — the specification's "present only when there is one", checked in all three directions.
Status: unclaimed

## UI: the availability grid (§UI)

### S-31: The grid renders one cell per table per slot, and data-available matches GET /availability exactly.
Check: `$PWPY -c "$W"'
ta,_=SETUP()
OK(BOOK(ta,F+"T19:00","s31",table_id="t_2",ps=2),201)
api={s["starts_at_local"][-5:]:s["available_table_ids"] for s in OK(AV("r_anker",F,2),200)["slots"]}
def f(pg):
    LOGIN_UI(pg); SEARCH_UI(pg,"r_anker",F,2)
    assert SEE(pg,"availability-grid"),"no availability-grid"
    checked=0
    for at,avail in api.items():
        for tid in ["t_1","t_2","t_3"]:
            got=AVAILATTR(pg,tid,at)
            assert got is not None,"missing cell slot-%s-%s"%(tid,at)
            want="true" if tid in avail else "false"
            assert got==want,"slot-%s-%s data-available=%s want %s"%(tid,at,got,want)
            checked+=1
    return checked
n=UI(f)
assert n==len(api)*3,(n,len(api))
print("PASS",n,"cells")'`
Passes when: prints `PASS 27 cells`. Every table-slot pair has a cell and every `data-available` agrees with `available_table_ids` for the party size that was searched — including the false cells created by the seeded booking. A grid that marks everything available fails.
Status: unclaimed

### S-32: A declared pair that is available for the searched party size gets a combination cell.
Check: `$PWPY -c "$W"'
SETUP()
def f(pg):
    LOGIN_UI(pg); SEARCH_UI(pg,"r_anker",F,6)
    a=AVAILATTR(pg,["t_1","t_2"],"19:00")
    b=AVAILATTR(pg,["t_2","t_3"],"19:00")
    assert a=="true","slot-t_1+t_2-19:00 data-available=%r"%a
    assert b=="true","slot-t_2+t_3-19:00 data-available=%r"%b
    assert AVAILATTR(pg,["t_1","t_3"],"19:00") is None,"undeclared pair t_1+t_3 got a cell"
    assert AVAILATTR(pg,["t_2","t_1"],"19:00") is None,"cell id not in combinable order"
    for tid in ["t_1","t_2","t_3"]:
        assert AVAILATTR(pg,tid,"19:00")=="false","single %s offered for party 6"%tid
    return True
UI(f)
print("PASS")'`
Passes when: prints `PASS`. Both declared pairs get `slot-t_1+t_2-19:00` and `slot-t_2+t_3-19:00` marked available for party 6, the undeclared pair gets no cell, the id is in `combinable` order rather than reversed, and no single table is offered because none seats 6.
Status: unclaimed

### S-33: A combination cell goes unavailable when one of its tables is taken.
Check: `$PWPY -c "$W"'
ta,_=SETUP()
OK(BOOK(ta,F+"T19:00","s33",table_id="t_1",ps=2),201)
def f(pg):
    LOGIN_UI(pg); SEARCH_UI(pg,"r_anker",F,6)
    a=AVAILATTR(pg,["t_1","t_2"],"19:00")
    b=AVAILATTR(pg,["t_2","t_3"],"19:00")
    assert a=="false","pair containing the taken table still available: %r"%a
    assert b=="true","unaffected pair not available: %r"%b
    return True
UI(f)
print("PASS")'`
Passes when: prints `PASS`. The pair containing the booked table reads `data-available="false"` while the other pair stays `true`.
Status: unclaimed

### S-34: A closed day shows no-slots instead of the grid.
Check: `$PWPY -c "$W"'
RESET(FX(restaurants=[REST(opening_hours=[{"weekday":"fri","opens":"18:00","closes":"23:30"}])]))
def f(pg):
    LOGIN_UI(pg); SEARCH_UI(pg,"r_anker",F,4)
    assert SEE(pg,"no-slots"),"no-slots not shown on a closed day"
    t=TXT(pg,"no-slots")
    assert t,"no-slots is empty"
    assert not SEE(pg,"availability-grid") or not pg.query_selector_all(SELSTART("slot-")),"grid rendered on a closed day"
    SEARCH_UI(pg,"r_anker","2027-06-11",4)
    assert not SEE(pg,"no-slots"),"no-slots persists on an open day"
    assert SEE(pg,"availability-grid"),"grid missing on an open day"
    return t
print("PASS",repr(UI(f)))'`
Passes when: prints `PASS` and the message. 2027-06-10 is a Thursday and closed, so `no-slots` shows with non-empty text and no slot cells render; the Friday shows the grid and no `no-slots`. The non-empty assertion is what stops a blank box passing.
Status: unclaimed

### S-35: Clicking an available cell opens the booking form for that table and slot; clicking an unavailable one does nothing.
Check: `$PWPY -c "$W"'
ta,_=SETUP()
OK(BOOK(ta,F+"T19:00","s35",table_id="t_2",ps=2),201)
def f(pg):
    LOGIN_UI(pg); SEARCH_UI(pg,"r_anker",F,2)
    CLICK(pg,"slot-t_2-19:00"); pg.wait_for_timeout(500)
    assert not SEE(pg,"booking-form"),"unavailable cell opened the form"
    CLICK(pg,"slot-t_3-19:00"); pg.wait_for_timeout(600)
    assert SEE(pg,"booking-form"),"available cell did not open the form"
    s=TXT(pg,"booking-summary")
    assert s and "Terrace" in s,"booking-summary lacks the table label: %r"%s
    assert "19:00" in s,"booking-summary lacks the local start time: %r"%s
    ps=pg.input_value(SEL("booking-party-size"))
    assert str(ps).strip()=="2","booking-party-size not pre-filled from the search: %r"%ps
    return s
print("PASS",repr(UI(f)))'`
Passes when: prints `PASS` and the summary. The unavailable cell is inert, the available one opens the form, `booking-summary` names the table by its **label** ("Terrace") and the local start time, and party size is pre-filled from the search.
Status: unclaimed

### S-36: Booking while signed out shows auth-error or navigates to /login.
Check: `$PWPY -c "$W"'
SETUP()
def f(pg):
    SEARCH_UI(pg,"r_anker",F,2)
    CLICK(pg,"slot-t_3-19:00"); pg.wait_for_timeout(800)
    ok = SEE(pg,"auth-error") or "/login" in pg.url or SEE(pg,"login-submit")
    assert ok,"signed out: neither auth-error nor /login; url=%s"%pg.url
    assert not SEE(pg,"confirmation"),"a confirmation appeared while signed out"
    return pg.url
print("PASS",UI(f))'`
Passes when: prints `PASS` and the resulting URL. Either branch the specification permits is accepted, and in neither case does a confirmation appear.
Status: unclaimed

### S-37: A booked slot is unavailable on the next search, and cancelling frees it again.
Check: `$PWPY -c "$W"'
ta,_=SETUP()
def f(pg):
    LOGIN_UI(pg); SEARCH_UI(pg,"r_anker",F,2)
    assert AVAILATTR(pg,"t_3","19:00")=="true"
    CLICK(pg,"slot-t_3-19:00"); pg.wait_for_timeout(500)
    CLICK(pg,"booking-submit"); pg.wait_for_timeout(1200)
    assert SEE(pg,"confirmation"),"no confirmation after booking"
    ref=TXT(pg,"confirmation-reference")
    SEARCH_UI(pg,"r_anker",F,2)
    assert AVAILATTR(pg,"t_3","19:00")=="false","booked slot still available on the next search"
    pg.goto(BASE+"/lookup",wait_until="load")
    FILL(pg,"lookup-reference-input",ref); CLICK(pg,"lookup-submit"); pg.wait_for_timeout(900)
    CLICK(pg,"reservation-cancel-button"); pg.wait_for_timeout(1000)
    SEARCH_UI(pg,"r_anker",F,2)
    assert AVAILATTR(pg,"t_3","19:00")=="true","cancelled slot not freed on the next search"
    return ref
print("PASS",UI(f))'`
Passes when: prints `PASS` and the reference. The grid reflects the new booking on re-search, and reflects the cancellation afterwards — the browser is reading the server rather than caching its own optimistic view.
Status: unclaimed

## UI: booking form, confirmation and lookup (§UI)

### S-38: The confirmation shows the reference exactly and details naming restaurant, table label and local time.
Check: `$PWPY -c "$W"'
import re as _re
ta,_=SETUP()
def f(pg):
    LOGIN_UI(pg); SEARCH_UI(pg,"r_anker",F,4)
    CLICK(pg,"slot-t_2-19:00"); pg.wait_for_timeout(500)
    CLICK(pg,"booking-submit"); pg.wait_for_timeout(1200)
    assert SEE(pg,"confirmation"),"no confirmation"
    ref=TXT(pg,"confirmation-reference")
    assert _re.fullmatch(r"[A-Z0-9]{6,12}",ref or ""),"confirmation-reference is not exactly the reference: %r"%ref
    det=TXT(pg,"confirmation-details") or ""
    for want in ["Zum Anker","Corner","19:00"]:
        assert want in det,"confirmation-details lacks %r: %r"%(want,det)
    tb=TXT(pg,"confirmation-tables") or ""
    assert "Corner" in tb,"confirmation-tables lacks the table label: %r"%tb
    return ref,det
print("PASS",UI(f))'`
Passes when: prints `PASS` with the reference and details. `confirmation-reference` matches `^[A-Z0-9]{6,12}$` with no surrounding words, and the details name the restaurant and table by their human labels plus the local start time.
Status: unclaimed

### S-39: A combination booking's summary, confirmation and lookup name every table.
Check: `$PWPY -c "$W"'
ta,_=SETUP()
def f(pg):
    LOGIN_UI(pg); SEARCH_UI(pg,"r_anker",F,6)
    CLICK(pg,"slot-t_1+t_2-19:00"); pg.wait_for_timeout(600)
    s=TXT(pg,"booking-summary") or ""
    for lab in ["Window","Corner"]:
        assert lab in s,"booking-summary omits %r: %r"%(lab,s)
    CLICK(pg,"booking-submit"); pg.wait_for_timeout(1300)
    ref=TXT(pg,"confirmation-reference")
    ct=TXT(pg,"confirmation-tables") or ""
    for lab in ["Window","Corner"]:
        assert lab in ct,"confirmation-tables omits %r: %r"%(lab,ct)
    pg.goto(BASE+"/lookup",wait_until="load")
    FILL(pg,"lookup-reference-input",ref); CLICK(pg,"lookup-submit"); pg.wait_for_timeout(900)
    rt=TXT(pg,"reservation-tables") or ""
    for lab in ["Window","Corner"]:
        assert lab in rt,"reservation-tables omits %r: %r"%(lab,rt)
    return ref,s,ct,rt
print("PASS",UI(f))'`
Passes when: prints `PASS` with all four strings. Every table in the selection is named by label in `booking-summary`, `confirmation-tables` and `reservation-tables`. Labels rather than ids is the point: `t_1+t_2` appearing instead of "Window" and "Corner" fails.
Status: unclaimed

### S-40: Resubmitting the unchanged booking form returns the same reference and books once.
Check: `$PWPY -c "$W"'
ta,_=SETUP()
def f(pg):
    LOGIN_UI(pg); SEARCH_UI(pg,"r_anker",F,4)
    CLICK(pg,"slot-t_2-19:00"); pg.wait_for_timeout(500)
    CLICK(pg,"booking-submit"); pg.wait_for_timeout(1200)
    first=TXT(pg,"confirmation-reference")
    assert SEE(pg,"booking-form"),"form removed after success; spec requires it stays on screen"
    for _ in range(2):
        CLICK(pg,"booking-submit"); pg.wait_for_timeout(1100)
        assert not SEE(pg,"booking-error"),"booking-error on an unchanged resubmit"
        assert TXT(pg,"confirmation-reference")==first,"reference changed on resubmit"
    return first
ref=UI(f)
rs=OK(R("GET","/reservations",tok=ta),200)["reservations"]
assert len(rs)==1,"resubmit created %d reservations"%len(rs)
assert rs[0]["reference"]==ref,(ref,rs)
print("PASS",ref)'`
Passes when: prints `PASS` and the reference. The form stays on screen after success, two further unchanged submissions return the same reference with no `booking-error`, and the server holds exactly one reservation — §7 replay driven from the browser.
Status: unclaimed

### S-41: Changing a field makes the next submission a new booking.
Check: `$PWPY -c "$W"'
ta,_=SETUP()
def f(pg):
    LOGIN_UI(pg); SEARCH_UI(pg,"r_anker",F,4)
    CLICK(pg,"slot-t_2-19:00"); pg.wait_for_timeout(500)
    CLICK(pg,"booking-submit"); pg.wait_for_timeout(1200)
    first=TXT(pg,"confirmation-reference")
    FILL(pg,"booking-party-size",3); pg.wait_for_timeout(200)
    CLICK(pg,"booking-submit"); pg.wait_for_timeout(1200)
    second=TXT(pg,"confirmation-reference")
    assert second and second!=first,"changed field reused the reference: %r"%second
    assert not SEE(pg,"booking-error"),"booking-error on a legitimate new booking"
    return first,second
a,b=UI(f)
rs=OK(R("GET","/reservations",tok=ta),200)["reservations"]
refs={r["reference"] for r in rs if r["status"]=="confirmed"}
assert {a,b}<=refs or b in refs,(a,b,refs)
print("PASS",a,b)'`
Passes when: prints `PASS` and two different references. Changing party size produces a genuinely new booking rather than replaying the first — so the browser is varying the idempotency key with the body, not pinning one key per form.
Status: unclaimed

### S-42: Lookup shows a reservation, its exact status, and cancels without a manual reload.
Check: `$PWPY -c "$W"'
ta,_=SETUP()
b=OK(BOOK(ta,F+"T19:00","s42",table_id="t_2",ps=4),201)
def f(pg):
    LOGIN_UI(pg)
    pg.goto(BASE+"/lookup",wait_until="load")
    FILL(pg,"lookup-reference-input",b["reference"]); CLICK(pg,"lookup-submit"); pg.wait_for_timeout(900)
    assert SEE(pg,"reservation-detail"),"no reservation-detail"
    st=TXT(pg,"reservation-status")
    assert st=="confirmed","reservation-status is not exactly confirmed: %r"%st
    assert SEE(pg,"reservation-cancel-button"),"no cancel button on a confirmed booking"
    url=pg.url
    CLICK(pg,"reservation-cancel-button"); pg.wait_for_timeout(1100)
    assert pg.url==url,"page navigated/reloaded instead of updating in place"
    st2=TXT(pg,"reservation-status")
    assert st2=="cancelled","status after cancel is not exactly cancelled: %r"%st2
    assert not SEE(pg,"reservation-cancel-button"),"cancel button still present once cancelled"
    return st,st2
print("PASS",UI(f))'`
Passes when: prints `PASS ('confirmed', 'cancelled')`. The status text is exactly the bare word in both states, the cancel button disappears once cancelled, and the URL is unchanged — the update happened without a manual reload.
Status: unclaimed

### S-43: An unknown reference and a refused cancel both show reservation-error.
Check: `$PWPY -c "$W"'
seed=[{"id":"res_p","reference":"PASTONE","user_id":"u_ada","restaurant_id":"r_anker",
       "table_id":"t_2","starts_at_local":"2020-06-10T19:00","party_size":4}]
RESET(FX(reservations=seed))
def f(pg):
    LOGIN_UI(pg)
    pg.goto(BASE+"/lookup",wait_until="load")
    assert not SEE(pg,"reservation-error"),"reservation-error present before any lookup"
    FILL(pg,"lookup-reference-input","ZZZZZZ"); CLICK(pg,"lookup-submit"); pg.wait_for_timeout(900)
    assert SEE(pg,"reservation-error"),"no reservation-error for an unknown reference"
    assert TXT(pg,"reservation-error"),"reservation-error is empty"
    assert not SEE(pg,"reservation-detail"),"detail shown for an unknown reference"
    FILL(pg,"lookup-reference-input","PASTONE"); CLICK(pg,"lookup-submit"); pg.wait_for_timeout(900)
    assert SEE(pg,"reservation-detail"),"detail missing for a known reference"
    CLICK(pg,"reservation-cancel-button"); pg.wait_for_timeout(1100)
    assert SEE(pg,"reservation-error"),"no reservation-error when the cancel is refused"
    assert TXT(pg,"reservation-status")=="confirmed","status changed despite a refused cancel"
    return True
UI(f)
print("PASS")'`
Passes when: prints `PASS`. `reservation-error` is absent initially, shown with non-empty text for an unknown reference with no detail rendered, and shown again when a cancel is refused — the seeded booking starts in 2020, so it is past its cutoff and the cancel is 409 `cutoff_passed`. The status must not flip on a refused cancel.
Status: unclaimed

## UI: competing clients and uncertain outcomes (§Competing clients)

### S-44: A search that starts first but finishes last must not overwrite the newer results.
Check: `$PWPY -c "$W"'
import asyncio
from playwright.async_api import async_playwright
SETUP()
async def main():
    async with async_playwright() as p:
        br=await p.chromium.launch(); pg=await br.new_page(viewport={"width":1280,"height":900})
        async def h(route):
            r=await route.fetch()
            if "party_size=2" in route.request.url: await asyncio.sleep(1.5)
            await route.fulfill(response=r)
        await pg.route("**/availability**",h)
        await pg.goto(BASE+"/login",wait_until="load")
        await pg.fill("[data-testid=login-email]",ADA["email"]); await pg.fill("[data-testid=login-password]",ADA["password"])
        await pg.click("[data-testid=login-submit]"); await pg.wait_for_timeout(700)
        await pg.goto(BASE+"/",wait_until="load")
        await pg.select_option("[data-testid=restaurant-select]","r_anker")
        await pg.fill("[data-testid=date-input]",F)
        await pg.fill("[data-testid=party-size-input]","2"); await pg.click("[data-testid=search-button]")
        await pg.wait_for_timeout(120)
        await pg.fill("[data-testid=party-size-input]","6"); await pg.click("[data-testid=search-button]")
        await pg.wait_for_timeout(3000)
        c1=await pg.query_selector("[data-testid=\"slot-t_1-19:00\"]")
        a1=await c1.get_attribute("data-available") if c1 else None
        cp=await pg.query_selector("[data-testid=\"slot-t_1+t_2-19:00\"]")
        ap=await cp.get_attribute("data-available") if cp else None
        await br.close()
        return a1,ap
a1,ap=asyncio.run(main())
assert ap=="true","grid does not describe the newer party-6 search: combination cell %r"%ap
assert a1=="false","late party-2 response restored its own results: slot-t_1-19:00 %r"%a1
print("PASS",a1,ap)'`
Passes when: prints `PASS false true`. Search A (party 2) is delayed 1.5s so it genuinely resolves after search B (party 6) — verified achievable with the async driver. The grid must then describe B: the `[t_1,t_2]` combination available, and `t_1` alone unavailable because it seats 2 and B asked for 6. If A's late response wins, `slot-t_1-19:00` reads `true` and this fails.
Status: unclaimed

### S-45: A 409 table_unavailable shows booking-error, refreshes availability, preserves the form and shows no confirmation.
Check: `$PWPY -c "$W"'
ta,tb=SETUP()
def f(pg):
    LOGIN_UI(pg); SEARCH_UI(pg,"r_anker",F,4)
    pg.click(chr(91)+"data-testid=\"slot-t_2-19:00\""+chr(93)); pg.wait_for_timeout(500)
    assert SEE(pg,"booking-form")
    FILL(pg,"booking-party-size",3); pg.wait_for_timeout(150)
    OK(BOOK(tb,F+"T19:00","steal",table_id="t_2",ps=4),201)      # another client takes it
    CLICK(pg,"booking-submit"); pg.wait_for_timeout(1400)
    assert SEE(pg,"booking-error"),"no booking-error on 409 table_unavailable"
    assert TXT(pg,"booking-error"),"booking-error is empty"
    assert not SEE(pg,"confirmation"),"a confirmation was shown for a refused attempt"
    assert SEE(pg,"booking-form"),"form removed; spec requires the selection be preserved"
    ps=pg.input_value(chr(91)+"data-testid=\"booking-party-size\""+chr(93))
    assert str(ps).strip()=="3","the diner input was not preserved: %r"%ps
    s=TXT(pg,"booking-summary") or ""
    assert "Corner" in s,"the selected table was not preserved: %r"%s
    assert AVAILATTR(pg,"t_2","19:00")=="false","availability was not refreshed after the 409"
    return ps,s
print("PASS",UI(f))'`
Passes when: prints `PASS` with the preserved input and summary. Another account takes `t_2` after the form opens: the attempt shows non-empty `booking-error`, no confirmation, the form and the diner's edited party size survive, the selected table is still named, and the grid now marks `t_2` unavailable.
Status: unclaimed

### S-46: A lost booking response shows booking-uncertain, and retrying the unchanged form recovers the original reference.
Check: `$PWPY -c "$W"'
import asyncio
from playwright.async_api import async_playwright
ta,_=SETUP()
async def main():
    async with async_playwright() as p:
        br=await p.chromium.launch(); pg=await br.new_page(viewport={"width":1280,"height":900})
        state={"drop":True}
        async def h(route):
            if route.request.method=="POST" and state["drop"]:
                state["drop"]=False
                await route.fetch()                       # the server commits
                await route.abort("connectionfailed")     # the response never arrives
                return
            await route.continue_()
        await pg.route("**/reservations**",h)
        await pg.goto(BASE+"/login",wait_until="load")
        await pg.fill("[data-testid=login-email]",ADA["email"]); await pg.fill("[data-testid=login-password]",ADA["password"])
        await pg.click("[data-testid=login-submit]"); await pg.wait_for_timeout(700)
        await pg.goto(BASE+"/",wait_until="load")
        await pg.select_option("[data-testid=restaurant-select]","r_anker")
        await pg.fill("[data-testid=date-input]",F); await pg.fill("[data-testid=party-size-input]","4")
        await pg.click("[data-testid=search-button]"); await pg.wait_for_timeout(900)
        await pg.click("[data-testid=\"slot-t_2-19:00\"]"); await pg.wait_for_timeout(500)
        await pg.click("[data-testid=booking-submit]"); await pg.wait_for_timeout(2000)
        unc=await pg.query_selector("[data-testid=booking-uncertain]")
        unc_txt=(await unc.inner_text()).strip() if unc else None
        err=await pg.query_selector("[data-testid=booking-error]")
        conf=await pg.query_selector("[data-testid=confirmation-reference]")
        await pg.click("[data-testid=booking-submit]"); await pg.wait_for_timeout(2000)
        unc2=await pg.query_selector("[data-testid=booking-uncertain]")
        err2=await pg.query_selector("[data-testid=booking-error]")
        ref=await pg.query_selector("[data-testid=confirmation-reference]")
        ref_txt=(await ref.inner_text()).strip() if ref else None
        await br.close()
        return unc_txt,bool(err),bool(conf),bool(unc2),bool(err2),ref_txt
u,e,c,u2,e2,ref=asyncio.run(main())
assert u,"no nonempty booking-uncertain after a lost response: %r"%u
assert not e,"booking-error shown for an uncertain outcome"
assert not c,"a confirmation was shown for a lost response"
rs=OK(R("GET","/reservations",tok=ta),200)["reservations"]
assert len(rs)==1,"the retry created a second booking: %d"%len(rs)
assert ref==rs[0]["reference"],"retry did not recover the original reference: %r vs %r"%(ref,rs[0]["reference"])
assert not u2 and not e2,"uncertainty/error elements not removed after a successful retry"
print("PASS",u,ref)'`
Passes when: prints `PASS` with the uncertainty text and the reference. The first submission reaches the server and commits while its response is dropped — the mechanism is verified: `route.fetch()` then `route.abort()` leaves the server with the booking and the browser with a network failure. The UI must then show non-empty `booking-uncertain` with **no** `booking-error` and **no** confirmation; retrying the unchanged form must reuse the same idempotency key and body so the server replays rather than books again; and the recovered reference must be the original one with the uncertainty elements removed. Exactly one reservation exists throughout.
Status: unclaimed

### S-47: The uncertainty and refusal rules hold for a combination booking too.
Check: `$PWPY -c "$W"'
import asyncio
from playwright.async_api import async_playwright
ta,tb=SETUP()
async def main():
    async with async_playwright() as p:
        br=await p.chromium.launch(); pg=await br.new_page(viewport={"width":1280,"height":900})
        state={"drop":True}
        async def h(route):
            if route.request.method=="POST" and state["drop"]:
                state["drop"]=False
                await route.fetch(); await route.abort("connectionfailed"); return
            await route.continue_()
        await pg.route("**/reservations**",h)
        await pg.goto(BASE+"/login",wait_until="load")
        await pg.fill("[data-testid=login-email]",ADA["email"]); await pg.fill("[data-testid=login-password]",ADA["password"])
        await pg.click("[data-testid=login-submit]"); await pg.wait_for_timeout(700)
        await pg.goto(BASE+"/",wait_until="load")
        await pg.select_option("[data-testid=restaurant-select]","r_anker")
        await pg.fill("[data-testid=date-input]",F); await pg.fill("[data-testid=party-size-input]","6")
        await pg.click("[data-testid=search-button]"); await pg.wait_for_timeout(900)
        await pg.click("[data-testid=\"slot-t_1+t_2-19:00\"]"); await pg.wait_for_timeout(500)
        await pg.click("[data-testid=booking-submit]"); await pg.wait_for_timeout(2000)
        unc=await pg.query_selector("[data-testid=booking-uncertain]")
        u=(await unc.inner_text()).strip() if unc else None
        await pg.click("[data-testid=booking-submit]"); await pg.wait_for_timeout(2000)
        ref=await pg.query_selector("[data-testid=confirmation-reference]")
        rt=await pg.query_selector("[data-testid=confirmation-tables]")
        await br.close()
        return u,((await ref.inner_text()).strip() if ref else None),((await rt.inner_text()).strip() if rt else None)
u,ref,tabs=asyncio.run(main())
assert u,"no booking-uncertain for a lost combination booking"
rs=[r for r in OK(R("GET","/reservations",tok=ta),200)["reservations"]]
assert len(rs)==1 and rs[0]["table_ids"]==["t_1","t_2"],rs
assert ref==rs[0]["reference"],(ref,rs[0]["reference"])
for lab in ["Window","Corner"]:
    assert lab in (tabs or ""),"confirmation-tables omits %r after recovery: %r"%(lab,tabs)
print("PASS",ref)'`
Passes when: prints `PASS` and the reference. A lost response on a *combination* booking produces the same uncertainty handling, the retry recovers the original reference, exactly one reservation exists holding both tables, and the recovered confirmation still names both table labels.
Status: unclaimed

## Upgrading a stage-1 service (§Existing clients after an upgrade)

### S-48: A stage-2 service accepts an export produced by the team's stage-1 service.
Check: `TK_REPO="${TK_REPO:-/Users/aashanjaved/band-work/result}"; docker rm -f tk-up1 tk-up2 >/dev/null 2>&1; docker network rm tk-up-net >/dev/null 2>&1; docker network create tk-up-net >/dev/null && docker build -q -t tk-s1old "$TK_REPO/stage-1" >/dev/null && docker build -q -t tk-s2new "$TK_REPO/stage-2" >/dev/null && docker run -d --name tk-up1 --network tk-up-net -p 18091:8080 -e PORT=8080 tk-s1old >/dev/null && docker run -d --name tk-up2 --network tk-up-net -p 18092:8080 -e PORT=8080 tk-s2new >/dev/null && for i in $(seq 1 60); do curl -fsS http://127.0.0.1:18091/health >/dev/null 2>&1 && curl -fsS http://127.0.0.1:18092/health >/dev/null 2>&1 && break; sleep 1; done && /Users/aashanjaved/dark-factory-wearedevs/.venv/bin/python -c 'import json,urllib.request as U
def R(base,m,p,b=None,tok=None,key=None):
    h={"Content-Type":"application/json"}
    if tok: h["Authorization"]="Bearer "+tok
    if key: h["Idempotency-Key"]=key
    d=None if b is None else json.dumps(b).encode()
    try:
        x=U.urlopen(U.Request(base+p,method=m,data=d,headers=h),timeout=20); return x.status,json.loads(x.read() or b"null")
    except U.HTTPError as e: return e.code,json.loads(e.read() or b"null")
A,B="http://127.0.0.1:18091","http://127.0.0.1:18092"
fx={"users":[{"id":"u_ada","email":"ada@example.com","password":"correct horse","display_name":"Ada"}],
    "restaurants":[{"id":"r_anker","name":"Zum Anker","timezone":"Europe/Berlin","slot_minutes":30,
      "reservation_duration_minutes":90,"cancellation_cutoff_minutes":120,
      "opening_hours":[{"weekday":w,"opens":"18:00","closes":"23:30"} for w in ["mon","tue","wed","thu","fri","sat","sun"]],
      "tables":[{"id":"t_1","label":"Window","capacity":2},{"id":"t_2","label":"Corner","capacity":4}]}],
    "reservations":[]}
assert R(A,"POST","/_test/reset",fx)[0]==204
tok=R(A,"POST","/auth/login",{"email":"ada@example.com","password":"correct horse"})[1]["token"]
st,b=R(A,"POST","/reservations",{"restaurant_id":"r_anker","table_id":"t_2","starts_at_local":"2027-06-10T19:00","party_size":4},tok=tok,key="up1")
assert st==201,(st,b)
ref=b["reference"]
st,snap=R(A,"GET","/_test/export"); assert st==200,st
st,_=R(B,"POST","/_test/import",snap); assert st==204,"stage 2 refused a stage-1 export: %s"%st
st,g=R(B,"GET","/reservations/"+ref,tok=tok)
assert st==200 and g["reference"]==ref,"retained reference lost: %s %r"%(st,g)
assert g["table_ids"]==["t_2"] and g.get("table_id")=="t_2",g
st,rep=R(B,"POST","/reservations",{"restaurant_id":"r_anker","table_id":"t_2","starts_at_local":"2027-06-10T19:00","party_size":4},tok=tok,key="up1")
assert st==200 and rep["reference"]==ref,"stage-1 receipt not replayable on stage 2: %s %r"%(st,rep)
st,_=R(B,"POST","/auth/login",{"email":"ada@example.com","password":"correct horse"}); assert st==200,st
print("UPGRADE OK",ref)'; r=$?; docker rm -f tk-up1 tk-up2 >/dev/null 2>&1; docker network rm tk-up-net >/dev/null 2>&1; exit $r`
Passes when: exits 0 and prints `UPGRADE OK <reference>`. A real stage-1 image produces the export and a real stage-2 image imports it — not a stage-2 service importing its own snapshot. The pre-upgrade bearer token still authenticates, the retained reference still resolves, the stage-1 idempotency receipt still replays to the original response, and hashed-password login still works. The response now also carries `table_ids`, which stage 1 never wrote.
Status: unclaimed

### S-49: A browser signed in before the upgrade stays signed in, and its retained reference works through the lookup screen.
Check: `$PWPY -c "$W"'
ta,_=SETUP()
b=OK(BOOK(ta,F+"T19:00","s49",table_id="t_2",ps=4),201)
snap=OK(R("GET","/_test/export"),200)
def f(pg):
    LOGIN_UI(pg)
    cu=TXT(pg,"current-user"); assert cu and "Ada" in cu,cu
    s,_,_=R("POST","/_test/import",snap)            # upgrade happens between browser requests
    assert s==204,s
    pg.goto(BASE+"/lookup",wait_until="load"); pg.wait_for_timeout(400)
    cu2=TXT(pg,"current-user")
    assert cu2 and "Ada" in cu2,"browser lost its session across the import: %r"%cu2
    FILL(pg,"lookup-reference-input",b["reference"]); CLICK(pg,"lookup-submit"); pg.wait_for_timeout(900)
    assert SEE(pg,"reservation-detail"),"retained reference not found after the import"
    assert TXT(pg,"reservation-status")=="confirmed",TXT(pg,"reservation-status")
    assert not SEE(pg,"reservation-error"),"reservation-error shown for a retained reference"
    return cu2
print("PASS",UI(f,route=None))'`
Passes when: prints `PASS` and the display name. The import lands between browser requests, as the specification scopes it; the session survives with no reload or new screen, and the retained reference resolves through `/lookup` with status `confirmed`.
Status: unclaimed

### S-50: A booking whose response was lost before the export is still recoverable after the import, with the same key and body.
Check: `$PWPY -c "$W"'
import asyncio
from playwright.async_api import async_playwright
ta,_=SETUP()
async def run():
    async with async_playwright() as p:
        br=await p.chromium.launch(); pg=await br.new_page(viewport={"width":1280,"height":900})
        state={"drop":True}
        async def h(route):
            if route.request.method=="POST" and state["drop"]:
                state["drop"]=False
                await route.fetch(); await route.abort("connectionfailed"); return
            await route.continue_()
        await pg.route("**/reservations**",h)
        await pg.goto(BASE+"/login",wait_until="load")
        await pg.fill("[data-testid=login-email]",ADA["email"]); await pg.fill("[data-testid=login-password]",ADA["password"])
        await pg.click("[data-testid=login-submit]"); await pg.wait_for_timeout(700)
        await pg.goto(BASE+"/",wait_until="load")
        await pg.select_option("[data-testid=restaurant-select]","r_anker")
        await pg.fill("[data-testid=date-input]",F); await pg.fill("[data-testid=party-size-input]","4")
        await pg.click("[data-testid=search-button]"); await pg.wait_for_timeout(900)
        await pg.click("[data-testid=\"slot-t_2-19:00\"]"); await pg.wait_for_timeout(500)
        await pg.click("[data-testid=booking-submit]"); await pg.wait_for_timeout(2000)
        u1=await pg.query_selector("[data-testid=booking-uncertain]")
        snap=OK(R("GET","/_test/export"),200)
        s,_,_=R("POST","/_test/import",snap)
        assert s==204,s
        await pg.click("[data-testid=booking-submit]"); await pg.wait_for_timeout(2200)
        ref=await pg.query_selector("[data-testid=confirmation-reference]")
        u2=await pg.query_selector("[data-testid=booking-uncertain]")
        e2=await pg.query_selector("[data-testid=booking-error]")
        await br.close()
        return bool(u1),((await ref.inner_text()).strip() if ref else None),bool(u2),bool(e2)
u1,ref,u2,e2=asyncio.run(run())
assert u1,"no booking-uncertain after the lost response"
rs=OK(R("GET","/reservations",tok=ta),200)["reservations"]
assert len(rs)==1,"retry after upgrade created a second booking: %d"%len(rs)
assert ref==rs[0]["reference"],"original confirmation not recovered after the upgrade: %r vs %r"%(ref,rs[0]["reference"])
assert not u2 and not e2,"uncertainty/error not cleared after a successful post-upgrade retry"
print("PASS",ref)'`
Passes when: prints `PASS` and the reference. The booking commits, its response is dropped, the state is exported and imported — the upgrade — and the unchanged form then retries with the same key and body and recovers the original reference. Exactly one reservation exists. This is the requirement that the pending retry identity survives the upgrade, and it is the hardest thing in the stage.
Status: unclaimed

## UI quality — the part a human scores (§Product and visual direction)

Every entry in this subsection states a **proxy** and names what the proxy does not establish, per
§16. None of them is the human judgement itself; they are the deterministic floor beneath it.

### S-51: The seven required states are visually distinct from one another.
Check: `$PWPY -c "$W"'
ta,tb=SETUP()
OK(BOOK(ta,F+"T21:00","s51",table_id="t_2",ps=4),201)
def f(pg):
    styles={}
    LOGIN_UI(pg); SEARCH_UI(pg,"r_anker",F,4)
    styles["available"]=STYLE(pg,"slot-t_3-19:00")
    styles["unavailable"]=STYLE(pg,"slot-t_2-21:00")
    pg.click(chr(91)+"data-testid=\"slot-t_3-19:00\""+chr(93)); pg.wait_for_timeout(500)
    styles["selected"]=STYLE(pg,"slot-t_3-19:00")
    pg.route("**/reservations**",lambda r:(pg.wait_for_timeout(0),r.continue_())[1])
    CLICK(pg,"booking-submit"); pg.wait_for_timeout(120)
    l=TID(pg,"booking-loading") or TID(pg,"booking-submit")
    styles["loading"]=STYLE(pg,"booking-loading") if TID(pg,"booking-loading") else STYLE(pg,"booking-submit")
    pg.wait_for_timeout(1500)
    styles["successful"]=STYLE(pg,"confirmation") if TID(pg,"confirmation") else None
    SEARCH_UI(pg,"r_anker",F,4)
    pg.click(chr(91)+"data-testid=\"slot-t_3-19:00\""+chr(93)); pg.wait_for_timeout(400)
    OK(BOOK(tb,F+"T19:00","s51b",table_id="t_3",ps=4),201)
    CLICK(pg,"booking-submit"); pg.wait_for_timeout(1400)
    styles["refused"]=STYLE(pg,"booking-error") if TID(pg,"booking-error") else None
    return styles
st=UI(f)
for k,v in st.items():
    assert v is not None,"state %r produced no element to measure"%k
pairs=[(a,b) for a in st for b in st if a<b]
same=[(a,b) for a,b in pairs if st[a]==st[b]]
assert not same,"states not visually distinct: %r"%same
print("PASS",len(st),"states,",len(pairs),"pairs all distinct")'`
Passes when: prints `PASS` with every pair distinct. **Proxy:** it compares seven computed style vectors — background, border, colour, opacity, outline, text-decoration, font-weight — and requires every pair to differ in at least one. **What it does not establish:** that the differences are *legible* to a person, that colour is not the only channel, or that the states look deliberate. A human still judges that; this only makes "all seven render identically" impossible to pass. The `uncertain` state is covered separately by S-46, which asserts its text is non-empty.
Status: unclaimed

### S-52: The empty results state says what is absent, rather than rendering a blank area.
Check: `$PWPY -c "$W"'
RESET(FX(restaurants=[REST(opening_hours=[{"weekday":"fri","opens":"18:00","closes":"23:30"}])]))
def f(pg):
    LOGIN_UI(pg); SEARCH_UI(pg,"r_anker",F,4)
    e=TID(pg,"no-slots")
    assert e and e.is_visible(),"no-slots is absent or hidden on a closed day"
    t=(e.inner_text() or "").strip()
    assert len(t)>=12,"empty state text is too short to say anything: %r"%t
    words=[w for w in t.split() if len(w)>2]
    assert len(words)>=3,"empty state is not a sentence: %r"%t
    box=e.bounding_box()
    assert box and box["height"]>=16 and box["width"]>=80,"empty state has no rendered area: %r"%box
    return t
print("PASS",repr(UI(f)))'`
Passes when: prints `PASS` and the message. **Proxy:** the element is visible, occupies real area, and carries at least twelve characters forming three or more words. **What it does not establish:** that the wording is helpful or says what to do next. It does make the specific defect the registrar named — "an empty results area rendering as a blank box with no text" — impossible to pass.
Status: unclaimed

### S-53: A loading state is shown while a search is in flight.
Check: `$PWPY -c "$W"'
import asyncio
from playwright.async_api import async_playwright
SETUP()
async def run():
    async with async_playwright() as p:
        br=await p.chromium.launch(); pg=await br.new_page(viewport={"width":1280,"height":900})
        async def h(route):
            r=await route.fetch(); await asyncio.sleep(1.2); await route.fulfill(response=r)
        await pg.route("**/availability**",h)
        await pg.goto(BASE+"/login",wait_until="load")
        await pg.fill("[data-testid=login-email]",ADA["email"]); await pg.fill("[data-testid=login-password]",ADA["password"])
        await pg.click("[data-testid=login-submit]"); await pg.wait_for_timeout(700)
        await pg.goto(BASE+"/",wait_until="load")
        await pg.select_option("[data-testid=restaurant-select]","r_anker")
        await pg.fill("[data-testid=date-input]",F); await pg.fill("[data-testid=party-size-input]","4")
        await pg.click("[data-testid=search-button]"); await pg.wait_for_timeout(350)
        mid=await pg.evaluate("""()=>{const b=document.body.innerText||"";
            const busy=document.querySelector("[aria-busy=true],[data-loading=true],[data-testid=search-loading]");
            const dis=document.querySelector("[data-testid=search-button]");
            return {busy:!!busy, disabled: dis?dis.disabled:false, txt:/loading|searching|…|\\.\\.\\./i.test(b)}}""")
        await pg.wait_for_timeout(1600)
        after=await pg.evaluate("""()=>{const busy=document.querySelector("[aria-busy=true],[data-loading=true],[data-testid=search-loading]");
            const dis=document.querySelector("[data-testid=search-button]");
            return {busy:!!busy, disabled: dis?dis.disabled:false}}""")
        await br.close(); return mid,after
mid,after=asyncio.run(run())
assert mid["busy"] or mid["disabled"] or mid["txt"],"nothing indicated loading while the search was in flight: %r"%mid
assert not (after["busy"] and not mid["busy"]),"loading indicator appeared only after completion"
assert not after["busy"] or not mid["busy"] or True
print("PASS",mid)'`
Passes when: prints `PASS` and the observed mid-flight state. **Proxy:** with the availability response delayed 1.2s, at 350ms the page must show at least one of `aria-busy="true"`, `data-loading="true"`, a `search-loading` element, a disabled search button, or loading text. **What it does not establish:** that the indicator is well-placed, non-jarring or informative. It does make "no loading state at all" impossible to pass.
Status: unclaimed

### S-54: The required flows have no horizontal page scrolling at a 375-pixel viewport.
Check: `$PWPY -c "$W"'
ta,_=SETUP()
b=OK(BOOK(ta,F+"T19:00","s54",table_id="t_2",ps=4),201)
def f(pg):
    bad={}
    LOGIN_UI(pg)
    for route in ["/","/signup","/login","/lookup"]:
        pg.goto(BASE+route,wait_until="load"); pg.wait_for_timeout(400)
        o=OVERFLOW(pg)
        if o["sw"]>o["cw"]+1: bad[route]=o
    SEARCH_UI(pg,"r_anker",F,6); pg.wait_for_timeout(400)
    o=OVERFLOW(pg)
    if o["sw"]>o["cw"]+1: bad["/ after search"]=o
    pg.click(chr(91)+"data-testid=\"slot-t_1+t_2-19:00\""+chr(93)); pg.wait_for_timeout(500)
    o=OVERFLOW(pg)
    if o["sw"]>o["cw"]+1: bad["/ booking form"]=o
    pg.goto(BASE+"/lookup",wait_until="load")
    FILL(pg,"lookup-reference-input",b["reference"]); CLICK(pg,"lookup-submit"); pg.wait_for_timeout(800)
    o=OVERFLOW(pg)
    if o["sw"]>o["cw"]+1: bad["/lookup detail"]=o
    return bad
bad=UI(f,w=375,h=780)
assert not bad,"horizontal page scrolling at 375px: %r"%bad
print("PASS no horizontal scroll at 375px")'`
Passes when: prints `PASS no horizontal scroll at 375px`. Checks all four routes plus the populated grid, the open booking form and the lookup detail, since overflow usually appears only once real content lands. A wide grid is allowed to scroll **inside its own container**; what fails is the document scrolling.
Status: unclaimed

### S-55: The grid scrolls inside its own container at 375px and its caption stays readable and unclipped.
Check: `$PWPY -c "$W"'
SETUP()
def f(pg):
    LOGIN_UI(pg); SEARCH_UI(pg,"r_anker",F,6); pg.wait_for_timeout(400)
    g=TID(pg,"availability-grid")
    assert g,"no availability-grid"
    m=pg.eval_on_selector(chr(91)+"data-testid=\"availability-grid\""+chr(93),
      "e=>{const s=getComputedStyle(e);return {sw:e.scrollWidth,cw:e.clientWidth,ox:s.overflowX,oy:s.overflowY}}")
    doc=OVERFLOW(pg)
    assert doc["sw"]<=doc["cw"]+1,"document scrolls horizontally: %r"%doc
    if m["sw"]>m["cw"]+1:
        assert m["ox"] in ("auto","scroll"),"grid overflows but its container does not scroll: %r"%m
    cap=pg.evaluate("""()=>{const g=document.querySelector("[data-testid=availability-grid]");
        let n=g.previousElementSibling; let hops=0;
        while(n&&hops<3){const t=(n.innerText||"").trim(); if(t.length>=3){const r=n.getBoundingClientRect();
            const cs=getComputedStyle(n);
            return {text:t.slice(0,80), right:r.right, vw:window.innerWidth, clipped:(cs.textOverflow==="ellipsis"&&n.scrollWidth>n.clientWidth+1)}}
            n=n.previousElementSibling; hops++}
        return null}""")
    return m,cap
m,cap=UI(f,w=375,h=780)
if cap is not None:
    assert cap["right"]<=cap["vw"]+1,"caption extends past the viewport: %r"%cap
    assert not cap["clipped"],"caption is clipped at 375px: %r"%cap
print("PASS",m,cap)'`
Passes when: prints `PASS` with the grid metrics and caption. **Proxy:** if the grid is wider than its box it must declare `overflow-x: auto|scroll`, the document must not scroll, and any heading immediately preceding the grid must fit inside the viewport and not be ellipsis-clipped. **What it does not establish:** that the scroll affordance is discoverable, or that the caption reads well. A grid with no caption passes this entry — the caption requirement is only enforced when one exists.
Status: unclaimed

### S-56: Every required input has a visible label, and keyboard focus is apparent.
Check: `$PWPY -c "$W"'
SETUP()
def f(pg):
    missing=[]; unfocusable=[]
    for route,ids in [("/signup",["signup-email","signup-password","signup-display-name"]),
                      ("/login",["login-email","login-password"]),
                      ("/",["restaurant-select","date-input","party-size-input"]),
                      ("/lookup",["lookup-reference-input"])]:
        pg.goto(BASE+route,wait_until="load"); pg.wait_for_timeout(300)
        for t in ids:
            lab=LABELOF(pg,t)
            vis=pg.evaluate("""(t)=>{const i=document.querySelector("[data-testid=\\""+t+"\\"]");
                if(!i) return false; const l=i.labels&&i.labels[0]; if(!l) return false;
                const r=l.getBoundingClientRect(); const s=getComputedStyle(l);
                return r.width>0&&r.height>0&&s.visibility!=="hidden"&&s.display!=="none"&&Number(s.opacity)>0.05}""",t)
            if not lab or not vis: missing.append((route,t,lab,vis))
            before=STYLE(pg,t)
            pg.focus(chr(91)+"data-testid=\""+t+"\""+chr(93)); pg.wait_for_timeout(120)
            after=pg.eval_on_selector(chr(91)+"data-testid=\""+t+"\""+chr(93),
              "e=>{const s=getComputedStyle(e);return [s.outlineStyle,s.outlineWidth,s.outlineColor,s.boxShadow,s.borderTopColor,s.backgroundColor]}")
            pg.evaluate("()=>document.activeElement&&document.activeElement.blur()"); pg.wait_for_timeout(120)
            unfoc=pg.eval_on_selector(chr(91)+"data-testid=\""+t+"\""+chr(93),
              "e=>{const s=getComputedStyle(e);return [s.outlineStyle,s.outlineWidth,s.outlineColor,s.boxShadow,s.borderTopColor,s.backgroundColor]}")
            if after==unfoc: unfocusable.append((route,t,after))
    return missing,unfocusable
missing,unfoc=UI(f,route=None)
assert not missing,"inputs without a visible associated label: %r"%missing
assert not unfoc,"inputs whose focused appearance is identical to unfocused: %r"%unfoc
print("PASS all required inputs labelled and focus-visible")'`
Passes when: prints `PASS`. **Proxy for labels:** each input resolves to a `<label>` with non-empty text that has real dimensions and is not `hidden`/`display:none`/transparent — so `aria-label` alone does **not** pass, because the requirement is a *visible* label. **Proxy for focus:** the computed outline, box-shadow, border or background must differ between focused and unfocused. **What neither establishes:** that the label wording is clear or the focus ring has adequate contrast.
Status: unclaimed

### S-57: Key text meets a 4.5:1 contrast ratio against its background.
Check: `$PWPY -c "$W"'
ta,_=SETUP()
b=OK(BOOK(ta,F+"T19:00","s57",table_id="t_2",ps=4),201)
def f(pg):
    bad=[]
    def eff(t):
        return pg.evaluate("""(t)=>{const e=document.querySelector("[data-testid=\\""+t+"\\"]");
            if(!e) return null; const fg=getComputedStyle(e).color; let n=e, bg="rgba(0, 0, 0, 0)";
            while(n){const c=getComputedStyle(n).backgroundColor;
                if(c&&!/rgba\\(0, 0, 0, 0\\)|transparent/.test(c)){bg=c;break} n=n.parentElement}
            if(/rgba\\(0, 0, 0, 0\\)|transparent/.test(bg)) bg="rgb(255, 255, 255)";
            return [fg,bg]}""",t)
    LOGIN_UI(pg); SEARCH_UI(pg,"r_anker",F,4)
    for t in ["current-user","search-button","slot-t_2-19:00"]:
        v=eff(t)
        if v and RATIO(v[0],v[1])<4.5: bad.append((t,v,round(RATIO(v[0],v[1]),2)))
    pg.goto(BASE+"/lookup",wait_until="load")
    FILL(pg,"lookup-reference-input",b["reference"]); CLICK(pg,"lookup-submit"); pg.wait_for_timeout(800)
    for t in ["reservation-status","lookup-submit"]:
        v=eff(t)
        if v and RATIO(v[0],v[1])<4.5: bad.append((t,v,round(RATIO(v[0],v[1]),2)))
    return bad
bad=UI(f,route=None)
assert not bad,"text below 4.5:1 contrast: %r"%bad
print("PASS contrast >= 4.5:1 on sampled key text")'`
Passes when: prints `PASS`. **Proxy:** computes the WCAG ratio from resolved foreground colour against the nearest non-transparent ancestor background, for five named elements across two screens. **What it does not establish:** contrast for every element, for text over images or gradients, or for disabled and hover variants. It is a sample, deliberately named as one — a service can fail contrast elsewhere and still pass this.
Status: unclaimed

### S-58: Restaurants and tables are shown by human-readable name, not by raw identifier.
Check: `$PWPY -c "$W"'
ta,_=SETUP()
b=OK(BOOK(ta,F+"T19:00","s58",table_ids=["t_1","t_2"],ps=6),201)
def f(pg):
    LOGIN_UI(pg); SEARCH_UI(pg,"r_anker",F,6)
    body=pg.inner_text("body")
    assert "Zum Anker" in body,"the restaurant name is not shown on the search screen"
    for lab in ["Window","Corner","Terrace"]:
        assert lab in body,"table label %r not shown in the grid: labels are required, ids are not enough"%lab
    pg.click(chr(91)+"data-testid=\"slot-t_1+t_2-19:00\""+chr(93)); pg.wait_for_timeout(500)
    s=TXT(pg,"booking-summary") or ""
    assert "Window" in s and "Corner" in s,"booking-summary does not name both tables by label: %r"%s
    assert "t_1+t_2" not in s,"booking-summary shows the concatenated id form: %r"%s
    pg.goto(BASE+"/lookup",wait_until="load")
    FILL(pg,"lookup-reference-input",b["reference"]); CLICK(pg,"lookup-submit"); pg.wait_for_timeout(800)
    rt=TXT(pg,"reservation-tables") or ""
    assert "Window" in rt and "Corner" in rt,"reservation-tables lacks labels: %r"%rt
    assert "t_1+t_2" not in rt,"reservation-tables shows the concatenated id form: %r"%rt
    return s,rt
print("PASS",UI(f,route=None))'`
Passes when: prints `PASS` with the summary and lookup text. **Proxy:** the restaurant name and all three table labels appear as rendered text, and neither the booking summary nor the lookup detail contains the literal `t_1+t_2`. **What it does not establish:** that combinations "read as intentional seating options" — that phrasing is a human judgement. It does forbid the specific failure of surfacing the concatenated technical identifier to the diner. Note the `data-testid` values legitimately contain ids; this checks visible text, not attributes.
Status: unclaimed

## Declared human-judged — no entry written

Per §16 rule 2, these requirements from §Product and visual direction have **no faithful
deterministic proxy** and are therefore left to the human judge. They are not waived and they are not
case-2 refusals; they are recorded here so nobody mistakes the absence of an entry for the absence of
a requirement, and so no seat manufactures a check that would pass without meaning anything.

| Requirement | Why no command can settle it |
|---|---|
| "Feels like a coherent, presentation-ready restaurant product, not a test harness with controls attached" | Aesthetic and holistic. Nothing prints. |
| "Warm, confident hospitality character" | Aesthetic. |
| "Obvious visual hierarchy; a diner can scan dates, times, party size and table choices" | Scanability is a perceptual claim; element order and font size are proxies so weak they would mislead. |
| "Combined tables read as intentional seating options" | S-58 forbids the concatenated-id failure; whether the phrasing reads as intentional is judgement. |
| "A consistent visual system for typography, spacing, colour, controls and feedback" | Consistency across a whole design is not reducible to a comparison a script can make honestly. |
| "Primary actions are easy to identify" | S-51 proves states differ; salience is judgement. |
| "Considered empty, loading and error states" | S-52, S-53 and S-43 enforce presence and non-emptiness. "Considered" is the human's word. |
| "Navigation consistent across the required routes" | S-28 proves the routes exist and S-29 that the user identity persists; consistency of navigation design is judgement. |

**The honest summary of this subsection:** S-51 to S-58 are a floor, not a score. They make eight
specific failures impossible to pass — all states identical, a blank empty box, no loading indicator,
horizontal page scroll at 375px, a clipped caption, a missing or invisible label, an invisible focus
ring, unreadable contrast on sampled text, and raw ids shown where names belong. They do not
establish that the interface is good, and a verdict passing all eight says only that.
