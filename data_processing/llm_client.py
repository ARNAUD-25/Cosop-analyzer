"""
Calls the Mistral AI API to extract IFAD partner organisations.
Model: mistral-small-latest

1. Chunk-by-chunk extraction 
2. Name normalization using an LLM (acronyms, variants, duplicates)
3. Merge + fuzzy deduplication (threshold 85%) + acronym-based deduplication
"""

import os
import json
import re
import time
import requests

from dotenv import load_dotenv
from rapidfuzz import fuzz, process
from config import MISTRAL_URL, MISTRAL_MODEL, CHUNK_SIZE, SLEEP_BETWEEN_CHUNKS, RANDOM_SEED, FUZZY_THRESHOLD

load_dotenv()



# Keywords indicating a partnership mention
PARTNERSHIP_KEYWORDS = [
    "partnership", "partner", "collaboration", "cooperat",
    "agreement", "cofinanc", "co-financ", "joint", "together with",
    "in partnership", "potential", "memorandum", "mou", "signatory",
    "signed", "support from", "working with", "engagement with",
]


def _split_into_chunks(text: str) -> list[str]:
    
    chunks = []
    start = 0
    
    while start < len(text):
        end = start + CHUNK_SIZE
        if end < len(text):
            nl = text.rfind("\n", start, end)
            if nl > start:
                end = nl
        chunk = text[start:end].strip()
        if chunk:
            chunks.append(chunk)
        start = end
        
    return chunks


def _post_mistral(messages: list[dict], api_key: str, max_tokens: int = 4000) -> str:
    
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
    payload = {"model": MISTRAL_MODEL, "messages": messages, "temperature": 0, "max_tokens": max_tokens, "random_seed": RANDOM_SEED}
    
    for attempt in range(4):
        
        r = requests.post(MISTRAL_URL, headers=headers, json=payload, timeout=60)
        
        if r.status_code == 429:
            wait = 30 * (attempt + 1)
            print(f"  Rate limit -- waiting {wait}s (attempt {attempt+1}/4)")
            time.sleep(wait)
            continue
        
        r.raise_for_status()
        
        return r.json()["choices"][0]["message"]["content"]
    
    raise Exception("Persistent rate limit after 4 attempts")


def _call_mistral(chunk: str, i: int, total: int, api_key: str) -> list[dict]:
    
    messages = [
        {
            "role": "system",
            "content": "You extract partner organisations from IFAD documents. Return valid JSON only. No markdown. No explanation."
        },
        {
            "role": "user",
            "content": f"""List ALL partner organisations in this IFAD COSOP text (part {i}/{total}).
A partner is any real institution, ministry, agency, company or body that collaborates with IFAD.
Be EXHAUSTIVE, include every organisation mentioned even once, including audit agencies (BPK, BPKP), bilateral agencies (JICA, GIZ, USAID, AFD, SNV), private sector (Mars Inc.).
Exclude IFAD itself, laws, regulations, IFAD projects (YESS/TEKAD/READSI/UPLANDS/MAHFSA/SSTC/SMPEI/IMPLI/CoPLI/HDDAP/IPDMIP), journals, media, individual persons, frameworks or agreements (e.g. UNSDCF, Paris Agreement), roles or positions or offices (e.g. Resident Coordinator, UN Resident Coordinator, United Nations Resident Coordinator, Resident Coordinator Office, RCO) these are job titles or coordination mechanisms, not partner organisations, mechanisms or instruments (e.g. Reverse Linkage Mechanism), and organisations cited only as data sources.

Return a JSON array of objects. Each object must have:
- "name": full official name (expand acronyms: MoF->Ministry of Finance, ADB->Asian Development Bank, WFP->World Food Programme, GIZ->Deutsche Gesellschaft fuer Internationale Zusammenarbeit, MoV->Ministry of Villages Development of Disadvantaged Regions and Transmigration, MoEF->Ministry of Environment and Forestry, MoA->Ministry of Agriculture, OJK->Indonesia Financial Services Authority, etc.)
- "aliases": list of ALL short forms, acronyms, and alternative names used in this text for this organisation.
  Be thorough, include:
  * Official acronyms: ADB, WFP, OJK, GIZ, JICA, USAID, FAO, UNDP, etc.
  * Informal short names: "World Bank", "the Bank", "Netherlands", "UK", "Danish", "Norwegian"
  * Local language names: "Bappenas", "Kemendagri", "MoEF", "MoA", "MoV", "MoF", "KUKM"
  * Any other form used to refer to this organisation in the text
  Examples: ["ADB"], ["MoV", "Ministry of Villages"], ["OJK", "Financial Services Authority"],
  ["FCDO", "UK", "United Kingdom", "British Embassy"], ["UN Women", "gender equality and empowerment"],
  ["Danish", "DANIDA"], ["Norwegian", "Norway"], ["Korean Eximbank", "KEXIM"]
  Empty list only if the organisation appears exclusively under its full official name.
- "category": Government/Multilateral/Bilateral/NGO/UN Agency/Private Sector/Other
- "status": Active/Potential/Inactive/Unknown
- "roles": list of strings
- "sectors": list of strings
- "description": one sentence string
- "evidence": list of 2 to 3 short quotes from the text that mention this organisation in a partnership context (phrases containing words like "partnership", "cooperation", "collaboration", "potential", "agreement", "co-financing", "working with")

Return [] if no partners found.

TEXT:
{chunk}"""
        }
    ]
    
    raw = _post_mistral(messages, api_key, max_tokens=4000)
    partners = parse_json_from_llm(raw)
    
    print(f"  {len(partners)} partner(s) -- chunk {i}/{total}")
    
    return partners


