"""PubMed E-utilities API client with ISSN-batch search."""

import time
import requests
from datetime import datetime, timedelta
from typing import Optional


EUTILS_BASE = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils"
_RATE_DELAY_NO_KEY = 0.4  # seconds between calls (safe for 3 req/sec without API key)
_RATE_DELAY_WITH_KEY = 0.11  # seconds between calls (safe for 10 req/sec with API key)


def _get(url: str, params: dict, timeout: int = 30) -> requests.Response:
    delay = _RATE_DELAY_WITH_KEY if params.get("api_key") else _RATE_DELAY_NO_KEY
    time.sleep(delay)
    resp = requests.get(url, params=params, timeout=timeout)
    resp.raise_for_status()
    return resp


def _date_range(days_back: int) -> tuple[str, str]:
    end = datetime.now()
    start = end - timedelta(days=days_back)
    return start.strftime("%Y/%m/%d"), end.strftime("%Y/%m/%d")


def search_by_issns(
    issns: list[str],
    days_back: int = 90,
    subject_focus: str = "",
    max_per_batch: int = 25,
    max_total: int = 200,
    ncbi_api_key: Optional[str] = None,
) -> list[str]:
    """Search PubMed across a list of ISSNs and return unique PMIDs.

    ISSNs are batched into groups of `max_per_batch` to stay within URL limits.
    If `subject_focus` is provided it is ANDed with each batch query.
    """
    start_date, end_date = _date_range(days_back)
    all_pmids: list[str] = []
    seen: set[str] = set()

    for i in range(0, len(issns), max_per_batch):
        batch = issns[i : i + max_per_batch]
        issn_term = " OR ".join(f"{issn}[issn]" for issn in batch)

        if subject_focus:
            term = f'({issn_term}) AND ("{subject_focus}"[Title/Abstract])'
        else:
            term = issn_term

        params: dict = {
            "db": "pubmed",
            "term": term,
            "mindate": start_date,
            "maxdate": end_date,
            "datetype": "pdat",
            "retmax": max_total,
            "retmode": "json",
        }
        if ncbi_api_key:
            params["api_key"] = ncbi_api_key

        try:
            resp = _get(f"{EUTILS_BASE}/esearch.fcgi", params)
            batch_pmids = resp.json().get("esearchresult", {}).get("idlist", [])
            for pmid in batch_pmids:
                if pmid not in seen:
                    seen.add(pmid)
                    all_pmids.append(pmid)
        except Exception as e:
            print(f"  Warning: batch {i//max_per_batch + 1} failed: {e}")

        if len(all_pmids) >= max_total:
            break

    return all_pmids[:max_total]


def fetch_summaries(
    pmids: list[str],
    ncbi_api_key: Optional[str] = None,
) -> dict:
    """Fetch document summaries for a list of PMIDs."""
    if not pmids:
        return {}
    params: dict = {
        "db": "pubmed",
        "id": ",".join(pmids),
        "retmode": "json",
    }
    if ncbi_api_key:
        params["api_key"] = ncbi_api_key

    resp = _get(f"{EUTILS_BASE}/esummary.fcgi", params)
    return resp.json().get("result", {})


def fetch_abstract(
    pmid: str,
    ncbi_api_key: Optional[str] = None,
) -> str:
    """Fetch the full abstract text for a single PMID."""
    params: dict = {
        "db": "pubmed",
        "id": pmid,
        "retmode": "text",
        "rettype": "abstract",
    }
    if ncbi_api_key:
        params["api_key"] = ncbi_api_key

    resp = _get(f"{EUTILS_BASE}/efetch.fcgi", params)
    return resp.text.strip()


def fetch_abstracts_for_pmids(
    pmids: list[str],
    ncbi_api_key: Optional[str] = None,
    min_length: int = 150,
) -> dict[str, str]:
    """Fetch abstracts for all PMIDs, skipping short/empty responses."""
    results: dict[str, str] = {}
    for pmid in pmids:
        try:
            text = fetch_abstract(pmid, ncbi_api_key)
            if len(text) >= min_length:
                results[pmid] = text
            else:
                print(f"  Skipping PMID {pmid} — abstract too short ({len(text)} chars)")
        except requests.HTTPError as e:
            print(f"  Warning: HTTP error fetching PMID {pmid}: {e}")
        except Exception as e:
            print(f"  Warning: Could not fetch PMID {pmid}: {e}")
    return results
