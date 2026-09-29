# Running Tablekeeper (stage 1)

Docker is the only prerequisite. Run the block below from this directory
(`stage-1/`). It builds the image and starts the service, with no manual setup
and no editing.

```sh
docker rm -f tk-s1 >/dev/null 2>&1 || true
docker network create tk-s1-net >/dev/null 2>&1 || true
docker build -t tk-s1 .
docker run -d --name tk-s1 --network tk-s1-net -p 18080:8080 -e PORT=8080 tk-s1
```

The service answers on <http://127.0.0.1:18080>. It is ready once
`GET /health` returns `200 {"status": "ok"}`, which takes a second or two.

The service listens on the port named by `PORT` and defaults to 8080. To use a
different published port, change the `-p` mapping; to use a different container
port, pass a different `-e PORT`.

To stop it afterwards, run `docker rm -f tk-s1` and then
`docker network rm tk-s1-net`.

## Outbound network

The image needs no outbound access at run time: it is Python standard library
only, and the IANA timezone database is installed during `docker build`. Nothing
is fetched while serving.

The command above uses an ordinary bridge network, because a published port is
how you reach the service from the host. Docker will not publish a port for a
container whose only network is `--internal`, so the two cannot be combined on
one network. To confirm the service runs with no outbound access, attach it to
an internal network and reach it by container name from a sibling container on
that same network instead of through a published port — which is how the grading
harness exercises it.
