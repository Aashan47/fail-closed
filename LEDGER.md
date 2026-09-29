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
Status: FAILED at 90028fd — verdicts/C-0.md at 93baa86; superseded by C-142

### C-1: RUN.md's own command builds and starts the service without manual setup.
Check: `cd /Users/aashanjaved/band-work/result/stage-1 && docker rm -f tk-s1 >/dev/null 2>&1; docker network create --internal tk-s1-noout >/dev/null 2>&1; awk '/^```/{f=!f;next} f' RUN.md > /tmp/tk-runmd.sh && test -s /tmp/tk-runmd.sh && sh -eux /tmp/tk-runmd.sh && start=$(date +%s) && until curl -fsS http://127.0.0.1:18080/health; do [ $(( $(date +%s) - start )) -lt 60 ] || { echo "NOT HEALTHY"; exit 1; }; sleep 1; done && echo "RUNMD OK"`
Passes when: exits 0 and prints `RUNMD OK`. The fenced code blocks of `RUN.md` must contain exactly the shell commands that build and start the service and nothing else, must require no editing, and must leave the service answering on port 18080.
Status: unclaimed

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
Status: unclaimed

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
Status: unclaimed

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
Status: unclaimed

### C-8: Repeated resets are supported and each one takes full effect.
Check: `python3 -c "$P"'
for i in range(4):
    RESET(FX(restaurants=[REST(id="r_%d"%i,name="Round %d"%i)]))
    rs=OK(R("GET","/restaurants"),200)["restaurants"]
    assert [r["id"] for r in rs]==["r_%d"%i],(i,rs)
print("PASS")'`
Passes when: prints `PASS`. After each of four consecutive resets only that fixture's restaurant is visible.
Status: unclaimed

### C-9: A reset fixture carrying an ID longer than 64 characters is rejected.
Check: `python3 -c "$P"'
ERR(R("POST","/_test/reset",FX(users=[dict(ADA,id="u"*65)])),422,"validation_failed")
ERR(R("POST","/_test/reset",FX(restaurants=[REST(id="r"*65)])),422,"validation_failed")
ERR(R("POST","/_test/reset",FX(restaurants=[REST(tables=[{"id":"t"*65,"label":"1","capacity":2}])])),422,"validation_failed")
print("PASS")'`
Passes when: prints `PASS`. An over-long user, restaurant or table ID in a fixture is 422 `validation_failed`.
Status: unclaimed

### C-10: A reset fixture carrying a reservation reference of invalid format is rejected.
Check: `python3 -c "$P"'
for bad in ["x","lower01","TOO-LONG-WITH-DASH","ABCDEFGHIJKLM",""]:
    ERR(R("POST","/_test/reset",FX(reservations=[SEED(bad,F+"T19:00")])),422,"validation_failed")
print("PASS")'`
Passes when: prints `PASS`. Each malformed seeded reference is 422 `validation_failed`.
Status: unclaimed

### C-11: Unknown fields in a request body are ignored, never an error.
Check: `python3 -c "$P"'
t,_=SETUP()
b=OK(R("POST","/reservations",{"restaurant_id":"r_anker","table_id":"t_2","starts_at_local":F+"T19:00","party_size":4,"nonsense":[1,2,3],"vip":True},tok=t,key="k1"),201)
assert b["status"]=="confirmed" and "nonsense" not in b,b
OK(R("POST","/auth/signup",{"email":"zoe@example.com","password":"correct horse","display_name":"Zoe","extra":{"a":1}}),201)
OK(PATCHR(t,b["reference"],{"party_size":2,"junk":"ignored"}),200)
print("PASS")'`
Passes when: prints `PASS`. Extra body fields are accepted and do not appear in the response.
Status: unclaimed

### C-12: Unknown query parameters are ignored.
Check: `python3 -c "$P"'
SETUP()
s,b,_=R("GET","/availability?restaurant_id=r_anker&date="+F+"&party_size=4&sort=whatever&page=3")
assert s==200,(s,b)
assert b["restaurant_id"]=="r_anker" and b["date"]==F,b
print("PASS")'`
Passes when: prints `PASS`.
Status: unclaimed

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
Status: unclaimed

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
Status: unclaimed

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
Status: unclaimed

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
Status: unclaimed

### C-17: GET /restaurants/{unknown} is 404 not_found.
Check: `python3 -c "$P"'
SETUP()
ERR(R("GET","/restaurants/r_nope"),404,"not_found")
print("PASS")'`
Passes when: prints `PASS`.
Status: unclaimed

