import re
from typing import List

def normalize_post(t: str) -> str:
    # Remove URLs
    t = re.sub(r'https?://\S+', '', t)
    # Remove excessive whitespace
    t = re.sub(r'\s+', ' ', t)
    t = t.strip()
    return t

def extract_symbols(t: str, inst: dict) -> List[str]:
    # Extract cashtags
    tickers = set(re.findall(r'\$([A-Z]{1,5})(?![A-Z])', t))

    # Add instrument symbol if mentioned
    if inst["symbol"] in t.upper() or inst["symbol"] in tickers:
        tickers.add(inst["symbol"])

    # Add if company name mentioned
    if inst["company_name"] and inst["company_name"].upper() in t.upper():
        tickers.add(inst["symbol"])

    return list(tickers)
