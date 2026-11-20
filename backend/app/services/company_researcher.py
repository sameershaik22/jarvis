from __future__ import annotations

import re
from dataclasses import dataclass
from urllib.parse import quote_plus

from bs4 import BeautifulSoup

from app.services.browser_controller import BrowserController
from app.services.tavily_search import search_tavily
from app.services.page_extractor import (
    build_google_search_url,
    canonicalize_url,
    classify_external_links,
    extract_urls_from_text,
    is_safe_company_website,
    parse_google_results_from_html,
)


@dataclass
class HostCompanyResearchResult:
    host_linkedin_url: str | None
    host_designation: str | None
    company_name: str | None
    company_linkedin_url: str | None
    official_website: str | None
    company_location: str | None
    relationship_status: str  # Verified | Possible Match | Unverified | Manual Review Required
    evidence_urls: list[str]
    notes: str


async def research_host_company(
    host_name: str | None,
    host_linkedin_url: str | None,
    initial_company_name: str | None,
    post_external_urls: list[str] | None = None,
    browser: BrowserController | None = None,
    allow_live_browser: bool = True,
) -> HostCompanyResearchResult:
    """Module 6: Verify ONLY the podcast host's profile and associated company.

    Does NOT prospect other employees or marketing decision-makers.
    """
    evidence_urls: list[str] = []
    designation: str | None = None
    company_name = initial_company_name
    company_linkedin_url: str | None = None
    official_website: str | None = None
    company_location: str | None = None
    notes_parts: list[str] = []

    classified = classify_external_links(post_external_urls or [])
    if classified["linkedin_companies"]:
        company_linkedin_url = classified["linkedin_companies"][0]
        evidence_urls.append(company_linkedin_url)
    if classified["websites"]:
        official_website = classified["websites"][0]
        evidence_urls.append(official_website)

    resolved_host_linkedin = canonicalize_url(host_linkedin_url)
    if resolved_host_linkedin:
        evidence_urls.append(resolved_host_linkedin)

    if allow_live_browser and browser is not None and host_name:
        # Step 1: If no host LinkedIn URL, search Tavily or LinkedIn
        if not resolved_host_linkedin:
            # Query Tavily first for exact host LinkedIn
            t_res = await search_tavily(f"{host_name} {company_name or 'real estate'} LinkedIn", max_results=3)
            for r in t_res:
                u = r.get("url", "")
                if "linkedin.com/in/" in u:
                    resolved_host_linkedin = canonicalize_url(u)
                    if resolved_host_linkedin:
                        evidence_urls.append(resolved_host_linkedin)
                        notes_parts.append(f"Located host LinkedIn via Tavily search: {resolved_host_linkedin}")
                        break

            if not resolved_host_linkedin:
                search_url = f"https://www.linkedin.com/search/results/people/?keywords={quote_plus(host_name)}"
                res = await browser.open_url(search_url, screenshot_label="host_li_search")
                if res.success and (not res.gate or not res.gate.restricted):
                    html = await browser.get_html()
                    soup = BeautifulSoup(html, "lxml")
                    for a in soup.find_all("a", href=True):
                        href = a["href"]
                        if "/in/" in href:
                            resolved_host_linkedin = canonicalize_url(
                                href if href.startswith("http") else f"https://www.linkedin.com{href}"
                            )
                            if resolved_host_linkedin:
                                evidence_urls.append(resolved_host_linkedin)
                                notes_parts.append(f"Located host LinkedIn via search: {resolved_host_linkedin}")
                                break

        # Step 2: Open host LinkedIn profile if accessible
        if resolved_host_linkedin:
            prof_res = await browser.open_url(resolved_host_linkedin, screenshot_label="host_profile")
            if prof_res.success and (not prof_res.gate or not prof_res.gate.restricted):
                prof_html = await browser.get_html()
                soup = BeautifulSoup(prof_html, "lxml")
                headline_el = soup.select_one(".text-body-medium, h2")
                if headline_el:
                    designation = re.sub(r"\s+", " ", headline_el.get_text(" ", strip=True))[:200]
                for a in soup.find_all("a", href=True):
                    href = a["href"]
                    if "/company/" in href and not company_linkedin_url:
                        company_linkedin_url = canonicalize_url(
                            href if href.startswith("http") else f"https://www.linkedin.com{href}"
                        )
                        if company_linkedin_url:
                            evidence_urls.append(company_linkedin_url)
                            if not company_name:
                                comp_txt = re.sub(r"\s+", " ", a.get_text(" ", strip=True))
                                if comp_txt:
                                    company_name = comp_txt[:150]
                notes_parts.append("Inspected host LinkedIn profile.")
            elif prof_res.gate and prof_res.gate.restricted:
                notes_parts.append(f"Host LinkedIn access gated: {prof_res.gate.reason}")

        # Step 3: Open company LinkedIn page if available & accessible
        if company_linkedin_url:
            comp_res = await browser.open_url(company_linkedin_url, screenshot_label="host_company_li")
            if comp_res.success and (not comp_res.gate or not comp_res.gate.restricted):
                comp_html = await browser.get_html()
                soup = BeautifulSoup(comp_html, "lxml")
                body_text = soup.get_text(" ", strip=True)
                if not company_name:
                    h1 = soup.find("h1")
                    if h1:
                        company_name = re.sub(r"\s+", " ", h1.get_text(" ", strip=True))[:150]
                for u in extract_urls_from_text(body_text):
                    if is_safe_company_website(u) and not official_website:
                        official_website = u
                        evidence_urls.append(u)
                        break
                loc_match = re.search(r"Headquarters\s+([A-Za-z0-9 ,.-]{3,80})", body_text)
                if loc_match:
                    company_location = loc_match.group(1).strip()
                notes_parts.append("Inspected host company LinkedIn page (Employees/About scope limited to host verification).")

        # Step 4: Search for official website if company known without website
        if company_name and not official_website:
            t_res = await search_tavily(f"{company_name} real estate official website", max_results=3)
            for m in t_res:
                u = m.get("url", "")
                if is_safe_company_website(u):
                    official_website = u
                    evidence_urls.append(official_website)
                    notes_parts.append(f"Located company website via Tavily search: {official_website}")
                    break

            if not official_website:
                g_res = await browser.open_url(build_google_search_url(f'"{company_name}" real estate official website'), screenshot_label="company_web_search")
                if g_res.success and (not g_res.gate or not g_res.gate.restricted):
                    g_matches = parse_google_results_from_html(await browser.get_html())
                    for m in g_matches:
                        if is_safe_company_website(m.get("url")):
                            official_website = m["url"]
                            evidence_urls.append(official_website)
                            notes_parts.append(f"Located company website via Google search: {official_website}")
                            break

    if resolved_host_linkedin and (company_linkedin_url or official_website) and company_name:
        rel_status = "Verified"
    elif company_name or resolved_host_linkedin:
        rel_status = "Possible Match"
    else:
        rel_status = "Unverified"

    return HostCompanyResearchResult(
        host_linkedin_url=resolved_host_linkedin,
        host_designation=designation,
        company_name=company_name,
        company_linkedin_url=company_linkedin_url,
        official_website=official_website,
        company_location=company_location,
        relationship_status=rel_status,
        evidence_urls=list(dict.fromkeys(evidence_urls)),
        notes=" ".join(notes_parts) if notes_parts else "Company research completed from available public metadata.",
    )

