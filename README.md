# IG-Automate

Fully automated Instagram content pipeline for a "fun easy AI tech" account,
built to run entirely on free tiers.

Niche: fun, low-jargon AI tips for a non-technical audience.
Style inspiration: @nextbysophie, @withkundall, @aiwithsachi, @itsmariahbrunner, @leadwithzoe

## How it works

```
research_agent   (weekly)   -> reads config/niche.json + data/competitor_seed.json
                                + a live scrape of each seed creator's recent posts
                                (Apify, optional -- see setup) + real engagement data
                                from published_log.json + live AI/tech trend signal
                                (Hacker News, free, no key)
                                writes data/strategy.json (pillars, formats, notes,
                                paused_pillars/formats, decision_log)

content_agent    (2x/week)  -> reads strategy.json, asks Groq for post concepts
                                (respecting whatever research_agent paused, and
                                riffing on trending topics where they fit), renders
                                images (pollinations.ai, free), appends ready posts
                                to data/queue.json

publisher_agent  (hourly)   -> checks data/queue.json for posts whose scheduled_for
                                time has passed, publishes via Instagram Graph API,
                                moves them to data/published_log.json. Retries a
                                failed post up to 3 times before marking it
                                "abandoned" so it stops eating hourly retries forever.

analytics_agent  (daily)    -> pulls engagement stats for posts 48h+ old, writes
                                them into published_log.json
```

All four run as GitHub Actions on cron schedules -- no server required. State
lives in JSON files committed back to the repo by the workflows themselves.

### What's actually agentic here

This isn't just four scripts calling an LLM in sequence -- the pipeline makes
real decisions from data, in code, not just in a prompt:

- **Closed performance loop.** `research_agent` computes an engagement score
  (likes + comments + 2x saves + 2x shares) per pillar and per format from
  `published_log.json`'s insights, and feeds the actual numbers into its
  strategy prompt -- not just "consider performance," the real averages.
- **Deterministic pause/resume.** Once a pillar or format has 3+ published
  samples and its average engagement is under half the account's overall
  average, the pipeline pauses it in code (`apply_performance_decisions` in
  `agents/research_agent.py`), regardless of what the LLM's own
  `recommended_pillars`/`recommended_formats` picks. This is enforced, not a
  suggestion the model can ignore. It never zeroes out the pillar list --
  if everything's currently underperforming, it keeps generating rather than
  producing nothing.
- **Live trend awareness.** `lib/trend_client.py` pulls recent high-point
  Hacker News stories mentioning AI/GPT/LLM/etc (free, keyless, via
  Algolia's public HN search API) so `content_agent` can riff on what's
  actually being talked about right now, not just the static pillar list.
- **Live competitor scraping (optional).** `lib/apify_client.py` pulls each
  seed creator's recent posts (caption, likes, comments) via Apify's
  Instagram scraper when `APIFY_API_TOKEN` is set, feeding real numbers
  into the strategy prompt instead of relying only on what you've
  manually typed into `competitor_seed.json`. Best-effort -- if the token
  isn't set, or a scrape fails, it falls back to the manual seed file with
  no error. Worth knowing: this is metered (Apify's free tier gives
  monthly credit, not unlimited use) and scraping Instagram via a third
  party sits in a legal gray area their ToS technically doesn't allow,
  though at "a handful of public accounts, once a week" it's low-risk in
  practice.
- **Self-healing publish queue.** A post that fails to publish is retried
  automatically; after 3 failures it's marked `abandoned` instead of being
  retried hourly forever with no resolution.
- **Adaptive posting cadence.** Once there are 6+ published, scored posts,
  `research_agent` compares recent posts to older ones. A clear trend (15%+
  change) moves `config/niche.json`'s `posting_cadence.days` one step on a
  fixed ladder (1x -> 2x -> 3x -> 4x -> 5x per week; see
  `lib/cadence.py:CADENCE_LADDER`): up on rising engagement, down on
  falling. It never jumps more than one step per week and is capped between
  1x and 5x/week, so it can't drift to posting daily or stopping outright.
  A flat trend, or not enough data yet, changes nothing.

## One-time setup

### 1. Groq API key (free)
- Go to https://console.groq.com/keys, create a key.
- Groq runs its own inference hardware rather than sharing capacity the way
  some free-tier LLM APIs do, so it's less prone to "model overloaded"
  errors under normal use. Default model is `openai/gpt-oss-120b`
  (`lib/groq_client.py`); if Groq deprecates it, set the `GROQ_MODEL` env
  var/secret to switch without a code change.

### 2. Apify API token (free, optional)
- Go to https://console.apify.com/settings/integrations, sign up, copy
  your API token.
- Optional: without it, `research_agent` just relies on
  `data/competitor_seed.json` and general knowledge, same as before. With
  it, it also live-scrapes each seed creator's recent posts weekly.
- Free tier gives monthly usage credit (metered, not unlimited) -- fine
  for a light weekly scrape of ~5 creators, but not something to run
  constantly while testing.

### 3. Instagram Business account + Graph API access (free)
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

### 4. Make the repo public
The publisher needs publicly reachable image URLs (raw.githubusercontent.com).
Graph API cannot accept direct file uploads. Set this repo to public in
Settings, or swap `lib/image_client.py`/`publisher_agent.py` for a paid image
host later if you'd rather stay private.

### 5. Add repo secrets
Settings > Secrets and variables > Actions > New repository secret:
- `GROQ_API_KEY`
- `APIFY_API_TOKEN` (optional -- see step 2)
- `IG_BUSINESS_ACCOUNT_ID`
- `IG_ACCESS_TOKEN`

### 6. Enable Actions and seed content
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
  you admire (screenshot + describe hook/format/why it worked). Supplements
  the live Apify scrape (if configured) with the "why it worked" reasoning
  a raw scrape can't give you.

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

- **Competitor scraping is optional and metered.** Without `APIFY_API_TOKEN`,
  seed `data/competitor_seed.json` manually. With it, live scraping runs on
  Apify's free monthly credit, not unlimited -- fine for the pipeline's
  weekly cadence, not for constant manual re-runs. Also carries some ToS
  risk inherent to scraping (see "What's actually agentic here" above).
- **Images only, no reels.** Free video generation isn't good enough yet;
  reels stay a manual/future addition.
- **Image quality is best-effort.** pollinations.ai is a free public
  service, not a paid SLA. Swap `lib/image_client.py` for Ideogram/Stability
  if/when there's budget.
- **Instagram token expiry.** Long-lived tokens expire after 60 days;
  refresh manually until token-refresh automation is added.
- **Rate limits.** Groq and pollinations.ai free tiers can throttle under
  heavy use; this pipeline's default cadence (2-3 posts/week) stays well
  within limits. (An earlier version of this pipeline used Gemini, whose
  free tier turned out to be a tighter 5 req/min / 20 req/day per model
  with frequent "model overloaded" errors -- switched to Groq for more
  headroom and reliability.)
