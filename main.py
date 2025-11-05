import os
import time
import json
import hashlib
import logging
from datetime import datetime, timedelta

from dotenv import load_dotenv
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from webdriver_manager.chrome import ChromeDriverManager
from bs4 import BeautifulSoup
import telegram

# --- Configuration ---
# Load environment variables
load_dotenv()

# Set up logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# Telegram Configuration
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

# Job Filtering Configuration
INCLUSION_KEYWORDS = ["javascript", "reactjs", "angular", "jquery", "nextjs"]
EXCLUSION_KEYWORDS = ["associate", "senior", "mid-level", "0-5 years", "lead"]

# Cache Configuration
JOB_CACHE_FILE = "job_cache.json"
CACHE_RETENTION_HOURS = 48  # Store jobs for 48 hours

# URLs
NAUKRI_URL = "https://www.naukri.com/frontend-developer-jobs"
LINKEDIN_URL = "https://www.linkedin.com/jobs/search/?keywords=frontend%20developer&location=India"


# --- Helper Functions ---
def setup_driver():
    """Sets up and returns a headless Selenium WebDriver."""
    chrome_options = Options()
    chrome_options.add_argument("--headless")
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")
    chrome_options.add_argument("--disable-gpu")    
    try:
        service = Service(ChromeDriverManager().install())
        driver = webdriver.Chrome(service=service, options=chrome_options)
        return driver
    except Exception as e:
        logging.error(f"Failed to set up WebDriver: {e}")
        return None

def get_job_hash(job_title, company_name):
    """Generates a unique and consistent hash for a job posting."""
    return hashlib.md5(f"{job_title.strip()}-{company_name.strip()}".lower().encode()).hexdigest()

def load_job_cache():
    """Loads and cleans the job cache from the JSON file."""
    if not os.path.exists(JOB_CACHE_FILE):
        return {}
    try:
        with open(JOB_CACHE_FILE, "r") as f:
            cache_data = json.load(f)
            cutoff_time = datetime.now() - timedelta(hours=CACHE_RETENTION_HOURS)
            # Keep only jobs that are not older than the retention period
            fresh_cache = {
                job_hash: timestamp
                for job_hash, timestamp in cache_data.items()
                if datetime.fromisoformat(timestamp) > cutoff_time
            }
            return fresh_cache
    except (json.JSONDecodeError, FileNotFoundError):
        return {}

def save_job_cache(cache):
    """Saves the updated job cache to the JSON file."""
    with open(JOB_CACHE_FILE, "w") as f:
        json.dump(cache, f, indent=4)

def filter_job(title, description):
    """Filters jobs based on inclusion and exclusion keywords."""
    # Combine title and description for a comprehensive check
    full_text = (title + " " + description).lower()
    
    # Exclusion check (high priority)
    if any(keyword in full_text for keyword in EXCLUSION_KEYWORDS):
        return False
        
    # Inclusion check
    if any(keyword in full_text for keyword in INCLUSION_KEYWORDS):
        return True
        
    return False

async def send_telegram_notification(job):
    """Sends a formatted job notification asynchronously."""
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        logging.warning("Telegram credentials not set. Skipping notification.")
        return
        
    try:
        bot = telegram.Bot(token=TELEGRAM_BOT_TOKEN)
        message = (
            f"<b>{job['title']}</b>\n"
            f"<i>{job['company']}</i>\n\n"
            f"<b>Source:</b> {job['source']}\n"
            f"<b>Posted:</b> {job['posted_date']}\n\n"
            f"<a href='{job['link']}'>➡️ Apply Now</a>"
        )
        await bot.send_message(chat_id=TELEGRAM_CHAT_ID, text=message, parse_mode='HTML')
        logging.info(f"Notification sent for: {job['title']}")
    except telegram.error.BadRequest as e:
        logging.error(f"Telegram BadRequest Error (check Chat ID): {e}")
    except Exception as e:
        logging.error(f"Error sending Telegram notification: {e}")

