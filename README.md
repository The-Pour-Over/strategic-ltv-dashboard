# Strategic LTV Monthly Dashboard

Auto-updating LTV dashboard for The Pour Over, powered by beehiiv segment data.

## Setup

1. Push this repo to GitHub
2. Go to **Settings → Secrets → Actions** and add:
   - `BEEHIIV_API_KEY` — your beehiiv API key (Settings → API in beehiiv)
3. Go to **Settings → Pages** and set source to **Deploy from branch: main / root**
4. Your dashboard will be live at `https://nicolethepourover.github.io/<repo-name>/`

## How it works

- A GitHub Action runs on the **1st of every month at 8am UTC**
- It fetches fresh data from all T+ beehiiv segments
- Updates `index.html` with the new numbers and today's date
- Commits and pushes — GitHub Pages serves the updated file automatically

## Manual refresh

Go to **Actions → Monthly beehiiv Data Update → Run workflow** to trigger a refresh any time.
