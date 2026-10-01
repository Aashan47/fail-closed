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
Status: retired unactivated — replaced by Conventions §12 (TK_REPO); see REFUSALS.md at 5dd2e8c

### C-149: The service builds from a clean container at a named revision and serves /health within 60 seconds.
Check: `R="${TK_REPO:-/Users/aashanjaved/band-work/result}"; test -z "$(git -C "$R" status --porcelain)" || { echo "TREE NOT CLEAN IN $R"; exit 1; }; before=$(git -C "$R" rev-parse HEAD); docker rm -f tk-s1 >/dev/null 2>&1; docker network rm tk-s1-net >/dev/null 2>&1; docker builder prune -af >/dev/null 2>&1; test -f "$R/stage-1/Dockerfile" && test -f "$R/stage-1/RUN.md" && docker network create tk-s1-net && docker build --no-cache -t tk-s1 "$R/stage-1" && docker run -d --name tk-s1 --network tk-s1-net -p 18080:8080 -e PORT=8080 tk-s1 && start=$(date +%s) && until curl -fsS http://127.0.0.1:18080/health; do [ $(( $(date +%s) - start )) -lt 60 ] || { echo "NOT HEALTHY WITHIN 60s"; exit 1; }; sleep 1; done && echo " HEALTHY IN $(( $(date +%s) - start ))s" && test "$(docker inspect tk-s1 --format '{{json .NetworkSettings.Ports}}')" != "{}" && echo "PORT PUBLISHED" && test -z "$(git -C "$R" status --porcelain)" && test "$(git -C "$R" rev-parse HEAD)" = "$before" && echo "TREE CLEAN AND UNMOVED AT $before"`
Passes when: exits 0 and prints the `/health` body, then `HEALTHY IN <n>s` with `n` at most 60, then `PORT PUBLISHED`, then `TREE CLEAN AND UNMOVED AT <revision>`. Replaces C-142 and is the gate in its place. It refuses to start against a dirty tree, and it proves afterwards that the tree neither changed nor moved during the run, so the revision it certifies is the revision it built.
Status: retired unactivated — replaced by Conventions §12 (TK_REPO); see REFUSALS.md at 5dd2e8c

### C-150: At run time the service has no outbound network access, and still serves /health.
Check: `R="${TK_REPO:-/Users/aashanjaved/band-work/result}"; test -z "$(git -C "$R" status --porcelain)" || { echo "TREE NOT CLEAN IN $R"; exit 1; }; before=$(git -C "$R" rev-parse HEAD); docker rm -f tk-c150 >/dev/null 2>&1; docker network rm tk-c150-noout >/dev/null 2>&1; docker network create --internal tk-c150-noout && test "$(docker network inspect tk-c150-noout --format '{{.Internal}}')" = "true" && docker build -q -t tk-s1 "$R/stage-1" >/dev/null && docker run -d --name tk-c150 --network tk-c150-noout -e PORT=8080 tk-s1 >/dev/null && for i in $(seq 1 60); do docker run --rm --network tk-c150-noout alpine:3 wget -qO- -T3 http://tk-c150:8080/health >/dev/null 2>&1 && break; sleep 1; done; docker run --rm --network tk-c150-noout alpine:3 sh -c 'wget -qO- -T5 http://tk-c150:8080/health || exit 1; nslookup example.com >/dev/null 2>&1 && exit 2; nc -w4 -z 1.1.1.1 80 2>/dev/null && exit 3; wget -qO- -T4 http://example.com >/dev/null 2>&1 && exit 4; echo " NO EGRESS"'; r=$?; docker rm -f tk-c150 >/dev/null 2>&1; docker network rm tk-c150-noout >/dev/null 2>&1; test $r -eq 0 && test -z "$(git -C "$R" status --porcelain)" && test "$(git -C "$R" rev-parse HEAD)" = "$before" && echo "TREE CLEAN AND UNMOVED AT $before"; exit $?`
Passes when: exits 0 and prints the `/health` body, then `NO EGRESS`, then `TREE CLEAN AND UNMOVED AT <revision>`. Replaces C-143. The service is attached only to an internal network and publishes no port; it is reached by container name from a sibling `alpine:3`, the way the graded harness reaches it in isolated mode. Exit 1 means the service did not answer, 2 that DNS resolved, 3 that raw TCP opened, 4 that an HTTP fetch succeeded. Because the probe must print the service's own health body to pass, it cannot pass by a tool being absent.
Status: retired unactivated — replaced by Conventions §12 (TK_REPO); see REFUSALS.md at 5dd2e8c

### C-151: The graded stage-1 suite passes in the mode grading uses, at a named revision.
Check: `R="${TK_REPO:-/Users/aashanjaved/band-work/result}"; test -z "$(git -C "$R" status --porcelain)" || { echo "TREE NOT CLEAN IN $R"; exit 1; }; before=$(git -C "$R" rev-parse HEAD); cd /Users/aashanjaved/dark-factory-wearedevs && ./.venv/bin/python -m harness run --track tablekeeper --repo "$R" --stage 1 --mode isolated --out /Users/aashanjaved/band-work/checks/s1-iso-$(date +%s); r=$?; test $r -eq 0 && test -z "$(git -C "$R" status --porcelain)" && test "$(git -C "$R" rev-parse HEAD)" = "$before" && echo "TREE CLEAN AND UNMOVED AT $before"; exit $?`
Passes when: the harness exits 0 reporting zero failures and zero errors for stage 1, then `TREE CLEAN AND UNMOVED AT <revision>` prints. Replaces C-146. `--mode isolated` is the grading mode: the service gets no outbound access and is reached by container name, so a pass cannot be earned by a service that fetches something at run time.
Status: retired unactivated — replaced by Conventions §12 (TK_REPO); see REFUSALS.md at 5dd2e8c

### C-152: The shipped stage-1 checks pass in the mode grading uses, at a named revision.
Check: `R="${TK_REPO:-/Users/aashanjaved/band-work/result}"; test -z "$(git -C "$R" status --porcelain)" || { echo "TREE NOT CLEAN IN $R"; exit 1; }; before=$(git -C "$R" rev-parse HEAD); cd /Users/aashanjaved/dark-factory-wearedevs && ./.venv/bin/python -m harness run --track tablekeeper --repo "$R" --stage 1 --mode isolated --out /Users/aashanjaved/band-work/checks/s1-iso-shipped-$(date +%s); r=$?; test $r -eq 0 && test -z "$(git -C "$R" status --porcelain)" && test "$(git -C "$R" rev-parse HEAD)" = "$before" && echo "TREE CLEAN AND UNMOVED AT $before"; exit $?`
Passes when: the harness exits 0 reporting zero failures and zero errors for stage 1, then `TREE CLEAN AND UNMOVED AT <revision>` prints. Replaces C-147. Host mode remains useful while developing, but per the harness's own warning it must never be the basis of a pass, so no live entry in this ledger claims anything from it.
Status: retired unactivated — replaced by Conventions §12 (TK_REPO); see REFUSALS.md at 5dd2e8c

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

## Superseded by Errata 3 — authorised, run, and passed

| Original | Replaced by | Why |
|---|---|---|
| C-28 | C-153 | booked against an availability snapshot its own bookings invalidated |
| C-46 | C-154 | demanded 27 coexisting bookings where the ceiling is 9 |
| C-56 | C-155 | fixture gave both restaurants the same table ids |
| C-123 | C-156 | booked 9 across three pairwise-overlapping starts |

`@registrar` authorises supersession, not `@scribe`, and the errata-2 precedent says entries of
unexecuted shape should not displace entries of proven shape. These four are unexecuted. The FAIL
verdicts establish the originals are defective; they do not establish that the replacements work.

Settled: the `66e7967` bound was met and the supersession was authorised at `9013eef`; C-153…C-156
passed at `ec1fe94`, see `verdicts/`. The sentence above records the state at the time of writing.

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

A handoff also names the revision **twice, adjacently**, because a handoff file cannot contain the
hash of the commit that contains it:

```
Parent revision: <pre-commit HEAD>   — NOT the submission
Submitted revision: derive with `git log -1 --format=%H -- handoffs/batch-<n>.md`
```

`Parent revision:` alone is correct and misleading, which is worse than wrong-by-construction: it is
the only revision in the file, so a reader looking for "the revision" finds it and cites a commit
that **does not contain the handoff**. That happened on this clause's first use, to two seats. The
derivation must sit beside the field a reader actually reads, not under a separate heading further
down — a correct value in the wrong place is still a misread waiting to happen.

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
   judge.

4. **An entry may not assert that a run occurred.** `Passes when:` specifies what a run must print;
   no entry prose — from any seat, including `@scribe` — may claim that a run happened or quote its
   output. A claim of a run is unauditable by construction: `@auditor` runs the Check, not the prose
   around it, and nothing in any mandate or in the harness inspects it. Git is tamper-evident, not
   checked — it pins who wrote a line and that it has not changed, never that a quoted output came
   from a run. **There is exactly one checked home for a claim of a run: `verdicts/<claim-id>.md`.**
   This clause exists because six such claims were written into this file with fabricated outputs and
   were caught only by the author running them; no other seat was positioned to find them. `aria-label` present is not the label being visible; seven `data-state` values existing is
   not seven visually distinct states. A proxy presented as the whole property is a **case-3 refusal**.

Stage 1 ended on an instrument reporting success about something it never tested. Five of the seven
ledger defects were checks that could not establish what their prose claimed. The UI is where that
mistake is cheapest to make and most expensive to find, because a green `data-testid` looks exactly
like a working interface until a person opens it.

## The gate

### S-0: The stage-2 service builds from a clean container, serves /health within 60 seconds, and genuinely publishes its port.
Check: `TK_REPO="${TK_REPO:-/Users/aashanjaved/band-work/result}"; test -z "$(git -C "$TK_REPO" status --porcelain)" || { echo "TREE NOT CLEAN"; exit 1; }; before=$(git -C "$TK_REPO" rev-parse HEAD); docker rm -f tk-s2 >/dev/null 2>&1; docker network rm tk-s2-net >/dev/null 2>&1; docker builder prune -af >/dev/null 2>&1; test -f "$TK_REPO/stage-2/Dockerfile" && test -f "$TK_REPO/stage-2/RUN.md" && docker network create tk-s2-net && docker build --no-cache -t tk-s2 "$TK_REPO/stage-2" && docker run -d --name tk-s2 --network tk-s2-net -p 18080:8080 -e PORT=8080 tk-s2 && start=$(date +%s) && until curl -fsS http://127.0.0.1:18080/health; do [ $(( $(date +%s) - start )) -lt 60 ] || { echo "NOT HEALTHY WITHIN 60s"; exit 1; }; sleep 1; done && echo " HEALTHY IN $(( $(date +%s) - start ))s" && test "$(docker inspect tk-s2 --format '{{json .NetworkSettings.Ports}}')" != "{}" && echo "PORT PUBLISHED" && test -z "$(git -C "$TK_REPO" status --porcelain)" && test "$(git -C "$TK_REPO" rev-parse HEAD)" = "$before" && echo "TREE CLEAN AND UNMOVED AT $before"`
Passes when: exits 0 and prints the `/health` body, then `HEALTHY IN <n>s` with `n` at most 60, then `PORT PUBLISHED`, then `TREE CLEAN AND UNMOVED AT <revision>`. This is the gate. `PORT PUBLISHED` is the assertion C-0 assumed and never checked, which cost stage 1 an hour; it is asserted here rather than inferred from the curl succeeding.
Status: passed at 0b0e01d — see verdicts/S-0.md

### S-1: The stage-2 service has no outbound network access at run time and still serves.
Check: `TK_REPO="${TK_REPO:-/Users/aashanjaved/band-work/result}"; docker rm -f tk-s1x >/dev/null 2>&1; docker network rm tk-s1x-noout >/dev/null 2>&1; docker network create --internal tk-s1x-noout && test "$(docker network inspect tk-s1x-noout --format '{{.Internal}}')" = "true" && docker build -q -t tk-s2 "$TK_REPO/stage-2" >/dev/null && docker run -d --name tk-s1x --network tk-s1x-noout -e PORT=8080 tk-s2 >/dev/null && for i in $(seq 1 60); do docker run --rm --network tk-s1x-noout alpine:3 wget -qO- -T3 http://tk-s1x:8080/health >/dev/null 2>&1 && break; sleep 1; done; docker run --rm --network tk-s1x-noout alpine:3 sh -c 'wget -qO- -T5 http://tk-s1x:8080/health || exit 1; nslookup example.com >/dev/null 2>&1 && exit 2; nc -w4 -z 1.1.1.1 80 2>/dev/null && exit 3; wget -qO- -T4 http://example.com >/dev/null 2>&1 && exit 4; echo " NO EGRESS"'; r=$?; docker rm -f tk-s1x >/dev/null 2>&1; docker network rm tk-s1x-noout >/dev/null 2>&1; exit $r`
Passes when: exits 0 and prints the `/health` body then `NO EGRESS`. Replicates C-143 against stage 2, because §2's no-outbound rule applies to every stage and the UI adds fonts, scripts and stylesheets — the exact assets a service is tempted to fetch at run time. Exit 1 means the service did not answer, 2 DNS resolved, 3 raw TCP opened, 4 an HTTP fetch succeeded.
Status: passed at eb5bcb9 — see verdicts/S-1.md

### S-2: RUN.md's own command builds and starts the stage-2 service from a clean checkout.
Check: `TK_REPO="${TK_REPO:-/Users/aashanjaved/band-work/result}"; test -z "$(git -C "$TK_REPO" status --porcelain)" || { echo "TREE NOT CLEAN"; exit 1; }; before=$(git -C "$TK_REPO" rev-parse HEAD); cd "$TK_REPO/stage-2" && docker rm -f tk-s2 >/dev/null 2>&1; awk '/^```/{f=!f;next} f' RUN.md > /tmp/tk-s2-runmd.sh && test -s /tmp/tk-s2-runmd.sh && sh -eux /tmp/tk-s2-runmd.sh && start=$(date +%s) && until curl -fsS http://127.0.0.1:18080/health; do [ $(( $(date +%s) - start )) -lt 60 ] || { echo "NOT HEALTHY"; exit 1; }; sleep 1; done && test -z "$(git -C "$TK_REPO" status --porcelain)" && test "$(git -C "$TK_REPO" rev-parse HEAD)" = "$before" && echo "RUNMD OK AT $before"`
Passes when: exits 0 and prints the `/health` body then `RUNMD OK AT <revision>`. The fenced blocks of `stage-2/RUN.md` must hold exactly the build-and-start commands, need no editing, and work from the stage directory of any clean checkout. Stage 1's C-1 found a `RUN.md` that attached the container to an `--internal` network and published nothing; this asserts the replacement did not regress.
Status: passed at eb5bcb9 — see verdicts/S-2.md

## Stage 1 must still behave — stage-2/ is graded against suite 1

