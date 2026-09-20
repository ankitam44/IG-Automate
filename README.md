# IG-Automate

Fully automated Instagram content pipeline for a "fun easy AI tech" account,
built to run entirely on free tiers.

Niche: fun, low-jargon AI tips for a non-technical audience.
Style inspiration: @nextbysophie, @withkundall, @aiwithsachi, @itsmariahbrunner, @leadwithzoe

## How it works

```
research_agent   (weekly)   -> reads config/niche.json + data/competitor_seed.json
                                writes data/strategy.json (pillars, formats, notes)

content_agent    (2x/week)  -> reads strategy.json, asks Gemini for post concepts,
                                renders images (pollinations.ai, free), appends
                                ready posts to data/queue.json

publisher_agent  (hourly)   -> checks data/queue.json for posts whose scheduled_for
                                time has passed, publishes via Instagram Graph API,
                                moves them to data/published_log.json

analytics_agent  (daily)    -> pulls engagement stats for posts 48h+ old, writes
                                them into published_log.json so research_agent's
                                next run can factor in what actually performed
```

All four run as GitHub Actions on cron schedules -- no server required. State
lives in JSON files committed back to the repo by the workflows themselves.

## One-time setup

### 1. Gemini API key (free)
- Go to https://aistudio.google.com/apikey, create a key.
- Free tier: ~15 requests/min, 1M tokens/day on gemini-1.5-flash. Enough for
  this pipeline's volume.

### 2. Instagram Business account + Graph API access (free)
- Convert your Instagram account to a Business or Creator account (in-app).
- Link it to a Facebook Page (required by the Graph API, even though you'll
  never post to the Page itself).
- Create a Meta developer app at https://developers.facebook.com/apps,
  add the "Instagram Graph API" product.
- Generate a long-lived Page access token with `instagram_content_publish`
  and `pages_read_engagement` permissions. Use the Graph API Explorer to
  get a short-lived token first, then exchange it for a long-lived one
  (60 days). You'll need to repeat this exchange periodically -- token
  refresh automation is not yet built (see Known Limitations).
- Find your Instagram Business Account ID via:
  `GET /me/accounts` -> `GET /{page-id}?fields=instagram_business_account`

### 3. Make the repo public
The publisher needs publicly reachable image URLs (raw.githubusercontent.com).
Graph API cannot accept direct file uploads. Set this repo to public in
Settings, or swap `lib/image_client.py`/`publisher_agent.py` for a paid image
host later if you'd rather stay private.

### 4. Add repo secrets
Settings > Secrets and variables > Actions > New repository secret:
- `GEMINI_API_KEY`
- `IG_BUSINESS_ACCOUNT_ID`
- `IG_ACCESS_TOKEN`

### 5. Enable Actions and seed content
- Go to the Actions tab, enable workflows if prompted.
- Manually run "Research Agent" once (workflow_dispatch) to generate an
  initial strategy.
- Manually run "Content Agent" once to fill the queue.
- From then on, everything runs on its own schedule.

## Editing your strategy

- `config/niche.json` -- niche, tone, audience, content pillars, posting
  cadence (days/time/timezone). Edit any time; picked up on the next
  research_agent run.
- `data/competitor_seed.json` -- manually add reference posts from creators
  you admire (screenshot + describe hook/format/why it worked). Free tier
  has no automated Instagram scraper, so this is how you seed taste until
  the account has enough of its own performance data.

## Local testing

```bash
cp .env.example .env   # fill in keys
export $(cat .env | xargs)
python agents/research_agent.py
python agents/content_agent.py
```
(`publisher_agent.py` requires `GITHUB_REPOSITORY` to be set and the repo
to be public with pushed images, so it's easiest to test via workflow_dispatch
in Actions rather than locally.)

## Known limitations (free tier)

- **No automated competitor scraping.** Seed `data/competitor_seed.json`
  manually. The strategy improves automatically over time as your own
  posts accumulate engagement data.
- **Images only, no reels.** Free video generation isn't good enough yet;
  reels stay a manual/future addition.
- **Image quality is best-effort.** pollinations.ai is a free public
  service, not a paid SLA. Swap `lib/image_client.py` for Ideogram/Stability
  if/when there's budget.
- **Instagram token expiry.** Long-lived tokens expire after 60 days;
  refresh manually until token-refresh automation is added.
- **Rate limits.** Gemini free tier and pollinations.ai can throttle under
  heavy use; this pipeline's default cadence (2-3 posts/week) stays well
  within limits.
