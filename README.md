# lexup_by_refine
This is a prototype for LEXUP, a vocab learning system that is tailored to you and your path.

## How it works
1. Visitor answers the quiz on the landing page and picks a monthly or yearly plan.
2. `POST /submit` saves the answers to Airtable (`subscription_status = pending`) and creates a Stripe Checkout session for the chosen plan.
3. Stripe calls `POST /webhook`; the Airtable row is updated by record ID (`client_reference_id`):
   - `checkout.session.completed` -> `active`, plus `stripe_customer_id` and `plan`
   - `checkout.session.expired` -> `expired`
   - `customer.subscription.updated` / `.deleted` -> Stripe's subscription status (`past_due`, `canceled`, ...)

## Environment variables (Render -> Environment)
| Key | What it is |
| --- | --- |
| `STRIPE_SECRET` | Stripe secret key (`sk_test_...` in sandbox) |
| `STRIPE_WEBHOOK_SECRET` | Signing secret (`whsec_...`) of the webhook endpoint |
| `STRIPE_PRICE_MONTHLY` | `price_...` ID of the monthly price |
| `STRIPE_PRICE_YEARLY` | `price_...` ID of the yearly price |
| `AIRTABLE_TOKEN` / `AIRTABLE_ID` | Airtable token and base ID |
| `SITE_URL` | Public URL, used for Stripe redirects and CORS (defaults to the Render URL) |

## Stripe webhook
Endpoint: `<SITE_URL>/webhook`. Events to send: `checkout.session.completed`, `checkout.session.expired`, `customer.subscription.updated`, `customer.subscription.deleted`.

## Daily email (`daily_job.py`)
A Render cron job runs `python daily_job.py` once a day. For each subscriber with `subscription_status = active` whose delivery day is today it:
1. asks Claude for the day's words, definitions, examples and crossword clues (never repeating a word that subscriber has had),
2. builds the crossword grid in code (`crossword.py`; the AI only supplies words and clues),
3. sends the email through Resend (`lexup_email.py` builds the HTML).

Per-subscriber history (last send date + words already sent) is stored as JSON in an Airtable **long text** field named `drop_state`. Create that field once; the job fails safely (sends nothing) if it is missing.

Extra environment variables for the cron job: `RESEND_API_KEY`, `EMAIL_FROM` (e.g. `LexUp <drops@yourdomain.com>`), `EMAIL_REPLY_TO`, `ANTHROPIC_API_KEY`. Optional: `LLM_MODEL`, `TIMEZONE` (default `America/New_York`), `WORDS_PER_EMAIL` (5), `MAX_EMAILS_PER_RUN` (100, the Resend free-plan daily cap).

Try it locally:
```bash
python daily_job.py --sample    # writes preview.html, no network needed
python daily_job.py --dry-run   # real Airtable + AI calls, sends/saves nothing, writes ./dry_run/*.html
python -m unittest discover -s tests
```

## Not built yet
- Need to make sure words are not repeated for users
- The "real-world article" the landing page promises (the AI can't be trusted to invent real links).
- A self-serve cancel link (Stripe customer portal); for now the email says to reply to cancel.
- Decide if we need an unsubscribe button