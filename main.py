from fastapi import FastAPI, HTTPException, Body
from pydantic import BaseModel
from typing import List
from motor.motor_asyncio import AsyncIOMotorClient
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, NoSuchElementException
from fastapi.middleware.cors import CORSMiddleware
from datetime import datetime
import logging
import httpx

# MongoDB Configuration
MONGO_URI = "mongodb+srv://nafseerck:7gbNMNAc5s236F5K@overthetop.isxuv3s.mongodb.net"
DATABASE_NAME = "ninjadb"
COLLECTION_NAME = "wordpressUrls"


# Telegram Bot Configuration
TELEGRAM_BOT_TOKEN = "7850246709:AAF86-OK1MJj5_1eUCJhl5MZ9i2jCatZVNg"
TELEGRAM_CHAT_ID = "1780375318"

# Selenium Configuration
CHROMEDRIVER_PATH = "/usr/local/bin/chromedriver"
# CHROMEDRIVER_PATH = "/Users/nafseerck/OTT/domain-hider-selenium/chromedriver"
service = Service(CHROMEDRIVER_PATH)
options = webdriver.ChromeOptions()
options.add_argument("--headless")
options.add_argument("--disable-gpu")
options.add_argument("--no-sandbox")
options.page_load_strategy = "eager"

# FastAPI Setup
app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Adjust this in production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Logging Configuration
logging.basicConfig(level=logging.INFO)

# MongoDB Client
client = AsyncIOMotorClient(MONGO_URI)
db = client[DATABASE_NAME]
collection = db[COLLECTION_NAME]

# Pydantic Model
class WordPressUrl(BaseModel):
    url: str
    username: str
    password: str
    
    
async def send_telegram_message(message: str):
    """
    Send a message to a Telegram bot.
    """
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": message,
        "parse_mode": "HTML"
    }
    async with httpx.AsyncClient() as client:
        try:
            response = await client.post(url, json=payload)
            response.raise_for_status()
            logging.info(f"Message sent to Telegram: {message}")
        except httpx.HTTPError as e:
            logging.error(f"Failed to send message to Telegram: {str(e)}")    

@app.post("/wordpress-process/")
async def process_wordpress_urls(data: dict = Body(...)):
    """
    Process WordPress URLs from a JSON body with Telegram notifications.
    """
    wordpress_urls = data.get("wordpressUrls")
    if not wordpress_urls:
        raise HTTPException(status_code=400, detail="Invalid or missing 'wordpressUrls' in payload")

    logging.info(f"Processing {len(wordpress_urls)} WordPress URLs from the request body.")
    
    # Notify Telegram that the process has started
    await send_telegram_message(f"🚀 <b>WordPress Process Started Successfully</b>\nTotal WordPress URLs to process: <b>{len(wordpress_urls)}</b>")

    successful_results = []

    for wp_url in wordpress_urls:
        url = wp_url["url"]
        username = wp_url["username"]
        password = wp_url["password"]
        

        if not url.startswith("http"):
            url = f"https://{url}"

        try:
            with webdriver.Chrome(service=service, options=options) as driver:
                login_url = f"{url.rstrip('/')}/wp-login.php"
                print(login_url)

                # Set a timeout for the page load
                driver.set_page_load_timeout(10)
                try:
                    driver.get(login_url)
                except TimeoutException:
                    logging.info(f"Page load timeout for {url}, skipping this site.")
                    continue

                try:
                    username_input = WebDriverWait(driver, 20).until(
                        EC.presence_of_element_located((By.ID, "user_login"))
                    )
                    password_input = driver.find_element(By.ID, "user_pass")
                    submit_button = driver.find_element(By.ID, "wp-submit")
                    
                    username_input.clear()
                    username_input.send_keys(username)
                    
                    password_input.clear()
                    password_input.send_keys(password)
                    
                    submit_button.click()
                    
                    
                except TimeoutException:
                    logging.info(f"Login form elements not found for {url}")
                    continue

                WebDriverWait(driver, 10).until(lambda d: d.current_url != login_url)
                current_url = driver.current_url

                if "wp-admin" in current_url and "wp-admin/profile.php" not in current_url:
                    logging.info(f"Login successful: {url}")
                    successful_results.append({
                        "url": url,
                        "username": username,
                        "password": password
                    })

                else:
                    logging.info(f"Login failed for {url}")
        except Exception as e:
            logging.error(f"Error processing {url}: {e}")

    if successful_results:
        # Save successful results to MongoDB
        filename = f"processwordpressurl_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        document = {
            "filename": filename,
            "wordpressUrls": successful_results,
            "createdAt": datetime.now(),
        }
        await collection.insert_one(document)
        logging.info(f"Results saved with filename: {filename}")

        # Notify Telegram about successful results
        success_count = len(successful_results)
        await send_telegram_message(
            f"✅ <b>WordPress Process Completed</b>\n"
            f"File Name: <b>{filename}</b>\n"
            f"Total WordPress URLs Processed: <b>{len(wordpress_urls)}</b>\n"
            f"Successful Logins: <b>{success_count}</b>"
        )
    else:
        logging.info("No successful logins to save.")
        await send_telegram_message(
            f"❌ <b>WordPress Process Completed</b>\nNo successful logins were recorded."
        )

    return {
        "message": "Processing completed",
        "successful_results": successful_results
    }
