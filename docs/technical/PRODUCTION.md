# Production: going live and staying watched

Production is the pilot with real merchants, real phone numbers and real
Wave payments. It runs from [`render.production.yaml`](../../render.production.yaml),
separate from the test environment in `render.yaml` (shared test numbers,
simulated payments, free plan). The two never share a database.

What watches it:

| Question | Where the answer is | Alerts you |
|---|---|---|
| Is the API up and reaching its database? | Uptime monitor on `/ready` | SMS / WhatsApp / email within 2 minutes |
| Are requests failing or slow? | Grafana Cloud: *Fidelia API overview* | `HighErrorRate`, `SlowRequests` |
| Are payments being confirmed? | Grafana Cloud: *Webhooks overview* | `PaymentWebhookFailing` |
| Can people sign in? Is someone burning SMS? | Grafana Cloud: *Fidelia apps and sign-in* | `OtpDeliveryFailing`, `OtpSentButNotVerified`, `OtpDailyBudgetReached` |
| Are the apps crashing? | Same dashboard; stacks in the installer site (*Erreurs des apps*) | `AppErrorSpike`, `AppCrashAfterRelease` |
| Is the pilot being used? | Grafana Cloud: *Fidelia pilot usage*; `GET /api/admin/usage` | — |
| What happened at 14:02? | Log service, searched by `request_id` or route | — |

## 1. Accounts to open (once)

1. **Render**: a paid workspace. The API runs on the Starter instance type
   (always on), the installer site as a static site.
2. **Neon**: the production project on a paid plan, with point-in-time
   restore. See § Database.
3. **Africa's Talking**: production account with credit, and the `FIDELIA`
   sender ID applied for (approval takes time; codes work without it).
4. **Cloudflare R2**: a `fidelia-media-prod` bucket and an API token limited to it.
5. **Grafana Cloud**: free tier is enough for the pilot (metrics, dashboards,
   alerting).
6. **Better Stack** (or UptimeRobot): uptime monitors, and log storage if
   Render's own retention is too short for you.

## 2. Deploy

1. Render → **New → Blueprint** → the `fidelia-BE` repository, Blueprint path
   `render.production.yaml`. Render asks for every `sync: false` value; fill
   them from the table in § 6.
2. The API deploys with `autoDeploy: false`: a merge to `main` does not reach
   real merchants until someone presses **Manual Deploy**. Migrations run in
   the pre-deploy step; if one fails, the previous build keeps serving.
3. Once the API is up, copy its address into the installer site's
   `VITE_FIDELIA_API_BASE`, and the installer site's address into the API's
   `CORS_ORIGINS`. Redeploy both.
4. Check: `https://<api>/health` → `{"status":"ok"}`, `/ready` →
   `{"ready":true}`, and `/metrics` → **404** (it needs the token).
5. Build the apps for production: `scripts/build-release.sh https://<api>`
   in each app repository, with the production address. Test builds keep
   pointing at the test API.

The API refuses to start in production with a test-only setting: a console
SMS sender, `TEST_OTP_NUMBERS`, simulated payments, local media storage or a
missing encryption key. A failed start in the deploy log names the setting.

## 3. Metrics and alerts (Grafana Cloud)

The API exports Prometheus metrics at `/metrics`, labelled by route template
(`/api/venues/{venue_id}`, never a raw URL) to keep the series count small.
In production the endpoint answers only with `METRICS_TOKEN`.

1. **Scrape the API.** Grafana Cloud → *Connections* → **Metrics Endpoint** →
   new scrape job:
   * Name: `fidelia-api`
   * URL: `https://<api>/metrics`
   * Authentication: **Basic**. Username: anything (e.g. `grafana`).
     Password: the API's `METRICS_TOKEN`, copied from Render → fidelia-api-prod
     → Environment.
   * Interval: 1 minute.

   *Test connection* must succeed; within two minutes `fidelia_build_info`
   appears in *Explore*.
2. **Dashboards.** *Dashboards → New → Import*, once per file in
   [`monitoring/grafana/dashboards/`](../../monitoring/grafana/dashboards/):
   `api-overview.json`, `apps-and-auth.json`, `pilot-usage.json`,
   `webhooks-overview.json`. Pick the Grafana Cloud Prometheus data source.
   Each has a fixed uid, so importing a newer version replaces the old one.
3. **Alert rules.** [`monitoring/rules/alerts.yml`](../../monitoring/rules/alerts.yml)
   is the same file the local Prometheus uses. Load it into Grafana Cloud's
   Prometheus with `mimirtool` (credentials from *Grafana Cloud → your stack →
   Prometheus → Details*; the key needs the `rules:write` scope):

   ```bash
   mimirtool rules load monitoring/rules/alerts.yml \
     --address=https://<prometheus host from Details> \
     --id=<Prometheus instance ID> --key=<access policy token>
   ```

   Run it again after every change to the file. The rules then show under
   *Alerting → Alert rules* (data-source managed).
4. **Who gets told.** *Alerting → Contact points*: add at least two people,
   by email and by a channel someone reads at night (Grafana's mobile app, or
   a Telegram or Slack integration). *Notification policies*: `severity =
   critical` → everyone, repeat every 1 h; `warning` → email, repeat every 4 h.
