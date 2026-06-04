"""
1. Read the PDF
2. Call the LLM (or return from disk cache)
3. Filters non-specific extracted entities and enriches them with mentions, first-page occurrence, and supporting evidence.
4. Save to disk cache
"""
import io
import re
import hashlib
import json
import os
import pypdf
from .pdf_reader import read_pdf
from .llm_client import ask_llm

CACHE_DIR = ".cosop_cache"
EXCLUDE_NAMES = ["ifad", "international fund for agricultural development"]


def _is_generic(name: str) -> bool:
    
    """
    Detects non-specific category names using universal linguistic patterns.
    """
    n = name.lower().strip()
    name_no_parens = re.sub(r'\s*\([^)]*\)', '', n).strip()

    generic_endings = (
        "enterprises", "organizations", "organisations",
        "associations", "companies", "institutions",
        "governments", "stakeholders", "actors", "entities",
        "banks", "funds", "bodies",
    )
    generic_starts = (
        "local ", "provincial ", "regional ", "national and local",
        "village-owned", "community-based", "civil society",
        "private sector", "commercial ", "youth ",
    )
    semantic_patterns = (
        "village-owned", "bum desa", "bumdes",
        "resident coordinator",
        "business partners",
        "reverse linkage",
    )

    # Pattern: "X at national/local/regional level"
    if "at national" in n or "at local" in n or "at regional" in n:
        return True
    
    # Ends with a broad plural noun representing a category rather than a specific entity.
    if any(n.endswith(e) for e in generic_endings) and " at " in n:
        return True
    
    # Starts with a general adjective that does not refer to a specific entity.
    if any(n.startswith(s) for s in generic_starts):
        return True
    
    if any(name_no_parens.startswith(s) for s in generic_starts):
        return True
    
    # Semantic patterns regardless of exact wording
    if any(p in n for p in semantic_patterns):
        return True
    
    return False


def _get_search_terms(partner: dict) -> list[str]:
    
    terms = set()
    name = partner.get("name", "").strip()
    
    if not name:
        return []
    
    terms.add(name.lower())
    name_clean = re.sub(r'\s*\([^)]*\)', '', name).strip().lower()
    
    if name_clean and name_clean != name.lower():
        terms.add(name_clean)
        
    for m in re.finditer(r'\(([A-Za-z0-9][A-Za-z0-9\-]{2,15})\)', name):
        acronym = m.group(1)
        terms.add(acronym.lower())
        for part in acronym.split('-'):
            if len(part) >= 3:
                terms.add(part.lower())
                
    for alias in (partner.get("aliases") or []):
        if isinstance(alias, str) and len(alias.strip()) >= 3:
            terms.add(alias.strip().lower())
            
    short = partner.get("short_name", "").strip()
    
    if short and len(short) >= 3:
        terms.add(short.lower())
        
    return [t for t in terms if t and len(t) >= 3]


def _count_mentions(partner: dict, text_lower: str) -> int:
    
    terms = _get_search_terms(partner)
    
    if not terms:
        return 0
    return max(text_lower.count(t) for t in terms)


def _find_first_page(partner: dict, pages: list[str]) -> int | None:
    
    terms = _get_search_terms(partner)
    for i, page_text in enumerate(pages):
        page_lower = page_text.lower()
        for term in terms:
            if term in page_lower:
                return i + 1
    return None


def _fix_missing_aliases(partners: list[dict], text_lower: str) -> None:
    
    """
    For any partner with 0 mentions, scan the document for words
    from the partner name that appear 1-30 times likely short forms.
    Works for any language and any document.
    """
    
    for partner in partners:
        
        if partner.get("mention_count", 0) > 0:
            continue
        
        name = partner.get("name", "").strip()
        name_clean = re.sub(r'\s*\([^)]*\)', '', name).strip().lower()
        words = name_clean.split()
        
        new_aliases = []
        for word in words:
            word_clean = re.sub(r'[^a-z]', '', word.lower())
            if len(word_clean) < 5:
                continue
            count = text_lower.count(word_clean)
            if 0 < count <= 30:
                new_aliases.append(word_clean)
                
        if new_aliases:
            existing = [a.lower() for a in (partner.get("aliases") or [])]
            for alias in new_aliases:
                if alias not in existing:
                    partner["aliases"].append(alias)
                    
        for m in re.finditer(r'\b([A-Z]{2,6})\b', name):
            word = m.group(1).lower()
            if len(word) >= 3 and word not in [a.lower() for a in (partner.get("aliases") or [])]:
                if text_lower.count(word) > 0:
                    partner["aliases"].append(m.group(1))