### C-18: GET /availability is public.
Check: `python3 -c "$P"'
SETUP()
b=OK(AV("r_anker",F,4),200)
assert b["restaurant_id"]=="r_anker" and b["date"]==F and b["timezone"]=="Europe/Berlin",b
assert isinstance(b["slots"],list) and b["slots"],b
print("PASS")'`
Passes when: prints `PASS`. No bearer token was sent.
Status: unclaimed

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
Status: unclaimed

### C-20: available_table_ids lists the tables with capacity at or above party_size, in fixture order.
Check: `python3 -c "$P"'
SETUP()
assert FREE("r_anker",F,2,F+"T19:00")==["t_1","t_2","t_3"],FREE("r_anker",F,2,F+"T19:00")
assert FREE("r_anker",F,4,F+"T19:00")==["t_2","t_3"],FREE("r_anker",F,4,F+"T19:00")
assert FREE("r_anker",F,5,F+"T19:00")==[],FREE("r_anker",F,5,F+"T19:00")
print("PASS")'`
Passes when: prints `PASS`. Order follows the fixture, not sorting.
Status: unclaimed

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
Status: unclaimed

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
Status: unclaimed

### C-23: A closed day returns an empty slots list.
Check: `python3 -c "$P"'
RESET(FX(restaurants=[REST(opening_hours=[{"weekday":"fri","opens":"18:00","closes":"23:30"}])]))
b=OK(AV("r_anker","2027-06-10",4),200)
assert b["slots"]==[],b
assert OK(AV("r_anker","2027-06-11",4),200)["slots"],"friday should be open"
print("PASS")'`
Passes when: prints `PASS`. 2027-06-10 is a Thursday, which the fixture leaves closed; 2027-06-11 is the Friday and is open.
Status: unclaimed

### C-24: Each of restaurant_id, date and party_size is required on GET /availability.
Check: `python3 -c "$P"'
SETUP()
ERR(R("GET","/availability?date="+F+"&party_size=4"),422,"validation_failed")
ERR(R("GET","/availability?restaurant_id=r_anker&party_size=4"),422,"validation_failed")
ERR(R("GET","/availability?restaurant_id=r_anker&date="+F),422,"validation_failed")
ERR(R("GET","/availability"),422,"validation_failed")
print("PASS")'`
Passes when: prints `PASS`.
Status: unclaimed

### C-25: An integer-valued query parameter must be plain decimal digits.
Check: `python3 -c "$P"'
SETUP()
for bad in ["4.0","+4"," 4","1e9","0x4","four","-1","0",""]:
    ERR(AV("r_anker",F,bad),422,"validation_failed")
print("PASS")'`
Passes when: prints `PASS`. Each spelling is 422 `validation_failed` whatever its numeric value.
Status: unclaimed

### C-26: An unparseable or impossible date on GET /availability is rejected.
Check: `python3 -c "$P"'
SETUP()
for bad in ["2027-06-31","2027-02-30","2027-13-01","10/06/2027","2027-6-1","not-a-date","2027-06-10T19:00",""]:
    ERR(AV("r_anker",bad,4),422,"validation_failed")
print("PASS")'`
Passes when: prints `PASS`.
Status: unclaimed

### C-27: An unknown restaurant_id on GET /availability is 404 not_found.
Check: `python3 -c "$P"'
SETUP()
ERR(AV("r_nope",F,4),404,"not_found")
print("PASS")'`
Passes when: prints `PASS`.
Status: unclaimed

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
Status: unclaimed

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
Status: unclaimed

### C-30: POST /auth/login returns 200 with user_id, display_name and a usable token.
Check: `python3 -c "$P"'
RESET(FX())
b=OK(R("POST","/auth/login",{"email":ADA["email"],"password":ADA["password"]}),200)
assert set(["user_id","display_name","token"])<=set(b),b
assert b["display_name"]=="Ada",b
assert OK(LIST(b["token"]),200)["reservations"]==[],"token unusable"
print("PASS")'`
Passes when: prints `PASS`.
Status: unclaimed

### C-31: Signing up with an already registered email is 409 email_taken.
Check: `python3 -c "$P"'
RESET(FX())
ERR(R("POST","/auth/signup",{"email":ADA["email"],"password":"correct horse","display_name":"X"}),409,"email_taken")
OK(R("POST","/auth/signup",{"email":"zoe@example.com","password":"correct horse","display_name":"Zoe"}),201)
ERR(R("POST","/auth/signup",{"email":"zoe@example.com","password":"another one","display_name":"Y"}),409,"email_taken")
print("PASS")'`
Passes when: prints `PASS`.
Status: unclaimed

