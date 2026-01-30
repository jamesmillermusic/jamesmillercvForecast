### Forecasting various time periods in 2026 ### COMBINED WITH ### Auto-updating SARIMAX order and seasonal_order parameters ###

import pandas as pd
import itertools
import warnings
from statsmodels.tsa.statespace.sarimax import SARIMAX
import matplotlib.pyplot as plt
import json
from datetime import datetime
import gspread
from google.oauth2.service_account import Credentials

warnings.filterwarnings("ignore")

# =========================
# 1. Load and prepare data
# =========================
URL = "https://docs.google.com/spreadsheets/d/12XxYn4zgcHVMJfme0rvQRA4eyJe9y005nc8Jx2DM9f8/export?format=csv&gid=1047244059"

df = pd.read_csv(URL, parse_dates=["Date"], dayfirst=True)
df = df.sort_values("Date").set_index("Date")
df["Actual Views"] = df["Actual Views"].fillna(0)
df = df.asfreq("D", fill_value=0)
df.index = pd.to_datetime(df.index)

print("Index monotonic:", df.index.is_monotonic_increasing)
print("Missing values:", df.isnull().sum().sum())
print("Latest data point:", df.index.max())
print("Current YTD (2026):", df.loc[df.index.year == 2026, "Actual Views"].sum())

# =========================
# 2. Hyperparameter tuning (best order)
# =========================
print("\nRunning SARIMAX grid search... this may take a few minutes.")

p = d = q = range(0, 3)
P = D = Q = range(0, 2)
s = 7  # weekly seasonality
pdq = list(itertools.product(p, d, q))
seasonal_pdq = list(itertools.product(P, D, Q))

best_aic = float("inf")
best_order = None
best_seasonal_order = None

for order_candidate in pdq:
    for seasonal_candidate in seasonal_pdq:
        try:
            model = SARIMAX(
                df["Actual Views"],
                order=order_candidate,
                seasonal_order=(seasonal_candidate[0], seasonal_candidate[1], seasonal_candidate[2], s),
                enforce_stationarity=False,
                enforce_invertibility=False
            )
            results_test = model.fit(disp=False)
            if results_test.aic < best_aic:
                best_aic = results_test.aic
                best_order = order_candidate
                best_seasonal_order = (seasonal_candidate[0], seasonal_candidate[1], seasonal_candidate[2], s)
        except:
            continue

print(f"\nBest order: {best_order}, Best seasonal_order: {best_seasonal_order}, AIC: {best_aic:.1f}")

# =========================
# 3. Fit SARIMAX with best params
# =========================
model = SARIMAX(
    df["Actual Views"],
    order=best_order,
    seasonal_order=best_seasonal_order,
    enforce_stationarity=False,
    enforce_invertibility=False
)
results = model.fit(disp=False)

# =========================
# 4. Compute bias from residuals
# =========================
residuals = results.resid
bias_daily = residuals.mean()
print(f"Daily bias correction: {bias_daily:.2f}")

# =========================
# 5. Forecast helper function with bias correction
# =========================
def forecast_period(start_date, end_date):
    """Forecast total views from start_date to end_date inclusive with bias correction"""
    last_observed = df.index.max()
    forecast_days = (end_date - last_observed).days
    forecast_days = max(forecast_days, 0)

    actual_period = df.loc[(df.index >= start_date) & (df.index <= end_date), "Actual Views"].sum()

    if forecast_days > 0:
        forecast = results.get_forecast(steps=forecast_days)
        mean = forecast.predicted_mean - bias_daily  # apply daily bias correction
        conf = forecast.conf_int()
        conf_lower = conf.iloc[:, 0] - bias_daily
        conf_upper = conf.iloc[:, 1] - bias_daily

        total = actual_period + mean.sum()
        lower = actual_period + conf_lower.sum()
        upper = actual_period + conf_upper.sum()
    else:
        total = actual_period
        lower = actual_period
        upper = actual_period

    return {"Actual": actual_period, "Forecast": total, "CI Lower": lower, "CI Upper": upper}

# =========================
# 6. Define forecast periods
# =========================
today = pd.Timestamp.now().normalize()
current_year = today.year

periods = {
    "7 Days from Now": (today, today + pd.Timedelta(days=6)),
    "Current Calendar Month": (pd.Timestamp(today.year, today.month, 1),
                               pd.Timestamp(today.year, today.month, 1) + pd.offsets.MonthEnd(0)),
    "Next Calendar Month": (pd.Timestamp(today.year, today.month, 1) + pd.offsets.MonthBegin(1),
                            pd.Timestamp(today.year, today.month, 1) + pd.offsets.MonthEnd(1)),
    "Next 3 Calendar Months": (pd.Timestamp(today.year, today.month, 1) + pd.offsets.MonthBegin(1),
                               pd.Timestamp(today.year, today.month, 1) + pd.offsets.MonthEnd(3)),
    "First Half of Year": (pd.Timestamp(current_year, 1, 1), pd.Timestamp(current_year, 6, 30)),
    "Last Half of Year": (pd.Timestamp(current_year, 7, 1), pd.Timestamp(current_year, 12, 31)),
    "Full Year": (pd.Timestamp(current_year, 1, 1), pd.Timestamp(current_year, 12, 31))
}

# =========================
# 7. Run forecasts and output
# =========================
results_dict = {}
for name, (start, end) in periods.items():
    results_dict[name] = forecast_period(start, end)

for name, values in results_dict.items():
    print(f"\n=== {name} ===")
    print(f"Actual Observed: {values['Actual']}")
    print(f"Forecast Total: {values['Forecast']:.1f}")
    print(f"95% CI Lower: {values['CI Lower']:.1f}")
    print(f"95% CI Upper: {values['CI Upper']:.1f}")

# Print forecasts only
print("\n\n===Forecast totals===")
for name, values in results_dict.items():
    print(f"{name}: {values['Forecast']:.1f}")
    
# =========================
# 8. Plot residuals
# =========================
residuals.plot(title="Residuals")
plt.show()



# =========================
# 9. Prepare output row (JSON for GitHub Actions)
# =========================
timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

row = {
    "Timestamp": timestamp
}

for name, values in results_dict.items():
    row[name] = round(values["Forecast"], 1)

print(json.dumps(row))


# =========================
# 10. Write to Google Sheets
# =========================
SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]
CREDS = json.loads(open("creds.json").read())
SPREADSHEET_ID = "12XxYn4zgcHVMJfme0rvQRA4eyJe9y005nc8Jx2DM9f8"

creds = Credentials.from_service_account_info(CREDS, scopes=SCOPES)
client = gspread.authorize(creds)

sheet = client.open_by_key(SPREADSHEET_ID).worksheet("Forecast Log")

with open("output.json") as f:
    row = json.loads(f.read())

# Order must match headers
headers = sheet.row_values(1)
values = [row.get(h, "") for h in headers]

sheet.append_row(values, value_input_option="USER_ENTERED")
