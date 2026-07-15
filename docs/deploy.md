# Deploying FlowBlow to Google Cloud Run

FlowBlow serves standalone HTML/SVG diagrams through FastAPI and uvicorn. The
Docker image includes the bundled Caveat font and a colour emoji font.

## Prerequisites

```bash
gcloud auth login
gcloud config set project YOUR_PROJECT_ID
gcloud services enable run.googleapis.com cloudbuild.googleapis.com artifactregistry.googleapis.com
```

## Deploy From Source

```bash
gcloud run deploy flowblow \
  --source . \
  --region us-central1 \
  --allow-unauthenticated \
  --memory 512Mi \
  --cpu 1 \
  --concurrency 40 \
  --timeout 60
```

Test it:

```bash
URL=$(gcloud run services describe flowblow --region us-central1 --format='value(status.url)')
curl "$URL/healthz"
curl "$URL/examples/architecture.html" > out.html
```

## Build Then Deploy

```bash
gcloud builds submit --tag gcr.io/$(gcloud config get-value project)/flowblow

gcloud run deploy flowblow \
  --image gcr.io/$(gcloud config get-value project)/flowblow \
  --region us-central1 \
  --allow-unauthenticated \
  --memory 512Mi --cpu 1 --concurrency 40
```

## Settings

| Flag | Suggested | Reason |
| --- | --- | --- |
| `--memory` | `512Mi` | HTML rendering is lightweight. |
| `--cpu` | `1` | Layout is CPU-bound but short. |
| `--concurrency` | `20`-`40` | Requests do not allocate large image buffers. |
| `--timeout` | `60` | Renders are normally sub-second. |
| `--min-instances` | `0` | Scale to zero when idle. |

## Environment Variables

| Variable | Effect |
| --- | --- |
| `PORT` | Port to listen on, set automatically by Cloud Run. |