def _normalize_names_with_llm(raw_names: list[str], api_key: str) -> dict[str, str]:
    
    if not raw_names:
        return {}
    
    names_list = "\n".join(f"- {n}" for n in raw_names)
    
    messages = [
        {"role": "system", "content": "You are an expert in international development organisations. Respond with valid JSON only."},
        {"role": "user", "content": f"""Normalise these organisation names from an IFAD COSOP document.
Return ONLY a JSON object: keys=original names (case-sensitive), values=canonical full names.

Rules:
1. Expand ALL acronyms to full official names
2. Merge variants of the SAME organisation under ONE canonical name:
   - All UK representations: "British Embassy", "Embassy of the United Kingdom", "FCDO", "Foreign Commonwealth and Development Office" -> "Foreign, Commonwealth and Development Office (FCDO)"
   - All Netherlands representations: "Kingdom of the Netherlands", "Embassy of the Netherlands", "Royal Netherlands Embassy", "Dutch Embassy", "Embassy of the Kingdom of the Netherlands" -> "Embassy of the Kingdom of the Netherlands in Indonesia"
   - "Financial Services Authority" and "Indonesia Financial Services Authority" and "OJK" -> "Indonesia Financial Services Authority (OJK)"
   - "ASEAN" and "ASEAN Secretariat" -> "Association of Southeast Asian Nations"
   - "World Bank Group" and "World Bank" -> "World Bank"
   - Any short/long/acronym versions of the same organisation -> same canonical name
3. Fix spelling mistakes
4. If already correct and complete, keep as is

NAMES:
{names_list}"""}
    ]
    
    try:
        raw = _post_mistral(messages, api_key, max_tokens=2000)
        raw = re.sub(r"```json\s*|```\s*", "", raw)
        m = re.search(r'\{.*\}', raw, re.DOTALL)
        
        if m:
            parsed = json.loads(m.group())
            if isinstance(parsed, dict):
                return {str(k).lower().strip(): str(v) for k, v in parsed.items() if isinstance(k, str) and isinstance(v, str)}
            
    except Exception as e:
        print(f"  Normalisation error: {e}")
        
    return {}


def _normalize_key(name: str) -> str:
    
    name = re.sub(r'\s*\([^)]*\)', '', name)
    name = re.sub(r'[^\w\s]', ' ', name)
    return re.sub(r'\s+', ' ', name).strip().lower()


def _extract_acronym(name: str) -> str:
    
    m = re.search(r'\(([A-Za-z]{2,8})\)', name)
    return m.group(1).upper() if m else ""


def _enrich_evidence(partner: dict, full_text: str) -> list[str]:
    
    """
    Searches the full document text for sentences mentioning this partner.
    Returns sentences exactly as they appear in the document.
    """
    
    existing = [e for e in (partner.get("evidence") or []) if len(e.split()) >= 5]
    name = partner.get("name", "").strip().lower()
    aliases = [a.lower() for a in (partner.get("aliases") or []) if isinstance(a, str)]
    search_terms = [t for t in [name] + aliases if len(t) >= 3]

    if not search_terms:
        return existing

    sentences = re.split(r'(?<=[.!?\n])\s+', full_text.replace('\n', ' '))

    found = []
    for sentence in sentences:
        sentence = sentence.strip()
        if len(sentence.split()) < 5 or len(sentence) > 500:
            continue
        sentence_lower = sentence.lower()
        if not any(term in sentence_lower for term in search_terms):
            continue
        if sentence not in existing and sentence not in found:
            found.append(sentence)
        if len(found) >= 3:
            break

    return (existing + found)[:5]


