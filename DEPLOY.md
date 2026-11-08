# Deploying TPA Ascend Search for free

Everything here runs on free tiers that never ask for a credit card: GitHub (private repo + Actions), Streamlit
Community Cloud, and SerpApi's free plan. Without a payment method on file, none of them can charge you: if a free
limit runs out, the service simply pauses until next month.

## How it fits together

```
GitHub Actions (twice a day)            data branch                  Streamlit Community Cloud
scan.yml: load DB → scan → news   ──▶   ascend.db.gz (one commit,  ──▶  app checks every 10 min and
        → save DB                       overwritten each scan)          switches to the newest scan
```

- **Scans** use fast-flights (Google Flights, free, no quota). If Google blocks GitHub's servers (3 failures in a
  row), that scan switches to SerpApi for a small fixed plan: 3 destinations × first date window × one-way and round
  trip = 6 searches, once a day at most, never going over 200 a month and always leaving the last 50 untouched
  for testing and the demo.
- **The app** only reads the database. Live search on the server uses free fast-flights only (`LIVE_SERPAPI=off`),
  capped per day (`LIVE_SEARCH_DAILY_CAP`), with a friendly message once the cap is reached. Book now is always the free
  Google Flights link.
- **Actions minutes:** a scan takes about 15–30 minutes; 2 a day is about 1,500 of the 2,000 free minutes a month
  for a private repo.

## Steps

### 1. Accounts (already done: GitHub; check SerpApi)
- SerpApi: sign in at serpapi.com → *Your Account* and note the real monthly searches on the free plan. Keep
  `SERPAPI_MONTHLY_BUDGET` (in `.github/workflows/scan.yml`) below it. It's 200 now.
- Your laptop's `.env` key and GitHub share one SerpApi account, so local live searches count against the same quota.

### 2. Code on GitHub
- `.env` and `.streamlit/secrets.toml` are in `.gitignore`; the repo stays **private**.
- Repo secret `SERPAPI_API_KEY` is set (Settings → Secrets and variables → Actions).

### 3. Run the scan once
After the PR is merged into `main`: **Actions → Price scan → Run workflow**. When it finishes, its summary shows
searches OK/failed, fares saved and SerpApi used. A run that saves no fares fails on purpose and leaves the previous
data in place. The `data` branch is already seeded with a copy of the local database as the demo backup.

### 4. Read-only token for the app
github.com → Settings → Developer settings → **Fine-grained personal access tokens → Generate new token**
- Repository access: *Only select repositories* → `tpa-ascend-search`
- Repository permissions: **Contents: Read-only** (nothing else)
- Expiration: up to 1 year (put a reminder to renew it)

### 5. Deploy on Streamlit Community Cloud
share.streamlit.io → *Continue with GitHub* → **Create app → Deploy a public app from GitHub**
- Repository `aineshkumar7official/tpa-ascend-search`, branch `main`, main file `app.py`
- App URL: e.g. `tpa-ascendsearch`
- **Advanced settings** → Python **3.12**, and paste into Secrets:

```toml
DATA_REPO = "aineshkumar7official/tpa-ascend-search"
GITHUB_TOKEN = "github_pat_..."        # the token from step 4
FARE_OPTIONS = "off"                    # no Chrome on the server
LIVE_SERPAPI = "off"                    # public visitors never spend SerpApi
LIVE_SEARCH_DAILY_CAP = "60"            # live Google requests per day for the whole app
```

Then **Deploy**. Pushing to `main` redeploys the app automatically; new prices need no redeploy.

### 6. Share it
Apps from a private repo start private. In the app's **Settings → Sharing**, choose *This app is public* to share
the link. Free apps go to sleep after a while without visitors and wake up (about 30 seconds) on the next visit.
