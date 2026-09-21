import asyncio
from datetime import datetime
import re
from typing import List, Set, Tuple
import pandas as pd
from bs4 import BeautifulSoup
from playwright.async_api import async_playwright
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.mime.base import MIMEBase
from email import encoders
import os

# ------------------------------------------------------------
# 1. Directory & File Path Setup
# ------------------------------------------------------------
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
os.chdir(SCRIPT_DIR)

EXCEL_PATH = "FundingRadar.xlsx"
SEEN_URLS_PATH = "seen_urls.csv"

LINK_INTEREST_PATTERN = re.compile(
    r"(grant|fund|funding|award|opportun|event|workshop|call|travel|summer|"
    r"fellowship|student|early|career|ecs|conference|asc|ecr|training|school|"
    r"mobility|scholarship|bursary|support|application|apply)",
    re.IGNORECASE
)

# ------------------------------------------------------------
# 2. Persistence / Deduplication Helper
# ------------------------------------------------------------
def process_deduplication(df_new: pd.DataFrame) -> Tuple[pd.DataFrame, int]:
    """Compares new scraped results against seen_urls.csv to flag new items."""
    today_str = datetime.now().strftime("%Y-%m-%d")

    # Load or initialize history database
    if os.path.exists(SEEN_URLS_PATH):
        df_history = pd.read_csv(SEEN_URLS_PATH)
    else:
        df_history = pd.DataFrame(columns=["URL", "First_Seen", "Last_Seen", "Organization", "Title"])

    seen_urls = set(df_history["URL"].dropna())

    # Mark whether each scraped link is brand new
    is_new_list = []
    for _, row in df_new.iterrows():
        url = row["URL"]
        if url in seen_urls:
            is_new_list.append(False)
            # Update Last_Seen date in history
            df_history.loc[df_history["URL"] == url, "Last_Seen"] = today_str
        else:
            is_new_list.append(True)
            # Add new record to history
            new_record = pd.DataFrame([{
                "URL": url,
                "First_Seen": today_str,
                "Last_Seen": today_str,
                "Organization": row["Organization"],
                "Title": row["Page_Title"]
            }])
            df_history = pd.concat([df_history, new_record], ignore_index=True)
            seen_urls.add(url)

    df_new["Is_New"] = is_new_list

    # Save updated ledger back to CSV
    df_history.to_csv(SEEN_URLS_PATH, index=False)
    
    new_count = sum(is_new_list)
    return df_new, new_count

# ------------------------------------------------------------
# 3. Email Helper Function
# ------------------------------------------------------------
def send_radar_email(excel_path: str, df_results: pd.DataFrame, new_count: int):
    """Sends an email highlighting NEW opportunities found."""
    SENDER_EMAIL = "rer1019@gmail.com"
    SENDER_PASSWORD = "izzs mcla catz fbla"
    RECIPIENT_EMAIL = "rachel.roday@nina.no"
    
    # Filter for hits, prioritizing new opportunities
    hits = df_results[df_results['N_Matches'] > 0].sort_values(by=["Is_New", "N_Matches"], ascending=[False, False])
    top_matches = hits.head(10)
    
    if top_matches.empty:
        summary_html = "<p>No matching opportunities found during this run.</p>"
    else:
        summary_html = f"<h3>Top Funding Opportunities ({new_count} NEW found):</h3><ul>"
        for _, row in top_matches.iterrows():
            new_badge = "<b><span style='color:green;'>[NEW]</span></b> " if row.get("Is_New") else ""
            summary_html += (
                f"<li>{new_badge}<b>{row['Organization']}</b> - <a href='{row['URL']}'>{row['Page_Title']}</a><br>"
                f"<i>Matches ({row['N_Matches']}):</i> {row['Matches']}</li><br>"
            )
        summary_html += "</ul>"

    msg = MIMEMultipart()
    msg['From'] = SENDER_EMAIL
    msg['To'] = RECIPIENT_EMAIL
    msg['Subject'] = f"🎯 Monthly Funding Radar - {new_count} New Opportunities Discovered"

    body = f"""
    <html>
      <body>
        <h2>Monthly Funding Radar Report</h2>
        {summary_html}
        <p>The full Excel report is attached.</p>
      </body>
    </html>
    """
    msg.attach(MIMEText(body, 'html'))

    if os.path.exists(excel_path):
        with open(excel_path, "rb") as f:
            part = MIMEBase("application", "octet-stream")
            part.set_payload(f.read())
            encoders.encode_base64(part)
            part.add_header("Content-Disposition", f"attachment; filename={os.path.basename(excel_path)}")
            msg.attach(part)

    try:
        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
            server.login(SENDER_EMAIL, SENDER_PASSWORD)
            server.sendmail(SENDER_EMAIL, RECIPIENT_EMAIL, msg.as_string())
        print("[✔] Email successfully sent!")
    except Exception as e:
        print(f"[-] Failed to send email: {e}")