### C-32: A password shorter than 8 characters is 422 validation_failed.
Check: `python3 -c "$P"'
RESET(FX())
for pw in ["1234567","a",""]:
    ERR(R("POST","/auth/signup",{"email":"new@example.com","password":pw,"display_name":"X"}),422,"validation_failed")
OK(R("POST","/auth/signup",{"email":"new@example.com","password":"12345678","display_name":"X"}),201)
print("PASS")'`
Passes when: prints `PASS`. Seven characters is refused and eight is accepted.
Status: unclaimed

### C-33: An email not of the form local@domain is 422 validation_failed.
Check: `python3 -c "$P"'
RESET(FX())
for em in ["not-an-email","@example.com","ada@","ada example.com","","ada@@example.com"]:
    ERR(R("POST","/auth/signup",{"email":em,"password":"correct horse","display_name":"X"}),422,"validation_failed")
print("PASS")'`
Passes when: prints `PASS`.
Status: unclaimed

### C-34: A wrong password or an unknown email on login is 401 unauthenticated.
Check: `python3 -c "$P"'
RESET(FX())
ERR(R("POST","/auth/login",{"email":ADA["email"],"password":"wrong password"}),401,"unauthenticated")
ERR(R("POST","/auth/login",{"email":"nobody@example.com","password":"correct horse"}),401,"unauthenticated")
print("PASS")'`
Passes when: prints `PASS`. An unknown email is 401, not 404 — the service does not disclose which accounts exist.
Status: unclaimed

### C-35: A body field of the wrong JSON type is 400 malformed_request.
Check: `python3 -c "$P"'
RESET(FX())
ERR(R("POST","/auth/signup",{"email":17,"password":"correct horse","display_name":"X"}),400,"malformed_request")
ERR(R("POST","/auth/signup",{"email":"a@example.com","password":["x"],"display_name":"X"}),400,"malformed_request")
ERR(R("POST","/auth/login",{"email":{"a":1},"password":"correct horse"}),400,"malformed_request")
print("PASS")'`
Passes when: prints `PASS`.
Status: unclaimed

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
Status: unclaimed

### C-37: An unknown bearer token is 401 unauthenticated.
Check: `python3 -c "$P"'
SETUP()
ERR(LIST("not-a-real-token"),401,"unauthenticated")
ERR(LIST("x"*200),401,"unauthenticated")
print("PASS")'`
Passes when: prints `PASS`.
Status: unclaimed

### C-38: A malformed Authorization header is 401 unauthenticated.
Check: `python3 -c "$P"'
t,_=SETUP()
for h in ["","Bearer","Bearer ","bearer","Basic "+t,t,"Token "+t]:
    ERR(R("GET","/reservations",hdr={"Authorization":h}),401,"unauthenticated")
print("PASS")'`
Passes when: prints `PASS`. A header that is present but not a well-formed bearer credential is 401, never a 5xx and never treated as authenticated.
Status: unclaimed

### C-39: A seeded user can log in with the fixture password immediately after reset.
Check: `python3 -c "$P"'
RESET(FX())
for u in [ADA,BOB]:
    b=OK(R("POST","/auth/login",{"email":u["email"],"password":u["password"]}),200)
    assert b["display_name"]==u["display_name"],b
print("PASS")'`
Passes when: prints `PASS`.
Status: unclaimed

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
Status: unclaimed

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
Status: unclaimed

### C-42: Stored credentials carry the marker of a recognised password-hashing function.
Check: `python3 -c "$P"'
RESET(FX())
blob=json.dumps(EXPORT()).lower()
marks=["$2a$","$2b$","$2y$","$argon2","scrypt","pbkdf2","bcrypt"]
hit=[m for m in marks if m in blob]
assert hit,"no recognised KDF marker in export; markers looked for: %r"%marks
print("PASS",hit)'`
Passes when: prints `PASS` and the marker found. If the implementation uses a different but genuine password-hashing function whose serialised form matches none of these markers, `@auditor` records a fail naming the function and `@scribe` writes a replacement entry — the check is not edited.
Status: unclaimed

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
Status: unclaimed

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
Status: unclaimed

