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

today = datetime.date.today().strftime("%Y-%m-%d")
next_week = (datetime.date.today() + datetime.timedelta(days=7)).strftime("%Y-%m-%d")

url = f"https://idapps.ethz.ch/cookpit-pub-services/v1/weeklyrotas/?client-id=ethz-wcms&lang=de&rs-first=0&rs-size=50&valid-after={today}&valid-before={next_week}&facility=3"

response = json.loads(
    requests.get(url, headers={"User-Agent": "Custom"}, json=True).text
)
start_of_the_week = datetime.datetime.strptime(
    response["weekly-rota-array"][0]["valid-from"], "%Y-%m-%d"
)
entries_this_week = response["weekly-rota-array"][0]["day-of-week-array"]
crispy_beefs = []

for entry in entries_this_week:
    day = entry["day-of-week-desc"]
    if day in ["Samstag", "Sonntag"]:
        continue
    date = (
        start_of_the_week + datetime.timedelta(days=int(entry["day-of-week-code"]) - 1)
    ).strftime("%Y-%m-%d")
    meal_times = entry["opening-hour-array"][0]["meal-time-array"]
    for meal_time in meal_times:
        if meal_time["name"] != "Mittag":
            continue

        for meal in meal_time["line-array"]:
            name = meal["meal"]["name"]
            # description = meal["meal"]["description"]
            if name.lower() == "crispy beef":
                crispy_beefs += [(day, date)]

if len(crispy_beefs) == 0:
    sys.exit()


def create_event(creds, weekday, date, attendees):
    service = build("calendar", "v3", credentials=creds)
    start = f"{date}T12:00:00"
    end = f"{date}T13:00:00"

    event = {
        "summary": f"Crispy Beef on {date} ({weekday})",
        "location": "Clausiusbar",
        "description": "Crispy Beef",
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

with open("recipients.txt", "r") as r:
    recipients = r.read().split("\n")

errors = []
events = []

for crispy_beef in crispy_beefs:
    try:
        res = create_event(creds, crispy_beef[0], crispy_beef[1], recipients)
        # Unused, as the htmlLink appears not to work...
        events.append(f"{crispy_beef[0]}: {res['htmlLink']}")
    except Exception as e:
        errors.append(e)

subject = f"Crispy Beef this {' and '.join(c[0] for c in crispy_beefs)}"
for recipient in recipients:
    error = send_message(creds, subject, "", recipient)
    if error is not None:
        errors.append(error)

if len(errors) > 0:
    raise Exception(errors)
