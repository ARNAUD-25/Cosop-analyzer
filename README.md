# PDF Partner Analyzer

Interactive dashboard to extract and visualize IFAD partner organisations from COSOP documents using AI.

## Screenshots

![Home](screenshots/01_home.png)
![Dashboard](screenshots/02_dashboard.png)
![Detail](screenshots/03_detail.png)

## Installation

```bash
# 1. Clone the repo
git clone https://github.com/<your-username>/cosop-analyzer.git
cd cosop-analyzer

# 2. Create a virtual environment
python -m venv .venv
source .venv/bin/activate        # macOS / Linux
.venv\Scripts\activate           # Windows

# 3. Install dependencies
pip install -r requirements.txt

# 4. Configure API key
cp .env.example .env # Edit .env and add your Mistral API key

# 5. Run the application
python -m streamlit run app.py
```

Opens automatically on **http://localhost:8501**


## Environment variables

`API_KEY` — Mistral AI API key, free at https://console.mistral.ai/api-keys


## Project structure

```
cosop_analyzer/
│
├── app.py                         [ Streamlit UI (entry point) ]
│
├── data_processing/
│   ├── pdf_reader.py              [ Reads PDF text (pypdf) ]
│   ├── llm_client.py              [ Calls Mistral AI API ]
│   └── extractor.py               [ Orchestrates pipeline + cache ]
│
├── data_visualization/
│   └── charts.py                  [ Plotly charts ]
│
├── data_export/
│   └── exporter.py                [ Excel export ]
│
├── utils/
│   └── validators.py              [ PDF file validation ]
│
├── requirements.txt
├── .env.example
└── .gitignore
```

## Solution description

The pipeline works in 4 steps:

1. **PDF reading** : extracts all text from the uploaded COSOP document.

2. **AI extraction** : The document is split into chunks, and Mistral AI (`mistral-small-latest`) is called on each chunk to extract partner organisations. The document can be in any language; the model understands it and always returns results in English. For each partner, it extracts the name, category, status, roles, sectors, description, and supporting quotes.

3. **Deduplication** : normalizes organisation names (expands acronyms and merges variants) using a second LLM call, then applies fuzzy matching (85% threshold) and acronym-based merging.

4. **Additional processing** : counts mentions of each partner in the document, finds the first page where they appear, and extracts relevant sentences as evidence

Results are saved on disk for each document using an MD5 hash of the file content. Each COSOP document has its own cache file. Uploading a different document always starts a new extraction.

## Key capabilities

- Upload PDF with strict validation (extension + magic bytes + file size)
- AI extraction of partner organisations with automatic deduplication
- Multilingual support: works with COSOP documents in any language
- Interactive filters: category, status, minimum mentions, name search
- Donut chart by category and horizontal bar chart by mentions
- Partner detail panel with roles, sectors, description, and supporting evidence text
- Excel export (3 sheets: Summary, Partner List, By Category)
- Document viewer page by page
- AI-generated COSOP summary

## Notes

- Processing takes approximately 5 minutes for a full COSOP (25 chunks × 8s = rate limit compliance)
- Results are cached so loading the same document again is instant
- The PDF must contain selectable text
- Add `.cosop_cache/` to `.gitignore` and do not commit cached results