### C-45: reference is 6 to 12 characters of A-Z and 0-9.
Check: `python3 -c "$P"'
t,_=SETUP()
refs=[OK(BOOK(t,F+"T"+at,"k-"+at+tid,tid=tid,ps=2),201)["reference"] for at,tid in [("18:00","t_1"),("18:00","t_2"),("19:30","t_3"),("21:00","t_1"),("22:00","t_2")]]
for r in refs:
    assert REF.match(r),"bad reference %r"%r
print("PASS",refs)'`
Passes when: prints `PASS` and the references, each matching `^[A-Z0-9]{6,12}$`.
Status: unclaimed

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
Status: unclaimed

### C-47: A table already taken for an overlapping interval is 409 table_unavailable.
Check: `python3 -c "$P"'
t,_=SETUP()
OK(BOOK(t,F+"T19:00","k1",tid="t_2"),201)
for at in ["18:00","18:30","19:00","19:30","20:00"]:
    ERR(BOOK(t,F+"T"+at,"k-"+at,tid="t_2"),409,"table_unavailable")
print("PASS")'`
Passes when: prints `PASS`. Every start whose 90-minute interval meets the existing booking is refused, not only the identical one.
Status: unclaimed

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
Status: unclaimed

### C-49: The same time on a different table succeeds.
Check: `python3 -c "$P"'
t,_=SETUP()
a=OK(BOOK(t,F+"T19:00","k1",tid="t_2"),201)
b=OK(BOOK(t,F+"T19:00","k2",tid="t_3"),201)
assert a["starts_at"]==b["starts_at"] and a["table_id"]!=b["table_id"],(a,b)
print("PASS")'`
Passes when: prints `PASS`.
Status: unclaimed

### C-50: A start that is not on the slot grid is 422 not_on_slot_grid.
Check: `python3 -c "$P"'
t,_=SETUP()
for at in ["19:15","18:01","19:45","22:15"]:
    ERR(BOOK(t,F+"T"+at,"k-"+at),422,"not_on_slot_grid")
print("PASS")'`
Passes when: prints `PASS`. The grid runs in 30-minute steps from the 18:00 opening.
Status: unclaimed

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
Status: unclaimed

### C-52: A reservation that would end after closes is 422 outside_opening_hours.
Check: `python3 -c "$P"'
t,_=SETUP()
OK(BOOK(t,F+"T22:00","k1"),201)
for at in ["22:30","23:00"]:
    ERR(BOOK(t,F+"T"+at,"k-"+at,tid="t_3"),422,"outside_opening_hours")
print("PASS")'`
Passes when: prints `PASS`. 22:00 plus 90 minutes is exactly 23:30 and is allowed; 22:30 and 23:00 would end after the close and are refused even though both are on the grid.
Status: unclaimed

### C-53: A party_size above the table's capacity is 422 party_exceeds_capacity.
Check: `python3 -c "$P"'
t,_=SETUP()
ERR(BOOK(t,F+"T19:00","k1",tid="t_1",ps=3),422,"party_exceeds_capacity")
ERR(BOOK(t,F+"T19:00","k2",tid="t_2",ps=5),422,"party_exceeds_capacity")
OK(BOOK(t,F+"T19:00","k3",tid="t_1",ps=2),201)
print("PASS")'`
Passes when: prints `PASS`. Exactly the capacity is allowed; one more is refused.
Status: unclaimed

### C-54: A party_size below 1 or not an integer is 422 validation_failed.
Check: `python3 -c "$P"'
t,_=SETUP()
for i,ps in enumerate([0,-1,"4",4.5,True,False,None,[4],{"n":4},"four",""]):
    ERR(BOOK(t,F+"T19:00","k%d"%i,ps=ps),422,"validation_failed")
print("PASS")'`
Passes when: prints `PASS`. Strings and booleans are 422 `validation_failed` here, not 400 — the endpoint-specific rule of §5 takes precedence.
Status: unclaimed

### C-55: A starts_at_local that is not a bare local YYYY-MM-DDTHH:MM is 422 validation_failed.
Check: `python3 -c "$P"'
t,_=SETUP()
bad=[F+"T19:00:00",F+"T19:00Z",F+"T19:00:00+02:00",F+" 19:00",F+"T19",F,"19:00",F+"T19:00:00.000",""]
for i,at in enumerate(bad):
    ERR(BOOK(t,at,"k%d"%i),422,"validation_failed")
print("PASS")'`
Passes when: prints `PASS`. Seconds, a `Z`, an explicit offset and a space separator are all refused.
Status: unclaimed