def extract_partners(uploaded_file) -> list[dict]:
    
    """
    Uses disk cache : LLM is only called once per unique document.
    """
    
    os.makedirs(CACHE_DIR, exist_ok=True)
    uploaded_file.seek(0)
    file_bytes = uploaded_file.read()
    file_hash = hashlib.md5(file_bytes).hexdigest()
    cache_path = os.path.join(CACHE_DIR, f"{file_hash}.json")

    if os.path.exists(cache_path):
        with open(cache_path, "r", encoding="utf-8") as f:
            return json.load(f)

    full_text = read_pdf(io.BytesIO(file_bytes))
    reader = pypdf.PdfReader(io.BytesIO(file_bytes))
    pages = [page.extract_text() or "" for page in reader.pages]
    partners = ask_llm(full_text)

    # Removes IFAD itself, overly general references that do not refer to a specific organization,
    # as well as entries flagged by the LLM as non-specific. 
    partners = [
        p for p in partners
        if not any(ex in p.get("name", "").lower() for ex in EXCLUDE_NAMES)
        and p.get("is_specific", True)
        and not _is_generic(p.get("name", ""))
    ]

    # Clean up names
    for partner in partners:
        partner["name"] = re.sub(r'\s+GmbH\b', '', partner["name"]).strip()
        partner["name"] = re.sub(r',?\s+of the Republic of \w+\b', '', partner["name"]).strip()
        partner["name"] = re.sub(r'\s+of \w+ Republic\b', '', partner["name"]).strip()
        partner["name"] = re.sub(r'\s*\(Indonesia\)', '', partner["name"]).strip()
        partner["name"] = re.sub(r',?\s+"Indonesia"', '', partner["name"]).strip()

    full_text_lower = full_text.lower()

    # First pass: enrich with mentions, first page,..
    for partner in partners:
        partner["mention_count"] = _count_mentions(partner, full_text_lower)
        partner["first_page"] = _find_first_page(partner, pages)
        partner.setdefault("category", "Other")
        partner.setdefault("status", "Unknown")
        partner.setdefault("roles", [])
        partner.setdefault("sectors", [])
        partner.setdefault("description", "")
        partner.setdefault("evidence", [])
        partner.setdefault("aliases", [])

    # Second pass: fix partners still at 0 mentions
    _fix_missing_aliases(partners, full_text_lower)
    for partner in partners:
        if partner["mention_count"] == 0:
            partner["mention_count"] = _count_mentions(partner, full_text_lower)
            if partner["first_page"] is None:
                partner["first_page"] = _find_first_page(partner, pages)

    clean_text = re.sub(r'[\uf0b7\uf0a7\uf020\u2022\u25cf\u2013\u2014]', ' ', full_text)
    clean_text = re.sub(r'\s+', ' ', clean_text)
    all_sentences = re.split(r'(?<=[.!?])\s+', clean_text)
    all_sentences = [s.strip() for s in all_sentences if len(s.split()) >= 5]

    raw_lines = []
    for line in full_text.split("\n"):
        clean = re.sub(r'[\uf0b7\uf0a7\uf020\u2022\u25cf\u2013\u2014]', '', line).strip()
        clean = re.sub(r'\s+', ' ', clean)
        if len(clean.split()) >= 2:
            raw_lines.append(clean)

    # Final pass: replace short or missing evidence with best sentences from document
    for partner in partners:
        evidence = partner.get("evidence") or []
        good = [e for e in evidence if len(e.split()) >= 8]
        if good:
            partner["evidence"] = good
            continue

        name = partner.get("name", "").strip()
        name_clean = re.sub(r'\s*\([^)]*\)', '', name).strip().lower()
        aliases = [a.lower() for a in (partner.get("aliases") or []) if len(a) >= 3]
        for m in re.finditer(r'\(([A-Za-z0-9][A-Za-z0-9\-]{2,15})\)', name):
            aliases.append(m.group(1).lower())
        terms = sorted(set([name.lower(), name_clean] + aliases), key=len, reverse=True)
        terms = [t for t in terms if len(t) >= 3]

        scored = []
        seen = set()
        for s in all_sentences:
            s_lower = s.lower()
            norm = re.sub(r'[^a-z0-9]', '', s_lower)
            if norm in seen:
                continue
            for t in terms:
                if t in s_lower:
                    seen.add(norm)
                    scored.append((len(t), s))
                    break
                
        scored.sort(key=lambda x: x[0], reverse=True)
        found = [s for _, s in scored[:3]]

        if not found:
            for idx, line in enumerate(raw_lines):
                line_lower = line.lower()
                norm = re.sub(r'[^a-z0-9]', '', line_lower)
                if norm in seen:
                    continue
                if any(t in line_lower for t in terms):
                    seen.add(norm)
                    if len(line.split()) < 10:
                        context_parts = [adj.strip() for adj in raw_lines[max(0, idx-3):idx+4] if adj.strip()]
                        merged = " ".join(context_parts)
                        found.append(merged if len(merged.split()) >= 5 else line)
                    else:
                        found.append(line)
                if len(found) >= 3:
                    break

        found = [f for f in found if len(f.split()) >= 5]
        if found:
            partner["evidence"] = found

    partners.sort(key=lambda p: p["mention_count"], reverse=True)
    
    with open(cache_path, "w", encoding="utf-8") as f:
        json.dump(partners, f, ensure_ascii=False, indent=2)
        
    meta_path = cache_path.replace(".json", ".meta.json")
    
    with open(meta_path, "w", encoding="utf-8") as f:
        json.dump({"filename": uploaded_file.name}, f)
        
    print(f"Cache saved: {cache_path} ({len(partners)} partners)")
    return partners
