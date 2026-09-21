# Research Opportunity Radar

A web-crawling and opportunity monitoring platform for identifying:

- Travel grants
- Fieldwork funding
- Student awards
- Early-career researcher opportunities
- Workshops
- Summer schools
- Conferences
- Research networks

## Current Focus Areas

- Arctic science
- Ecology
- Marine science
- Movement ecology
- Seabirds
- Climate change

## Built in Python Using

- **Playwright** & **BeautifulSoup** for dynamic web scraping and data collection
- **Pandas** for data manipulation and deduplication (`seen_urls.csv` ledger management)
- **SMTP** for automated monthly email notifications and summaries

## Status

**Production** (Automated via Windows Task Scheduler on the `P:\` drive, complying with corporate IT security and Controlled Folder Access guidelines)[cite: 1].

# USE ME (Adapt This for Your Own Research Field)

Want to deploy your own automated grant radar for a different field (like aquaculture, fish telemetry, or marine biology)? Here is what you need to swap out and configure:

- **Target URL Ledger:** Replace the source links with grant aggregators, university portals, or funding bodies specific to your domain.
- **AI-Assisted URL Discovery:** Ask an AI assistant to brainstorm high-value funding homepages and domain targets to feed into your tracking ledger.
- **Keyword Filters:** Update the search terms or regex matching logic in the script to catch field-specific terms (e.g., *aquaculture*, *acoustic tagging*, *bivalve*, *pinniped*, or *carrying capacity*) instead of default ecology keywords.
- **DOM Selectors:** Adjust the Playwright or BeautifulSoup selectors (`soup.select(...)`) if your new target websites have a different HTML structure for titles, deadlines, and links.
- **Notification Settings:** Point the SMTP configuration to your own email address to receive a clean digest on the 1st of every month.
