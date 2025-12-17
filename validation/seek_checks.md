# Sector Data Validation Checks

This document describes all validation checks performed on sector-related data. There are two separate validation systems:

1. **SEEK-Specific Validation** — Purpose-code level checks for health and agriculture spending, fetched directly from SEEK pipeline
2. **Sectors View Validation** — Quality checks on the dashboard's sectors dataset

Both run automatically as part of the full validation process.

---

# Part A: SEEK-Specific Validation

These checks fetch data directly from the SEEK data pipeline (`seek/sectors.py`) at purpose-code level and compare it against previous releases. This validation is independent of the dashboard's sectors_view parquet file.

## A1. Data Fetch Checks (Must Pass)

### A1.1 Data Fetch Successful
- **What it checks**: The SEEK pipeline returns data without errors
- **Why it matters**: If the data fetch fails, no validation can occur
- **Failure means**: There's a problem with the SEEK data source or pipeline

### A1.2 Data Not Empty
- **What it checks**: The fetched data contains at least one row
- **Why it matters**: Empty data indicates a complete pipeline failure
- **Failure means**: The SEEK pipeline returned no results

---

## A2. Release Comparison Checks (Warnings)

These checks compare the current data against the previous release. They generate warnings at three levels:
- **High** — Likely a real problem requiring investigation
- **Medium** — Possibly an issue, worth checking
- **Info** — Notable change, probably fine

### A2.1 How Comparison Works

The SEEK validation tracks three aggregates for each donor:
1. **Total spending** — Sum of all ODA at purpose-code level
2. **Health spending** — Sum filtered to health-related purpose codes only
3. **Agriculture spending** — Sum filtered to agriculture-related purpose codes only

For each aggregate, the system compares the **latest year's data** in the current release against the same data from the previous release.

### A2.2 Drift Detection Method

For each sector (total, health, agriculture), the validation:

1. Calculates the **percentage change** for each donor between releases
2. Computes the **average change** across all donors
3. Computes the **standard deviation** of changes across all donors
4. Calculates a **Z-score** for each donor: how many standard deviations their change is from the average
5. Flags donors using both Z-score and percentage thresholds

**Thresholds:**
- Medium warning: Z-score > 2.0 OR percentage change > 20%
- High warning: Z-score > 3.0 OR percentage change > 40%

This approach catches:
- Donors with unusually large changes relative to other donors (Z-score)
- Any donor with a substantial absolute change (percentage threshold)

---

## A3. Specific SEEK Checks Performed

### A3.1 Total Spending by Donor

**What it checks**: How each donor's total ODA spending changed from the previous release

**Example warnings**:
- "SEEK total: Belgium changed +85% (z=3.2, typical: +5% ± 12%)"
- "SEEK total: Japan changed -25% (z=1.5, typical: +5% ± 12%)"

**Why it matters**: Large changes in total spending may indicate data errors, methodology changes, or significant revisions

### A3.2 Health Spending by Donor

**What it checks**: How each donor's health sector spending changed from the previous release

**Example warnings**:
- "SEEK health: Germany changed -35% (z=2.5, typical: +3% ± 10%)"
- "SEEK health: USA changed +50% (z=2.8, typical: +3% ± 10%)"

**Why it matters**: Health is a priority sector for SEEK analysis; unexpected changes require investigation

### A3.3 Agriculture Spending by Donor

**What it checks**: How each donor's agriculture sector spending changed from the previous release

**Example warnings**:
- "SEEK agriculture: France changed +120% (z=4.1, typical: +8% ± 15%)"
- "SEEK agriculture: UK changed -45% (z=3.0, typical: +8% ± 15%)"

**Why it matters**: Agriculture is a priority sector for SEEK analysis; unexpected changes require investigation

### A3.4 Missing Critical Donors

**What it checks**: Whether any major donor that had spending in the previous release now has zero

**Critical donors monitored**: France, Germany, Italy, Japan, UK, USA, Canada

**Level**: Always High

**Example warnings**:
- "SEEK total: Canada has no data (had 2,500,000 in previous release)"
- "SEEK health: Japan has no data (had 1,200,000 in previous release)"
- "SEEK agriculture: Germany has no data (had 800,000 in previous release)"

**Why it matters**: Major donors dropping to zero is nearly always a data error

### A3.5 New Donors Appearing

**What it checks**: Whether any donors appear in the current release that weren't present before

**Level**: Info

**Example warning**:
- "SEEK total: New donors in this release: Slovenia, Estonia, and 3 others"

**Why it matters**: New donors are typically legitimate additions but worth noting

---

## A4. Purpose Codes Tracked

### A4.1 Health Purpose Codes (29 codes)

