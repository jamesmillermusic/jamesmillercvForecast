import os
import json
import gspread
from google.oauth2.service_account import Credentials

SPREADSHEET_ID = "12XxYn4zgcHVMJfme0rvQRA4eyJe9y005nc8Jx2DM9f8"
SHEET_NAME = "Forecast Log"

creds_dict = json.loads(os.environ["GOOGLE_CREDS"])

scopes = ["https://www.googleapis.com/auth/spreadsheets"]
creds = Credentials.from_service_account_info(creds_dict, scopes=scopes)
client = gspread.authorize(creds)

sheet = client.open_by_key(SPREADSHEET_ID).worksheet(SHEET_NAME)

with open("output.json") as f:
    row = json.loads(f.read())

headers = sheet.row_values(1)
values = [row.get(h, "") for h in headers]

sheet.append_row(values, value_input_option="USER_ENTERED")
