# Deploying FlowBlow to Google Cloud Run

FlowBlow ships with a [`Dockerfile`](../Dockerfile) that bundles everything the
renderer needs (Pillow, matplotlib, the vendored Caveat font, and a colour
emoji font) and serves the API with uvicorn on `$PORT`. That makes it a
one-command deploy to Cloud Run.

## Prerequisites

```bash
gcloud auth login
gcloud config set project YOUR_PROJECT_ID
gcloud services enable run.googleapis.com cloudbuild.googleapis.com artifactregistry.googleapis.com
```

## Option A — deploy straight from source (simplest)

Cloud Run builds the image from the `Dockerfile` for you:

```bash
gcloud run deploy flowblow \
  --source . \
  --region us-central1 \
  --allow-unauthenticated \
  --memory 2Gi \
  --cpu 2 \
  --concurrency 8 \
  --timeout 120
```

When it finishes, `gcloud` prints the service URL. Test it:

```bash
URL=$(gcloud run services describe flowblow --region us-central1 --format='value(status.url)')
curl "$URL/healthz"
curl "$URL/examples/architecture.png" -o out.png
open "$URL/"          # the interactive playground
```

## Option B — build the image yourself, then deploy

```bash
# Build & push with Cloud Build
gcloud builds submit --tag gcr.io/$(gcloud config get-value project)/flowblow

# Deploy that image
gcloud run deploy flowblow \
  --image gcr.io/$(gcloud config get-value project)/flowblow \
  --region us-central1 \
  --allow-unauthenticated \
  --memory 2Gi --cpu 2 --concurrency 8
```

You can also build locally and test before pushing:

```bash
docker build -t flowblow .
docker run --rm -p 8080:8080 flowblow
curl localhost:8080/examples/simple.png -o out.png
```

## Recommended settings & why

| Flag | Suggested | Reason |
|------|-----------|--------|
| `--memory` | `2Gi` | A 2160×3840 PNG is supersampled during drawing; peak RAM per request is a few hundred MB. `1Gi` works for smaller frames/scales. |
| `--cpu` | `2` | Layout + Pillow drawing is CPU-bound; 2 vCPU keeps renders well under a second. |
| `--concurrency` | `4`–`8` | Each in-flight render holds a large image in memory; low concurrency avoids OOM. Cloud Run scales out horizontally instead. |
| `--timeout` | `120` | Generous; renders are typically < 1 s. |
| `--min-instances` | `0` | Scale to zero when idle (default). Set `1` to avoid cold starts. |

## Cold starts

The image pre-builds matplotlib's font cache and warms the LaTeX renderer at
**build** time, so the first request only pays for process start (~1–3 s).
Set `--min-instances 1` if you need consistently low latency.

## Locking it down

`--allow-unauthenticated` makes the service public. To require auth instead:

```bash
gcloud run deploy flowblow --source . --no-allow-unauthenticated ...
# then call with an identity token:
curl -H "Authorization: Bearer $(gcloud auth print-identity-token)" "$URL/examples/simple.png" -o out.png
```

## Continuous deploy (optional)

[`cloudbuild.yaml`](../cloudbuild.yaml) builds the image and deploys it. Wire it
to a Cloud Build trigger on your repo, or run it manually:

```bash
gcloud builds submit --config cloudbuild.yaml \
  --substitutions=_REGION=us-central1,_SERVICE=flowblow
```

## Environment variables

| Variable | Effect |
|----------|--------|
| `PORT` | Port to listen on (set automatically by Cloud Run). |
| `MPLCONFIGDIR` | matplotlib cache dir (defaults to `/opt/mplcache` in the image). |
| `FLOWBLOW_CHROMIUM` | Unused by the PNG path; only relevant to the optional HTML/browser flow. |