### C-56: An unknown restaurant, an unknown table, or a table of another restaurant is 404 not_found.
Check: `python3 -c "$P"'
RESET(FX(restaurants=[REST(),DSTR("America/New_York",rid="r_ny",opens="18:00",closes="23:30")]))
t=LOGIN(ADA)
ERR(BOOK(t,F+"T19:00","k1",rid="r_nope"),404,"not_found")
ERR(BOOK(t,F+"T19:00","k2",tid="t_nope"),404,"not_found")
ERR(BOOK(t,F+"T19:00","k3",rid="r_ny",tid="t_2"),404,"not_found")
print("PASS")'`
Passes when: prints `PASS`. The third case names a table id that exists, but under a different restaurant.
Status: unclaimed

### C-57: An unparseable request body is 400 malformed_request.
Check: `python3 -c "$P"'
t,_=SETUP()
for raw in [b"{not json",b"",b"[]",b"null",b"\"string\"",b"{\"a\":}"]:
    s,b,_=R("POST","/reservations",raw,tok=t,key="k1")
    assert s==400 and b.get("error",{}).get("code")=="malformed_request",(raw,s,b)
print("PASS")'`
Passes when: prints `PASS`. A body that does not parse, and a parsed value that is not a JSON object, are both 400 `malformed_request`.
Status: unclaimed

### C-58: A booking is not refused merely because its start is in the past.
Check: `python3 -c "$P"'
t,_=SETUP()
b=OK(BOOK(t,"2020-06-10T19:00","k1"),201)
assert b["status"]=="confirmed" and b["starts_at_local"]=="2020-06-10T19:00",b
assert "2020-06-10T19:00" in SLOTS("r_anker","2020-06-10",4)
print("PASS")'`
Passes when: prints `PASS`. 2020-06-10 is a Wednesday and open in the fixture; the booking is confirmed despite being years in the past.
Status: unclaimed

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
Status: unclaimed

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
Status: unclaimed

### C-61: An empty reservation list is returned as an empty array.
Check: `python3 -c "$P"'
ta,_=SETUP()
b=OK(LIST(ta),200)
assert b=={"reservations":[]},b
print("PASS",b)'`
Passes when: prints `PASS {'reservations': []}` — the key is present with an empty array, not omitted and not null.
Status: unclaimed

### C-62: GET /reservations/{reference} returns the caller's booking and 404 for anyone else's.
Check: `python3 -c "$P"'
ta,tb=SETUP()
a=OK(BOOK(ta,F+"T19:00","a1"),201)
got=OK(GETR(ta,a["reference"]),200)
assert got["reference"]==a["reference"] and got["reservation_id"]==a["reservation_id"],got
ERR(GETR(tb,a["reference"]),404,"not_found")
print("PASS")'`
Passes when: prints `PASS`. The other account gets 404 `not_found`, not 403 — the existence of the booking is not disclosed.
Status: unclaimed

### C-63: An unknown reference is 404 not_found.
Check: `python3 -c "$P"'
ta,_=SETUP()
for ref in ["ZZZZZZ","ABC123","nope","z"*100]:
    ERR(GETR(ta,ref),404,"not_found")
print("PASS")'`
Passes when: prints `PASS`.
Status: unclaimed

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
Status: unclaimed

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
Status: unclaimed

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
Status: unclaimed

### C-67: Cancelling a reservation whose start has already passed is 409 cutoff_passed.
Check: `python3 -c "$P"'
RESET(FX(reservations=[SEED("SEED01","2020-06-10T19:00")]))
ta=LOGIN(ADA)
ERR(CANCEL(ta,"SEED01"),409,"cutoff_passed")
assert OK(GETR(ta,"SEED01"),200)["status"]=="confirmed"
print("PASS")'`
Passes when: prints `PASS`. "Within the cutoff of `starts_at`, or later" covers a start in the past.
Status: unclaimed

### C-68: Cancelling someone else's reservation is 404 not_found.
Check: `python3 -c "$P"'
ta,tb=SETUP()
a=OK(BOOK(ta,F+"T19:00","a1"),201)
ERR(CANCEL(tb,a["reference"]),404,"not_found")
assert OK(GETR(ta,a["reference"]),200)["status"]=="confirmed"
print("PASS")'`
Passes when: prints `PASS`.
Status: unclaimed

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
Status: unclaimed

### C-70: PATCH requires no idempotency key.
Check: `python3 -c "$P"'
ta,_=SETUP()
a=OK(BOOK(ta,F+"T19:00","a1"),201)
s,b,_=R("PATCH","/reservations/"+a["reference"],{"party_size":2},tok=ta)
assert s==200,(s,b)
print("PASS")'`
Passes when: prints `PASS`. No `Idempotency-Key` header was sent and the amendment still succeeded.
Status: unclaimed

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
Status: unclaimed

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
Status: unclaimed