### S-3: The stage-1 graded suite passes against stage-2/ in the grading mode.
Check: `TK_REPO="${TK_REPO:-/Users/aashanjaved/band-work/result}"; test -z "$(git -C "$TK_REPO" status --porcelain)" || { echo "TREE NOT CLEAN"; exit 1; }; before=$(git -C "$TK_REPO" rev-parse HEAD); cd /Users/aashanjaved/dark-factory-wearedevs && ./.venv/bin/python -m harness run --track tablekeeper --repo "$TK_REPO" --stage 2 --mode isolated --out /Users/aashanjaved/band-work/checks/s2-iso-$(date +%s); r=$?; test $r -eq 0 && test -z "$(git -C "$TK_REPO" status --porcelain)" && test "$(git -C "$TK_REPO" rev-parse HEAD)" = "$before" && echo "TREE CLEAN AND UNMOVED AT $before"; exit $?`
Passes when: the harness exits 0 reporting zero failures and zero errors for **both** stage 1 and stage 2, then `TREE CLEAN AND UNMOVED AT <revision>` prints. `--stage 2` runs suite 1 and suite 2 against `stage-2/`, so a stage-1 regression fails here. A printed failure for stage 3 is expected and required; per `harness/cli.py:459` the next-stage probe's exit code is not this run's and the probe failing is the good case.
Status: passed at eb5bcb9 — see verdicts/S-3.md

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
Status: passed at eb5bcb9 — see verdicts/S-4.md

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
Status: passed at eb5bcb9 — see verdicts/S-5.md

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
Status: passed at eb5bcb9 — see verdicts/S-6.md

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
Status: passed at eb5bcb9 — see verdicts/S-7.md

### S-8: A pair not listed in combinable is 422 combination_not_allowed.
Check: `$PWPY -c "$W"'
ta,_=SETUP()
ERR(BOOK(ta,F+"T19:00","s8a",table_ids=["t_1","t_3"],ps=6),422,"combination_not_allowed")
ERR(BOOK(ta,F+"T19:00","s8b",table_ids=["t_3","t_1"],ps=6),422,"combination_not_allowed")
OK(BOOK(ta,F+"T19:00","s8c",table_ids=["t_1","t_2"],ps=6),201)
print("PASS")'`
Passes when: prints `PASS`. `[t_1,t_3]` is refused in both orderings even though the two tables are free and their summed capacity is sufficient, while a declared pair at the same slot is accepted.
Status: passed at eb5bcb9 — see verdicts/S-8.md

### S-9: Combining is not transitive.
Check: `$PWPY -c "$W"'
ta,_=SETUP()
ERR(BOOK(ta,F+"T19:00","s9",table_ids=["t_1","t_3"],ps=6),422,"combination_not_allowed")
OK(BOOK(ta,F+"T19:00","s9a",table_ids=["t_1","t_2"],ps=6),201)
RESET(FX()); ta=LOGIN(ADA)
OK(BOOK(ta,F+"T19:00","s9b",table_ids=["t_2","t_3"],ps=8),201)
print("PASS")'`
Passes when: prints `PASS`. `[t_1,t_2]` and `[t_2,t_3]` are both declared and both bookable, and `{t_1,t_3}` is still refused — the specification says transitivity must not be inferred.
Status: passed at eb5bcb9 — see verdicts/S-9.md

### S-10: A combinable entry is an unordered pair.
Check: `$PWPY -c "$W"'
RESET(FX(restaurants=[REST(combinable=[["t_2","t_1"]])])); ta=LOGIN(ADA)
b=OK(BOOK(ta,F+"T19:00","s10",table_ids=["t_1","t_2"],ps=6),201)
assert sorted(b["table_ids"])==["t_1","t_2"],b
RESET(FX(restaurants=[REST(combinable=[["t_1","t_2"]])])); ta=LOGIN(ADA)
OK(BOOK(ta,F+"T19:00","s10b",table_ids=["t_2","t_1"],ps=6),201)
print("PASS")'`
Passes when: prints `PASS`. A pair declared `[t_2,t_1]` is bookable as `[t_1,t_2]` and a pair declared `[t_1,t_2]` is bookable as `[t_2,t_1]`. The fixture's ordering does not constrain the request's.
Status: passed at eb5bcb9 — see verdicts/S-10.md

### S-11: More than two tables is 422 combination_not_allowed.
Check: `$PWPY -c "$W"'
ta,_=SETUP()
ERR(BOOK(ta,F+"T19:00","s11a",table_ids=["t_1","t_2","t_3"],ps=10),422,"combination_not_allowed")
RESET(FX(restaurants=[REST(combinable=[["t_1","t_2"],["t_2","t_3"],["t_1","t_3"]])])); ta=LOGIN(ADA)
ERR(BOOK(ta,F+"T19:00","s11b",table_ids=["t_1","t_2","t_3"],ps=10),422,"combination_not_allowed")
print("PASS")'`
Passes when: prints `PASS`. Three tables is refused even when every constituent pair is declared — the rule is pairs only, not "any set whose pairs are all combinable".
Status: passed at eb5bcb9 — see verdicts/S-11.md

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
Status: passed at eb5bcb9 — see verdicts/S-12.md

### S-13: A duplicate table id in the set is 422 validation_failed.
Check: `$PWPY -c "$W"'
ta,_=SETUP()
ERR(BOOK(ta,F+"T19:00","s13a",table_ids=["t_2","t_2"],ps=4),422,"validation_failed")
ERR(BOOK(ta,F+"T19:00","s13b",table_ids=["t_1","t_1"],ps=2),422,"validation_failed")
print("PASS")'`
Passes when: prints `PASS`. A duplicate is `validation_failed`, not `combination_not_allowed` — the specification separates a malformed set from an undeclared pair.
Status: passed at eb5bcb9 — see verdicts/S-13.md

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
Status: passed at eb5bcb9 — see verdicts/S-14.md

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
Status: passed at eb5bcb9 — see verdicts/S-15.md

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
Status: passed at eb5bcb9 — see verdicts/S-16.md

### S-17: available_options orders singles in fixture order, then pairs in combinable order.
Check: `$PWPY -c "$W"'
RESET(FX(restaurants=[REST(tables=[{"id":"t_3","label":"Terrace","capacity":4},{"id":"t_1","label":"Window","capacity":4},{"id":"t_2","label":"Corner","capacity":4}],combinable=[["t_2","t_3"],["t_1","t_2"]])]))
s=SLOT("r_anker",F,4,F+"T19:00")
ids=[o["table_ids"] for o in s["available_options"]]
assert ids==[["t_3"],["t_1"],["t_2"],["t_2","t_3"],["t_1","t_2"]],ids
print("PASS",ids)'`
Passes when: prints `PASS` and the order. The fixture deliberately lists tables `t_3,t_1,t_2` and pairs `[t_2,t_3],[t_1,t_2]`, so alphabetical or id-sorted output fails. Singles precede pairs, each group in its own declared order, and `table_ids` within a pair follows `combinable` order.
Status: passed at eb5bcb9 — see verdicts/S-17.md

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
Status: passed at eb5bcb9 — see verdicts/S-18.md

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
Status: passed at eb5bcb9 — see verdicts/S-19.md

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
Status: passed at eb5bcb9 — see verdicts/S-20.md

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
Status: passed at eb5bcb9 — see verdicts/S-21.md

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
Status: passed at eb5bcb9 — see verdicts/S-22.md

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
Status: passed at eb5bcb9 — see verdicts/S-23.md

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
Status: passed at eb5bcb9 — see verdicts/S-24.md

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
Status: passed at eb5bcb9 — see verdicts/S-25.md

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
Status: passed at eb5bcb9 — see verdicts/S-26.md

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
Status: passed at eb5bcb9 — see verdicts/S-27.md

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
Status: passed at eb5bcb9 — see verdicts/S-28.md

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
Status: passed at eb5bcb9 — see verdicts/S-29.md

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
Status: passed at eb5bcb9 — see verdicts/S-30.md

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
Status: passed at eb5bcb9 — see verdicts/S-31.md

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
Status: passed at eb5bcb9 — see verdicts/S-32.md

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
Status: passed at eb5bcb9 — see verdicts/S-33.md

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
Status: passed at eb5bcb9 — see verdicts/S-34.md

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
Status: passed at eb5bcb9 — see verdicts/S-35.md

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
Status: passed at eb5bcb9 — see verdicts/S-36.md

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
Status: passed at eb5bcb9 — see verdicts/S-37.md

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
Status: passed at eb5bcb9 — see verdicts/S-38.md

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
Status: passed at eb5bcb9 — see verdicts/S-39.md

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
Status: passed at eb5bcb9 — see verdicts/S-40.md

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
Status: FAILED at eb5bcb9 — see verdicts/S-41.md; superseded by S-59

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
Status: passed at eb5bcb9 — see verdicts/S-42.md

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
Status: passed at eb5bcb9 — see verdicts/S-43.md

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
Status: passed at eb5bcb9 — see verdicts/S-44.md

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
Status: passed at eb5bcb9 — see verdicts/S-45.md

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
Status: passed at eb5bcb9 — see verdicts/S-46.md

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
Status: FAILED at eb5bcb9 — see verdicts/S-47.md; superseded by S-60

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
Status: passed at eb5bcb9 — see verdicts/S-48.md

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
Status: FAILED at eb5bcb9 — see verdicts/S-49.md; superseded by S-61

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
Status: FAILED at eb5bcb9 — see verdicts/S-50.md; superseded by S-62

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
Status: FAILED at eb5bcb9 — see verdicts/S-51.md; superseded by S-63

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
Status: passed at eb5bcb9 — see verdicts/S-52.md

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
Status: passed at eb5bcb9 — see verdicts/S-53.md

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
Status: passed at eb5bcb9 — see verdicts/S-54.md

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
Status: passed at eb5bcb9 — see verdicts/S-55.md

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
Status: passed at eb5bcb9 — see verdicts/S-56.md

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
Status: passed at eb5bcb9 — see verdicts/S-57.md

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
Status: FAILED at eb5bcb9 — see verdicts/S-58.md; superseded by S-64

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

---

# ERRATA 4 — six stage-2 Checks that could not establish their own prose

Six Checks have FAIL verdicts at `eb5bcb9`, each with a quoted run, and all six are defects in the
Check rather than the implementation. The graded suite **passed** at that revision — suite 1
`120 passed`, suite 2 `25 passed`, `claimed_stage 2`, isolated — so the submission is right and these
six were wrong. The `66e7967` bound is met.

```
S-47  TargetClosedError: ElementHandle.inner_text: Target page has been closed
S-50  TargetClosedError: ElementHandle.inner_text: Target page has been closed
S-41  AssertionError: changed field reused the reference: None
S-51  AssertionError: status 409 want (201,)  {'code': 'table_unavailable'}
S-58  AssertionError: booking-summary does not name both tables by label: ''
S-49  AssertionError: retained reference not found after the import
```

## Defect 8 — the same body written three times, correct once

S-46, S-47 and S-50 share one structure. S-46 closes the browser **after** reading the confirmation
and passes; S-47 and S-50 close it **before** and cannot pass on any service. The correct ordering
was in the entry immediately above the first of them.

## Defect 9 — three more Checks demanding state the occupancy rule forbids

**S-41** resubmits after changing only `booking-party-size`, so the second submission targets the
table its own first booking holds. **S-51** needed a second account to take a cell the browser had
just filled. **S-58** booked a pair and then required selecting that pair from `available_options`
its own booking had emptied.

This is stage 1's D-6 for the third, fourth and fifth time. C-46 asked for 27 coexisting bookings
against a ceiling of 9; C-123 asked for 9 across pairwise-overlapping starts. **Four of the six
defects here contradict a rule stated elsewhere in this same file**, and S-49 contradicts C-112 —
*"Import removes all previous destination data and credentials"* — which I wrote and which passed.

S-41 also mis-stated the requirement. The specification says changing a field makes the next
submission a **new booking request**; a new request may legitimately be refused. Asserting a new
*reference* required an outcome the occupancy rule forbids.

## Replacement entries

**All six were executed against a live service before being committed.** Outputs are quoted in each
entry. `@auditor`'s run settles them; mine only establishes that the commands execute and their
assertions are reachable — the thing errata-2's replacements lacked when supersession was refused.

### S-59: Changing a field makes the next submission a new booking request rather than a replay.
Check: `$PWPY -c "$W"'
ta,_=SETUP()
def f(pg):
    LOGIN_UI(pg); SEARCH_UI(pg,"r_anker",F,4)
    CLICK(pg,"slot-t_2-19:00"); pg.wait_for_timeout(500)
    CLICK(pg,"booking-submit"); pg.wait_for_timeout(1300)
    first=TXT(pg,"confirmation-reference")
    assert first,"no confirmation on the first booking"
    FILL(pg,"booking-party-size",3); pg.wait_for_timeout(200)
    CLICK(pg,"booking-submit"); pg.wait_for_timeout(1400)
    after=TXT(pg,"confirmation-reference")
    replayed = (after==first and not SEE(pg,"booking-error"))
    assert not replayed,"changed field replayed the original receipt: %r"%after
    assert SEE(pg,"booking-error") or (after and after!=first),"changed field produced neither a new booking nor a refusal"
    return first,after,SEE(pg,"booking-error")
r=UI(f)
rs=[x for x in OK(R("GET","/reservations",tok=ta),200)["reservations"] if x["status"]=="confirmed"]
assert len(rs)==1,"a changed-field submission must not create a second overlapping booking: %r"%rs
print("PASS",r)'`
Passes when: prints `PASS` with the first reference, the post-change state and the error flag. Replaces S-41. The changed body must **not** replay the original receipt; because the form still targets the table the first booking holds, the new request is legitimately refused with `booking-error`, which is what the occupancy rule requires. Exactly one confirmed booking exists.
Status: passed at 1fe8ebe — see verdicts/S-59.md

### S-60: The uncertainty and refusal rules hold for a combination booking too.
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
        await pg.fill("[data-testid=date-input]",F); await pg.fill("[data-testid=party-size-input]","6")
        await pg.click("[data-testid=search-button]"); await pg.wait_for_timeout(900)
        await pg.click(SEL("slot-t_1+t_2-19:00")); await pg.wait_for_timeout(500)
        await pg.click("[data-testid=booking-submit]"); await pg.wait_for_timeout(2000)
        unc=await pg.query_selector("[data-testid=booking-uncertain]")
        u=(await unc.inner_text()).strip() if unc else None
        await pg.click("[data-testid=booking-submit]"); await pg.wait_for_timeout(2200)
        ref=await pg.query_selector("[data-testid=confirmation-reference]")
        rt=await pg.query_selector("[data-testid=confirmation-tables]")
        ref_t=(await ref.inner_text()).strip() if ref else None
        rt_t=(await rt.inner_text()).strip() if rt else None
        await br.close()
        return u,ref_t,rt_t
u,ref,tabs=asyncio.run(run())
assert u,"no booking-uncertain for a lost combination booking"
rs=OK(R("GET","/reservations",tok=ta),200)["reservations"]
assert len(rs)==1 and rs[0]["table_ids"]==["t_1","t_2"],rs
assert ref==rs[0]["reference"],(ref,rs[0]["reference"])
for lab in ["Window","Corner"]:
    assert lab in (tabs or ""),"confirmation-tables omits %r after recovery: %r"%(lab,tabs)
print("PASS",ref)'`
Passes when: prints `PASS` and the reference. Replaces S-47. Identical in substance; the browser is closed **after** the confirmation is read, which S-47 did before, making it unsatisfiable on any service.
Status: passed at 1fe8ebe — see verdicts/S-60.md

