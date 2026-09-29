# Running Tablekeeper (stage 1)

Docker is the only prerequisite. Run the block below from this directory
(`stage-1/`). It builds the image and starts the service, with no manual setup
and no editing.

The container is attached to an `--internal` Docker network, so it has no
outbound network access while serving. The published port stays reachable from
the host. The service listens on the port named by `PORT` and defaults to 8080.

```sh
docker rm -f tk-s1 >/dev/null 2>&1 || true
docker network create --internal tk-s1-noout >/dev/null 2>&1 || true
docker build -t tk-s1 .
docker run -d --name tk-s1 --network tk-s1-noout -p 18080:8080 -e PORT=8080 tk-s1
```

The service answers on <http://127.0.0.1:18080>. It is ready once
`GET /health` returns `200 {"status": "ok"}`.

To stop it afterwards, run `docker rm -f tk-s1` and then
`docker network rm tk-s1-noout`.