# --- Scraper Functions ---
def scrape_naukri_jobs(driver):
    """Scrapes job listings from Naukri.com."""
    logging.info("Scraping Naukri.com...")
    jobs = []
    try:
        driver.get(NAUKRI_URL)
        # Use WebDriverWait for reliability instead of time.sleep()
        WebDriverWait(driver, 20).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, "div.srp-jobaste"))
        )
        
        soup = BeautifulSoup(driver.page_source, 'html.parser')
        # Corrected selector for Naukri job cards
        job_cards = soup.find_all('div', class_='srp-jobaste')

        logging.info(f"Found {len(job_cards)} job cards on Naukri.")
        
        for card in job_cards:
            title_elem = card.find('a', class_='title')
            company_elem = card.find('a', class_='comp-name')
            
            if not title_elem or not company_elem:
                continue

            title = title_elem.text.strip()
            company = company_elem.text.strip()
            link = title_elem['href']
            
            posted_date_elem = card.find('span', class_='job-post-day')
            posted_date = posted_date_elem.text.strip() if posted_date_elem else "Not specified"
            
            description_elem = card.find('div', class_='dsc')
            description = description_elem.text.strip() if description_elem else ""

            jobs.append({
                'title': title, 'company': company, 'link': link,
                'posted_date': posted_date, 'source': 'Naukri',
                'description': description
            })
    except Exception as e:
        logging.error(f"Error scraping Naukri: {e}", exc_info=True)
    return jobs

def scrape_linkedin_jobs(driver):
    """Scrapes job listings from LinkedIn Jobs."""
    logging.info("Scraping LinkedIn Jobs...")
    jobs = []
    try:
        driver.get(LINKEDIN_URL)
        WebDriverWait(driver, 20).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, "ul.jobs-search__results-list"))
        )
        
        # Scroll to load more jobs
        for _ in range(3):
            driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
            time.sleep(2)

        soup = BeautifulSoup(driver.page_source, 'html.parser')
        # Corrected selector for LinkedIn job cards
        job_cards = soup.find_all('li')

        logging.info(f"Found {len(job_cards)} potential job items on LinkedIn.")

        for card in job_cards:
            title_elem = card.find('h3', class_='base-search-card__title')
            company_elem = card.find('h4', class_='base-search-card__subtitle')
            link_elem = card.find('a', class_='base-card__full-link')
            
            if not title_elem or not company_elem or not link_elem:
                continue
                
            title = title_elem.text.strip()
            company = company_elem.text.strip()
            link = link_elem['href']
            
            posted_date_elem = card.find('time', class_='job-search-card__listdate')
            if posted_date_elem and 'datetime' in posted_date_elem.attrs:
                posted_date = posted_date_elem['datetime']
            elif posted_date_elem:
                posted_date = posted_date_elem.text.strip()
            else:
                posted_date = "Not specified"

            jobs.append({
                'title': title, 'company': company, 'link': link,
                'posted_date': posted_date, 'source': 'LinkedIn',
                'description': title # Use title for description as it's not readily available
            })
    except Exception as e:
        logging.error(f"Error scraping LinkedIn: {e}", exc_info=True)
    return jobs

# --- Main Application Logic ---
async def main():
    """Main function to orchestrate the job scraping and notification process."""
    driver = setup_driver()
    if not driver:
        return

    try:
        job_cache = load_job_cache()
        new_jobs_found = []

        logging.info("Starting new job search cycle...")

        # Scrape both platforms
        naukri_jobs = scrape_naukri_jobs(driver)
        linkedin_jobs = scrape_linkedin_jobs(driver)
        all_jobs = naukri_jobs + linkedin_jobs
        
        logging.info(f"Total jobs scraped: {len(all_jobs)}")

        new_notification_count = 0
        for job in all_jobs:
            # First, check if the job is relevant
            if not filter_job(job['title'], job['description']):
                continue

            # If relevant, check if it's new
            job_hash = get_job_hash(job['title'], job['company'])
            if job_hash not in job_cache:
                await send_telegram_notification(job)
                # Add to cache with current timestamp
                job_cache[job_hash] = datetime.now().isoformat()
                new_notification_count += 1
                time.sleep(1) # Small delay between notifications
        
        logging.info(f"New notifications sent: {new_notification_count}")

        save_job_cache(job_cache)
        logging.info("Job search cycle finished.")

    except Exception as e:
        logging.error(f"An error occurred in the main loop: {e}", exc_info=True)
    finally:
        if driver:
            driver.quit()

if __name__ == "__main__":
    import asyncio
    while True:
        asyncio.run(main())
        logging.info("Waiting for 30 minutes before the next run...")
        time.sleep(30 * 60) # 30 minutes