# ------------------------------------------------------------
# 4. Parsing Helpers & Crawler Logic
# ------------------------------------------------------------
def make_absolute_url(base_url: str, href: str) -> str:
    if not href or href.startswith(("javascript:", "#", "mailto:")):
        return None
    if re.match(r"^https?://", href, re.IGNORECASE):
        return href
    return f"{base_url.rstrip('/')}/{href.lstrip('/')}"

async def fetch_and_parse(page, url: str) -> Tuple[str, str, BeautifulSoup]:
    try:
        await page.goto(url, wait_until="domcontentloaded", timeout=25000)
        await page.wait_for_timeout(1500)
        content = await page.content()
        soup = BeautifulSoup(content, 'html.parser')
        title = soup.title.get_text(strip=True) if soup.title else ""
        return title, content, soup
    except Exception:
        return "", "", None

def scan_text_for_keywords(soup: BeautifulSoup, keywords: List[str]) -> Tuple[str, int]:
    if not soup:
        return "", 0
    for tag in soup(["script", "style", "nav", "footer", "header", "noscript"]):
        tag.decompose()
    page_text = soup.get_text(separator=' ', strip=True).lower()
    matches = sorted(list(set([kw for kw in keywords if kw.lower() in page_text])))
    return "; ".join(matches), len(matches)

def extract_child_links(soup: BeautifulSoup, base_url: str) -> Set[str]:
    if not soup:
        return set()
    discovered = set()
    for a_tag in soup.find_all("a", href=True):
        href = a_tag["href"]
        if LINK_INTEREST_PATTERN.search(href):
            abs_url = make_absolute_url(base_url, href)
            if abs_url and abs_url != base_url:
                discovered.add(abs_url)
    return discovered

async def check_organization(browser, org_name: str, homepage_url: str, keywords: List[str]) -> List[dict]:
    print(f"\n=================================\nChecking: {org_name}\n=================================")
    context = await browser.new_context(
        user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    )
    page = await context.new_page()
    results = []

    try:
        print(f" Scanning Homepage: {homepage_url}")
        title, _, soup = await fetch_and_parse(page, homepage_url)
        if soup:
            matches_str, n_matches = scan_text_for_keywords(soup, keywords)
            results.append({
                "Organization": org_name, "Homepage": homepage_url, "Page_Title": title,
                "URL": homepage_url, "Matches": matches_str, "N_Matches": n_matches
            })
            child_links = list(extract_child_links(soup, homepage_url))
            print(f" Found {len(child_links)} interesting links")

            for child_url in child_links[:15]:
                print(f"  └─ Scanning Child Page: {child_url}")
                c_title, _, c_soup = await fetch_and_parse(page, child_url)
                if c_soup:
                    c_matches_str, c_n_matches = scan_text_for_keywords(c_soup, keywords)
                    results.append({
                        "Organization": org_name, "Homepage": homepage_url, "Page_Title": c_title,
                        "URL": child_url, "Matches": c_matches_str, "N_Matches": c_n_matches
                    })
        else:
            results.append({
                "Organization": org_name, "Homepage": homepage_url, "Page_Title": None,
                "URL": homepage_url, "Matches": None, "N_Matches": 0
            })
    except Exception as e:
        print(f"Failed: {org_name} ({e})")
        results.append({
            "Organization": org_name, "Homepage": homepage_url, "Page_Title": None,
            "URL": homepage_url, "Matches": None, "N_Matches": 0
        })
    finally:
        await context.close()

    return results

async def main():
    if not os.path.exists(EXCEL_PATH):
        print(f"[-] Error: Could not find {EXCEL_PATH} in {SCRIPT_DIR}")
        return

    df_sources = pd.read_excel(EXCEL_PATH, sheet_name="Source")
    df_keywords = pd.read_excel(EXCEL_PATH, sheet_name="Scraper Keywords")
    
    keywords = [
        str(kw).strip().lower() 
        for kw in df_keywords["Keywords"].dropna() 
        if str(kw).strip().lower() != "plain text"
    ]

    all_results = []
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        for idx, row in df_sources.iterrows():
            org, url = row["Organization/Event"], row["Website"]
            if pd.isna(url):
                continue
            all_results.extend(await check_organization(browser, org, url, keywords))
        await browser.close()

    df_out = pd.DataFrame(all_results)
    
    # Process deduplication against seen_urls.csv
    df_out, new_count = process_deduplication(df_out)
    df_out = df_out.sort_values(by=["Is_New", "N_Matches"], ascending=[False, False])

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_path = f"FundingRadarResults_{timestamp}.xlsx"

    try:
        df_out.to_excel(output_path, index=False, sheet_name="Results")
        print(f"\n[✔] Done! Results written to {output_path}")
        send_radar_email(output_path, df_out, new_count)
    except Exception as e:
        print(f"[-] Error saving Excel file: {e}")

if __name__ == "__main__":
    asyncio.run(main())