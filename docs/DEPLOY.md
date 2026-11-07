# Deploy the live demo

The demo image in `deploy/demo/` runs the API and the Streamlit page behind one port. It needs no database or queue.

## Settings

Set these as secrets on your host, never in the repo.

| Setting | Value |
|---|---|
| `LLM_API_KEY` | A key on a plan that doesn't train on prompts |
| `LLM_BASE_URL` | `https://generativelanguage.googleapis.com/v1beta/openai` for Gemini |
| `LLM_MODEL` | `gemini-3.1-flash-lite`, the model the accuracy results used |
| `MAX_EML_ATTACHMENTS` | `4`, because one `.eml` counts as one request against the daily limit but makes one model call per document |
| `INTERNAL_API_TOKEN` | A long random value. The image refuses to start without it |
| `DAILY_EXTRACT_LIMIT` | The most extract requests per day. Defaults to 200 |

## Cost

`DAILY_EXTRACT_LIMIT` is the spending safety. A request can make several model calls, and retried calls can add more. In our evaluation, 68 calls cost about ₹1 by our estimate, so the default should stay small. It counts per running copy and resets on restart, so also set a budget alert in your Google billing account.

## Hosting on Google Cloud Run (recommended)

Cloud Run builds the image from the repo, gives an HTTPS address, and costs little at demo traffic. The app needs about 1 GB of memory for the spaCy model, so give it 2 GiB. Run these in Google Cloud Shell, where `gcloud` is already signed in.

1. Turn on the services and get the code:

```bash
gcloud services enable run.googleapis.com cloudbuild.googleapis.com artifactregistry.googleapis.com secretmanager.googleapis.com
```

```bash
git clone https://github.com/nivedhitaramu/meridian-ocr-connector.git && cd meridian-ocr-connector && cp deploy/demo/Dockerfile Dockerfile
```

2. Store the two secrets. Paste the key when asked, and the token is generated:

```bash
read -s -p "Gemini key: " KEY && printf %s "$KEY" | gcloud secrets create meridian-llm-key --data-file=-
```

```bash
openssl rand -hex 32 | tr -d '
' | gcloud secrets create meridian-internal-token --data-file=-
```

3. Let Cloud Run read them:

```bash
PROJECT_NUMBER=$(gcloud projects describe "$(gcloud config get-value project)" --format='value(projectNumber)') && for s in meridian-llm-key meridian-internal-token; do gcloud secrets add-iam-policy-binding $s --member="serviceAccount:${PROJECT_NUMBER}-compute@developer.gserviceaccount.com" --role=roles/secretmanager.secretAccessor; done
```

4. Deploy. The first build takes about 10 minutes:

```bash
gcloud run deploy meridian-demo --source . --region asia-south1 --memory 2Gi --cpu 2 --cpu-boost --max-instances 1 --timeout 300 --allow-unauthenticated --set-env-vars LLM_BASE_URL=https://generativelanguage.googleapis.com/v1beta/openai,LLM_MODEL=gemini-3.1-flash-lite,DAILY_EXTRACT_LIMIT=50,MAX_EML_ATTACHMENTS=4 --set-secrets LLM_API_KEY=meridian-llm-key:latest,INTERNAL_API_TOKEN=meridian-internal-token:latest
```

It prints the service URL, which is the live demo link. `--max-instances 1` and `DAILY_EXTRACT_LIMIT=50` cap the model spend.

**Other hosts:** any host that runs a Docker image with 2 GB of memory and HTTPS works. On a VM, run `docker build -f deploy/demo/Dockerfile -t meridian-demo .`, then `docker run -d --restart unless-stopped --env-file .env -p 7860:7860 meridian-demo`, and put an HTTPS proxy in front of port 7860. Hugging Face Docker Spaces now need a paid plan.

## Check it

1. Open `/healthz` and expect `{"ok":true}`.
2. Upload `samples/S02_invoice.pdf` and `samples/S02_packing.pdf`, and expect Match.
3. Open `/v1/metrics` without the token, and expect a 401.

Use synthetic documents only.