### C-73: PATCH onto a table taken for an overlapping interval is 409 table_unavailable.
Check: `python3 -c "$P"'
ta,_=SETUP()
a=OK(BOOK(ta,F+"T19:00","a1",tid="t_2"),201)
OK(BOOK(ta,F+"T19:00","a2",tid="t_3"),201)
ERR(PATCHR(ta,a["reference"],{"table_id":"t_3"}),409,"table_unavailable")
print("PASS")'`
Passes when: prints `PASS`.
Status: unclaimed

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
Status: unclaimed

### C-75: Amending a cancelled reservation is 409 reservation_cancelled.
Check: `python3 -c "$P"'
ta,_=SETUP()
a=OK(BOOK(ta,F+"T19:00","a1"),201)
OK(CANCEL(ta,a["reference"]),200)
ERR(PATCHR(ta,a["reference"],{"table_id":"t_3"}),409,"reservation_cancelled")
ERR(PATCHR(ta,a["reference"],{"party_size":2}),409,"reservation_cancelled")
print("PASS")'`
Passes when: prints `PASS`.
Status: unclaimed

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
Status: unclaimed

### C-77: Amending someone else's reservation is 404 not_found.
Check: `python3 -c "$P"'
ta,tb=SETUP()
a=OK(BOOK(ta,F+"T19:00","a1"),201)
ERR(PATCHR(tb,a["reference"],{"party_size":2}),404,"not_found")
ERR(PATCHR(tb,"ZZZZZZ",{"party_size":2}),404,"not_found")
print("PASS")'`
Passes when: prints `PASS`.
Status: unclaimed

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
Status: unclaimed

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
Status: unclaimed

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
Status: unclaimed

### C-81: An Idempotency-Key longer than 255 characters is 422 validation_failed.
Check: `python3 -c "$P"'
ta,_=SETUP()
body={"restaurant_id":"r_anker","table_id":"t_2","starts_at_local":F+"T19:00","party_size":4}
ERR(R("POST","/reservations",body,tok=ta,key="k"*256),422,"validation_failed")
ERR(R("POST","/reservations",body,tok=ta,key="k"*4000),422,"validation_failed")
OK(R("POST","/reservations",body,tok=ta,key="k"*255),201)
print("PASS")'`
Passes when: prints `PASS`. Exactly 255 characters is accepted and 256 is refused.
Status: unclaimed

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
Status: unclaimed

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
Status: unclaimed

### C-84: The same key with the same body on a different path is a different request and succeeds.
Check: `python3 -c "$P"'
ta,_=SETUP()
a=OK(BOOK(ta,F+"T19:00","shared-key",tid="t_2"),201)
s,b,_=R("POST","/reservation-moves",{"moves":[{"reference":a["reference"],"table_id":"t_3"}]},tok=ta,key="shared-key")
assert s==201,"moves with a key already used by POST /reservations: %s %r"%(s,b)
assert b["reservations"][0]["table_id"]=="t_3",b
print("PASS")'`
Passes when: prints `PASS`. A key spent on `POST /reservations` does not block `POST /reservation-moves`.
Status: unclaimed

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
Status: unclaimed

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
Status: unclaimed

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
Status: unclaimed

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
Status: unclaimed

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
Status: unclaimed

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
Status: unclaimed

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
Status: unclaimed

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
Status: unclaimed

### C-93: Local times skipped by Europe/Berlin's spring-forward never appear in availability.
Check: `python3 -c "$P"'
RESET(FX(restaurants=[DSTR("Europe/Berlin")]))
got=SLOTS("r_dst","2026-03-29",4)
want=["2026-03-29T"+t for t in ["01:00","01:30","03:00","03:30","04:00","04:30"]]
assert got==want,(got,want)
print("PASS",len(got))'`
Passes when: prints `PASS 6`. The 01:00-to-06:00 window yields six slots: the 02:00 and 02:30 steps are absent because those local times do not exist.
Status: unclaimed

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
Status: unclaimed

### C-95: Europe/Berlin's repeated hour resolves to the first occurrence.
Check: `python3 -c "$P"'
RESET(FX(restaurants=[DSTR("Europe/Berlin")]))
ta=LOGIN(ADA)
b=OK(BOOK(ta,"2026-10-25T02:00","k1",rid="r_dst",tid="t_2"),201)
assert b["starts_at"]=="2026-10-25T02:00:00+02:00","expected the pre-change offset, got %r"%b["starts_at"]
assert "t_2" not in FREE("r_dst","2026-10-25",4,"2026-10-25T02:00")
print("PASS",b["starts_at"])'`
Passes when: prints `PASS 2026-10-25T02:00:00+02:00`. The booking landed on the instant before the clocks changed, not the one after.
Status: unclaimed

