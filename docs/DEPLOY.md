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

## Hosting

The app needs enough memory for the spaCy model, which rules out very small free plans. Any host that runs a Docker image and provides HTTPS works, such as Hugging Face Spaces (Docker) or a small VM. Check the current limits and terms of whichever you choose.

**Hugging Face Spaces:**
1. Create a Docker Space, set to public so graders can open it.
2. Add the settings above as secrets.
3. Copy `deploy/demo/Dockerfile` to the Space's root as `Dockerfile`, and push the repo there.

**A VM with Docker:**

```bash
docker build -f deploy/demo/Dockerfile -t meridian-demo .
```

```bash
docker run -d --restart unless-stopped --env-file .env -p 7860:7860 meridian-demo
```

Then put an HTTPS proxy in front of port 7860.

## Check it

1. Open `/healthz` and expect `{"ok":true}`.
2. Upload `samples/S02_invoice.pdf` and `samples/S02_packing.pdf`, and expect Match.
3. Open `/v1/metrics` without the token, and expect a 401.

Use synthetic documents only.