| Code | Description |
|------|-------------|
| 120 | Health, general |
| 121 | Health, general (sub-category) |
| 12110 | Health policy and administrative management |
| 12181 | Medical education/training |
| 12182 | Medical research |
| 12191 | Medical services |
| 122 | Basic health |
| 12220 | Basic health care |
| 12230 | Basic health infrastructure |
| 12240 | Basic nutrition |
| 12250 | Infectious disease control |
| 12261 | Health education |
| 12262 | Malaria control |
| 12263 | Tuberculosis control |
| 12264 | COVID-19 control |
| 12281 | Health personnel development |
| 123 | Non-communicable diseases (NCDs) |
| 12310 | NCDs control, general |
| 12320 | Tobacco use control |
| 12330 | Control of harmful use of alcohol and drugs |
| 12340 | Promotion of mental health and well-being |
| 12350 | Other prevention and treatment of NCDs |
| 12382 | Research for prevention and control of NCDs |
| 130 | Population policies/programmes and reproductive health |
| 13010 | Population policy and administrative management |
| 13020 | Reproductive health care |
| 13030 | Family planning |
| 13040 | STD control including HIV/AIDS |
| 13081 | Personnel development for population and reproductive health |

### A4.2 Agriculture Purpose Codes (39 codes)

| Code | Description |
|------|-------------|
| 31110 | Agricultural policy and administrative management |
| 31120 | Agricultural development |
| 31130 | Agricultural land resources |
| 31140 | Agricultural water resources |
| 31150 | Agricultural inputs |
| 31161 | Food crop production |
| 31162 | Industrial crops/export crops |
| 31163 | Livestock |
| 31164 | Agrarian reform |
| 31165 | Agricultural alternative development |
| 31166 | Agricultural extension |
| 31181 | Agricultural education/training |
| 31182 | Agricultural research |
| 31191 | Agricultural services |
| 31192 | Plant and post-harvest protection and pest control |
| 31193 | Agricultural financial services |
| 31194 | Agricultural co-operatives |
| 31195 | Livestock/veterinary services |
| 31210 | Forestry policy and administrative management |
| 31220 | Forestry development |
| 31261 | Fuelwood/charcoal |
| 31281 | Forestry education/training |
| 31282 | Forestry research |
| 31291 | Forestry services |
| 31310 | Fishing policy and administrative management |
| 31320 | Fishery development |
| 31381 | Fishery education/training |
| 31382 | Fishery research |
| 31391 | Fishery services |
| 43040 | Rural development |
| 43041 | Multi-sector aid for basic social services |
| 43042 | Rural land policy and management |
| 43050 | Non-agricultural alternative development |
| 43060 | Household food security programmes |
| 43071 | Food security policy and administrative management |
| 43072 | Household food security programmes |
| 43073 | Food safety and quality |
| 43081 | Multi-hazard response preparedness |
| 43082 | Disaster risk reduction |

---

## A5. SEEK Manifest

The SEEK validation stores history in: `validation_data/manifests/seek_sectors_validation.json`

**Contents:**
- Release history with timestamps
- Total, health, and agriculture spending by donor for each release
- Latest year used for comparison

**First run:** Establishes baseline, no warnings generated (nothing to compare against)

### A5.1 Release Name Handling

The release name (e.g., "april_2025") represents the OECD data release, not the computation date. You provide this explicitly when running validation.

**Comparison logic:**
- Always compares against the **most recent stored release** by timestamp
- Running the same release name multiple times compares against existing stored data
- When a new OECD data release comes out, use a new release name (e.g., "june_2025")

**Example workflow:**
1. First run (release="april_2025"): Creates baseline, no comparison
2. Re-run (release="april_2025"): Compares against stored "april_2025" data
3. New data (release="june_2025"): Compares against "april_2025"
4. Re-run (release="june_2025"): Compares against stored "june_2025" data

---

# Part B: Sectors View Validation

These checks validate the `sectors_view` parquet dataset used by the dashboard. This data is at the sub-sector level (aggregated from purpose codes).

## B1. Hard Gate Checks (Must Pass)

These checks must pass for the data to be considered valid. Failures block deployment.

### B1.1 File Exists
- **What it checks**: The sectors_view data directory exists and can be read
- **Why it matters**: Without the data, no dashboard visualisations work
- **Failure means**: The data pipeline didn't complete successfully

### B1.2 Data Not Empty
- **What it checks**: The dataset contains at least one row
- **Why it matters**: An empty dataset indicates a complete pipeline failure
- **Failure means**: Something went wrong during data extraction or processing

### B1.3 Schema Valid
- **What it checks**: All required columns are present
- **Required columns**:
  - `year` — The reporting year
  - `donor_code`, `donor_name` — Who provided the aid
  - `recipient_code`, `recipient_name` — Who received the aid
  - `indicator`, `indicator_name` — Type of flow (Bilateral or Imputed multilateral)
  - `sector_name`, `sub_sector_code`, `sub_sector_name` — What the aid was for
  - Value columns in 4 currencies × 2 price types (current/constant)
- **Why it matters**: Missing columns break dashboard queries
- **Failure means**: The pipeline produced incomplete output

