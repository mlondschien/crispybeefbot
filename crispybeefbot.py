import base64
import json
import os
from email.message import EmailMessage
import sys
import requests
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from google.auth.transport.requests import Request
import datetime
from pathlib import Path
import re


MENSA_IDS = {
    "Clausiusbar": 3,
    "Dozentenfoyer": 5,
    "food&lab": 7,
    "Archimedes": 8,
    "Polyterrasse": 9,
    "Polysnack": 10,
    "Tannenbar": 11,
    "Food Market (grill bbq)": 18,
    "Food Market (green day)": 17,
    "Fusion": 20,
}

BASE_URL = "https://idapps.ethz.ch/cookpit-pub-services/v1/weeklyrotas?client-id=ethz-wcms&lang=de&rs-first=0&rs-size=50"

with open(Path(__file__).parent / "messages.json") as f:
    items = json.load(f)

today = datetime.date.today().strftime("%Y-%m-%d")
next_week = (datetime.date.today() + datetime.timedelta(days=7)).strftime("%Y-%m-%d")

emails = []

for item in items.values():
    for mensa in item["mensas"]:
        mensa_id = MENSA_IDS[mensa]

        url = f"{BASE_URL}&valid-after={today}&valid-before={next_week}&facility={mensa_id}"

        response = json.loads(requests.get(url, headers={"User-Agent": "Custom"}, json=True).text)

        if len(response["weekly-rota-array"]) == 0:
            continue
        
        start_of_the_week = datetime.datetime.strptime(
            response["weekly-rota-array"][0]["valid-from"], "%Y-%m-%d"
        )
        entries_this_week = response["weekly-rota-array"][0]["day-of-week-array"]

        for entry in entries_this_week:
            day = entry.get("day-of-week-desc")
            if day in ["Samstag", "Sonntag"]:
                continue
            date = (
                start_of_the_week + datetime.timedelta(days=int(entry["day-of-week-code"]) - 1)
            ).strftime("%Y-%m-%d")
            meal_times = entry.get("opening-hour-array",[{}])[0].get("meal-time-array", [])
            for meal_time in meal_times:
                if "dinner" in meal_time["name"].lower() or "Abend" in meal_time["name"]:
                    continue

                for meal in meal_time["line-array"]:
                    if "meal" not in meal:
                        # E.g., if one day is a holiday:
                        # (Pdb) meal_time["line-array"]
                        # [{'name': 'fire'}, {'name': 'grill'}]
                        continue  
    

                    name = meal["meal"]["name"]
                    if re.search(item["regex"], name, re.IGNORECASE) is not None:
                        emails += [(mensa, day, date, name, item["recipients"])]

if len(emails) == 0:
    sys.exit()

def create_event(creds, mensa, day, date, name, attendees):
    service = build("calendar", "v3", credentials=creds)

    start = f"{date}T12:00:00"
    end = f"{date}T13:00:00"

    event = {
        "summary": f"{name} on {date} ({day}) at {mensa}",
        "location": mensa,
        "description": name,
        "start": {"dateTime": start, "timeZone": "Europe/Zurich"},
        "end": {"dateTime": end, "timeZone": "Europe/Zurich"},
        "attendees": [{"email": attendee} for attendee in attendees],
    }

    # sendUpdates="all" sends an email to all attendees
    return (
        service.events()
        .insert(calendarId="primary", body=event, sendUpdates="all")
        .execute()
    )


def send_message(creds, subject, content, to, sender="crispybeefbot"):
    # From https://developers.google.com/gmail/api/guides/sending
    try:
        service = build("gmail", "v1", credentials=creds)
        message = EmailMessage()

        message.set_content(content)

        message["To"] = to
        message["From"] = sender
        message["Subject"] = subject

        # encoded message
        encoded_message = base64.urlsafe_b64encode(message.as_bytes()).decode()

        create_message = {"raw": encoded_message}

        service.users().messages().send(userId="me", body=create_message).execute()

    except Exception as e:
        return e

creds = Credentials.from_authorized_user_info(json.loads(os.environ["GOOGLE_TOKEN"]))
if not creds.valid:
    # Note: If the "app" is in testing, the refresh token will be valid for 7 days only.
    # "publish" the "app" to circumvent this. Still, need to refresh the auth token
    # with the refresh token (both part of the GOOGLE_TOKEN json).
    creds.refresh(Request())

errors = []
events = []

for email in emails:

    try:
        create_event(creds, *email)
        # Unused, as the htmlLink appears not to work...
        # events.append(f"{crispy_beef[0]}: {res['htmlLink']}")
    except Exception as e:
        errors.append(e)

if len(errors) > 0:
    raise Exception(errors)
