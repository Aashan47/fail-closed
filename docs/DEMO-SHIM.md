# The live demo, and the one thing it adds

**https://tablekeeper.aashanjaved.com** runs `stage-2/app.py` from this repository, byte-identical.

Two things sit beside it so a judge does not have to set anything up. Neither is part of the
submitted service and neither changes it.

**`seed.py`** starts `app.py` unchanged and then seeds one restaurant by POSTing to the service's
own public `/_test/reset`, exactly as any client would. The service starts empty by design, and an
empty restaurant list is a poor first screen.

**`demoproxy.py`** is a reverse proxy in front of the service. It passes every request and response
through untouched except for one injected `<script>` in HTML documents, which pre-fills the sign-in
form with the seeded account and says so on the page. Judges can press Sign in without inventing an
account, or use "Create an account" and make their own.

Both exist so that **`stage-2/app.py` never had to be edited for the demo**. The code that runs at
that URL is the code in this repository. Sign-in is still required to book, as the specification
demands; the shim only saves typing.

Demo account: `ada@example.com` / `correct horse`.
