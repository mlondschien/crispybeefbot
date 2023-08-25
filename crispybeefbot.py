import base64
import json
import os
from email.message import EmailMessage
import sys
import requests
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build

url = "http://mensazurich.ch:8080/api/de/all/getMensaForCurrentWeek"

response = json.loads(
    requests.get(url, headers={"User-Agent": "Custom"}, json=True).text
)

crispy_beefs = []

for date, info in response["Clausiusbar"]["weekdays"].items():
    for mealtype, meal in info["mealTypes"].items():
        for menu in meal["menus"]:
            if "crispy beef" in " ".join(menu["description"]).lower():
                crispy_beefs += [(info["label"], date)]

# if len(crispy_beefs) == 0:
    # sys.exit()

subject = f"Crispy Beef on {' and '.join(c[0] for c in crispy_beefs)}"


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

with open("recipients.txt", "r") as r:
    recipients = r.read().split("\n")

errors = []
for recipient in recipients:
    error = send_message(creds, subject, "", recipient)
    if error is not None:
        errors.append(error)

if len(errors) > 0:
    raise Exception(errors)
