import streamlit as st
import os
import json
import pandas as pd
import pypdf
import io
from datetime import datetime
from dotenv import load_dotenv

load_dotenv()

from data_processing.extractor import extract_partners, CACHE_DIR
from data_visualization.charts import chart_by_category, chart_by_mentions
from data_export.exporter import export_to_excel
from utils.validators import is_valid_pdf

st.set_page_config(
    page_title="PDF Partner Analyzer",
    page_icon=None,
    layout="wide",
)

st.markdown("""
<style>
footer { visibility: hidden; }
[data-testid="stFileUploaderDropzoneInstructions"] { display: none; }
.hist { padding:10px; background:#f8f9fa; border-radius:6px; margin-bottom:8px; border-left:3px solid #2d6a4f; }
.hist b { font-size:0.85rem; }
.hist small { color:#888; font-size:0.75rem; }
</style>
""", unsafe_allow_html=True)

def get_cache_history():
    if not os.path.exists(CACHE_DIR):
        return []
    history = []
    for fname in os.listdir(CACHE_DIR):
        if fname.endswith(".json") and not fname.endswith(".meta.json"):
            fpath = os.path.join(CACHE_DIR, fname)
            try:
                with open(fpath, "r", encoding="utf-8") as f:
                    data = json.load(f)
                mtime = os.path.getmtime(fpath)
                meta_path = fpath.replace(".json", ".meta.json")
                filename = fname[:16] + "..."
                if os.path.exists(meta_path):
                    with open(meta_path) as mf:
                        filename = json.load(mf).get("filename", filename)
                pages_path = fpath.replace(".json", ".pages.json")
                history.append({
                    "filename": filename,
                    "hash": fname.replace(".json", ""),
                    "partners": len(data),
                    "active": sum(1 for p in data if p.get("status") == "Active"),
                    "date": datetime.fromtimestamp(mtime).strftime("%d %b %Y, %H:%M"),
                    "has_pages": os.path.exists(pages_path),
                    "cache_path": fpath,
                })
            except Exception:
                pass
    return sorted(history, key=lambda x: x["date"], reverse=True)[:5]


# ── Sidebar ─-
with st.sidebar:
    st.markdown("## PDF Partner Analyzer")
    st.markdown("*IFAD Partner Extraction App*")
    st.divider()
    st.markdown("#### Upload the document")
    st.caption("Supported format: PDF with selectable text")
    uploaded_file = st.file_uploader(
        "Drop your PDF here or click to browse",
        type=["pdf"],
        label_visibility="collapsed"
    )
    history = get_cache_history()
    if history:
        st.divider()
        st.markdown("**Recent documents**")
        for item in history:
            st.markdown(
                f'<div class="hist"><b>{item["filename"]}</b><br>'
                f'<small>{item["partners"]} partners · {item["active"]} active · {item["date"]}</small></div>',
                unsafe_allow_html=True
            )

# ── Session state ──
if "partners" not in st.session_state:
    st.session_state.partners = []
if "pages" not in st.session_state:
    st.session_state.pages = []

# ── Processing ──
if uploaded_file:
    valid, error = is_valid_pdf(uploaded_file)
    if not valid:
        st.error(error)
        st.stop()

    file_key = f"{uploaded_file.name}_{uploaded_file.size}"
    if st.session_state.get("file_key") != file_key:
        st.session_state.partners = []
        st.session_state.pages = []
        st.session_state.pop("summary", None)
        st.session_state.file_key = file_key

       # Read pages for the Content tab
        uploaded_file.seek(0)
        reader = pypdf.PdfReader(io.BytesIO(uploaded_file.read()))
        st.session_state.pages = [p.extract_text() or "" for p in reader.pages]

        with st.spinner("Analysing document… "):
            try:
                partners = extract_partners(uploaded_file)
                st.session_state.partners = partners
            except Exception as e:
                st.session_state.file_key = None
                st.error(f"Extraction failed: {e}")
                st.stop()

# ── Dashboard ──
partners = st.session_state.partners

