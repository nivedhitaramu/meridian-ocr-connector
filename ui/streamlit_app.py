"""Receiving-clerk page. Talks to the FastAPI service, so the page and API return the same object."""
import os

import requests
import streamlit as st

API_URL = os.getenv("API_URL", "http://localhost:8000")
INTERNAL_HEADERS = {"X-Internal-Token": os.getenv("INTERNAL_API_TOKEN", "")}
STATUS_STYLE = {
    "Match": ("✅", "green"), "Mismatch": ("❌", "red"),
    "Incomplete": ("⚠️", "orange"), "Not applicable": ("➖", "gray"),
}
LABELS = {"commercial_invoice": "Commercial invoice", "packing_list": "Packing list",
          "delivery_receipt": "Delivery receipt", "unknown": "Unknown"}


def _cell(value) -> str:
    return "Not found" if value is None else str(value)


st.set_page_config(page_title="Meridian Freight · Receiving check", page_icon="📦", layout="wide")
st.title("📦 Meridian Freight — receiving check")
st.caption("Upload the commercial invoice and the packing list. A delivery receipt on its own is accepted too. "
           "PDF, PNG or JPEG, up to 10 MB each. Synthetic documents only.")

mode = st.radio("Input", ["Upload files", "Email (.eml)"], horizontal=True, label_visibility="collapsed")

result = None
if mode == "Upload files":
    c1, c2 = st.columns(2)
    f1 = c1.file_uploader("Document 1 (e.g. commercial invoice)", type=["pdf", "png", "jpg", "jpeg"])
    f2 = c2.file_uploader("Document 2 (e.g. packing list) — optional", type=["pdf", "png", "jpg", "jpeg"])
    if st.button("Check shipment", type="primary", disabled=f1 is None):
        files = {"file": ("upload", f1.getvalue())}  # we never send the real filename
        if f2 is not None:
            files["file2"] = ("upload", f2.getvalue())
        with st.spinner("Reading documents…"):
            r = requests.post(f"{API_URL}/v1/extract", files=files, timeout=180)
        result = r.json() if r.ok else {"error": r.json().get("error", "Could not read this document.")}
else:
    fe = st.file_uploader("Email with attachments", type=["eml"])
    if st.button("Check email", type="primary", disabled=fe is None):
        with st.spinner("Reading attachments…"):
            r = requests.post(f"{API_URL}/v1/extract-eml", files={"file": ("upload.eml", fe.getvalue())}, timeout=300)
        result = r.json() if r.ok else {"error": r.json().get("error", "Could not read this document.")}

if result:
    if "error" in result:
        st.error(result["error"])
    else:
        icon, color = STATUS_STYLE[result["check"]["status"]]
        st.markdown(f"## {icon} :{color}[{result['check']['status']}]")
        st.write(result["check"]["reason"])

        cols = st.columns(len(result["documents"]))
        for col, doc in zip(cols, result["documents"]):
            with col:
                st.subheader(f"{doc['slot']}. {LABELS[doc['document_type']]}")
                f = doc["fields"]
                qty = f["total_quantity"]
                st.table({
                    "Field": ["Invoice / ref", "Shipper", "Receiver", "Date", "Total quantity", "Total weight (kg)"],
                    "Value": [_cell(f["invoice_number"]), _cell(f["shipper_name"]), _cell(f["receiver_name"]),
                              _cell(f["shipment_date"]),
                              f"{qty:,} {doc['quantity_unit'] or ''}".strip() if qty is not None else "Not found",
                              _cell(f["total_weight_kg"])],
                })
                if doc["used_vision_fallback"]:
                    st.info("Read via redacted-image fallback.")

        st.divider()
        st.subheader("Trace — last request")
        t = result["pipeline"]["timings_ms"]
        m = st.columns(5)
        for i, stage in enumerate(["ocr", "pii", "llm", "rule"]):
            m[i].metric(stage.upper(), f"{t.get(stage, 0)} ms")
        m[4].metric("Status", result["check"]["status"])
        st.write("**Entities masked before the model call:**", result["pii"]["entity_counts"] or "none")
        st.caption(f"request_id {result['request_id']} · model {result['pipeline']['model']} · "
                   f"masked_before_llm={result['pii']['masked_before_llm']}")
        with st.expander("Server trace events (sanitized)"):
            try:
                st.json(requests.get(f"{API_URL}/v1/trace/last", headers=INTERNAL_HEADERS, timeout=10).json())
            except requests.RequestException:
                st.write("Trace unavailable.")
        with st.expander("Raw JSON response"):
            st.json(result)
