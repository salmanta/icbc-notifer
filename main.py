import json
import datetime
import os
import platform
import requests
import time
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Set the earliest acceptable appointment date from environment variable
target_date_str = os.getenv('TARGET_DATE', (datetime.date.today() + datetime.timedelta(days=7)).strftime('%Y-%m-%d'))
year, month, day = map(int, target_date_str.split('-'))
TARGET_DATE = datetime.date(year, month, day)

# Telegram configuration from environment variables
TELEGRAM_BOT_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN')
TELEGRAM_CHAT_ID = os.getenv('TELEGRAM_CHAT_ID')

def refresh_token():
    refresh_url = 'https://onlinebusiness.icbc.com/deas-api/v1/webLogin/webLogin'
    refresh_headers = {
        'sec-ch-ua-platform': 'macOS',
        'Cache-control': 'no-cache, no-store',
        'Referer': 'https://onlinebusiness.icbc.com/webdeas-ui/login;type=driver',
        'pragma': 'no-cache',
        'sec-ch-ua': '"Not A(Brand";v="8", "Chromium";v="132"',
        'sec-ch-ua-mobile': '?0',
        'Expires': '0',
        'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/132.0.0.0 Safari/537.36',
        'Accept': 'application/json, text/plain, */*',
        'DNT': '1',
        'Content-Type': 'application/json'
    }
    refresh_data = {
        "drvrLastName": os.getenv('DRIVER_LAST_NAME'),
        "licenceNumber": os.getenv('LICENSE_NUMBER'),
        "keyword": os.getenv('KEYWORD')
    }
    try:
        response = requests.put(refresh_url, headers=refresh_headers, json=refresh_data)
        response.raise_for_status()
        token = response.headers.get('Authorization')
        if token:
            return token
        raise Exception("No token in response headers")
    except Exception as e:
        print(f"Error refreshing token: {str(e)}")
        return None

# API endpoint and base headers
url = 'https://onlinebusiness.icbc.com/deas-api/v1/web/getAvailableAppointments'
headers = {
    'sec-ch-ua-platform': 'macOS',
    'Authorization': 'Bearer DUMMY',
    'Referer': 'https://onlinebusiness.icbc.com/webdeas-ui/booking',
    'sec-ch-ua': '"Not A(Brand";v="8", "Chromium";v="132"',
    'sec-ch-ua-mobile': '?0',
    'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/132.0.0.0 Safari/537.36',
    'Accept': 'application/json, text/plain, */*',
    'DNT': '1',
    'Content-Type': 'application/json'
}

data = {
    "aPosID": 8,
    "examType": "5-R-1",
    "examDate": datetime.date.today().isoformat(),
    "ignoreReserveTime": False,
    "prfDaysOfWeek": "[0,1,2,3,4,5,6]",
    "prfPartsOfDay": "[0,1]",
    "lastName": os.getenv('DRIVER_LAST_NAME'),
    "licenseNumber": os.getenv('LICENSE_NUMBER')
}

# Make the API request
while True:
    try:
        response = requests.post(url, headers=headers, json=data)
        
        # Handle 403 error (token expired)
        if response.status_code == 403:
            print("Token expired. Attempting to refresh...")
            new_token = refresh_token()
            if new_token:
                headers['Authorization'] = new_token
                print("Token refreshed successfully. Retrying request...")
                response = requests.post(url, headers=headers, json=data)
            else:
                print("Failed to refresh token. Will retry in 60 seconds...")
                time.sleep(60)
                continue
        
        response.raise_for_status()  # Raise an exception for other bad status codes
        appointments = response.json()
        print("API Response Status Code:", response.status_code)
        print("API Response:", response.text[:200])  # Print first 200 chars of response for debugging
    except Exception as e:
        print("Error fetching appointments:", str(e))
        time.sleep(60)  # Still sleep on error to avoid rapid retries
        continue

    # Find the earliest available date
    available_dates = sorted([
        datetime.date.fromisoformat(appt["appointmentDt"]["date"]) for appt in appointments
    ])
    earliest_date = available_dates[0] if available_dates else "No appointments available"

    # Check for earlier appointments
    if earliest_date <= TARGET_DATE:
        print("🚨 EARLY APPOINTMENT FOUND! 🚨", earliest_date)

        # Send a message to the Telegram chat
        telegram_message = f"🚨 EARLY APPOINTMENT FOUND! 🚨\n\nAvailable dates: {earliest_date}"
        telegram_url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
        payload = {"chat_id": TELEGRAM_CHAT_ID, "text": telegram_message}
        requests.post(telegram_url, data=payload)

        # Make a loud notification on different platforms
        if platform.system() == "Darwin":  # macOS
            os.system(f"osascript -e 'display notification \"Appointment Available!\" with title \"ICBC\" sound name \"Glass\"'")
            os.system("afplay /System/Library/Sounds/Ping.aiff")  # Play a sound
        elif platform.system() == "Linux":
            os.system("notify-send 'ICBC' 'Appointment Available!'")
            os.system("paplay /usr/share/sounds/freedesktop/stereo/alarm-clock-elapsed.oga")
        elif platform.system() == "Windows":
            import winsound
            winsound.MessageBeep(winsound.MB_ICONEXCLAMATION)

    else:
        print(f"No early appointments found. Earliest available date: {earliest_date}")

    print("Waiting 1 minute before next check...")
    time.sleep(60)  # Changed from 3600 to 60 (1 minute)


