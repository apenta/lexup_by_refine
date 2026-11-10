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

## Not built yet
Picking words, generating the crossword, and sending the emails on each person's delivery days.