### B1.4 No Duplicate Records
- **What it checks**: Each combination of year + donor + recipient + indicator + sub-sector appears only once
- **Why it matters**: Duplicates cause double-counting in totals
- **Failure means**: Data was incorrectly merged during processing

### B1.5 Value Columns Populated
- **What it checks**: Value columns contain actual numbers, not all null
- **Why it matters**: Empty value columns mean no financial data
- **Failure means**: Currency conversion or data extraction failed

### B1.6 Name Mappings Complete
- **What it checks**: Every code has a human-readable name
  - Every `donor_code` has a `donor_name`
  - Every `recipient_code` has a `recipient_name`
  - Every `indicator` has an `indicator_name`
- **Why it matters**: Unmapped codes appear as blank in reports
- **Failure means**: Lookup tables are incomplete

### B1.7 Critical Donors Present
- **What it checks**: All major DAC donors have data
- **Major donors**: France, Germany, Italy, Japan, UK, USA, Canada, and others
- **Why it matters**: Missing major donors makes totals wrong
- **Failure means**: Data filtering incorrectly excluded donors

### B1.8 Values Within Bounds
- **What it checks**: No values exceed physically possible limits
- **Why it matters**: Extremely large values indicate unit errors
- **Failure means**: A calculation or conversion went wrong

---

## B2. Anomaly Detection (Warnings)

These checks compare against previous releases and historical patterns.

### B2.1 Year-over-Year Changes

**What it checks**: Whether each donor's spending change from last year fits their historical pattern

**How it works**: Calculates typical year-over-year variation, flags if current change exceeds 2 standard deviations

**Example warning**: "Germany: 2023 change is +45% (typical: +5% ± 8%, z=5.0)"

### B2.2 Release Drift by Donor

**What it checks**: Whether total spending by donor changed significantly from previous release

**Thresholds**: >20% (medium), >40% (high)

**Example warning**: "Canada: +35% vs previous release"

### B2.3 Row Count Changed

**What it checks**: Whether total number of records changed significantly

**Thresholds**: >15% (medium), >30% (high)

**Example warning**: "Row count: 4,500,000 → 3,800,000 (-15.6%)"

### B2.4 Sector Allocation Drift

**What it checks**: Whether spending distribution across sectors changed significantly

**Thresholds**:
- Overall sector: >20% (medium), >40% (high)
- Donor-sector: >40% (medium), >60% (high)

**Example warning**: "Sector 'Health': -25% vs previous release"

### B2.5 New/Removed Codes

**What it checks**: Whether donor, recipient, indicator, or sector codes were added or removed

**Levels**: Info for new codes, Medium/High for removed codes

**Example warnings**:
- "New donor codes: [999]"
- "Removed sectors: ['Climate']"

### B2.6 Major Donor Data Gaps

**What it checks**: Whether major donors are missing data for the latest year or have all zeros

**Level**: High

**Example warnings**:
- "Japan: No data for 2023 (had data in 2022)"
- "UK: All zeros for 2023"

### B2.7 Indicator Coverage Gaps

**What it checks**: Whether indicators that had data before are now empty

**Level**: High if missing, Medium if all zeros

---

## B3. Sectors View Manifest

The sectors_view validation stores history in: `validation_data/manifests/sectors_view.json`

**Contents:**
- Aggregates by donor, year, sector, sub-sector
- Donor-sector combinations
- Distribution statistics (min, max, median)
- Historical year-over-year variation patterns

---

# Part C: Summary Comparison

| Aspect | SEEK Validation | Sectors View Validation |
|--------|-----------------|------------------------|
| **Data Source** | `seek/sectors.py` (fetched live) | `sectors_view` parquet file |
| **Granularity** | Purpose code level | Sub-sector level |
| **Focus** | Health & agriculture spending | All sectors |
| **Hard Gates** | 2 checks | 8 checks |
| **Anomaly Checks** | 5 check types | 7 check types |
| **Manifest** | `seek_sectors_validation.json` | `sectors_view.json` |

---

# Part D: Running Validation

## Full Validation (Both Systems)

```python
from src.data.scripts.validate import run_validation

result = run_validation(release="april_2025")
```

## SEEK Validation Only

```python
from validation import validate_seek_sectors

report = validate_seek_sectors(release="april_2025")
```

## Sectors View Validation Only

```python
from validation import validate_dataset

report = validate_dataset("sectors_view", release="april_2025")
```

## Skip SEEK (Sectors View Only)

```python
from src.data.scripts.validate import run_validation

result = run_validation(release="april_2025", include_seek=False)
```

---

# Part E: How to Interpret Warnings

### High Priority
Require investigation before using the data:
- Check if OECD data source changed
- Verify methodology revisions
- Compare against other sources
- Document if it's a genuine change

### Medium Priority
Should be reviewed but may not indicate problems:
- Check if change aligns with known policy changes
- Verify affected donors/sectors make sense
- Document if no issue found

### Info Level
For awareness only:
- New codes/donors are usually fine
- No action needed unless something looks wrong
