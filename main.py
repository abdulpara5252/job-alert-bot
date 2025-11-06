import os
import time
import json
import hashlib
import logging
import asyncio
from datetime import datetime, timedelta
from threading import Thread

from dotenv import load_dotenv
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from bs4 import BeautifulSoup
import telegram
from flask import Flask

# --- Configuration ---
# Load environment variables from .env file
load_dotenv()

# Set up logging to output to console
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# Telegram Configuration
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

# Job Filtering Configuration
INCLUSION_KEYWORDS = ["javascript", "reactjs", "angular", "jquery", "nextjs", "vue"]
EXCLUSION_KEYWORDS = ["associate", "senior", "mid-level", "0-5 years", "lead", "staff", "principal"]

# Cache Configuration
JOB_CACHE_FILE = "job_cache.json"
CACHE_RETENTION_HOURS = 48  # Store jobs for 48 hours

# URLs
NAUKRI_URL = "https://www.naukri.com/frontend-developer-jobs"
LINKEDIN_URL = "https://www.linkedin.com/jobs/search/?keywords=frontend%20developer&location=India&f_TPR=r86400" # Last 24 hours

# --- Flask Web Server to Keep Service Alive ---
app = Flask(__name__)

@app.route('/')
def index():
    """A simple endpoint to respond to health checks."""
    return "Job Alert Bot is alive and running!"

def run_web_server():
    """Runs the Flask web server."""
    # Railway provides the PORT environment variable
    port = int(os.environ.get("PORT", 8080))
    app.run(host='0.0.0.0', port=port)

# --- Helper Functions ---
def setup_driver():
    """Sets up and returns a headless Selenium WebDriver."""
    chrome_options = Options()
    chrome_options.add_argument("--headless")
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")
    chrome_options.add_argument("--disable-gpu")
    chrome_options.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/98.0.4758.102 Safari/537.36")
    
    try:
        driver = webdriver.Chrome(options=chrome_options)
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
    full_text = (title + " " + description).lower()
    
    if any(keyword in full_text for keyword in EXCLUSION_KEYWORDS):
        return False
        
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
        logging.error(f"Telegram BadRequest Error (check Chat ID format for channels vs. private): {e}")
    except Exception as e:
        logging.error(f"Error sending Telegram notification: {e}")

# --- Scraper Functions ---
def scrape_naukri_jobs(driver):
    """Scrapes job listings from Naukri.com with robust selectors."""
    logging.info("Scraping Naukri.com...")
    jobs = []
    try:
        driver.get(NAUKRI_URL)
        WebDriverWait(driver, 20).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, "article.jobTuple"))
        )
        
        soup = BeautifulSoup(driver.page_source, 'html.parser')
        job_cards = soup.select('article.jobTuple')

        logging.info(f"Found {len(job_cards)} job cards on Naukri.")
        
        for card in job_cards:
            title_elem = card.select_one('a.title')
            company_elem = card.select_one('a.subTitle')
            
            if not title_elem or not company_elem:
                continue

            title = title_elem.text.strip()
            company = company_elem.text.strip()
            link = title_elem['href']
            
            posted_date_elem = card.select_one('span.postedDate')
            posted_date = posted_date_elem.text.strip() if posted_date_elem else "Not specified"
            
            description_elem = card.select_one('div.job-description')
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
    """Scrapes job listings from LinkedIn Jobs with robust selectors."""
    logging.info("Scraping LinkedIn Jobs...")
    jobs = []
    try:
        driver.get(LINKEDIN_URL)
        WebDriverWait(driver, 20).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, "ul.jobs-search__results-list"))
        )
        
        for _ in range(2):
            driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
            time.sleep(3)

        soup = BeautifulSoup(driver.page_source, 'html.parser')
        job_cards = soup.select('ul.jobs-search__results-list > li')

        logging.info(f"Found {len(job_cards)} potential job items on LinkedIn.")

        for card in job_cards:
            title_elem = card.select_one('h3.base-search-card__title')
            company_elem = card.select_one('h4.base-search-card__subtitle')
            link_elem = card.select_one('a.base-card__full-link')
            
            if not title_elem or not company_elem or not link_elem:
                continue
                
            title = title_elem.text.strip()
            company = company_elem.text.strip()
            link = link_elem['href']
            
            posted_date_elem = card.select_one('time.job-search-card__listdate--new, time.job-search-card__listdate')
            posted_date = posted_date_elem.text.strip() if posted_date_elem else "Not specified"

            jobs.append({
                'title': title, 'company': company, 'link': link,
                'posted_date': posted_date, 'source': 'LinkedIn',
                'description': title
            })
    except Exception as e:
        logging.error(f"Error scraping LinkedIn: {e}", exc_info=True)
    return jobs

# --- Main Application Logic ---
async def main_bot_logic():
    """Main function to orchestrate the job scraping and notification process."""
    driver = setup_driver()
    if not driver:
        logging.error("Driver setup failed. Aborting this cycle.")
        return

    try:
        job_cache = load_job_cache()
        
        logging.info("Starting new job search cycle...")

        all_jobs = scrape_naukri_jobs(driver) + scrape_linkedin_jobs(driver)
        
        logging.info(f"Total jobs scraped before filtering: {len(all_jobs)}")

        new_notification_count = 0
        filtered_out_count = 0
        
        for job in all_jobs:
            job_hash = get_job_hash(job['title'], job['company'])

            if job_hash in job_cache:
                continue
            
            if filter_job(job['title'], job['description']):
                await send_telegram_notification(job)
                job_cache[job_hash] = datetime.now().isoformat()
                new_notification_count += 1
                await asyncio.sleep(1) # Asynchronous sleep
            else:
                logging.info(f"Filtered out job: '{job['title']}' due to keyword mismatch.")
                filtered_out_count += 1
        
        logging.info(f"New notifications sent: {new_notification_count}")
        logging.info(f"Jobs filtered out: {filtered_out_count}")
        logging.info(f"Jobs already in cache (skipped): {len(all_jobs) - new_notification_count - filtered_out_count}")

        save_job_cache(job_cache)
        logging.info("Job search cycle finished.")

    except Exception as e:
        logging.error(f"An error occurred in the main loop: {e}", exc_info=True)
    finally:
        if driver:
            driver.quit()

# --- Entry Point ---
if __name__ == "__main__":
    # Start the Flask web server in a background thread to keep the service alive
    flask_thread = Thread(target=run_web_server)
    flask_thread.daemon = True
    flask_thread.start()
    
    logging.info("Web server started to keep the bot alive on Railway.")

    # Main loop to run the bot logic periodically
    while True:
        try:
            asyncio.run(main_bot_logic())
        except Exception as e:
            logging.critical(f"A critical error occurred in the main execution loop: {e}", exc_info=True)

        logging.info("Waiting for 30 minutes before the next run...")
        time.sleep(30 * 60) # 30 minutes
