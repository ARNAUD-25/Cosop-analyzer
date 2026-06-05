"""
config.py 
"""

# LLM
MISTRAL_URL            = "https://api.mistral.ai/v1/chat/completions"
MISTRAL_MODEL          = "mistral-small-latest"
CHUNK_SIZE             = 12000
SLEEP_BETWEEN_CHUNKS   = 15
RANDOM_SEED            = 42
FUZZY_THRESHOLD    = 85

# Cache
CACHE_DIR = ".cosop_cache"

# Extraction
MAX_EVIDENCE       = 5
MIN_EVIDENCE_WORDS = 8