def _merge_partners(all_lists: list[list[dict]], name_mapping: dict[str, str]) -> list[dict]:
    
    merged: dict[str, dict] = {}
    STATUS_PRIORITY = {"Active": 4, "Potential": 3, "Inactive": 2, "Unknown": 1}

    for partner_list in all_lists:
        
        if not isinstance(partner_list, list):
            continue
        
        for partner in partner_list:
            
            if not isinstance(partner, dict):
                continue
            
            raw_name = partner.get("name", "")
            if not isinstance(raw_name, str) or not raw_name.strip():
                continue

            canonical = name_mapping.get(raw_name.lower().strip())
            
            if canonical:
                partner["name"] = canonical

            key = _normalize_key(partner["name"])
            
            if not key:
                continue

            # Deduplication by acronym
            acronym = _extract_acronym(partner["name"])
            
            if acronym:
                for existing_key, existing_val in merged.items():
                    if _extract_acronym(existing_val.get("name", "")) == acronym:
                        key = existing_key
                        break

            # Fuzzy matching
            existing_keys = list(merged.keys())
            
            if existing_keys:
                result = process.extractOne(key, existing_keys, scorer=fuzz.token_sort_ratio)
                if result and result[1] >= FUZZY_THRESHOLD:
                    key = result[0]

            if key not in merged:
                merged[key] = partner
                
            else:
                ex = merged[key]
                if len(partner.get("name", "")) > len(ex.get("name", "")):
                    ex["name"] = partner["name"]
                ex["evidence"] = list(dict.fromkeys((ex.get("evidence") or []) + (partner.get("evidence") or [])))[:5]
                ex["roles"] = list(dict.fromkeys((ex.get("roles") or []) + (partner.get("roles") or [])))
                ex["sectors"] = list(dict.fromkeys((ex.get("sectors") or []) + (partner.get("sectors") or [])))
                if STATUS_PRIORITY.get(partner.get("status", "Unknown"), 1) > STATUS_PRIORITY.get(ex.get("status", "Unknown"), 1):
                    ex["status"] = partner["status"]
                if len(partner.get("description", "")) > len(ex.get("description", "")):
                    ex["description"] = partner["description"]
                ex["aliases"] = list(set((ex.get("aliases") or []) + (partner.get("aliases") or [])))

    return list(merged.values())


def ask_llm(document_text: str) -> list[dict]:
    
    api_key = os.environ.get("API_KEY")
    
    if not api_key:
        raise ValueError("API_KEY not found. Check your .env file.")

    chunks = _split_into_chunks(document_text)
    total = len(chunks)
    
    print(f"Document split into {total} chunks of {CHUNK_SIZE} characters")

    all_results = []
    empty_chunks = []

    for i, chunk in enumerate(chunks, start=1):
        print(f"Processing chunk {i}/{total}...")
        try:
            partners = _call_mistral(chunk, i, total, api_key)
            if partners and isinstance(partners, list) and len(partners) > 0:
                all_results.append(partners)
            else:
                empty_chunks.append((i, chunk))
        except Exception as e:
            print(f" Error chunk {i}: {e}")
            empty_chunks.append((i, chunk))
        finally:
            if i < total:
                time.sleep(SLEEP_BETWEEN_CHUNKS)

    # Retry chunks that returned 0 partners
    if empty_chunks:
        print(f"Retrying {len(empty_chunks)} empty chunks...")
        
        for i, chunk in empty_chunks:
            print(f"  Retrying chunk {i}/{total}...")
            try:
                partners = _call_mistral(chunk, i, total, api_key)
                if partners and isinstance(partners, list) and len(partners) > 0:
                    all_results.append(partners)
            except Exception as e:
                print(f" Error retry chunk {i}: {e}")
            finally:
                time.sleep(SLEEP_BETWEEN_CHUNKS)

    if not all_results:
        return []

    all_raw_names = list({
        p.get("name", "").strip()
        for pl in all_results for p in pl
        if isinstance(p, dict) and p.get("name", "").strip()
    })

    print(f"Normalising {len(all_raw_names)} names...")
    name_mapping = _normalize_names_with_llm(all_raw_names, api_key)
    print(f"  -> {len(name_mapping)} mappings found")

    final = _merge_partners(all_results, name_mapping)

    # Enrich evidence with sentences from the full document
    print(f"Enriching evidence for {len(final)} partners...")
    for partner in final:
        partner["evidence"] = _enrich_evidence(partner, document_text)

    print(f"Total: {len(final)} partners")
    return final


def parse_json_from_llm(raw_text: str) -> list[dict]:
    
    raw_text = re.sub(r"```json\s*|```\s*", "", raw_text)
    m = re.search(r'\[.*\]', raw_text, re.DOTALL)
    
    if not m:
        return []
    
    try:
        result = json.loads(m.group())
        if not isinstance(result, list):
            return []
        partners = []
        for item in result:
            if isinstance(item, dict) and item.get("name"):
                partners.append(item)
            elif isinstance(item, str) and item.strip():
                partners.append({
                    "name": item.strip(),
                    "aliases": [],
                    "category": "Other",
                    "status": "Unknown",
                    "roles": [],
                    "sectors": [],
                    "description": "",
                    "evidence": []
                })
                
        return partners
    
    except json.JSONDecodeError:
        return []