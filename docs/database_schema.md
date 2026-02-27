# Database Schema Reference

Location Analyzer v2 uses a local SQLite database by default to cache extraction data, preventing redundant API calls and Playwright scraping costs.

## Location
**Path:** `data/location_analyzer.db`
*This directory is automatically mounted as a volume when running via Docker Compose.*

## Core Entity-Relationship Model

The schema is anchored by the `postcodes` table. All scraped features (Demographics, Transport, Amenities) are related via a `1-to-1` Foreign Key mapping on `postcode`.

### 1. `postcodes`
The master record tracking ML predictions and scraping metadata.
* `postcode` (Primary Key, VARCHAR 10): e.g. "SW1A 1AA"
* `outercode` (Index, VARCHAR 5): e.g. "SW1A"
* `address` (VARCHAR 255): Formatted Street Address (Optional)
* `prediction` (FLOAT): The median 1st-month sales prediction from XGBoost
* `min_prediction` (FLOAT): The lower bound sales prediction
* `max_prediction` (FLOAT): The upper bound sales prediction
* `created_at` (DATETIME)
* `updated_at` (DATETIME): Used to trigger cache-invalidation (TTL 30 days)

### 2. `demographics`
Derived from `Nomis/Doogal` (Census 2021)
* `id` (Primary Key, INTEGER)
* `postcode` (Foreign Key -> postcodes.postcode)
* `population` (INTEGER)
* `households` (INTEGER)
* `white` (FLOAT, 0.0-1.0): Percentage of demographic
* `non_white` (FLOAT, 0.0-1.0)
* `working` (FLOAT, 0.0-1.0): Employed population
* `unemployed` (FLOAT, 0.0-1.0): Unemployed population
* `unemployment_rate` (FLOAT, 0.0-1.0): True unemployment rate
* `ab` (FLOAT, 0.0-1.0): Social Grade AB (Higher/Intermediate Managerial)
* `c1_c2` (FLOAT, 0.0-1.0): Social Grade C1/C2 (Supervisory/Skilled Manual)
* `de` (FLOAT, 0.0-1.0): Social Grade DE (Semi-skilled/Unskilled)
* `avg_household_income` (FLOAT)

### 3. `crystal_transport`
Derived from `CrystalRoofScraper` (Connectivity)
* `id` (Primary Key, INTEGER)
* `postcode` (Foreign Key -> postcodes.postcode)
* `accessibility_score` (INTEGER): Index 0-8 (8 = Excellent)
* `raw_data` (JSON): Stores an array of nearest stations, transport types (Underground/National Rail), and distance (miles).

### 4. `crystal_restaurants`
Derived from `CrystalRoofScraper` (Competitor / Foot Traffic Indicators)
* `id` (Primary Key, INTEGER)
* `postcode` (Foreign Key -> postcodes.postcode)
* `fast_food_takeaway` (INTEGER): Count within radius
* `restaurant_cafe` (INTEGER): Count within radius
* `raw_data` (JSON): Array of explicitly named nearby restaurants.

### 5. `universities`
Derived from `GoogleMapsScraper` (Student Foot Traffic)
* `id` (Primary Key, INTEGER)
* `postcode` (Foreign Key -> postcodes.postcode)
* `count` (INTEGER): Universities within 2 miles
* `raw_data` (JSON): Array of university names and proximity.

### 6. Display Data Tables (Raw JSON Caches)
The following tables strictly store `raw_data` JSON objects. They are not used by the XGBoost ML Pipeline, but are required to populate the rich Frontend Dashboard charts (Pie Charts, Bar Charts).
* `crystal_ethnicity` -> (postcode, JSON array of ethnic breakdowns)
* `crystal_pubs` -> (postcode, pub count, JSON array of pubs)
* `crystal_income` -> (postcode, JSON array of local vs national income distribution)
* `crystal_occupation` -> (postcode, JSON array of job sector distributions)
