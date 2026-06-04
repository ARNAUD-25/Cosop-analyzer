# COSOP Partner Analyzer

Interactive dashboard to extract and visualize IFAD partner organisations from COSOP documents using AI.

## Screenshots

![Home](screenshots/01_home.png)
![Dashboard](screenshots/02_dashboard.png)
![Detail](screenshots/03_detail.png)

## Installation

```bash
# 1. Clone the repo

git clone https://github.com/ARNAUD-25/Cosop-analyzer.git

cd Cosop-analyzer

# 2. Create a virtual environment

python -m venv .venv

source .venv/bin/activate        # macOS / Linux

.venv\Scripts\activate           # Windows

# 3. Install dependencies

pip install -r requirements.txt --prefer-binary

# 4. Add your Mistral API key

cp .env.example .env

# Replace YOUR_ACTUAL_KEY with your key from https://console.mistral.ai/api-keys

sed -i "" "s/your_mistral_api_key_here/YOUR_ACTUAL_KEY/" .env # (macOS) 

sed -i "s/your_mistral_api_key_here/YOUR_ACTUAL_KEY/" .env # (Linux)

#[If key contains characters like / or &, this can break sed. Safer version : sed -i "" "s|your_mistral_api_key_here|YOUR_ACTUAL_KEY|" .env (using | instead of /)]

# 5. Run the application

python -m streamlit run app.py
```

Opens automatically on **http://localhost:8501**

## Environment variables

`API_KEY`  Mistral AI API key, free at https://console.mistral.ai/api-keys

## Project structure

```
cosop-analyzer/
│
├── app.py                        [ Streamlit (entry point) ]
│
├── data_processing/
│   ├── pdf_reader.py             [ Reads PDF text ]
│   ├── llm_client.py             [ Calls Mistral AI API ]
│   └── extractor.py              [ Orchestrates pipeline + cache ]
│
├── data_visualization/
│   └── charts.py                 [ Plotly charts ]
│
├── data_export/
│   └── exporter.py               [ Excel export ]
│
├── utils/
│   └── validators.py             [ PDF file validation ]
│
├── requirements.txt
├── .env.example
└── .gitignore
```

## Solution description

The pipeline works in 4 steps:

1. **PDF reading** : extracts all text from the uploaded COSOP document

2. **AI extraction** : The document is split into chunks, and Mistral AI(`mistral-small-latest`) is called on each chunk to extract partner organisations. The document can be in any language; the model understands it and always returns results in English. For each partner, it extracts the name, category, status, roles, sectors, description, and supporting quotes.

3. **Deduplication** : normalizes organisation names (expands acronyms and merges variants) using a second LLM call, then applies fuzzy matching and acronym-based merging.

4. **Additional processing** : counts mentions of each partner in the document, finds the first page where they appear, and extracts relevant sentences as evidence

## Key capabilities

- Upload PDF with strict validation (extension + magic bytes + file size)
- AI extraction of partner organisations with automatic deduplication
- Multilingual support works with COSOP documents in any language
- Interactive filters: category, status, minimum mentions, name search
- Donut chart by category and horizontal bar chart by mentions
- Partner detail panel with roles, sectors, description, and supporting evidence text
- Excel export (3 sheets: Summary, Partner List, By Category)
- Document viewer page by page
- AI-generated COSOP summary

## Notes

- Results are cached so loading the same document again is instant
- The PDF must contain selectable text (not a scanned image)
- Add `.cosop_cache/` to `.gitignore` and do not commit cached results