5. **Test the path once**: set `OTP_DAILY_SMS_BUDGET` to `1` for five minutes,
   request two codes, check `OtpDailyBudgetReached` reaches everyone, then put
   the budget back.

## 4. Uptime monitors

Grafana alerts only when metrics arrive. An outside monitor catches the
cases where nothing arrives at all (`ApiMetricsMissing` is the backstop).

| Monitor | URL | Every | Expect |
|---|---|---|---|
| API and database | `https://<api>/ready` | 1 min | 200 and `"ready":true` |
| Installer site | `https://<installer>/` | 5 min | 200 |
| Test download page | `https://<fidelia-web>/app/` | 5 min | 200 |

Alert after 2 failed checks, to the same people as critical alerts.

## 5. Logs

The API writes one JSON line per request (`LOG_FORMAT=json`):

```json
{"ts": "2026-10-04T14:02:11", "level": "info", "logger": "fidelia.access",
 "msg": "POST /api/sales 201 84ms", "request_id": "9f2c…", "method": "POST",
 "route": "/api/sales", "status": 201, "duration_ms": 84.2}
```

5xx lines are `level: error`. Query strings, IPs and bodies are never logged:
query strings carry phone numbers. Every response carries `X-Request-ID`; an
app or a merchant's screenshot can quote it to find the exact line.

Render keeps logs for a limited time. To keep them longer, Render →
*Workspace settings* → **Log Streams** → the syslog endpoint your log service
gives (Better Stack: *Sources → Render*). Keep 30 days at least.

## 6. Settings (keep this table current)

Values set by hand in the Render dashboard do not follow the Blueprint
afterwards. Whenever one changes there, change it here too.

| Setting | Where it comes from | Notes |
|---|---|---|
| `DATABASE_URL` | Neon, production project, direct endpoint | Never the test database |
| `FIDELIA_SECRET_KEY` | Generated by Render | Rotating it signs everyone out |
| `FIDELIA_ENCRYPTION_KEY` | Generated by Render | **Copy to the password manager.** Lost or changed: every merchant reconnects Wave |
| `MOBILE_MONEY_SECRETS` | Payment provider's webhook secret | `current,previous` while rotating |
| `AT_USERNAME`, `AT_API_KEY` | Africa's Talking, production app | |
| `AT_SENDER_ID` | Africa's Talking, once approved | Empty until then |
| `OTP_DAILY_SMS_BUDGET` | Blueprint: 300 | A few times a normal day; raise as the pilot grows |
| `R2_*`, `MEDIA_PUBLIC_BASE_URL` | Cloudflare R2 | Bucket `fidelia-media-prod` |
| `CORS_ORIGINS` | The installer site's exact address | Add the public site's domain once it has one |
| `METRICS_TOKEN` | Generated by Render | Also in Grafana Cloud's scrape job; rotate both together |
| `VITE_FIDELIA_API_BASE` (installer site) | The API's address | Rebuild the site after a change |

## 7. When an alert fires

| Alert | First look | Likely causes and fixes |
|---|---|---|
| **Uptime /ready down** | Render → fidelia-api-prod → Events and Logs | Deploy failed to start (the log names the bad setting); Neon down or out of compute: check Neon status; roll back with *Rollback* on the last good deploy |
| **ApiMetricsMissing** | Is the uptime monitor also red? | Both red: the API is down, see above. Only this one: the scrape fails, usually `METRICS_TOKEN` rotated on one side only |
| **HighErrorRate** | *API overview* → *Errors by route*; logs filtered on `level: error` | One route: a bug, often from the last deploy (*Running build* panel), so roll back. All routes: the database |
| **SlowRequests** | *Latency p95, slowest routes* | Database under load (Neon dashboard); one slow route: a missing index |
| **PaymentWebhookFailing** | Logs on route `/api/webhooks/mobile-money` | 401: the provider rotated its secret, so update `MOBILE_MONEY_SECRETS`; 5xx: a bug, payments are not being confirmed, so treat as urgent and tell affected merchants |
| **OtpDeliveryFailing** | Africa's Talking dashboard | Credit spent, sender ID rejected, provider outage. Nobody new can sign in meanwhile |
| **OtpSentButNotVerified** | *Fidelia apps and sign-in* → codes by result | SMS pumping: lower `OTP_DAILY_SMS_BUDGET`, check the provider's per-country spend. Or codes are not arriving: send one to your own phone |
| **OtpDailyBudgetReached** | Same dashboard | Real growth: raise the budget. An attack: keep it, it is doing its job, and look at the per-IP limits |
| **AppErrorSpike / AppCrashAfterRelease** | Installer site → *Erreurs des apps* | A bad release: stop sharing the new APK, fix, release the next tag |

After any incident a merchant noticed: write down what happened, when, what
fixed it, and what would have caught it sooner.

## Scaling beyond one instance

Counters live in the API process, and the scrape reaches one instance through
Render's public address. With `numInstances: 1` that is the whole picture.
Before adding instances: run Grafana Alloy as a Render private service that
scrapes every instance on the private network (`fidelia-api-prod-discovery`)
and remote-writes to Grafana Cloud, and turn the public scrape job off.

## Database

To be completed with the replica plan. Until then the minimum:

* Neon paid plan with point-in-time restore over at least 7 days.
* Restore tested once into a scratch branch, and the time it took noted here.
* The production `DATABASE_URL` known only to Render and the password manager.