if partners:

    st.markdown("# PDF Partner Analyzer")
    st.markdown(
        f"**Document:** {uploaded_file.name if uploaded_file else ''} &nbsp;·&nbsp; "
        f"**{len(partners)} partner organisations extracted** &nbsp;·&nbsp; "
        f"*Powered by Mistral Small (mistral-small-latest)*"
    )
    st.divider()

    tab1, tab2, tab3 = st.tabs(["Partners", "Document Content", "Summary"])

    # ── Tab 1 : Partners ──
    with tab1:

        # KPIs
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Total Partners", len(partners),
                  help="Total number of partner organisations extracted from the document")
        c2.metric("Categories", len(set(p["category"] for p in partners)),
                  help="Number of distinct organisation types")
        c3.metric("Active", sum(1 for p in partners if p["status"] == "Active"),
                  help="Active: currently engaged partner; \nPotential: partnership being explored; \nInactive: past partner")
        c4.metric("Mentioned in text", sum(1 for p in partners if p["mention_count"] > 0),
                  help="Partners found at least once in the document text")

        st.divider()

        # Graphics
        st.markdown("### Charts")
        col_pie, col_bar = st.columns(2, gap="large")
        with col_pie:
            chart_by_category(partners)
        with col_bar:
            with st.container(height=400):
                chart_by_mentions(partners)

        st.divider()

        # Filters
        st.markdown("### Partners")
        fc1, fc2, fc3, fc4 = st.columns([3, 2, 1, 3])

        all_categories = sorted(set(p["category"] for p in partners))
        sel_cat = fc1.multiselect("Category", all_categories, default=all_categories)

        all_statuses = sorted(set(p["status"] for p in partners))
        sel_sta = fc2.multiselect("Status", all_statuses, default=all_statuses)

        max_m = max(p["mention_count"] for p in partners)
        min_m = fc3.number_input("Min. mentions", min_value=0, max_value=max_m, value=0)

        search = fc4.text_input("Search", placeholder="Search by name…")

        filtered = [
            p for p in partners
            if p["category"] in sel_cat
            and p["status"] in sel_sta
            and p["mention_count"] >= min_m
            and search.lower() in p["name"].lower()
        ]

        st.caption(f"{len(filtered)} of {len(partners)} partners — click a row to see details")

        # Table
        df = pd.DataFrame([{
            "#": i + 1,
            "Name": p["name"],
            "Category": p["category"],
            "Status": p["status"],
            "Mentions": p["mention_count"],
            "First page": int(p["first_page"]) if p.get("first_page") else None,
        } for i, p in enumerate(filtered)])

        selection = st.dataframe(
            df,
            use_container_width=True,
            hide_index=True,
            on_select="rerun",
            selection_mode="single-row",
            key="partner_table",
        )

        # Details
        rows = selection.selection.rows if selection and selection.selection else []
        if rows:
            idx = rows[0]
            p = filtered[idx]
            st.divider()
            c1, c2, c3 = st.columns(3)
            c1.markdown(f"**#{idx + 1} — {p['name']}**")
            c1.write(f"Category: {p['category']}")
            c1.write(f"Status: {p['status']}")
            c2.write(f"Mentions: {p['mention_count']}")
            if p.get("first_page"):
                c2.write(f"First page: {p['first_page']}")
            c2.write(f"Roles: {', '.join(p['roles']) if p.get('roles') else '—'}")
            c3.write(f"Sectors: {', '.join(p['sectors']) if p.get('sectors') else '—'}")
            if p.get("description"):
                st.info(p["description"])
            if p.get("evidence"):
                st.markdown("**Additional details:**")
                for snippet in p["evidence"]:
                    st.markdown(f"> *{snippet}*")

        st.divider()

        # Export
        st.markdown("### Export")
        excel_bytes = export_to_excel(partners)
        st.download_button(
            label="Download Excel Report",
            data=excel_bytes,
            file_name="cosop_partners.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )

    # ── Tab 2 : Document Content ──
    with tab2:
        st.markdown("### Document Content")
        pages = st.session_state.pages
        if uploaded_file:
            uploaded_file.seek(0)
            st.download_button(
                label="Download PDF",
                data=uploaded_file.read(),
                file_name=uploaded_file.name,
                mime="application/pdf"
            )
            st.divider()
        if pages:
            page_num = st.selectbox(
                "Page",
                options=list(range(1, len(pages) + 1)),
                format_func=lambda x: f"Page {x} of {len(pages)}"
            )
            st.text_area(
                "",
                value=pages[page_num - 1],
                height=500,
                label_visibility="collapsed"
            )
        else:
            st.info("No pages available.")

    # ── Tab 3 : Summary ──
    with tab3:
        st.markdown("### AI-Generated Summary")
        st.caption("Summarises country context, strategic objectives, target groups and key interventions.")

        if "summary" not in st.session_state:
            if st.button("Generate summary"):
                with st.spinner("Generating summary…"):
                    from data_processing.llm_client import _post_mistral
                    api_key = os.environ.get("API_KEY")
                    full_text = " ".join(st.session_state.pages)
                    messages = [
                        {
                            "role": "system",
                            "content": "An expert in international development. Summarise IFAD COSOP documents clearly and concisely."
                        },
                        {
                            "role": "user",
                            "content": f"""Provide a structured summary of this IFAD COSOP document in English.
Include the following sections:
1. Country and period
2. Country context and key challenges
3. Strategic objectives
4. Target groups
5. Main interventions and projects
6. Key partnerships

Be concise, with a maximum of 300 words.

DOCUMENT:
{full_text[:100000]}"""
                        }
                    ]
                    st.session_state.summary = _post_mistral(messages, api_key, max_tokens=1000)

        if "summary" in st.session_state:
            st.markdown(st.session_state.summary)

else:
    # ── Home ──
    st.markdown("# PDF Partner Analyzer")
    st.markdown("*Upload the PDF in the sidebar to extract and explore IFAD partner organisations.*")
    st.divider()
    col1, col2 = st.columns(2)
    with col1:
        st.markdown("""
        **How it works**

        1. Upload a PDF document
        2. Mistral AI identifies all partner organisations
        3. Explore partners with interactive charts and filters
        """)
    with col2:
        st.markdown("""
        **What you can do**

        - Filter partners by category and number of mentions
        - Click any partner to view its roles, sectors, description, and additional details
        - Read the document page by page
        - Generate an AI summary of the COSOP PDF
        - Export all results to Excel
        """)
    st.divider()
    st.markdown("**AI Model**")
    st.info(
        "This app uses **Mistral Small** (`mistral-small-latest`), a large language model (LLM) "
        "developed by Mistral AI. The model is pretrained and available as open source on Hugging Face. "
        "It analyzes the COSOP PDF to automatically identify, categorize, and extract partner organizations. "
        "Each partner is assigned a status (Active / Potential / Inactive) based on the context in which it appears in the document."
    )