### C-96: Booking a local time skipped by America/New_York's spring-forward is 422 invalid_local_time.
Check: `python3 -c "$P"'
RESET(FX(restaurants=[DSTR("America/New_York")]))
ta=LOGIN(ADA)
for at in ["02:00","02:30"]:
    ERR(BOOK(ta,"2026-03-08T"+at,"k-"+at,rid="r_dst"),422,"invalid_local_time")
OK(BOOK(ta,"2026-03-08T01:30","k-ok",rid="r_dst"),201)
print("PASS")'`
Passes when: prints `PASS`.
Status: unclaimed

### C-97: Local times skipped by America/New_York's spring-forward never appear in availability.
Check: `python3 -c "$P"'
RESET(FX(restaurants=[DSTR("America/New_York")]))
got=SLOTS("r_dst","2026-03-08",4)
want=["2026-03-08T"+t for t in ["01:00","01:30","03:00","03:30","04:00","04:30"]]
assert got==want,(got,want)
print("PASS",len(got))'`
Passes when: prints `PASS 6`.
Status: unclaimed

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
Status: unclaimed

### C-99: America/New_York's repeated hour resolves to the first occurrence.
Check: `python3 -c "$P"'
RESET(FX(restaurants=[DSTR("America/New_York")]))
ta=LOGIN(ADA)
b=OK(BOOK(ta,"2026-11-01T01:30","k1",rid="r_dst",tid="t_2"),201)
assert b["starts_at"]=="2026-11-01T01:30:00-04:00","expected the pre-change offset, got %r"%b["starts_at"]
print("PASS",b["starts_at"])'`
Passes when: prints `PASS 2026-11-01T01:30:00-04:00`.
Status: unclaimed

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
Status: unclaimed

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
Status: unclaimed

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
Status: unclaimed

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
Status: unclaimed

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
Status: unclaimed

### C-105: POST /_test/import accepts an unchanged export and returns 204, without authentication.
Check: `python3 -c "$P"'
ta,_=SETUP()
OK(BOOK(ta,F+"T19:00","k1"),201)
snap=EXPORT()
s,b,_=R("POST","/_test/import",snap)
assert s==204,(s,b)
print("PASS")'`
Passes when: prints `PASS`.
Status: unclaimed

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
Status: unclaimed

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
Status: unclaimed

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
Status: unclaimed

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
Status: unclaimed

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
Status: unclaimed

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
Status: unclaimed

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
Status: unclaimed

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
Status: unclaimed

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
Status: unclaimed

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
Status: unclaimed

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
Status: unclaimed

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
Status: unclaimed

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
Status: unclaimed

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
Status: unclaimed

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
Status: unclaimed

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
Status: unclaimed

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
Status: unclaimed

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
Status: unclaimed

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
Status: unclaimed

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
Status: unclaimed

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
Status: unclaimed

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
Status: unclaimed

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
Status: unclaimed

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
Status: unclaimed

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
Status: unclaimed

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
Status: unclaimed

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
Status: unclaimed

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
Status: unclaimed

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
Status: unclaimed

### C-135: A rejected batch leaves its idempotency key reusable.
Check: `python3 -c "$P"'
ta,_=SETUP()
a=OK(BOOK(ta,F+"T19:00","k1",tid="t_2"),201)
ERR(MOVES(ta,"m1",[{"reference":a["reference"],"starts_at_local":F+"T19:15"}]),422,"not_on_slot_grid")
r=OK(MOVES(ta,"m1",[{"reference":a["reference"],"table_id":"t_3"}]),201)
assert r["reservations"][0]["table_id"]=="t_3",r
print("PASS")'`
Passes when: prints `PASS`. The key spent on a refused batch is a first use again, so the later different body is accepted rather than reported as reuse.
Status: unclaimed

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
Status: unclaimed

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
Status: unclaimed

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
Status: unclaimed

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
Status: unclaimed

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
Status: passed — verdicts/C-142.md at 849f5ae