### S-61: A browser signed in before the upgrade stays signed in, and its retained reference works through the lookup screen.
Check: `$PWPY -c "$W"'
ta,_=SETUP()
b=OK(BOOK(ta,F+"T19:00","s61",table_id="t_2",ps=4),201)
def f(pg):
    LOGIN_UI(pg)
    cu=TXT(pg,"current-user"); assert cu and "Ada" in cu,cu
    snap=OK(R("GET","/_test/export"),200)
    s,_,_=R("POST","/_test/import",snap)
    assert s==204,s
    pg.goto(BASE+"/lookup",wait_until="load"); pg.wait_for_timeout(500)
    cu2=TXT(pg,"current-user")
    assert cu2 and "Ada" in cu2,"browser lost its session across the import: %r"%cu2
    FILL(pg,"lookup-reference-input",b["reference"]); CLICK(pg,"lookup-submit"); pg.wait_for_timeout(900)
    assert SEE(pg,"reservation-detail"),"retained reference not found after the import"
    assert TXT(pg,"reservation-status")=="confirmed",TXT(pg,"reservation-status")
    assert not SEE(pg,"reservation-error"),"reservation-error shown for a retained reference"
    return cu2
print("PASS",UI(f,route=None))'`
Passes when: prints `PASS` and the display name. Replaces S-49. The export is taken **after** the browser signs in, so the session token is in the snapshot; S-49 exported before the login, so the token was never captured and the import then removed all destination credentials — which is exactly what C-112 requires and what made S-49 contradict it.
Status: passed at 1fe8ebe — see verdicts/S-61.md

### S-62: A booking whose response was lost before the export is still recoverable after the import.
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
        await pg.click(SEL("slot-t_2-19:00")); await pg.wait_for_timeout(500)
        await pg.click("[data-testid=booking-submit]"); await pg.wait_for_timeout(2000)
        u1=await pg.query_selector("[data-testid=booking-uncertain]")
        had=bool(u1)
        snap=OK(R("GET","/_test/export"),200)
        s,_,_=R("POST","/_test/import",snap)
        assert s==204,s
        await pg.click("[data-testid=booking-submit]"); await pg.wait_for_timeout(2300)
        ref=await pg.query_selector("[data-testid=confirmation-reference]")
        u2=await pg.query_selector("[data-testid=booking-uncertain]")
        e2=await pg.query_selector("[data-testid=booking-error]")
        ref_t=(await ref.inner_text()).strip() if ref else None
        await br.close()
        return had,ref_t,bool(u2),bool(e2)
had,ref,u2,e2=asyncio.run(run())
assert had,"no booking-uncertain after the lost response"
rs=OK(R("GET","/reservations",tok=ta),200)["reservations"]
assert len(rs)==1,"retry after upgrade created a second booking: %d"%len(rs)
assert ref==rs[0]["reference"],"original confirmation not recovered: %r vs %r"%(ref,rs[0]["reference"])
assert not u2 and not e2,"uncertainty/error not cleared after a successful post-upgrade retry"
print("PASS",ref)'`
Passes when: prints `PASS` and the reference. Replaces S-50. Same substance, with the browser closed **after** the reads. The booking commits, its response is dropped, state is exported and imported, and the unchanged form retries with the same key and body to recover the original reference.
Status: passed at 1fe8ebe — see verdicts/S-62.md

### S-63: The seven required states are visually distinct from one another.
Check: `$PWPY -c "$W"'
ta,tb=SETUP()
OK(BOOK(ta,F+"T21:00","s63",table_id="t_2",ps=2),201)
def f(pg):
    st={}
    LOGIN_UI(pg); SEARCH_UI(pg,"r_anker",F,2)
    st["available"]=STYLE(pg,"slot-t_3-19:00")
    st["unavailable"]=STYLE(pg,"slot-t_2-21:00")
    CLICK(pg,"slot-t_3-19:00"); pg.wait_for_timeout(500)
    st["selected"]=STYLE(pg,"slot-t_3-19:00")
    CLICK(pg,"booking-submit"); pg.wait_for_timeout(110)
    st["loading"]=STYLE(pg,"booking-loading") if TID(pg,"booking-loading") else STYLE(pg,"booking-submit")
    pg.wait_for_timeout(1600)
    st["successful"]=STYLE(pg,"confirmation") if TID(pg,"confirmation") else None
    SEARCH_UI(pg,"r_anker",F,2)
    CLICK(pg,"slot-t_1-19:00"); pg.wait_for_timeout(450)
    OK(BOOK(tb,F+"T19:00","s63b",table_id="t_1",ps=2),201)
    CLICK(pg,"booking-submit"); pg.wait_for_timeout(1500)
    st["refused"]=STYLE(pg,"booking-error") if TID(pg,"booking-error") else None
    return st
st=UI(f)
for k,v in st.items():
    assert v is not None,"state %r produced no element to measure"%k
pairs=[(a,b) for a in st for b in st if a<b]
same=[(a,b) for a,b in pairs if st[a]==st[b]]
assert not same,"states not visually distinct: %r"%same
print("PASS",len(st),"states,",len(pairs),"pairs distinct")'`
Passes when: prints `PASS 6 states, 15 pairs distinct`. Replaces S-51. The refusal is now produced on `t_1`, a cell still free when selected and taken by the second account before submit; S-51 re-selected the cell its own booking had just filled, so it never reached the measurement. **The measurement is unchanged and not weakened** — still seven computed style properties per state, still every pair required to differ. `uncertain` is measured by S-46, which asserts its text is non-empty. **Proxy:** style vectors differing does not establish that a person can tell the states apart.
Status: passed at 1fe8ebe — see verdicts/S-63.md

### S-64: Restaurants and tables are shown by human-readable name, not by raw identifier.
Check: `$PWPY -c "$W"'
SETUP()
def f(pg):
    LOGIN_UI(pg); SEARCH_UI(pg,"r_anker",F,6)
    body=pg.inner_text("body")
    assert "Zum Anker" in body,"the restaurant name is not shown on the search screen"
    for lab in ["Window","Corner","Terrace"]:
        assert lab in body,"table label %r not shown in the grid"%lab
    CLICK(pg,"slot-t_1+t_2-19:00"); pg.wait_for_timeout(600)
    s=TXT(pg,"booking-summary") or ""
    for lab in ["Window","Corner"]:
        assert lab in s,"booking-summary omits %r: %r"%(lab,s)
    assert "t_1+t_2" not in s,"booking-summary shows the concatenated id form: %r"%s
    CLICK(pg,"booking-submit"); pg.wait_for_timeout(1400)
    ref=TXT(pg,"confirmation-reference")
    ct=TXT(pg,"confirmation-tables") or ""
    for lab in ["Window","Corner"]:
        assert lab in ct,"confirmation-tables omits %r: %r"%(lab,ct)
    pg.goto(BASE+"/lookup",wait_until="load")
    FILL(pg,"lookup-reference-input",ref); CLICK(pg,"lookup-submit"); pg.wait_for_timeout(900)
    rt=TXT(pg,"reservation-tables") or ""
    for lab in ["Window","Corner"]:
        assert lab in rt,"reservation-tables omits %r: %r"%(lab,rt)
    assert "t_1+t_2" not in rt,"reservation-tables shows the concatenated id form: %r"%rt
    return s,ct,rt
print("PASS",UI(f,route=None))'`
Passes when: prints `PASS` with the summary, confirmation and lookup text. Replaces S-58. The pair is **selected from the grid and then booked**, rather than booked first and selected afterwards — S-58 emptied `available_options` with its own booking and then required the cell it had just removed. **Proxy:** it forbids the concatenated-id failure and requires labels in three places; whether combinations "read as intentional seating options" remains declared human-judged.
Status: passed at 1fe8ebe — see verdicts/S-64.md

## Superseded by Errata 4 — authorised, run, and passed

| Original | Replaced by | Why |
|---|---|---|
| S-41 | S-59 | required a new reference where the occupancy rule forbids one |
| S-47 | S-60 | closed the browser before reading the confirmation |
| S-49 | S-61 | exported before the browser signed in, so the token was never in the snapshot |
| S-50 | S-62 | closed the browser before reading the confirmation |
| S-51 | S-63 | re-selected a cell its own booking had filled, never reaching the measurement |
| S-58 | S-64 | booked the pair, then required selecting it from the options it had emptied |

Settled: the `66e7967` bound was met and the supersession was authorised at `62127f9`; S-59…S-64
passed at `1fe8ebe`, see `verdicts/`. The heading above recorded the state at the time of writing.

---

# ERRATA 5 — every check in this ledger can pass on content no eye can see

A human looking at the running service reported, at `c07cb94`: signed out, the header shows the brand
and two navigation links and nothing else; there is no visible way to sign in or create an account;
clicking a slot then shows an error telling the visitor to sign in, with no visible route to do so.

The elements are in the DOM. They have text, non-zero bounding boxes, no `display:none` and no
`visibility:hidden`, and a click by accessible name succeeds on them. **Every assertion this ledger
owns passes on them.** That includes S-57, which is this file's contrast claim: it reads
`getComputedStyle(e).color` and walks ancestors for a background, so it measures *declared* colour,
never *painted* colour. `color: transparent` resolves to `rgba(0, 0, 0, 0)`, from which this file's
own `LUM` takes the first three integers — `0, 0, 0` — and scores black-on-white at 21:1. An
`opacity: 0` ancestor is not in `color` or `backgroundColor` at all, so it is invisible to every
entry here. S-56 reads `aria-label` and `outlineStyle`; S-63 reads `data-state`; S-28 reads an HTTP
status. **Not one of the sixty-five claims written before this section can tell painted from
declared**, which is why the defect reached a human rather than a run.

The three defects that follow are in this ledger, not in the service.

## Defect 8 — the contrast claim measures declared colour, not painted colour

S-57 and S-56 compute from `getComputedStyle`. A control is invisible-but-conformant under at least
four mechanisms they cannot see: `color: transparent`; any `opacity: 0` on the element or an
ancestor; a foreground equal to a background that the ancestor walk does not reach (a gradient, an
image, a `background` shorthand on a sibling layer); and occlusion by a later-painted element.
Affects **S-56, S-57**. Neither is withdrawn — they still forbid what they always forbade — and
neither is edited. The new entries measure a different thing.

## Defect 9 — the claims are a sample, and the sample was chosen before the defect was known

S-57 names five elements on two screens and says so honestly. A sample cannot answer "is the same
class of defect anywhere else", which is the question a defect report of this shape forces. Affects
the coverage of **§UI quality** as a whole.

## Defect 10 — "sufficient contrast" was carried into this ledger as a word, not a number

The spec says, at `tablekeeper/spec/stage-2.md:61`, "text and controls need sufficient contrast", and
at `:53-54`, "Primary actions must be easy to identify". S-57 silently chose 4.5:1 without declaring
that it had chosen; "Primary actions are easy to identify" was instead routed to **Declared
human-judged**, where no command can fail. One of those two is a hidden decision and the other is no
decision. §18 below declares the numbers in the open.

## §17 The rendered-raster instrument (`$PX`)

Every entry in this section measures **pixels that were actually painted**, read back out of a
compositor screenshot. Nothing in it consults `getComputedStyle` for colour.

Load it alongside `$W` from §15. It is appended to `$W`, not a replacement, and §15 is unchanged:

```sh
export PWPY=/Users/aashanjaved/dark-factory-wearedevs/.venv/bin/python
export TK_REPO="${TK_REPO:-/Users/aashanjaved/band-work/result}"
export W="$(awk '/^#PW-BEGIN$/{f=1;next} /^#PW-END$/{f=0} f' "$TK_REPO/LEDGER.md")"
export PX="$(awk '/^#PX-BEGIN$/{f=1;next} /^#PX-END$/{f=0} f' "$TK_REPO/LEDGER.md")"
export WPX="$W
$PX"
```

Confirm all three loaded before running any entry below:

```sh
$PWPY -c "$WPX"'
print("WPX OK",BASE,PX_AA,PX_UI,len(PX_ENUM),len(PX_READ),len(PX_SURF))'
```

**How it reads painted pixels without a Python image library.** The harness interpreter has no
Pillow and no numpy — only Playwright. So the raster is taken with `page.screenshot(full_page=True)`,
handed back into the page as a `data:` URL, drawn to a detached `<canvas>` that is never appended to
the document, and read with `getImageData`. The decoder is Chromium's own. A `data:` URL does not
taint a canvas, so the pixels are readable. The screenshot is taken **before** the canvas exists, so
the instrument cannot alter what it measures.

**What each element yields.** For every measured element the instrument reports, from the raster:
the dominant colour inside its box inset by 2 CSS pixels (`bg`), the number of distinct colours in
that inset box (`distinct`), the highest contrast ratio between any colour covering at least 2 pixels
of that box and `bg` (`ratio_text`, with the colour that achieved it as `ink`), the dominant colour
of a 6-pixel ring immediately outside the box (`surround`), and the highest contrast ratio between
any colour in the full box and `surround` (`salience`). The 2-pixel inset exists so a border is not
read as the element's own ink; antialiased glyph edges sit *between* foreground and background, so
taking the maximum is the generous reading, never the harsh one.

**Verdicts.** `OK`; `NO-INK` — the inset box holds one colour, so nothing was painted inside it;
`LOW-CONTRAST` — a text-bearing element whose `ratio_text` is under its threshold;
`FLAT-AGAINST-PAGE` — an interactive element with no text of its own whose whole box is under 3:1
against the page immediately around it; `NO-PIXELS` — the box fell outside the raster.

**What it excludes, and this is the honest part.** An element is reported in a separate `skipped`
list, not measured, when it is `display:none`, not `visibility:visible`, `aria-hidden=true`, inside a
`[hidden]` ancestor, has a box under one pixel, or has another element at its centre point that is
neither its ancestor nor its descendant (`occluded-by-*`). Without the occlusion exclusion an open
modal fails every element behind it and no interface can pass. **The exclusion is a door**: a control
covered by a transparent overlay is skipped, not failed. That is why S-66, S-68 and S-70 require
named controls to appear in the *measured* set, and why every entry prints the skip list in full. A
reader must check what was skipped; a passing line alone does not tell them.

**What it does not establish.** It does not read text on a background it shares with an icon or an
image inside the same box — a visible border or glyph anywhere in the box can carry the ratio for
invisible text in that same box, which is why text-bearing leaf elements, not their containers, are
what the entries measure. It says nothing about hover, focus or disabled variants, nothing about
animation mid-flight, and nothing about whether a legible interface is a good one. It measures at
`devicePixelRatio` 1 and a 1280×900 viewport, which is what `UI()` from §15 creates.

