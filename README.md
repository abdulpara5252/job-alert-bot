# Serverless Frontend Job Alert Bot

## Objective

This project develops a lightweight, serverless Python application that automates the search for frontend software development roles on Naukri and LinkedIn. It uses a specific set of keywords to filter for relevant jobs, excludes roles that are not a good fit, and sends instant, formatted notifications to a Telegram channel. The bot operates without a persistent backend database and is optimized for deployment on a serverless platform like Railway.

## Key Features

*   **Targeted Web Scraping**: Scrapes job listings from Naukri.com and LinkedIn Jobs.
*   **Advanced Keyword Filtering**: Includes "Javascript", "ReactJs", "Angular", "JQuery", "NextJs" and excludes "Associate", "Senior", "mid-level", "0-5 Years".
*   **Real-Time Telegram Notifications**: Integrates with the Telegram Bot API to deliver instant, formatted alerts with job title, company, source, posted date, and an "Apply Now" link.
*   **Autonomous & Scheduled Operation**: Runs in a continuous loop, executing a new job search every 30 minutes for stateless, 24/7 operation.
*   **Stateless Deduplication (No Backend Database)**: Uses an in-memory Python set for current run deduplication and a simple file-based cache (`job_cache.json`) for deduplication across recent runs.
*   **Robust Error Handling & Logging**: Implements comprehensive logging to `stdout` and gracefully handles scraping exceptions.
*   **Serverless Deployment**: Architected for deployment on Railway, with dependencies managed in `requirements.txt` and a `Procfile` for runtime process definition.

## Technical Stack

*   **Language**: Python 3.9+
*   **Web Scraping**: Selenium and BeautifulSoup4
*   **Notifications**: `python-telegram-bot` library
*   **Deduplication**: In-memory Python set and `job_cache.json` (JSON file)
*   **Deployment**: Railway
*   **Configuration**: `python-dotenv` for local development

## Local Setup and Configuration

### Prerequisites

Before you begin, ensure you have the following installed:

*   Python 3.9+ (`python --version`)
*   `pip` (Python package installer)
*   Google Chrome browser (Selenium requires a browser to operate)

### Environment Variables (`.env` file)

Create a file named `.env` in the root directory of the project and populate it with your sensitive credentials. This file is crucial for securing your API tokens and other configuration details. The bot uses `python-dotenv` to load these variables locally.

```
TELEGRAM_BOT_TOKEN="YOUR_TELEGRAM_BOT_TOKEN"
TELEGRAM_CHAT_ID="YOUR_TELEGRAM_CHAT_ID"
# Optional, if LinkedIn requires login:
# LINKEDIN_USERNAME="YOUR_LINKEDIN_USERNAME"
# LINKEDIN_PASSWORD="YOUR_LINKEDIN_PASSWORD"
```

*   **`TELEGRAM_BOT_TOKEN`**: Obtain this from BotFather on Telegram.
*   **`TELEGRAM_CHAT_ID`**: Get your chat ID by sending a message to your bot and then visiting `https://api.telegram.org/bot<YOUR_BOT_TOKEN>/getUpdates`.

### Installing Dependencies

Navigate to the project root directory in your terminal and install the required Python packages:

```bash
pip install -r requirements.txt
```

### Running Locally

After setting up your `.env` file and installing dependencies, you can run the bot locally:

```bash
python main.py
```

The bot will start scraping, filtering, and sending notifications every 30 minutes. You will see logs in your terminal.

## Deployment to Railway

This bot is designed for serverless deployment on Railway. Follow these steps to deploy:

1.  **Create a new project on Railway**: Log in to your Railway account and create a new project.
2.  **Connect your GitHub repository**: Link your project to the GitHub repository where your bot's code is hosted.
3.  **Configure Environment Variables**: In your Railway project settings, navigate to the "Variables" section and add your `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID`, and any other necessary environment variables (e.g., `LINKEDIN_USERNAME`, `LINKEDIN_PASSWORD`). These should match the keys in your local `.env` file.
4.  **Procfile**: The `Procfile` in the root of the project specifies how Railway should run your application:

    ```
    worker: python main.py
    ```

    Railway will automatically detect this `Procfile` and use it to start the bot as a worker process.
5.  **Deploy**: Trigger a deployment from your Railway dashboard. Railway will build your application, install dependencies from `requirements.txt`, and start the worker process.

## Stateless Caching Mechanism (`job_cache.json`)

To prevent duplicate notifications without a persistent database, the bot employs a stateless caching mechanism using a local file named `job_cache.json`.

### How it Works:

1.  **Load on Start**: At the beginning of each 30-minute run, the bot attempts to load previously processed job IDs from `job_cache.json`.
2.  **In-Memory Deduplication**: During the current run, a Python `set` (`current_run_jobs`) stores the unique identifiers (MD5 hash of job title and company name) of all jobs found in the current scraping cycle. This prevents duplicate notifications within a single run.
3.  **Cross-Run Deduplication**: The `job_cache.json` file serves as a temporary persistent storage. Job IDs from the current run, along with a timestamp, are added to the cache.
4.  **Cache Retention**: When `job_cache.json` is loaded, older entries (e.g., jobs older than 24 hours as configured by `CACHE_RETENTION_HOURS` in `main.py`) are automatically filtered out. This keeps the cache size manageable and ensures that very old job postings don't permanently prevent new, relevant postings from being notified if they reappear.
5.  **Overwrite on End**: After each successful scraping and notification cycle, the entire `job_cache.json` file is overwritten with the updated set of job IDs, effectively maintaining a rolling window of recently processed jobs.

This approach ensures that the bot remains stateless from a deployment perspective (no external database required) while effectively managing deduplication across scheduled runs.