### C-143: At run time the service has no outbound network access, and still serves /health.
Check: `docker rm -f tk-c143 >/dev/null 2>&1; docker network rm tk-c143-noout >/dev/null 2>&1; docker network create --internal tk-c143-noout && test "$(docker network inspect tk-c143-noout --format '{{.Internal}}')" = "true" && docker build -q -t tk-s1 /Users/aashanjaved/band-work/result/stage-1 >/dev/null && docker run -d --name tk-c143 --network tk-c143-noout -e PORT=8080 tk-s1 >/dev/null && for i in $(seq 1 60); do docker run --rm --network tk-c143-noout alpine:3 wget -qO- -T3 http://tk-c143:8080/health >/dev/null 2>&1 && break; sleep 1; done; docker run --rm --network tk-c143-noout alpine:3 sh -c 'wget -qO- -T5 http://tk-c143:8080/health || exit 1; nslookup example.com >/dev/null 2>&1 && exit 2; nc -w4 -z 1.1.1.1 80 2>/dev/null && exit 3; wget -qO- -T4 http://example.com >/dev/null 2>&1 && exit 4; echo " NO EGRESS"'; r=$?; docker rm -f tk-c143 >/dev/null 2>&1; docker network rm tk-c143-noout >/dev/null 2>&1; exit $r`
Passes when: exits 0 and prints the `/health` body followed by `NO EGRESS`. Replaces C-2. The service is attached only to an internal network and publishes no port; it is reached by container name from a sibling `alpine:3` container, the way the graded harness reaches it in isolated mode. Exit 1 means the service did not answer, 2 that DNS resolved, 3 that a raw TCP connection opened, 4 that an HTTP fetch succeeded. Because the probe runs in a container whose tools are guaranteed and must print the service's own health body to pass, it cannot pass by a tool being absent. `alpine:3` is pulled once during setup; the no-outbound rule constrains the service, not the auditor's tooling.
Status: unclaimed

### C-144: The service listens on the port given in the PORT environment variable.
Check: `docker rm -f tk-c144 >/dev/null 2>&1; docker network rm tk-c144-net >/dev/null 2>&1; docker network create tk-c144-net >/dev/null && docker run -d --name tk-c144 --network tk-c144-net -p 18081:9091 -e PORT=9091 tk-s1 >/dev/null && for i in $(seq 1 60); do curl -fsS http://127.0.0.1:18081/health && break; sleep 1; done; r=$?; docker rm -f tk-c144 >/dev/null 2>&1; docker network rm tk-c144-net >/dev/null 2>&1; exit $r`
Passes when: exits 0 and prints the `/health` body. Replaces C-3. The container port is 9091, not 8080, so a hard-coded port cannot pass.
Status: unclaimed

### C-145: The service listens on port 8080 when PORT is not set.
Check: `docker rm -f tk-c145 >/dev/null 2>&1; docker network rm tk-c145-net >/dev/null 2>&1; docker network create tk-c145-net >/dev/null && docker run -d --name tk-c145 --network tk-c145-net -p 18082:8080 tk-s1 >/dev/null && for i in $(seq 1 60); do curl -fsS http://127.0.0.1:18082/health && break; sleep 1; done; r=$?; docker rm -f tk-c145 >/dev/null 2>&1; docker network rm tk-c145-net >/dev/null 2>&1; exit $r`
Passes when: exits 0 and prints the `/health` body. Replaces C-4. No `-e PORT` is passed, so the service must default to 8080.
Status: unclaimed

### C-146: The graded stage-1 suite passes in the mode grading uses.
Check: `cd /Users/aashanjaved/dark-factory-wearedevs && ./.venv/bin/python -m harness run --track tablekeeper --repo /Users/aashanjaved/band-work/result --stage 1 --mode isolated --out /Users/aashanjaved/band-work/checks/s1-iso-$(date +%s)`
Passes when: the harness exits 0 and its summary reports zero failures and zero errors for stage 1. Replaces C-141. `--mode isolated` is the grading mode: the service gets no outbound access and is reached by container name. A pass here, unlike a pass in host mode, cannot be earned by a service that fetches something at run time.
Status: unclaimed

### C-147: The shipped stage-1 checks pass in the mode grading uses.
Check: `cd /Users/aashanjaved/dark-factory-wearedevs && ./.venv/bin/python -m harness run --track tablekeeper --repo /Users/aashanjaved/band-work/result --stage 1 --mode isolated --out /Users/aashanjaved/band-work/checks/s1-iso-shipped-$(date +%s)`
Passes when: the harness exits 0 and its summary reports zero failures and zero errors for stage 1. Replaces C-140. Host mode is still useful while developing, but per the harness's own warning it must never be the basis of a pass, so no entry in this ledger claims anything from it.
Status: unclaimed

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