```python
#PX-BEGIN
import base64
PX_AA=4.5
PX_LARGE=3.0
PX_UI=3.0
PX_INSET=2
PX_MINPX=2
PX_RING=6
PX_ENUM="""() => {
  const INTER="button,a[href],input,select,textarea,summary,[role=button],[role=link],[role=tab],[onclick]";
  const own=(e)=>{let s="";for (const n of e.childNodes) if (n.nodeType===3) s+=n.nodeValue;
                  return s.replace(/\\s+/g," ").trim()};
  const els=[], skipped=[];
  for (const e of document.querySelectorAll("body *")) {
    const t=e.tagName;
    if (t==="SCRIPT"||t==="STYLE"||t==="NOSCRIPT"||t==="TEMPLATE") continue;
    if (e.namespaceURI && e.namespaceURI.indexOf("svg")>=0) continue;
    const ot=own(e), inter=e.matches(INTER);
    if (!ot && !inter) continue;
    const cs=getComputedStyle(e), r=e.getBoundingClientRect(), oe=e.closest("[data-testid]");
    const rec={tag:t.toLowerCase(), testid:e.getAttribute("data-testid")||null,
      owner:oe?oe.getAttribute("data-testid"):null,
      text:(ot||e.getAttribute("aria-label")||e.value||e.placeholder||"").replace(/\\s+/g," ").trim().slice(0,48),
      href:e.getAttribute("href")||null, interactive:inter, hasText:!!ot,
      x:r.x+window.scrollX, y:r.y+window.scrollY, w:r.width, h:r.height,
      fontSize:parseFloat(cs.fontSize)||0, fontWeight:parseInt(cs.fontWeight)||400};
    let why=null;
    if (cs.display==="none") why="display-none";
    else if (cs.visibility!=="visible") why="visibility-"+cs.visibility;
    else if (e.getAttribute("aria-hidden")==="true") why="aria-hidden";
    else if (e.closest("[hidden],[aria-hidden=true]")) why="hidden-ancestor";
    else if (r.width<1||r.height<1) why="zero-box";
    if (!why && r.bottom>0 && r.top<window.innerHeight && r.right>0 && r.left<window.innerWidth) {
      const cx=Math.min(window.innerWidth-1,Math.max(0,r.left+r.width/2));
      const cy=Math.min(window.innerHeight-1,Math.max(0,r.top+r.height/2));
      const top=document.elementFromPoint(cx,cy);
      if (top && top!==e && !e.contains(top) && !top.contains(e)) why="occluded-by-"+top.tagName.toLowerCase();
    }
    if (why) { skipped.push(Object.assign({why:why},rec)); continue; }
    els.push(rec);
  }
  return {els:els, skipped:skipped};
}"""
PX_READ="""async (a) => {
  const img=new Image();
  img.src="data:image/png;base64,"+a.b64;
  await img.decode();
  const c=document.createElement("canvas");
  c.width=img.naturalWidth; c.height=img.naturalHeight;
  const g=c.getContext("2d",{willReadFrequently:true});
  g.drawImage(img,0,0);
  const dpr=window.devicePixelRatio||1, W=img.naturalWidth, H=img.naturalHeight;
  const hist=(x0,y0,w,h,skip)=>{
    x0=Math.max(0,Math.min(W-1,Math.round(x0))); y0=Math.max(0,Math.min(H-1,Math.round(y0)));
    w=Math.max(1,Math.min(W-x0,Math.round(w))); h=Math.max(1,Math.min(H-y0,Math.round(h)));
    const d=g.getImageData(x0,y0,w,h).data, m=new Map(); let n=0;
    for (let yy=0; yy<h; yy++) for (let xx=0; xx<w; xx++) {
      if (skip) {
        const ax=x0+xx, ay=y0+yy;
        if (ax>=skip[0] && ax<skip[0]+skip[2] && ay>=skip[1] && ay<skip[1]+skip[3]) continue;
      }
      const i=((yy*w)+xx)*4, k=(d[i]<<16)|(d[i+1]<<8)|d[i+2];
      m.set(k,(m.get(k)||0)+1); n++;
    }
    return {n:n, hist:[...m.entries()].sort((p,q)=>q[1]-p[1]).slice(0,96)};
  };
  const out=[];
  for (const b of a.boxes) {
    const ins=Math.max(0,Math.min(a.inset,Math.floor((b.w-1)/2),Math.floor((b.h-1)/2)));
    const bx=b.x*dpr, by=b.y*dpr, bw=b.w*dpr, bh=b.h*dpr, iv=ins*dpr, rg=a.ring*dpr;
    out.push({inset:ins,
      inner:hist(bx+iv,by+iv,bw-2*iv,bh-2*iv,null),
      full:hist(bx,by,bw,bh,null),
      ring:hist(bx-rg,by-rg,bw+2*rg,bh+2*rg,
                [Math.max(0,Math.round(bx)),Math.max(0,Math.round(by)),Math.round(bw),Math.round(bh)])});
  }
  return out;
}"""
def PX_CSS(k):
    return "rgb(%d, %d, %d)"%((k>>16)&255,(k>>8)&255,k&255)
def PX_MAX(h,ref):
    best=1.0; bk=None
    for k,c in h:
        if c<PX_MINPX: continue
        rr=RATIO(PX_CSS(k),PX_CSS(ref))
        if rr>best: best=rr; bk=k
    return best,bk
def PX_SCAN(pg,surface=""):
    pg.wait_for_timeout(250)
    e=pg.evaluate(PX_ENUM); els=e["els"]
    sk=[dict(s,surface=surface) for s in e["skipped"]]
    if not els: return [],sk
    b64=base64.b64encode(pg.screenshot(full_page=True)).decode()
    px=pg.evaluate(PX_READ,{"b64":b64,"boxes":els,"inset":PX_INSET,"ring":PX_RING})
    rows=[]
    for el,s in zip(els,px):
        ih=s["inner"]["hist"]; bg=ih[0][0] if ih else None
        distinct=len([1 for k,c in ih if c>=PX_MINPX])
        mc,ink=PX_MAX(ih,bg) if bg is not None else (1.0,None)
        rh=s["ring"]["hist"]; sur=rh[0][0] if rh else None
        sal,_=PX_MAX(s["full"]["hist"],sur) if sur is not None else (1.0,None)
        big=el["fontSize"]>=24 or (el["fontSize"]>=18.66 and el["fontWeight"]>=700)
        if el["hasText"]:
            need=PX_LARGE if big else PX_AA; got=round(mc,2); kind="text"
        else:
            need=PX_UI; got=round(sal,2); kind="control"
        v="OK"
        if bg is None: v="NO-PIXELS"
        elif el["hasText"] and distinct<2: v="NO-INK"
        elif got<need: v=("LOW-CONTRAST" if el["hasText"] else "FLAT-AGAINST-PAGE")
        rows.append({"surface":surface,"testid":el["testid"],"owner":el["owner"],"tag":el["tag"],
            "text":el["text"],"href":el["href"],"kind":kind,"interactive":el["interactive"],
            "verdict":v,"measured":got,"need":need,"ratio_text":round(mc,2),"salience":round(sal,2),
            "distinct":distinct,"ink":None if ink is None else PX_CSS(ink),
            "bg":None if bg is None else PX_CSS(bg),"surround":None if sur is None else PX_CSS(sur),
            "inset":s["inset"],"box":[round(el["x"]),round(el["y"]),round(el["w"]),round(el["h"])]})
    return rows,sk
def PX_FAILS(rows):
    return [{k:r[k] for k in ("surface","testid","tag","text","kind","verdict","measured","need","ratio_text","salience","ink","bg","surround","distinct","box")} for r in rows if r["verdict"]!="OK"]
def PX_SKIPS(sk):
    return [[s.get("surface"),s.get("testid"),s.get("text"),s["why"],s["interactive"]] for s in sk]
def PX_FIND(rows,pat):
    return [r for r in rows if re.search(pat,(r["text"] or "")+" "+(r["href"] or ""),re.I)]
def PX_ROUTE(rows,pat,href):
    out=[]
    for r in rows:
        if not r["interactive"]: continue
        if re.search(pat,r["text"] or "",re.I) or re.search(href,r["href"] or "",re.I): out.append(r)
    return out
def PX_COVER(rows,surface,tid):
    for r in rows:
        if r["surface"]==surface and (r["testid"]==tid or r["owner"]==tid): return True
    return False
PX_SIGNIN="sign ?in|log ?in|sign-in|log-in"
PX_SIGNUP="sign ?up|creat.*account|register|join"
PX_SURF=["/ signed out","/login signed out","/signup signed out","/lookup signed out",
  "/ signed out, results","signed out, slot clicked","/login, bad credentials",
  "/lookup, unknown reference","/ signed in, results","booking form, signed in",
  "confirmation, signed in","/lookup, reservation shown"]
PX_REQUIRED={
 "/ signed out":["restaurant-select","date-input","party-size-input","search-button"],
 "/login signed out":["login-email","login-password","login-submit"],
 "/signup signed out":["signup-email","signup-password","signup-display-name","signup-submit"],
 "/lookup signed out":["lookup-reference-input","lookup-submit"],
 "/ signed out, results":["availability-grid","search-button"],
 "/login, bad credentials":["auth-error"],
 "/lookup, unknown reference":["reservation-error"],
 "/ signed in, results":["current-user","logout-button","availability-grid"],
 "booking form, signed in":["booking-form","booking-party-size","booking-summary","booking-submit"],
 "confirmation, signed in":["confirmation-reference","confirmation-details"],
 "/lookup, reservation shown":["reservation-detail","reservation-status","reservation-cancel-button"]}
def PX_TOUR(pg,ref):
    rows=[]; sk=[]; cen={}
    def g(n):
        r,s=PX_SCAN(pg,n); rows.extend(r); sk.extend(s); cen[n]=len(r)
    for p in ["/","/login","/signup","/lookup"]:
        pg.goto(BASE+p,wait_until="load"); g(p+" signed out")
    SEARCH_UI(pg,"r_anker",F,4); g("/ signed out, results")
    c=CELL(pg,"t_2","19:00")
    if c: c.click(); pg.wait_for_timeout(800)
    if SEE(pg,"booking-submit"): CLICK(pg,"booking-submit"); pg.wait_for_timeout(1400)
    g("signed out, slot clicked")
    pg.goto(BASE+"/login",wait_until="load")
    FILL(pg,"login-email",ADA["email"]); FILL(pg,"login-password","wrong password")
    CLICK(pg,"login-submit"); pg.wait_for_timeout(900); g("/login, bad credentials")
    pg.goto(BASE+"/lookup",wait_until="load")
    FILL(pg,"lookup-reference-input","NO-SUCH-REFERENCE"); CLICK(pg,"lookup-submit")
    pg.wait_for_timeout(1000); g("/lookup, unknown reference")
    LOGIN_UI(pg); SEARCH_UI(pg,"r_anker",F,4); g("/ signed in, results")
    CLICK(pg,"slot-t_2-19:00"); pg.wait_for_timeout(800); g("booking form, signed in")
    CLICK(pg,"booking-submit"); pg.wait_for_timeout(1600); g("confirmation, signed in")
    pg.goto(BASE+"/lookup",wait_until="load")
    FILL(pg,"lookup-reference-input",ref); CLICK(pg,"lookup-submit")
    pg.wait_for_timeout(1000); g("/lookup, reservation shown")
    return rows,sk,cen
#PX-END
```

## §18 The contrast thresholds, declared

The spec gives no figure. It says "text and controls need sufficient contrast" and "Primary actions
must be easy to identify". **`@scribe` picked the numbers below; the spec did not supply them**, and
this paragraph exists so no later reader mistakes them for quotation.

| Measured on | Threshold | Where the number comes from |
|---|---|---|
| Text under 24px, and under 18.66px bold | **4.5:1** | WCAG 2.1 AA, SC 1.4.3 (normal text) |
| Text 24px and over, or 18.66px and over at weight ≥ 700 | **3.0:1** | WCAG 2.1 AA, SC 1.4.3's own large-text allowance |
| An interactive element with no text of its own, against the page around it | **3.0:1** | WCAG 2.1 AA, SC 1.4.11 (non-text contrast) |
| A primary action's whole box, against the page around it | **3.0:1** | WCAG 2.1 AA, SC 1.4.11, applied to the one property §16 had routed to human judgement |

**On what basis.** WCAG 2.1 AA is the only widely published numeric definition of "sufficient"; this
file already used 4.5:1 in S-57 without saying it had chosen; and a declared number a run can fail is
worth more than a faithful quotation of "sufficient", which settles nothing. If `@registrar` prefers
a different figure, it is one line in this table and a new entry — not an edit to any entry below.

**These entries are not declared human-judged.** A human already judged this interface; that is how
the defect arrived. The §16 "Declared human-judged" table lists "Primary actions are easy to
identify" and that row stands unedited — S-71 does not replace it. S-71 settles a **floor** under it:
a primary action that is not painted distinguishably from the page cannot be easy to identify. Whether
a legible primary action is also *salient* remains the human's. A floor that can fail is not a
substitute for judgement and is not offered as one.

## Replacement and new entries — rendered appearance (§UI quality, §Product and visual direction)

### S-65: The rendered-raster instrument rejects a control that is invisible in pixels but passes every DOM-level assertion.
Check: `$PWPY -c "$WPX"'
SETUP()
INJ="""()=>{
  const mk=(id,css,label)=>{const b=document.createElement("button");
    b.setAttribute("data-testid",id); b.textContent=label;
    b.style.cssText="display:inline-block;margin:4px;padding:6px 10px;font-size:14px;border:none;background:#ffffff;"+css;
    document.body.appendChild(b); return b};
  mk("px-probe-transparent","color:transparent","Probe sign in");
  mk("px-probe-opacity","opacity:0;color:#111111","Probe create account");
  mk("px-probe-samecolour","color:#ffffff","Probe ghost");
  mk("px-probe-visible","color:#111111","Probe visible");
  return true}"""
NAMES=[("px-probe-transparent","Probe sign in"),("px-probe-opacity","Probe create account"),
       ("px-probe-samecolour","Probe ghost"),("px-probe-visible","Probe visible")]
INVIS=["px-probe-transparent","px-probe-opacity","px-probe-samecolour"]
def f(pg):
    pg.goto(BASE+"/",wait_until="load")
    pg.evaluate(INJ)
    dom={}
    for t,_n in NAMES:
        dom[t]=pg.evaluate("""(t)=>{const e=document.querySelector("[data-testid="+JSON.stringify(t)+"]");
            const r=e.getBoundingClientRect(),c=getComputedStyle(e);
            return {box:[Math.round(r.width),Math.round(r.height)],display:c.display,
                    visibility:c.visibility,text:e.textContent.trim()}}""",t)
    clicks={}
    for t,n in NAMES:
        try:
            pg.get_by_role("button",name=n).first.click(timeout=4000); clicks[t]="clicked"
        except Exception as ex:
            clicks[t]="failed: "+type(ex).__name__
    rows,sk=PX_SCAN(pg,"/ signed out + injected probes")
    px={r["testid"]:[r["verdict"],r["measured"],r["need"],r["distinct"],r["ink"],r["bg"]]
        for r in rows if (r["testid"] or "").startswith("px-probe")}
    skp=[s for s in PX_SKIPS(sk) if (s[1] or "").startswith("px-probe")]
    return dom,clicks,px,skp
dom,clicks,px,skp=UI(f,route=None)
print("DOM-LEVEL PREDICATES:",json.dumps(dom,sort_keys=True))
print("CLICK BY ACCESSIBLE NAME:",json.dumps(clicks,sort_keys=True))
print("RENDERED-PIXEL VERDICTS:",json.dumps(px,sort_keys=True))
print("PROBES EXCLUDED FROM MEASUREMENT:",json.dumps(skp,sort_keys=True))
assert not skp,"a probe was excluded instead of measured, so this run proves nothing: %r"%skp
for t,_n in NAMES:
    d=dom[t]
    assert d["box"][0]>0 and d["box"][1]>0,"%s has an empty box, so it is not the defect class under test: %r"%(t,d)
    assert d["display"]!="none","%s is display:none, so it is not the defect class under test: %r"%(t,d)
    assert d["visibility"]=="visible","%s is not visibility:visible, so it is not the defect class under test: %r"%(t,d)
    assert d["text"],"%s carries no text, so it is not the defect class under test: %r"%(t,d)
    assert clicks[t]=="clicked","a click by accessible name did not succeed on %s: %r"%(t,clicks[t])
for t in INVIS:
    assert t in px,"%s was never measured: %r"%(t,sorted(px))
    assert px[t][0]!="OK","the instrument passed %s, which no eye can see: %r"%(t,px[t])
assert px["px-probe-visible"][0]=="OK","the instrument rejected a plainly legible control, so it is too harsh to settle anything: %r"%px["px-probe-visible"]
print("PASS instrument rejects 3 of 3 pixel-invisible probes and accepts 1 of 1 legible probe, while non-zero box, display, visibility, text content and click-by-accessible-name all succeed on all four")'`
Passes when: prints the four DOM records, the four click outcomes, the four pixel verdicts, an empty exclusion list, and finally `PASS instrument rejects 3 of 3 …`. **This entry is about the instrument, not the service.** It is first because every entry after it is worthless if the instrument cannot fail: it injects three controls that are invisible in pixels by three different mechanisms — `color: transparent`, `opacity: 0`, foreground equal to background — and requires the raster to reject all three *while* every DOM-level predicate the human named passes on them, and requires it to accept a fourth that differs only in being legible. A run of this that prints `PASS` is the evidence that S-66 to S-71 mean something. **What it does not establish:** that the three mechanisms are the only ones, or that the instrument catches a fourth nobody has thought of.
Status: unclaimed

