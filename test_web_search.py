from app.services.web_search_service import (
    search_company_jobs,
    research_company
)


company = "Kotak Mahindra Bank"

print("JOBS")
print("=" * 60)

jobs = search_company_jobs(company)

for item in jobs[:10]:
    print(item.get("title"))
    print(item.get("href"))
    print(item.get("body"))
    print()


print("\nCOMPANY RESEARCH")
print("=" * 60)

research = research_company(company)

for item in research[:5]:
    print(item.get("title"))
    print(item.get("href"))
    print(item.get("body"))
    print()