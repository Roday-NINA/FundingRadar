# ============================================================
# Rachel Opportunity Radar v0.2
# ============================================================

# Libraries ---------------------------------------------------

library(readxl)
library(writexl)
library(rvest)
library(httr2)
library(dplyr)
library(stringr)
library(purrr)
library(tibble)

# Inputs ------------------------------------------------------

sources <- read_excel("FundingRadar.xlsx",  sheet = "Source")

test_sources <- sources |>
  filter( `Organization/Event` == "ICES")

keywords <- read_excel( "FundingRadar.xlsx",  sheet = "Scraper Keywords")

keywords <- keywords$Keywords |>
  na.omit() |>
  tolower()

# ------------------------------------------------------------
# Helper: Convert relative URLs to absolute
# ------------------------------------------------------------

make_absolute_url <- function(base_url, href) {
  
  if (is.na(href)) {
    return(NA_character_)
  }
  
  if (str_detect(href, "^https?://")) {
    return(href)
  }
  
  paste0(
    sub("/$", "", base_url),
    "/",
    sub("^/", "", href)
  )
  
}

# ------------------------------------------------------------
# Helper: Extract interesting links
# ------------------------------------------------------------

extract_interesting_links <- function(page) {
  
  links <- page |>
    html_elements("a") |>
    html_attr("href")
  
  links <- links[!is.na(links)]
  
  pattern <- paste(
    c(
      "grant",
      "fund",
      "funding",
      "award",
      "opportun",
      "event",
      "workshop",
      "call",
      "travel",
      "summer",
      "fellowship",
      "student",
      "early",
      "career",
      "ecs",
      "conference",
      "asc",
      "ecr",
      "training",
      "school",
      "mobility",
      "scholarship",
      "bursary",
      "support",
      "application",
      "apply"
    ),
    collapse = "|"
  )
  
  links[
    str_detect(
      tolower(links),
      pattern
    )
  ]
  
}

# ------------------------------------------------------------
# Helper: Scan page text
# ------------------------------------------------------------

scan_page <- function(url, keywords) {
  
  tryCatch({
    
    cat(" Scanning:", url, "\n")
    
    page <- read_html(url)
    
    text <- page |>
      html_text2() |>
      tolower()
    
    matches <- keywords[
      str_detect(
        text,
        fixed(keywords)
      )
    ]
    
    title <- page |>
      html_element("title") |>
      html_text2()
    
    tibble(
      Page_Title = title,
      URL = url,
      Matches = paste(unique(matches), collapse = "; "),
      N_Matches = length(unique(matches))
    )
    
  }, error = function(e) {
    
    tibble(
      Page_Title = NA_character_,
      URL = url,
      Matches = NA_character_,
      N_Matches = 0
    )
    
  })
  
}

# ------------------------------------------------------------
# Main Website Function
# ------------------------------------------------------------

check_website <- function(org_name,
                          homepage_url,
                          keywords) {
  
  cat("\n=================================\n")
  cat("Checking:", org_name, "\n")
  cat("=================================\n")
  
  tryCatch({
    
    homepage <- read_html(homepage_url)
    
    # Scan homepage itself
    homepage_result <- scan_page(
      homepage_url,
      keywords
    )
    
    # Collect interesting links
    links <- extract_interesting_links(
      homepage
    )
    
    links <- unique(
      map_chr(
        links,
        \(x) make_absolute_url(
          homepage_url,
          x
        )
      )
    )
    
    links <- links[!is.na(links)]
    
    cat(
      "Found",
      length(links),
      "interesting links\n"
    )
    
    # Scan discovered pages
    child_results <- map_dfr(
      links,
      \(x) scan_page(
        x,
        keywords
      )
    )
    
    bind_rows(
      homepage_result,
      child_results
    ) |>
      mutate(
        Organization = org_name,
        Homepage = homepage_url,
        .before = 1
      )
    
  }, error = function(e) {
    
    cat(
      "Failed:",
      org_name,
      "\n"
    )
    
    tibble(
      Organization = org_name,
      Homepage = homepage_url,
      Page_Title = NA_character_,
      URL = homepage_url,
      Matches = NA_character_,
      N_Matches = 0
    )
    
  })
  
}

# ------------------------------------------------------------
# Run Across All Sources
# ------------------------------------------------------------

results <- map2_dfr(
  sources$`Organization/Event`,
  sources$Website,
#  test_sources$`Organization/Event`,
#  test_sources$Website,
  \(org, url)
  check_website(
    org_name = org,
    homepage_url = url,
    keywords = keywords
  )
)

# ------------------------------------------------------------
# Basic Ranking
# ------------------------------------------------------------

results <- results |>
  arrange(
    desc(N_Matches)
  )

# ------------------------------------------------------------
# Save Results
# ------------------------------------------------------------

write_xlsx(
  list(
    Results = results
  ),
  "FundingRadarResults.xlsx"
)