### S-66: Signed out, the home page paints a legible route to sign in and a legible route to create an account.
Check: `$PWPY -c "$WPX"'
SETUP()
def f(pg):
    pg.goto(BASE+"/",wait_until="load")
    rows,sk=PX_SCAN(pg,"/ signed out")
    return rows,PX_SKIPS(sk)
rows,sk=UI(f,route=None)
si=PX_ROUTE(rows,PX_SIGNIN,"^/?login")
su=PX_ROUTE(rows,PX_SIGNUP,"^/?signup")
def shew(rs):
    return [[r["testid"],r["tag"],r["text"],r["href"],r["verdict"],r["measured"],r["need"],r["ink"],r["bg"],r["box"]] for r in rs]
print("MEASURED ON / SIGNED OUT:",len(rows))
print("EXCLUDED FROM MEASUREMENT:",json.dumps(sk,sort_keys=True))
print("SIGN-IN ROUTES:",json.dumps(shew(si),sort_keys=True))
print("CREATE-ACCOUNT ROUTES:",json.dumps(shew(su),sort_keys=True))
assert rows,"nothing was measured on / while signed out, so this run settles nothing"
assert si,"no interactive sign-in route was measured on / while signed out; excluded: %s"%json.dumps(sk,sort_keys=True)
assert su,"no interactive create-account route was measured on / while signed out; excluded: %s"%json.dumps(sk,sort_keys=True)
assert [r for r in si if r["verdict"]=="OK"],"a sign-in route exists on / but none of them is legible in rendered pixels: %s"%json.dumps(PX_FAILS(si),sort_keys=True)
assert [r for r in su if r["verdict"]=="OK"],"a create-account route exists on / but none of them is legible in rendered pixels: %s"%json.dumps(PX_FAILS(su),sort_keys=True)
print("PASS signed out, / paints at least one legible sign-in route and one legible create-account route")'`
Passes when: exits 0 and prints `PASS signed out, / paints at least one legible …`, with the candidate tables above it. This is the reported defect, stated as a claim. A route counts only if it is **interactive**, **measured** (not in the exclusion list), and **`OK` on painted pixels** at the §18 threshold; presence, a non-zero box, `display`, `visibility` and a successful click by accessible name are each insufficient on their own and in combination — S-65 is the proof of that. A route is recognised by its own text matching `sign in`/`log in` or `sign up`/`create account`/`register`, or by an `href` resolving to `/login` or `/signup`, so a button opening a modal counts and a link whose label is an icon alone does not. **What it does not establish:** that the route is placed where a visitor will look, or that one route is enough.
Status: unclaimed

### S-67: Every text-bearing and interactive element measured across twelve named surfaces meets the declared rendered-pixel threshold.
Check: `$PWPY -c "$WPX"'
ta,_=SETUP()
pre=OK(BOOK(ta,F+"T20:00","s67-seed",table_id="t_3",ps=4),201)
rows,sk,cen=UI(lambda pg:PX_TOUR(pg,pre["reference"]),route=None)
bad=PX_FAILS(rows)
print("CENSUS PER SURFACE:",json.dumps(cen,indent=1,sort_keys=True))
print("EXCLUDED FROM MEASUREMENT:",json.dumps(PX_SKIPS(sk),indent=1,sort_keys=True))
print("TOTAL MEASURED:",len(rows),"ACROSS SURFACES:",len(cen))
assert len(cen)==len(PX_SURF),"the tour reached %d surfaces, not the %d it names: %r"%(len(cen),len(PX_SURF),sorted(cen))
assert not bad,"%d of %d measured elements are below the declared rendered-pixel threshold:\n%s"%(len(bad),len(rows),json.dumps(bad,indent=1,sort_keys=True))
print("PASS",len(rows),"elements measured on",len(cen),"surfaces, none below threshold")'`
Passes when: exits 0, prints a per-surface census and a full exclusion list, and ends `PASS <n> elements measured on 12 surfaces, none below threshold`. The twelve surfaces are fixed in `PX_SURF`: `/`, `/login`, `/signup` and `/lookup` **signed out**; `/` signed out with results; **signed out after clicking an available slot**; `/login` after a refused login; `/lookup` after an unknown reference; `/` signed in with results; the booking form; the confirmation; and `/lookup` showing a real reservation. Signed-out surfaces are four of the twelve because the reported defect is only visible signed out. **Every text-bearing and every interactive element on each surface is measured, not a named sample** — that is the difference between this and S-57. A failing run quotes each element with its ratio, its ink and background colours as painted, and its box. **What it does not establish:** that twelve surfaces are every surface. Enumerating all reachable states is the genuinely hard part and this entry does not claim to have done it — the list is declared, not complete; the 375px viewport is not in it, nor are hover, focus and disabled variants, nor `no-slots`, `booking-error` or `booking-uncertain`. Those are named here as known gaps rather than implied to be covered.
Status: unclaimed

### S-68: The sweep's census is non-empty on every surface and includes every control the spec names there.
Check: `$PWPY -c "$WPX"'
ta,_=SETUP()
pre=OK(BOOK(ta,F+"T20:00","s68-seed",table_id="t_3",ps=4),201)
rows,sk,cen=UI(lambda pg:PX_TOUR(pg,pre["reference"]),route=None)
print("CENSUS PER SURFACE:",json.dumps(cen,indent=1,sort_keys=True))
print("EXCLUDED FROM MEASUREMENT:",json.dumps(PX_SKIPS(sk),indent=1,sort_keys=True))
thin=sorted([s for s in cen if cen[s]<6])
missing=[]
for s in sorted(PX_REQUIRED):
    for t in PX_REQUIRED[s]:
        if not PX_COVER(rows,s,t): missing.append([s,t])
si=PX_ROUTE([r for r in rows if r["surface"]=="/ signed out"],PX_SIGNIN,"^/?login")
su=PX_ROUTE([r for r in rows if r["surface"]=="/ signed out"],PX_SIGNUP,"^/?signup")
print("SURFACES UNDER 6 MEASURED ELEMENTS:",json.dumps(thin,sort_keys=True))
print("SPEC CONTROLS NOT MEASURED ON THEIR SURFACE:",json.dumps(missing,sort_keys=True))
print("TOTAL MEASURED:",len(rows))
assert len(cen)==len(PX_SURF),"the tour reached %d surfaces, not the %d it names: %r"%(len(cen),len(PX_SURF),sorted(cen))
assert not thin,"a surface measured fewer than 6 elements, so a pass there would be close to vacuous: %r"%[[s,cen[s]] for s in thin]
assert not missing,"controls the spec names were never measured on their surface: %s"%json.dumps(missing,sort_keys=True)
assert si and su,"the signed-out home census contains no sign-in route or no create-account route: signin=%d signup=%d"%(len(si),len(su))
assert len(rows)>=60,"only %d elements were measured in total, below the declared floor of 60"%len(rows)
print("PASS census non-vacuous:",len(rows),"elements,",len(cen),"surfaces, all",sum(len(PX_REQUIRED[s]) for s in PX_REQUIRED),"named spec controls measured")'`
Passes when: exits 0 and ends `PASS census non-vacuous: …`, having printed the per-surface census, the exclusion list, and empty lists for thin surfaces and missing controls. **This entry exists because S-67 passes vacuously if the enumeration finds nothing** — that is C-2's defect shape, and an empty sweep prints the same `PASS` as a complete one. It therefore fixes three floors, all declared by `@scribe` rather than taken from the spec: at least 6 measured elements per surface, at least 60 in total, and every `data-testid` the spec names for a surface measured **either on that element or on a descendant of it** (so a container whose text lives in a child still counts). The sign-in and create-account routes must also be in the signed-out home census, which closes the door left open by the occlusion exclusion in §17: a control hidden under an overlay is excluded from measurement, and exclusion fails this entry rather than passing S-67 quietly. **What it does not establish:** that 6, 60 and the named list are the right floors, or that an interface measuring 61 elements has been meaningfully covered.
Status: unclaimed

### S-69: No measured element paints nothing, and no named control is excluded for having no box.
Check: `$PWPY -c "$WPX"'
ta,_=SETUP()
pre=OK(BOOK(ta,F+"T20:00","s69-seed",table_id="t_3",ps=4),201)
rows,sk,cen=UI(lambda pg:PX_TOUR(pg,pre["reference"]),route=None)
blank=[r for r in rows if r["verdict"] in ("NO-INK","NO-PIXELS")]
flat=[r for r in rows if r["verdict"]=="FLAT-AGAINST-PAGE"]
boxless=[s for s in sk if s["why"]=="zero-box" and (s["interactive"] or s["hasText"]) and (s["text"] or "")]
print("CENSUS PER SURFACE:",json.dumps(cen,indent=1,sort_keys=True))
print("ELEMENTS WHOSE BOX HOLDS ONE COLOUR:",json.dumps(PX_FAILS(blank),indent=1,sort_keys=True))
print("CONTROLS FLAT AGAINST THE PAGE:",json.dumps(PX_FAILS(flat),indent=1,sort_keys=True))
print("NAMED CONTROLS EXCLUDED FOR HAVING NO BOX:",json.dumps(PX_SKIPS(boxless),indent=1,sort_keys=True))
assert len(cen)==len(PX_SURF),"the tour reached %d surfaces, not the %d it names: %r"%(len(cen),len(PX_SURF),sorted(cen))
assert rows,"nothing was measured, so this run settles nothing"
assert not blank,"%d measured elements paint a single colour across their whole box, so nothing of them is on screen: %s"%(len(blank),json.dumps(PX_FAILS(blank),indent=1,sort_keys=True))
assert not flat,"%d interactive elements are under 3.0:1 against the page around them across their whole box: %s"%(len(flat),json.dumps(PX_FAILS(flat),indent=1,sort_keys=True))
assert not boxless,"a named interactive or text-bearing element was excluded for having no box: %s"%json.dumps(PX_SKIPS(boxless),indent=1,sort_keys=True)
print("PASS",len(rows),"elements measured, 0 paint a single colour, 0 controls flat against the page, 0 named controls boxless")'`
Passes when: exits 0 and ends `PASS <n> elements measured, 0 paint a single colour, …`. This isolates the exact failure the human saw from the milder one. `LOW-CONTRAST` is text that is too faint to read; **`NO-INK` is text that was never painted at all**, which is what `color: transparent` and `opacity: 0` produce and what no entry before S-65 could see. It is separated from S-67 so that a verdict distinguishes "faint" from "absent" without a reader having to parse the failure list. It also covers two exclusion paths rather than only the measured set: an interactive element with no text of its own must be distinguishable from the page it sits on, and a named control reduced to a zero-size box fails here instead of being quietly excluded. **What it does not establish:** anything about elements excluded as occluded, `display:none` or `aria-hidden` — those remain in the printed exclusion list for a reader to check, and S-68 is what forces the ones that matter back into the measured set.
Status: unclaimed

### S-70: The error that tells a signed-out visitor to sign in is reached with a legibly painted route to signing in.
Check: `$PWPY -c "$WPX"'
SETUP()
def f(pg):
    SEARCH_UI(pg,"r_anker",F,4)
    c=CELL(pg,"t_2","19:00")
    assert c,"no available cell at 19:00 to click while signed out, so the reported path cannot be reproduced"
    c.click(); pg.wait_for_timeout(800)
    if SEE(pg,"booking-submit"): CLICK(pg,"booking-submit"); pg.wait_for_timeout(1400)
    err=TXT(pg,"auth-error")
    url=pg.url.replace(BASE,"") or "/"
    rows,sk=PX_SCAN(pg,"signed out, slot clicked")
    return rows,PX_SKIPS(sk),err,url
rows,sk,err,url=UI(f,route=None)
si=PX_ROUTE(rows,PX_SIGNIN,"^/?login")
su=PX_ROUTE(rows,PX_SIGNUP,"^/?signup")
ok=[r for r in si+su if r["verdict"]=="OK"]
form=[r for r in rows if r["testid"] in ("login-email","login-password","login-submit")]
formok=[r for r in form if r["verdict"]=="OK"]
print("URL AFTER CLICKING A SLOT WHILE SIGNED OUT:",url)
print("AUTH-ERROR TEXT:",json.dumps(err))
print("MEASURED ON THIS SURFACE:",len(rows))
print("EXCLUDED FROM MEASUREMENT:",json.dumps(sk,sort_keys=True))
print("ROUTES TO SIGNING IN ON THIS SURFACE:",json.dumps([[r["testid"],r["tag"],r["text"],r["href"],r["verdict"],r["measured"],r["need"],r["ink"],r["bg"]] for r in si+su],sort_keys=True))
print("LOGIN FORM ON THIS SURFACE:",json.dumps([[r["testid"],r["verdict"],r["measured"],r["need"]] for r in form],sort_keys=True))
assert rows,"nothing was measured on the surface reached by clicking a slot while signed out"
assert err or url.rstrip("/").endswith("/login"),"clicking a slot while signed out neither showed auth-error nor navigated to /login, so the reported path did not occur: url=%r"%url
if url.rstrip("/").endswith("/login"):
    assert len(formok)==3,"the click navigated to /login but the login form is not legible in rendered pixels: %s"%json.dumps(PX_FAILS(form),sort_keys=True)
    print("PASS the slot click delivered the visitor to a legibly painted /login form")
else:
    assert si or su,"the signed-out visitor is told to sign in with no interactive route to do so measured on the surface; excluded: %s"%json.dumps(sk,sort_keys=True)
    assert ok,"a route to signing in is present on the error surface but none of them is legible in rendered pixels: %s"%json.dumps(PX_FAILS(si+su),sort_keys=True)
    print("PASS the error surface paints a legible route to signing in:",json.dumps([[r["testid"],r["text"],r["href"],r["measured"]] for r in ok],sort_keys=True))
'`
Passes when: exits 0 and ends with one of the two `PASS …` lines, having printed the URL, the `auth-error` text, the census, the exclusion list and the route table. The human's second sentence is a separate claim from the first: the header is one surface, the state after clicking a slot is another, and a visitor stranded there is stranded whatever the header does. S-36 already permits either outcome — an `auth-error` in place, or a navigation to `/login` — so this entry branches on which happened and requires painted legibility in both: a route on the error surface, or an actually legible login form at the destination. **What it does not establish:** that the error text itself names the route, or that the route is reachable without scrolling.
Status: unclaimed

