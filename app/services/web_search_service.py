import os

from ddgs import DDGS


WEB_SEARCH_BACKEND = os.getenv(
    "WEB_SEARCH_BACKEND",
    "duckduckgo"
)

WEB_SEARCH_TIMEOUT = int(
    os.getenv(
        "WEB_SEARCH_TIMEOUT",
        "5"
    )
)


def web_search(query, max_results=3):
    print(f"Searching web: {query}", flush=True)

    try:
        results = DDGS(
            timeout=WEB_SEARCH_TIMEOUT
        ).text(
            query,
            region="in-en",
            safesearch="moderate",
            max_results=max_results,
            backend=WEB_SEARCH_BACKEND
        )

        return results or []

    except Exception as e:
        print("Web search error:", e, flush=True)
        return []


def search_company_jobs(company):
    queries = [
        f'"{company}" careers AI engineer',
        f'"{company}" careers data engineer',
        f'"{company}" careers machine learning',
        f'"{company}" careers MLOps',
        f'"{company}" careers DevOps'
    ]

    all_results = []

    for query in queries:
        results = web_search(
            query,
            max_results=3
        )

        all_results.extend(results)

    return all_results


def research_company(company):
    queries = [
        f'"{company}" official website what does company do',
        f'"{company}" AI data technology product',
        f'"{company}" startup company about'
    ]

    all_results = []

    for query in queries:
        all_results.extend(
            web_search(
                query,
                max_results=3
            )
        )

    return all_results
