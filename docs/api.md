# Location Analyzer v2 — API Reference

The backend exposes a single, highly-optimized RPC-style endpoint serving as the bridge between the Frontend interface and the ML Engine.

---

## `POST /predict`

Triggers real-time web-scraping for a specific location, feeds the extracted data into the XGBoost model, and returns a 12-month trailing sales forecast.

**Endpoint URL:** `http://127.0.0.1:8000/predict`
**Content-Type:** `application/json`

### Request Body Schema

| Field | Type | Required | Description |
| :--- | :--- | :--- | :--- |
| `postcode` | `string` | **Yes** | A valid UK Postcode (e.g., `"SW1A 1AA"` or `"m1 1af"`). Case and space insensitive. |
| `branch_name` | `string` | No | Internal name label for the dashboard UI display. |

**Example Request:**
```json
{
  "postcode": "M1 1AF",
  "branch_name": "Manchester Central"
}
```

### Response Schema

Returns a `200 OK` JSON response upon successful prediction.

| Field | Type | Description |
| :--- | :--- | :--- |
| `postcode` | `string` | The validated and normalized postcode. |
| `predicted_sales` | `float` | Estimated baseline average weekly revenue in GBP. |
| `currency` | `string` | Fixed to `"£"`. |
| `features` | `object` | An aggregated dictionary of all raw geographical, amenity, and demographic data scraped by the inference pipeline before transformations. |
| `time_series` | `array` | A 12-item array projecting future sales. Each containing `{ "date": "Jan 2026", "predicted_sales": 1500.50 }`. |

**Example Response:**
```json
{
  "postcode": "M1 1AF",
  "predicted_sales": 8450.25,
  "currency": "£",
  "features": {
    "population": 23405,
    "avg_household_income": 41200,
    "Transport_Accessibility_Score": 6,
    "ab": 3500
  },
  "time_series": [
    { "date": "Feb 2026", "predicted_sales": 8450.25 },
    { "date": "Mar 2026", "predicted_sales": 8800.00 },
    { "date": "Apr 2026", "predicted_sales": 9102.50 }
  ]
}
```

---

### Error Handling

| Status Code | Reason | Cause |
| :--- | :--- | :--- |
| `422 Unprocessable Entity` | **Validation Error** | The JSON payload was missing the required `postcode` field. |
| `404 Not Found` | **Extraction Error** | The scraper network could not locate data for the provided postcode (e.g., an invalid code). |
| `500 Internal Server Error` | **Pipeline/ML Error** | Catastrophic failure during inference. Includes failing Scikit-Learn strict-type validations, or the Web Scrapers being proxy blocked. |