### S-71: Each primary action is painted distinguishably from the page around it, at 3.0:1 or better.
Check: `$PWPY -c "$WPX"'
SETUP()
PRIMARY=[["/ signed out","/","search-button"],["/login signed out","/login","login-submit"],
         ["/signup signed out","/signup","signup-submit"],["/lookup signed out","/lookup","lookup-submit"]]
def f(pg):
    rows=[]
    for name,path,_t in PRIMARY:
        pg.goto(BASE+path,wait_until="load")
        r,_s=PX_SCAN(pg,name); rows.extend(r)
    LOGIN_UI(pg); SEARCH_UI(pg,"r_anker",F,4)
    CLICK(pg,"slot-t_2-19:00"); pg.wait_for_timeout(800)
    r,_s=PX_SCAN(pg,"booking form, signed in"); rows.extend(r)
    return rows
rows=UI(f,route=None)
want=[[n,t] for n,_p,t in PRIMARY]+[["booking form, signed in","booking-submit"]]
found=[]; absent=[]; dull=[]
for n,t in want:
    hit=[r for r in rows if r["surface"]==n and r["testid"]==t]
    if not hit: absent.append([n,t]); continue
    r=hit[0]
    found.append([n,t,r["salience"],r["ratio_text"],r["kind"],r["bg"],r["surround"],r["ink"]])
    if r["salience"]<PX_UI: dull.append([n,t,r["salience"],r["bg"],r["surround"]])
print("PRIMARY ACTIONS AS PAINTED:",json.dumps(found,indent=1,sort_keys=True))
print("NOT MEASURED:",json.dumps(absent,sort_keys=True))
print("UNDER 3.0:1 AGAINST THE PAGE:",json.dumps(dull,sort_keys=True))
assert not absent,"a primary action was never measured on its surface: %s"%json.dumps(absent,sort_keys=True)
assert not dull,"a primary action is under the declared 3.0:1 floor against the page immediately around it: %s"%json.dumps(dull,sort_keys=True)
print("PASS",len(found),"primary actions each paint at 3.0:1 or better against their surroundings")'`
Passes when: exits 0 and ends `PASS 5 primary actions each paint at 3.0:1 or better …`, with the measured figures above it. Five primary actions are named: `search-button`, `login-submit`, `signup-submit`, `lookup-submit`, `booking-submit`. The measurement is the highest contrast between any colour painted inside the control's full box — fill, border or glyph — and the dominant colour of a 6-pixel ring just outside it, so a filled button passes on its fill and a flat text button passes on its letters, while a control that paints nothing distinguishable fails at 1.0. **This is a floor under a property §16 routed to human judgement, and it does not replace that routing** — see §18. **What it does not establish:** that the action is the *most* salient thing on its surface, that it is positioned where a diner will look, or that five is the full set of primary actions.
Status: unclaimed

### S-72: After the fix, the harness command in the defect report passes suites 1 and 2 against stage-2/.
Check: `cd /Users/aashanjaved/dark-factory-wearedevs && ./.venv/bin/python -m harness run --track tablekeeper --repo /Users/aashanjaved/band-work/result --stage 2 --out /Users/aashanjaved/band-work/checks/fix-$(date +%s); echo "harness exit $?"`
Passes when: the harness exits 0, reporting zero failures and zero errors for **both** stage 1 and stage 2, and `harness exit 0` prints. This is the human's command, byte for byte as the defect report gave it, with the exit code echoed so a verdict can quote it. A printed failure for the stage-3 probe is expected and is not this run's exit code, per `harness/cli.py:459`. **It deliberately does not bracket the working tree.** Two `docs/` paths are dirty at `f63f657` and belong to nobody in this band; a clean-tree assertion here would fail for a reason that has nothing to do with the fix. That is ERRATA 2 / Defect 5 unresolved rather than discharged, and it is why S-73 exists beside this entry: this one proves the human's command passes where the human runs it, and S-73 proves the revision passes where nothing can move underneath it. **What it does not establish:** which revision was tested — the harness reads a working tree, so a verdict for this entry must name the revision separately and assert the tree held only those two `docs/` paths.
Status: unclaimed

### S-73: The same suites pass in grading mode against an immutable clone of the fixed revision.
Check: `SRC=/Users/aashanjaved/band-work/result; REV="${TK_REV:-$(git -C "$SRC" rev-parse HEAD)}"; C="$SRC/.auditor-clones/s73"; rm -rf "$C" && git clone -q --no-local "$SRC" "$C" && git -C "$C" checkout -q "$REV" && test -z "$(git -C "$C" status --porcelain)" || { echo "CLONE NOT CLEAN"; exit 1; }; before=$(git -C "$C" rev-parse HEAD); echo "AUDITING $before"; cd /Users/aashanjaved/dark-factory-wearedevs && ./.venv/bin/python -m harness run --track tablekeeper --repo "$C" --stage 2 --mode isolated --out /Users/aashanjaved/band-work/checks/s73-$(date +%s); r=$?; echo "harness exit $r"; test $r -eq 0 && test -z "$(git -C "$C" status --porcelain)" && test "$(git -C "$C" rev-parse HEAD)" = "$before" && echo "SUITES 1 AND 2 PASS IN ISOLATED MODE AT $before"`
Passes when: exits 0 and prints `AUDITING <revision>`, the harness summary with zero failures and zero errors for both stages, `harness exit 0`, then `SUITES 1 AND 2 PASS IN ISOLATED MODE AT <the same revision>`. `--mode isolated` is required because the harness defaults to `host`, where it warns that outbound is not blocked and that a submission must never be scored from that mode — ERRATA 1 / Defect 2, which cost C-140 and C-141 their meaning. `TK_REV` names the revision; unset, it audits the current `HEAD` of the source repository. `.auditor-clones/` is gitignored, so making the clone cannot dirty the source tree. **What it does not establish:** anything about the live working tree, which is the point — the clone is the thing audited, per §10.
Status: unclaimed

### S-74: The fix changed nothing under stage-1/.
Check: `SRC=/Users/aashanjaved/band-work/result; BASE_REV="${TK_BASE_REV:-f63f657d4839f3a9106c9956b4136ecbd3072f53}"; REV="${TK_REV:-$(git -C "$SRC" rev-parse HEAD)}"; echo "BASELINE $BASE_REV"; echo "FIXED    $(git -C "$SRC" rev-parse "$REV")"; git -C "$SRC" merge-base --is-ancestor "$BASE_REV" "$REV" || { echo "BASELINE IS NOT AN ANCESTOR OF THE FIX"; exit 1; }; d=$(git -C "$SRC" diff --name-only "$BASE_REV" "$REV" -- stage-1/); test -z "$d" && echo "STAGE-1 UNCHANGED" || { echo "STAGE-1 CHANGED:"; echo "$d"; exit 1; }; echo "CHANGED BY THE FIX:"; git -C "$SRC" diff --name-only "$BASE_REV" "$REV"`
Passes when: exits 0 and prints `BASELINE f63f657…`, `FIXED <revision>`, then `STAGE-1 UNCHANGED`, then the full list of paths the fix touched. The baseline defaults to `f63f657d4839f3a9106c9956b4136ecbd3072f53`, which was `HEAD` when this entry was written; `@registrar` dispatched from `c07cb94e73adc74c2e98beb0ca87df68a234bd36`, two commits earlier, and those two commits touch only `REFUSALS.md`, so `stage-1/`, `stage-2/` and `LEDGER.md` are byte-identical across them and either baseline settles this claim identically. The ancestry assertion is there so the claim cannot be settled by comparing two unrelated commits. **What it does not establish:** that the paths the fix did touch were the right ones.
Status: unclaimed

## What these ten entries do not reach

Named here rather than left for a reader to assume covered.

| Not reached | Why not, and what it would take |
|---|---|
| The 375px viewport | `UI()` from §15 builds a 1280×900 page and the instrument measures what that page paints. A narrow-viewport sweep is a separate entry and is not written. |
| Hover, focus and disabled appearance | The raster is a still of the resting state. Measuring focus would need the instrument run after a `Tab`, which no entry here does. |
| `no-slots`, `booking-error`, `booking-uncertain` | Each needs a fixture or a fault injection the tour does not perform. S-67 reaches twelve surfaces and these three are not among them. |
| Elements excluded as occluded, `display:none` or `aria-hidden` | Printed in every exclusion list, asserted on only where S-68 names the control. A control hidden under a transparent overlay is excluded, not failed. |
| Text sharing a box with an icon or image | A visible glyph anywhere in a box can carry the ratio for invisible text in that same box. Measuring leaves rather than containers narrows this; it does not close it. |
| Whether the interface is good | Unchanged from §16. These entries make a specific class of failure impossible to pass. They say nothing else. |

---

# ERRATA 6 — four of the five declared gaps needed no fault injection, and the fifth needed one this file already performs

ERRATA 5's closing table named the 375px viewport, the disabled appearance of every button,
`no-slots`, `booking-error` and `booking-uncertain` as out of reach for S-67's tour. **That was
honest about the tour and wrong about the reach.** `@builder` named the mechanisms: `no-slots` needs
only a date on a weekday the fixture's `opening_hours` omits; the disabled appearance is the resting
state of `search-button`, `booking-submit` and `reservation-cancel-button` while a request is in
flight; and 375px is an argument to `UI()`. `booking-error` is reached by the S-45 mechanism —
another account takes the table — with no fault at all, and `booking-uncertain` by the S-46
mechanism, which this file has performed since stage 2 opened.

So the gap was mine, not the interface's. The five entries below close it. **This matters beyond
tidiness**: the disabled appearance is where `@builder` reports finding the second instance of the
reported defect's shape — a rule repainting a background and leaving the text to inherit — and no
entry in ERRATA 5 measures a disabled button, because the tour never puts one in that state.

**§17 is not touched and the ten taken entries are not touched.** S-65 to S-74 were taken by
`@registrar` at `8caa6f08`, and a Check whose text is fixed while the prelude it loads changes
underneath it is the F-11 shape §13 exists to make visible. The `#PX-BEGIN`/`#PX-END` block is
therefore left byte-identical — `sha256
ab26a7c81555b741ae1c8df94371ef7946a4e9a78dc87126cb0e1061195934b9`, 9141 bytes — and the five entries
below load a **second, additive** block.

## §19 The extended-surface helpers (`$PX2`)

Loaded after `$W` and `$PX`, never in place of either:

```sh
export PX2="$(awk '/^#PX2-BEGIN$/{f=1;next} /^#PX2-END$/{f=0} f' "$TK_REPO/LEDGER.md")"
export WPX2="$W
$PX
$PX2"
```

Confirm all three loaded:

```sh
$PWPY -c "$WPX2"'
print("WPX2 OK",BASE,PX_AA,len(PX_SURF),len(PX_CLOSED()["restaurants"][0]["opening_hours"]))'
```

`PX_CLOSED()` omits Thursday from `opening_hours`, and `F` is `2027-06-10`, a Thursday — so the
fixture's own calendar closes the searched day without a fault, a fixture edit or a clock change.
`PX_DISABLE()` sets `disabled` on **every** `<button>` in the document and returns what it touched.

**The proxy in `PX_DISABLE`, labelled per §16 rule 1.** It measures what the stylesheet paints for
the disabled state, by putting the elements into that state directly. **It does not establish that
the service enters that state during a request** — S-53 is the entry that requires a loading state at
all, and this one says nothing about when it appears. The reason not to catch it in flight is that a
check racing a request is not deterministic, and a flaky Check is worse than a narrow one. Disabling
every button rather than the three named ones is deliberate: the grid cells are buttons too, and a
rule that fails on a named button fails on an unnamed one identically.

```python
#PX2-BEGIN
PX_DIS="""()=>{
  const out=[];
  for (const b of document.querySelectorAll("button")) {
    b.disabled=true;
    out.push(b.getAttribute("data-testid")||b.textContent.replace(/\\s+/g," ").trim().slice(0,32)||"button");
  }
  return out;
}"""
def PX_DISABLE(pg):
    return pg.evaluate(PX_DIS)
def PX_CLOSED():
    return FX(restaurants=[REST(opening_hours=[{"weekday":w,"opens":"18:00","closes":"23:30"}
                                               for w in WD if w!="thu"])])
def PX_LOSE(pg,pat="**/reservations**"):
    st={"drop":True}
    def h(route):
        if route.request.method=="POST" and st["drop"]:
            st["drop"]=False
            try: route.fetch()
            except Exception: pass
            route.abort("connectionfailed"); return
        route.continue_()
    pg.route(pat,h); return st
#PX2-END
```

## New entries — the five surfaces ERRATA 5 declared out of reach

### S-75: Every button is legible while disabled, on five surfaces.
Check: `$PWPY -c "$WPX2"'
ta,_=SETUP()
pre=OK(BOOK(ta,F+"T20:00","s75-seed",table_id="t_3",ps=4),201)
def f(pg):
    rows=[]; sk=[]; cen={}; dis={}
    def g(n):
        dis[n]=PX_DISABLE(pg)
        r,s=PX_SCAN(pg,n); rows.extend(r); sk.extend(s); cen[n]=len(r)
    pg.goto(BASE+"/login",wait_until="load"); g("/login, every button disabled")
    pg.goto(BASE+"/signup",wait_until="load"); g("/signup, every button disabled")
    LOGIN_UI(pg); SEARCH_UI(pg,"r_anker",F,4); g("/ signed in with results, every button disabled")
    SEARCH_UI(pg,"r_anker",F,4); CLICK(pg,"slot-t_2-19:00"); pg.wait_for_timeout(800)
    g("booking form, every button disabled")
    pg.goto(BASE+"/lookup",wait_until="load")
    FILL(pg,"lookup-reference-input",pre["reference"]); CLICK(pg,"lookup-submit")
    pg.wait_for_timeout(1000); g("/lookup reservation shown, every button disabled")
    return rows,sk,cen,dis
rows,sk,cen,dis=UI(f,route=None)
bad=PX_FAILS(rows)
n=sum(len(dis[k]) for k in dis)
print("BUTTONS DISABLED PER SURFACE:",json.dumps(dis,indent=1,sort_keys=True))
print("CENSUS PER SURFACE:",json.dumps(cen,indent=1,sort_keys=True))
print("EXCLUDED FROM MEASUREMENT:",json.dumps(PX_SKIPS(sk),indent=1,sort_keys=True))
print("TOTAL BUTTONS DISABLED:",n,"TOTAL MEASURED:",len(rows))
assert len(cen)==5,"reached %d of the 5 surfaces: %r"%(len(cen),sorted(cen))
assert n>=8,"only %d buttons were disabled across %d surfaces, so a pass here settles little: %s"%(n,len(dis),json.dumps(dis,sort_keys=True))
assert not bad,"%d of %d measured elements are below the declared threshold while every button is disabled:\n%s"%(len(bad),len(rows),json.dumps(bad,indent=1,sort_keys=True))
print("PASS",n,"buttons disabled across",len(cen),"surfaces,",len(rows),"elements measured, none below threshold")'`
Passes when: exits 0 and ends `PASS <n> buttons disabled across 5 surfaces, …`, having printed what was disabled on each surface, the census, and the exclusion list. **This is the entry ERRATA 5 was missing.** A rule matching `button[disabled]` that repaints the background and leaves the text to inherit produces exactly the reported defect in a state no entry in ERRATA 5 visits, because S-67's tour never disables anything. Every `<button>` is disabled rather than the three the spec names, because the grid cells are buttons and a rule does not care which button it matches. **Proxy, per §16 rule 1:** it measures what the stylesheet paints for the disabled state by entering that state directly. **What it does not establish:** that the service actually disables these buttons during a request — that is S-53's territory and this entry makes no claim about it — nor anything about the transition into or out of the state.
Status: unclaimed

### S-76: The same twelve surfaces hold at a 375-pixel viewport.
Check: `$PWPY -c "$WPX2"'
ta,_=SETUP()
pre=OK(BOOK(ta,F+"T20:00","s76-seed",table_id="t_3",ps=4),201)
rows,sk,cen=UI(lambda pg:PX_TOUR(pg,pre["reference"]),w=375,h=812,route=None)
bad=PX_FAILS(rows)
print("VIEWPORT 375x812")
print("CENSUS PER SURFACE:",json.dumps(cen,indent=1,sort_keys=True))
print("EXCLUDED FROM MEASUREMENT:",json.dumps(PX_SKIPS(sk),indent=1,sort_keys=True))
print("TOTAL MEASURED:",len(rows))
assert len(cen)==len(PX_SURF),"the tour reached %d surfaces, not the %d it names: %r"%(len(cen),len(PX_SURF),sorted(cen))
assert rows,"nothing was measured at 375 CSS pixels"
assert not bad,"%d of %d measured elements are below the declared threshold at 375 CSS pixels:\n%s"%(len(bad),len(rows),json.dumps(bad,indent=1,sort_keys=True))
print("PASS",len(rows),"elements measured at 375x812 across",len(cen),"surfaces, none below threshold")'`
Passes when: exits 0 and ends `PASS <n> elements measured at 375x812 across 12 surfaces, …`. ERRATA 5 named the narrow viewport out of reach because `UI()` builds 1280×900; it takes `w` and `h`, so the reach was one argument away. The spec requires the flows to stay clear and usable at 375 CSS pixels, and a layout that reflows text onto a new background is a contrast change, not only a layout change — S-54 and S-55 already measure scrolling and clipping at that width and neither reads a painted colour. **What it does not establish:** anything about intermediate widths, or about touch target sizes, which no entry in this file measures.
Status: unclaimed

### S-77: The closed-day no-slots surface is legible, signed out and signed in.
Check: `$PWPY -c "$WPX2"'
SETUP(PX_CLOSED())
def f(pg):
    rows=[]; sk=[]; st=[]
    SEARCH_UI(pg,"r_anker",F,4)
    r,s=PX_SCAN(pg,"no-slots, signed out"); rows.extend(r); sk.extend(s)
    st.append([SEE(pg,"no-slots"),TXT(pg,"no-slots"),SEE(pg,"availability-grid")])
    LOGIN_UI(pg); SEARCH_UI(pg,"r_anker",F,4)
    r,s=PX_SCAN(pg,"no-slots, signed in"); rows.extend(r); sk.extend(s)
    st.append([SEE(pg,"no-slots"),TXT(pg,"no-slots"),SEE(pg,"availability-grid")])
    return rows,sk,st
rows,sk,st=UI(f,route=None)
bad=PX_FAILS(rows)
print("SEARCHED DATE:",F,"WEEKDAY OMITTED FROM opening_hours: thu")
print("NO-SLOTS STATE [seen,text,grid] SIGNED OUT THEN SIGNED IN:",json.dumps(st))
print("EXCLUDED FROM MEASUREMENT:",json.dumps(PX_SKIPS(sk),indent=1,sort_keys=True))
print("TOTAL MEASURED:",len(rows))
assert st[0][0] or st[1][0],"the closed-day fixture produced no visible no-slots state on either search"
assert (st[0][1] or "").strip() or (st[1][1] or "").strip(),"no-slots is shown but carries no text: %r"%st
assert rows,"nothing was measured on the no-slots surface"
assert not bad,"%d of %d measured elements are below the declared threshold on the no-slots surface:\n%s"%(len(bad),len(rows),json.dumps(bad,indent=1,sort_keys=True))
print("PASS no-slots reached by a closed-day fixture and legible on both surfaces,",len(rows),"elements measured")'`
Passes when: exits 0 and ends `PASS no-slots reached by a closed-day fixture and legible …`, having printed the state tuple for both surfaces. No fault injection: `PX_CLOSED()` omits Thursday from `opening_hours` and `F` is a Thursday, so the restaurant's own calendar closes the searched day. S-34 already requires `no-slots` instead of the grid and S-52 that it say what is absent; **neither reads a painted pixel**, so an empty-state message painted on its own background is invisible to both. **What it does not establish:** that the wording is useful, which is `@registrar`'s and the human's; nor the appearance of a day that is open but fully booked, which is a different surface and has no entry.
Status: unclaimed

### S-78: The refusal surface after a 409 is legible.
Check: `$PWPY -c "$WPX2"'
ta,tb=SETUP()
def f(pg):
    LOGIN_UI(pg); SEARCH_UI(pg,"r_anker",F,4)
    CLICK(pg,"slot-t_2-19:00"); pg.wait_for_timeout(800)
    assert SEE(pg,"booking-form"),"the booking form did not open, so the refusal surface cannot be reached"
    OK(BOOK(tb,F+"T19:00","s78-steal",table_id="t_2",ps=4),201)
    CLICK(pg,"booking-submit"); pg.wait_for_timeout(1600)
    rows,sk=PX_SCAN(pg,"booking-error after a 409")
    return rows,sk,SEE(pg,"booking-error"),TXT(pg,"booking-error"),SEE(pg,"confirmation")
rows,sk,seen,txt,conf=UI(f,route=None)
bad=PX_FAILS(rows)
print("BOOKING-ERROR SHOWN:",seen,"CONFIRMATION SHOWN:",conf)
print("BOOKING-ERROR TEXT:",json.dumps(txt))
print("EXCLUDED FROM MEASUREMENT:",json.dumps(PX_SKIPS(sk),indent=1,sort_keys=True))
print("TOTAL MEASURED:",len(rows))
assert seen,"no booking-error after another account took the table, so the refusal surface was never reached"
assert (txt or "").strip(),"booking-error is shown but carries no text"
assert rows,"nothing was measured on the refusal surface"
assert not bad,"%d of %d measured elements are below the declared threshold on the refusal surface:\n%s"%(len(bad),len(rows),json.dumps(bad,indent=1,sort_keys=True))
print("PASS the refusal surface is legible,",len(rows),"elements measured")'`
Passes when: exits 0 and ends `PASS the refusal surface is legible, …`, having printed whether `booking-error` appeared, its text, and the exclusion list. No fault injection and no clock change: a second account takes `t_2` after the form opens, which is S-45's mechanism exactly. S-45 asserts the refusal's *behaviour* — the error appears, the form and the diner's input survive, availability refreshes — and reads no painted colour; an error message painted the colour of its own panel satisfies every one of its assertions. **What it does not establish:** the behaviour S-45 covers, which this entry does not re-claim beyond requiring the surface to have been reached at all.
Status: unclaimed

### S-79: The uncertain surface after a lost response is legible.
Check: `$PWPY -c "$WPX2"'
ta,_=SETUP()
def f(pg):
    PX_LOSE(pg)
    LOGIN_UI(pg); SEARCH_UI(pg,"r_anker",F,4)
    CLICK(pg,"slot-t_2-19:00"); pg.wait_for_timeout(800)
    assert SEE(pg,"booking-form"),"the booking form did not open, so the uncertain surface cannot be reached"
    CLICK(pg,"booking-submit"); pg.wait_for_timeout(2500)
    rows,sk=PX_SCAN(pg,"booking-uncertain after a lost response")
    return rows,sk,SEE(pg,"booking-uncertain"),TXT(pg,"booking-uncertain"),SEE(pg,"confirmation"),SEE(pg,"booking-error")
rows,sk,seen,txt,conf,err=UI(f,route=None)
bad=PX_FAILS(rows)
print("BOOKING-UNCERTAIN SHOWN:",seen,"CONFIRMATION SHOWN:",conf,"BOOKING-ERROR SHOWN:",err)
print("BOOKING-UNCERTAIN TEXT:",json.dumps(txt))
print("EXCLUDED FROM MEASUREMENT:",json.dumps(PX_SKIPS(sk),indent=1,sort_keys=True))
print("TOTAL MEASURED:",len(rows))
assert seen,"the POST response was dropped and no booking-uncertain surface appeared; confirmation=%r booking-error=%r"%(conf,err)
assert (txt or "").strip(),"booking-uncertain is shown but carries no text"
assert rows,"nothing was measured on the uncertain surface"
assert not bad,"%d of %d measured elements are below the declared threshold on the uncertain surface:\n%s"%(len(bad),len(rows),json.dumps(bad,indent=1,sort_keys=True))
print("PASS the uncertain surface is legible,",len(rows),"elements measured")'`
Passes when: exits 0 and ends `PASS the uncertain surface is legible, …`, having printed which of the three outcome panels appeared, the uncertain text, and the exclusion list. `PX_LOSE` lets the first `POST /reservations` reach the server with `route.fetch()` and then aborts the response with `connectionfailed`, so the booking commits and the browser never learns it did — S-46's mechanism, written against the **synchronous** Playwright API because `PX_SCAN` is synchronous. S-46 itself is async and is unaffected. **This is a fault injection and ERRATA 5 was right that one is needed; it was wrong that it was out of reach**, since this file has performed it since stage 2 opened. **What it does not establish:** the recovery S-46 covers — that retrying the unchanged form returns the original reference — which this entry does not re-claim.
Status: unclaimed

## What ERRATA 6 still does not reach

| Not reached | Why not |
|---|---|
| Hover and focus appearance | The raster is a still of the resting state. A focus sweep would need the instrument run after each `Tab`, and a hover sweep after each `hover()`. Neither is written. Still a gap. |
| A day that is open but fully booked | S-77 covers the closed day. The fully-booked grid is a different surface and no entry measures it. |
| Intermediate viewport widths, and touch target sizes | S-76 measures 375 and S-67 measures 1280. Nothing measures between them, and no entry in this file measures a target size. |
| Whether the service enters the disabled state during a request | S-75 enters it directly and says so. S-53 requires a loading state exists; nothing ties the two together. |
| Text sharing a box with an icon or image | Unchanged from §17. A visible glyph anywhere in a box can carry the ratio for invisible text beside it. |

---

# ERRATA 7 — two of my own Checks could not establish their own prose

S-69 and S-76 have FAIL verdicts at `fe543c4`, both against `dc6879c`, and **both are defects in the
Check rather than in the service — but that sentence is a reading, not a verdict, and this section
exists because nobody has run anything that establishes it.** Three seats agree on the cause. Three
seats agreeing on a reading is still a reading: `@scribe`'s diagnosis was explicitly unrun,
`@builder`'s probes are not evidence by its own mandate, and `@auditor` has stated twice that its
verdict files are not a second vote — `PX_SKIPS` prints no tag, so the identity of the zero-box
element appears nowhere in anything that ran, and its `NO-PIXELS` note was an observation about two
printed strings rather than a reachability claim.

So the two entries below do not assert the cause. **They settle it by run.** Supersession authorised
by `@registrar`, bounded to these two. **S-69 and S-76 stand, with their FAIL verdicts intact.**
Nothing is retired and nothing is deleted; the FAILs are the record.

## Defect 11 — S-69's third condition cannot be satisfied by any correct implementation

`LEDGER.md:4636` reads:

```
boxless=[s for s in sk if s["why"]=="zero-box" and (s["interactive"] or s["hasText"]) and (s["text"] or "")]
```

The `or s["hasText"]` clause admits **any** text-bearing element with a zero box. The entry's prose
says *"no named control is boxless"*; the code asserts something broader. S-69's first two conditions
printed empty at `fe543c4` and are not in question — only the third refused. **A Check no correct
implementation can satisfy is not strict, it is broken**, and S-80 is written to establish whether
that is what this is, rather than to assume it.

## Defect 12 — the exclusion list §17 calls a door cannot be inspected

§17 says *"a reader must check what was skipped; a passing line alone does not tell them"*. The
enumerator collects the tag at `:4321` and carries it into every skipped record at `:4339`, and then
`PX_SKIPS` at `:4421` drops it:

```
return [[s.get("surface"),s.get("testid"),s.get("text"),s["why"],s["interactive"]] for s in sk]
```

An element excluded with `testid: null` is therefore unidentifiable in the output of all seventeen
Checks. **The prose claims a reader can audit the exclusions and the code withholds the one field
that would let them.** This is why `@auditor` could not confirm the element's identity from its own
record and why a reader cloning this repository cannot either.

## Defect 13 — an out-of-raster box is silently mismeasured, and `NO-PIXELS` is unreachable

`:4354-4355` clamp the sample rectangle into the image:

```
x0=Math.max(0,Math.min(W-1,Math.round(x0))); y0=Math.max(0,Math.min(H-1,Math.round(y0)));
w=Math.max(1,Math.min(W-x0,Math.round(w)));  h=Math.max(1,Math.min(H-y0,Math.round(h)));
```

A box entirely outside the raster is reduced to a one-pixel column at the edge rather than reported
as outside. `hist()` therefore always returns at least one entry, `bg` at `:4397` is never `None`,
and `if bg is None: v="NO-PIXELS"` at `:4408` cannot fire. §17's prose at `:4282` documents a verdict
the code cannot emit. **This is a claim about source, auditable by opening the file, and it is still
not a run** — `@auditor`'s census of all fifteen logs (`NO-PIXELS 0 · NO-INK 159 · LOW-CONTRAST 2 ·
FLAT-AGAINST-PAGE 90`) is consistent with it and does not demonstrate it, as that seat said itself.

**S-76's deeper fault is not the false failure.** It refuses off-scrollport content instead of
measuring it, so nobody ever learns the contrast of the grid's scrolled-out columns at 375px. A
false failure is visible; a silent coverage hole is not. **Excluding them would have been the wrong
repair** — that insight is `@builder`'s and S-81 is built on it.

## §20 The scroll-aware and identity helpers (`$PX3`)

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
```

**What `PX3_ZB` does.** It finds every element that is text-bearing with a zero box and not hidden by
CSS — the exact population S-69's third condition refused on — and reports **tag, parent tag, parent
testid, computed display and visibility** alongside what `PX_SKIPS` already printed. Then it probes
whether the zero box is intrinsic, two ways: it applies a forcing inline style
(`display:block;width:240px;height:48px;min-width;min-height`) and re-measures, and it appends a
**fresh element of the same tag into the same parent** with the same forcing style and measures that.
If neither gets a box, no stylesheet change could give the original one.

**The limit on that, stated because it is the honest boundary.** It establishes that **no change to
the service's CSS** can give the element a box. It does **not** establish that no change to the
*markup* could — replacing a native `<select>` with a custom listbox would, which is a redesign aimed
at an assertion rather than at a requirement. The entry reports the fact and does not pretend the
fact settles the design question.

**What `PX_SCROLLSCAN` does.** For each scrollable container on a surface it takes the container's
full inventory of text-bearing and interactive elements, steps `scrollLeft` and `scrollTop` across
the whole range in 80%-of-scrollport increments, and at each position measures every inventory
element whose visible intersection with the scrollport is at least 8×8 — **measuring the painted
intersection rather than the declared box, so the clamp of Defect 13 is never reached.** Per element
it keeps the **best** result across all positions, because the question is whether content is legible
*when scrolled to*, and one position where it reads clearly answers that. An element whose best
result is below threshold at every position is illegible; an element that measures `OK` at some
position was merely off-scrollport.

```python
#PX3-BEGIN
PX3_INTER="button,a[href],input,select,textarea,summary,[role=button],[role=link],[role=tab],[onclick]"
PX3_ZB="""()=>{
  const INTER="button,a[href],input,select,textarea,summary,[role=button],[role=link],[role=tab],[onclick]";
  const own=(e)=>{let s="";for (const n of e.childNodes) if (n.nodeType===3) s+=n.nodeValue;
                  return s.replace(/\\s+/g," ").trim()};
  const found=[];
  for (const e of document.querySelectorAll("body *")) {
    const t=e.tagName;
    if (t==="SCRIPT"||t==="STYLE"||t==="NOSCRIPT"||t==="TEMPLATE") continue;
    if (e.namespaceURI && e.namespaceURI.indexOf("svg")>=0) continue;
    const ot=own(e);
    if (!ot) continue;
    const cs=getComputedStyle(e), r=e.getBoundingClientRect();
    if (cs.display==="none") continue;
    if (cs.visibility!=="visible") continue;
    if (e.getAttribute("aria-hidden")==="true") continue;
    if (e.closest("[hidden],[aria-hidden=true]")) continue;
    if (r.width>=1 && r.height>=1) continue;
    const p=e.parentElement;
    const prev=e.getAttribute("style");
    e.setAttribute("style",(prev||"")+";display:block;width:240px;height:48px;min-width:240px;min-height:48px;padding:8px");
    const r2=e.getBoundingClientRect();
    if (prev===null) { e.removeAttribute("style"); } else { e.setAttribute("style",prev); }
    const r3=e.getBoundingClientRect();
    found.push({tag:t.toLowerCase(), testid:e.getAttribute("data-testid")||null,
      text:ot.slice(0,48), interactive:e.matches(INTER),
      parentTag:p?p.tagName.toLowerCase():null,
      parentTestid:p?(p.getAttribute("data-testid")||null):null,
      display:cs.display, visibility:cs.visibility,
      boxAtRest:[Math.round(r.width),Math.round(r.height)],
      boxForced:[Math.round(r2.width),Math.round(r2.height)],
      boxRestored:[Math.round(r3.width),Math.round(r3.height)],
      cssCannotGiveBox:(r2.width<1 && r2.height<1)});
  }
  const fresh=[]; const seen={};
  for (const o of found) {
    const key=o.tag+"|"+(o.parentTestid||o.parentTag||"");
    if (seen[key]) continue; seen[key]=1;
    let parent=null;
    if (o.parentTestid) parent=document.querySelector("[data-testid="+JSON.stringify(o.parentTestid)+"]");
    if (!parent && o.parentTag) parent=document.querySelector(o.parentTag);
    if (!parent) { fresh.push({key:key, made:false}); continue; }
    const n=document.createElement(o.tag);
    n.textContent="PX3 fresh probe";
    n.setAttribute("style","display:block;width:240px;height:48px;min-width:240px;min-height:48px");
    parent.appendChild(n);
    const rr=n.getBoundingClientRect();
    fresh.push({key:key, made:true, tag:o.tag, parentTestid:o.parentTestid, parentTag:o.parentTag,
      box:[Math.round(rr.width),Math.round(rr.height)],
      freshAlsoZero:(rr.width<1 && rr.height<1)});
    n.remove();
  }
  return {found:found, fresh:fresh};
}"""
PX3_CONT="""()=>{
  const out=[];
  for (const e of document.querySelectorAll("body *")) {
    const cs=getComputedStyle(e);
    const hx=(e.scrollWidth-e.clientWidth>1)&&(cs.overflowX==="auto"||cs.overflowX==="scroll");
    const hy=(e.scrollHeight-e.clientHeight>1)&&(cs.overflowY==="auto"||cs.overflowY==="scroll");
    if (!hx && !hy) continue;
    const k="c"+out.length;
    e.setAttribute("data-px3",k);
    out.push({key:k, tag:e.tagName.toLowerCase(), testid:e.getAttribute("data-testid")||null,
      scrollWidth:e.scrollWidth, clientWidth:e.clientWidth,
      scrollHeight:e.scrollHeight, clientHeight:e.clientHeight, horiz:hx, vert:hy});
  }
  return out;
}"""
PX3_ELS="""(k)=>{
  const c=document.querySelector("[data-px3="+JSON.stringify(k)+"]");
  if (!c) return [];
  const INTER="button,a[href],input,select,textarea,summary,[role=button],[role=link],[role=tab],[onclick]";
  const own=(e)=>{let s="";for (const n of e.childNodes) if (n.nodeType===3) s+=n.nodeValue;
                  return s.replace(/\\s+/g," ").trim()};
  const out=[]; let i=0;
  for (const e of c.querySelectorAll("*")) {
    const t=e.tagName;
    if (t==="SCRIPT"||t==="STYLE"||t==="NOSCRIPT"||t==="TEMPLATE") continue;
    if (e.namespaceURI && e.namespaceURI.indexOf("svg")>=0) continue;
    const ot=own(e), inter=e.matches(INTER);
    if (!ot && !inter) continue;
    const cs=getComputedStyle(e), r=e.getBoundingClientRect();
    if (cs.display==="none"||cs.visibility!=="visible") continue;
    if (e.getAttribute("aria-hidden")==="true") continue;
    if (r.width<1||r.height<1) continue;
    if (!e.hasAttribute("data-px3e")) e.setAttribute("data-px3e",k+"-e"+(i++));
    out.push({key:e.getAttribute("data-px3e"), tag:t.toLowerCase(),
      testid:e.getAttribute("data-testid")||null,
      text:(ot||e.getAttribute("aria-label")||e.value||e.placeholder||"").replace(/\\s+/g," ").trim().slice(0,48),
      interactive:inter, hasText:!!ot,
      fontSize:parseFloat(cs.fontSize)||0, fontWeight:parseInt(cs.fontWeight)||400});
  }
  return out;
}"""
PX3_SET="""(a)=>{
  const c=document.querySelector("[data-px3="+JSON.stringify(a.k)+"]");
  c.scrollLeft=a.left; c.scrollTop=a.top;
  return [Math.round(c.scrollLeft),Math.round(c.scrollTop)];
}"""
PX3_VIS="""(k)=>{
  const c=document.querySelector("[data-px3="+JSON.stringify(k)+"]");
  if (!c) return [];
  const cr=c.getBoundingClientRect(); const out=[];
  for (const e of c.querySelectorAll("[data-px3e]")) {
    const r=e.getBoundingClientRect();
    const ix=Math.max(cr.left,Math.max(0,r.left)), ax=Math.min(cr.right,Math.min(window.innerWidth,r.right));
    const iy=Math.max(cr.top,Math.max(0,r.top)),  ay=Math.min(cr.bottom,Math.min(window.innerHeight,r.bottom));
    if (ax-ix<8 || ay-iy<8) continue;
    out.push({key:e.getAttribute("data-px3e"),
      x:ix+window.scrollX, y:iy+window.scrollY, w:ax-ix, h:ay-iy,
      full:[Math.round(r.width),Math.round(r.height)],
      whole:(r.left>=cr.left-0.5 && r.right<=cr.right+0.5 && r.left>=0 && r.right<=window.innerWidth)});
  }
  return out;
}"""
def PX3_ROW(el,s,surface,at):
    ih=s["inner"]["hist"]; bg=ih[0][0] if ih else None
    distinct=len([1 for k,c in ih if c>=PX_MINPX])
    mc,ink=PX_MAX(ih,bg) if bg is not None else (1.0,None)
    rh=s["ring"]["hist"]; sur=rh[0][0] if rh else None
    sal,_=PX_MAX(s["full"]["hist"],sur) if sur is not None else (1.0,None)
    big=el["fontSize"]>=24 or (el["fontSize"]>=18.66 and el["fontWeight"]>=700)
    if el["hasText"]:
        need=PX_LARGE if big else PX_AA; got=round(mc,2); kind="text"
    else:
        need=PX_UI; got=round(sal,2); kind="control"
    v="OK"
    if bg is None: v="NO-PIXELS"
    elif el["hasText"] and distinct<2: v="NO-INK"
    elif got<need: v=("LOW-CONTRAST" if el["hasText"] else "FLAT-AGAINST-PAGE")
    return {"surface":surface,"at":at,"key":el["key"],"testid":el["testid"],"tag":el["tag"],
            "text":el["text"],"kind":kind,"verdict":v,"measured":got,"need":need,
            "distinct":distinct,"ink":None if ink is None else PX_CSS(ink),
            "bg":None if bg is None else PX_CSS(bg),"surround":None if sur is None else PX_CSS(sur)}
def PX_SCROLLSCAN(pg,surface=""):
    pg.wait_for_timeout(250)
    cons=pg.evaluate(PX3_CONT)
    rows=[]; inv={}
    for c in cons:
        els=pg.evaluate(PX3_ELS,c["key"])
        emap={e["key"]:e for e in els}
        for e in els:
            inv[e["key"]]=dict(e,surface=surface,container=c["testid"] or c["tag"])
        sw=max(0,c["scrollWidth"]-c["clientWidth"]); sh=max(0,c["scrollHeight"]-c["clientHeight"])
        stx=max(1,int(c["clientWidth"]*0.8)); sty=max(1,int(c["clientHeight"]*0.8))
        lefts=list(range(0,sw+stx,stx)) if c["horiz"] and sw>0 else [0]
        tops=list(range(0,sh+sty,sty)) if c["vert"] and sh>0 else [0]
        for t in tops:
            for l in lefts:
                pos=pg.evaluate(PX3_SET,{"k":c["key"],"left":l,"top":t})
                pg.wait_for_timeout(120)
                vis=pg.evaluate(PX3_VIS,c["key"])
                if not vis: continue
                boxes=[{"x":v["x"],"y":v["y"],"w":v["w"],"h":v["h"]} for v in vis]
                b64=base64.b64encode(pg.screenshot(full_page=True)).decode()
                px=pg.evaluate(PX_READ,{"b64":b64,"boxes":boxes,"inset":PX_INSET,"ring":PX_RING})
                at="%s scrollLeft=%d scrollTop=%d"%(c["testid"] or c["tag"],pos[0],pos[1])
                for v,sx in zip(vis,px):
                    e=emap.get(v["key"])
                    if e: rows.append(PX3_ROW(e,sx,surface,at))
    return cons,rows,inv
def PX3_BEST(rows):
    best={}
    for r in rows:
        k=r["key"]
        if k not in best: best[k]=r; continue
        b=best[k]
        if (b["verdict"]!="OK" and r["verdict"]=="OK") or (b["verdict"]==r["verdict"] and r["measured"]>b["measured"]):
            best[k]=r
    return best
def PX_NAV(pg,ref,fn):
    out={}
    for p in ["/","/login","/signup","/lookup"]:
        pg.goto(BASE+p,wait_until="load"); out[p+" signed out"]=fn(p+" signed out")
    SEARCH_UI(pg,"r_anker",F,4); out["/ signed out, results"]=fn("/ signed out, results")
    c=CELL(pg,"t_2","19:00")
    if c: c.click(); pg.wait_for_timeout(800)
    if SEE(pg,"booking-submit"): CLICK(pg,"booking-submit"); pg.wait_for_timeout(1400)
    out["signed out, slot clicked"]=fn("signed out, slot clicked")
    pg.goto(BASE+"/login",wait_until="load")
    FILL(pg,"login-email",ADA["email"]); FILL(pg,"login-password","wrong password")
    CLICK(pg,"login-submit"); pg.wait_for_timeout(900); out["/login, bad credentials"]=fn("/login, bad credentials")
    pg.goto(BASE+"/lookup",wait_until="load")
    FILL(pg,"lookup-reference-input","NO-SUCH-REFERENCE"); CLICK(pg,"lookup-submit")
    pg.wait_for_timeout(1000); out["/lookup, unknown reference"]=fn("/lookup, unknown reference")
    LOGIN_UI(pg); SEARCH_UI(pg,"r_anker",F,4); out["/ signed in, results"]=fn("/ signed in, results")
    CLICK(pg,"slot-t_2-19:00"); pg.wait_for_timeout(800); out["booking form, signed in"]=fn("booking form, signed in")
    CLICK(pg,"booking-submit"); pg.wait_for_timeout(1600); out["confirmation, signed in"]=fn("confirmation, signed in")
    pg.goto(BASE+"/lookup",wait_until="load")
    FILL(pg,"lookup-reference-input",ref); CLICK(pg,"lookup-submit")
    pg.wait_for_timeout(1000); out["/lookup, reservation shown"]=fn("/lookup, reservation shown")
    return out
#PX3-END
```

## Superseding entries — authorised by `@registrar`, bounded to two

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

## Authorisation of record — ERRATA 7

`@registrar` authorised supersession on this ERRATA, **bounded to two entries**, and required the
Check text be handed to `@registrar` rather than to `@auditor`, on the precedent of ERRATA 4. The two
entries it specified are the two above:

| Authorised | Entry | What it must settle |
|---|---|---|
| ONE | S-80 | The identity of the zero-box element, printing its **tag**, by run rather than by inference — and whether its zero box is intrinsic, i.e. whether any change to `stage-2/` could give it one. |
| TWO | S-81 | Whether the 248 refused records at 375 pixels are off-scrollport or illegible — **by measuring them**, stepping the scrollport through its range, rather than by excluding them. |

S-80 and S-81 were written and committed at `1007a09` before that authorisation arrived; the messages
crossed. They are recorded here as authorised, not as written under authority they did not yet have.

**The cause of both refusals is UNESTABLISHED, and these two entries exist because of that.** Three
seats read the same two outputs and agreed, and agreement by reading is not a result:

- My own diagnosis — the `<option>` for S-69, the off-scrollport grid for S-76 — is **unrun**. I said
  so when I sent it and it is restated here so no reader takes the entries above as resting on it.
- `@builder`'s diagnosis is a run, and `@builder` declared in the same message that it is not
  evidence: a fresh `<option>` measuring `[0,0]`, `gridwrap` `scrollWidth` 655 against `clientWidth`
  349, no horizontal page scroll, 8.25:1 worst case after `scrollLeft = scrollWidth`. Every one of
  those is a probe this ledger names nowhere.
- `@auditor` stated twice, against its own interest, that `verdicts/S-69.md` and `verdicts/S-76.md`
  are **not a second vote** in either reading. `PX_SKIPS` prints `[surface, testid, text,
  interactive]` and no tag, so the tag of the zero-box element appears in nothing that ran; its
  `NO-PIXELS` note was an observation about two printed strings, not a reachability claim. Its
  measured addition across all fifteen run logs — `NO-PIXELS 0`, `NO-INK 159`, `LOW-CONTRAST 2`,
  `FLAT-AGAINST-PAGE 90` — it limited itself: these Checks print failing and probe records rather
  than every measured element, so zero occurrences is **consistent with** the reading and does not
  demonstrate it.

**A credit I gave wrongly, corrected.** I wrote that `@auditor` found the `NO-PIXELS` asymmetry.
It printed what the records carried and noted that §17's prose names a verdict they did not. The step
from that to the clamp at `:4354` is Defect 13's and mine, and the correction is `@auditor`'s.

**S-69 and S-76 STAND.** Their FAIL verdicts at `fe543c4` against `dc6879c` are intact and are the
record. S-80 supersedes S-69's third condition only; S-81 supersedes S-76 entirely. Nothing is
retired and nothing is deleted.

**NO FIX, by instruction.** `@registrar` instructed `@builder` not to change `stage-2/app.py`:
replacing the native `select` with a custom listbox, or reflowing the grid so it never overflows at
375, are redesigns aimed at an assertion rather than at a requirement, and the second puts suites 1
and 2 at risk across thirteen `slot-` references. `@builder` confirmed `git diff --stat dc6879c HEAD
-- stage-2/app.py` prints nothing. `dc6879c` remains the revision of record. If either entry above
establishes a real defect in it, the dispatch goes to `@builder` under the **original** claim
identifier.

**Coverage overlap, flagged by `@builder` and left in the design.** The elements S-81 reaches by
scrolling at 375 are grid cells and column headers, which S-67 already measures at 1280 where they
sit inside the scrollport. Agreement between the two is expected and disagreement would be
informative; that is a reason to keep both, not to narrow either. S-81's prose already bounds itself
to elements inside a scrollable container and does not re-claim S-67's resting raster at 1280.

**Nothing about the reported defect is in question.** S-66 passed at 9.62:1 on both controls, S-67
and S-68 passed the sweep at 832 elements over twelve surfaces, and S-75 passed at 100 buttons.
