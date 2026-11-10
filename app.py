# app.py
import json
import os
import re
import time

import requests
import stripe
from flask import Flask, request, jsonify, send_file
from flask_cors import CORS

app = Flask(__name__)

# ── Config ────────────────────────────────────────────────────────
SITE_URL = os.environ.get("SITE_URL", "https://lexup-by-refine.onrender.com").rstrip("/")

# The page is served by this app, so same-origin requests need no CORS.
# The extra origins are for opening index.html with VS Code Live Server locally.
CORS(app, origins=[SITE_URL, "http://127.0.0.1:5501", "http://localhost:5501"])

AIRTABLE_ID = os.environ.get("AIRTABLE_ID")
AIRTABLE_URL = f"https://api.airtable.com/v0/{AIRTABLE_ID}/Table%201"
AIRTABLE_TOKEN = os.environ.get("AIRTABLE_TOKEN")
STRIPE_SECRET = os.environ.get("STRIPE_SECRET")
STRIPE_WEBHOOK_SECRET = os.environ.get("STRIPE_WEBHOOK_SECRET")

# One Stripe price per plan. Set these in Render (Environment) to the
# price_... IDs from the Stripe dashboard, so no price IDs live in the code.
PLAN_PRICES = {
    "monthly": os.environ.get("STRIPE_PRICE_MONTHLY"),
    "yearly": os.environ.get("STRIPE_PRICE_YEARLY"),
}

stripe.api_key = STRIPE_SECRET
HEADERS = {
    "Authorization": f"Bearer {AIRTABLE_TOKEN}",
    "Content-Type": "application/json"
}
TIMEOUT = 10  # seconds, for Airtable calls


# ── Airtable helpers ──────────────────────────────────────────────
def airtable_update(record_id, fields):
    """PATCH fields onto one Airtable record. Raises on failure."""
    resp = requests.patch(
        f"{AIRTABLE_URL}/{record_id}",
        headers=HEADERS,
        json={"typecast": True, "fields": fields},
        timeout=TIMEOUT,
    )
    resp.raise_for_status()


def airtable_find_by_customer(customer_id):
    """Return the Airtable record ID for a Stripe customer, or None."""
    if not re.fullmatch(r"cus_[A-Za-z0-9]+", customer_id or ""):
        return None
    resp = requests.get(
        AIRTABLE_URL,
        headers=HEADERS,
        params={
            "filterByFormula": '{stripe_customer_id}="%s"' % customer_id,
            "maxRecords": 1,
        },
        timeout=TIMEOUT,
    )
    resp.raise_for_status()
    records = resp.json().get("records", [])
    return records[0]["id"] if records else None


@app.route("/")
def index():
    return send_file("index.html")


# ── Route 0: Plan prices, read from Stripe so the page never hardcodes them ──
_plans_cache = {"at": 0.0, "data": {}}

@app.route("/plans")
def plans():
    if time.time() - _plans_cache["at"] < 600 and _plans_cache["data"]:
        return jsonify(_plans_cache["data"])

    data = {}
    for plan, price_id in PLAN_PRICES.items():
        if not price_id:
            continue
        try:
            price = stripe.Price.retrieve(price_id)
            data[plan] = {
                "amount": price.unit_amount,  # in cents
                "currency": price.currency,
                "interval": price.recurring.interval,
            }
        except stripe.StripeError as e:
            print(f"plans: could not load {plan} price:", str(e))

    if data:
        _plans_cache.update(at=time.time(), data=data)
    return jsonify(data)


# ── Route 1: Receive quiz data and create Stripe Checkout Session ──
@app.route("/submit", methods=["POST"])
def submit():
    data = request.get_json(silent=True) or {}

    email = (data.get("email") or "").strip()
    plan = data.get("plan")
    price_id = PLAN_PRICES.get(plan)

    if not email:
        return jsonify({"error": "Email is required."}), 400
    if not price_id:
        return jsonify({"error": "Please choose a plan."}), 400

    # 1. Save to Airtable (status stays "pending" until Stripe confirms payment)
    airtable_payload = {
        "typecast": True,
        "fields": {
            "email": email,
            "vocab_area": data.get("vocab_area"),
            "job_title": data.get("job_title"),
            "experience": data.get("experience"),
            "frequency": data.get("frequency"),
            "delivery_days": data.get("delivery_days"),
            "submitted_at": data.get("submitted_at"),
            "subscription_status": "pending",
            "plan": plan,
        }
    }

    try:
        response = requests.post(AIRTABLE_URL, headers=HEADERS, json=airtable_payload, timeout=TIMEOUT)
    except requests.RequestException as e:
        print("submit: airtable request failed:", str(e))
        return jsonify({"error": "Could not save your answers. Please try again."}), 502

    if response.status_code not in [200, 201]:
        print("submit: airtable error", response.status_code, response.text)
        return jsonify({"error": "Could not save your answers. Please try again."}), 500

    record_id = response.json()["id"]

    # 2. Create Stripe Checkout Session for the chosen plan only.
    #    client_reference_id lets the webhook find this exact Airtable record.
    try:
        session = stripe.checkout.Session.create(
            mode="subscription",
            payment_method_types=["card"],
            customer_email=email,
            line_items=[{"price": price_id, "quantity": 1}],
            client_reference_id=record_id,
            metadata={"airtable_record_id": record_id, "plan": plan},
            success_url=f"{SITE_URL}/success?session_id={{CHECKOUT_SESSION_ID}}",
            cancel_url=f"{SITE_URL}/cancel",
        )
    except stripe.StripeError as e:
        # Stripe v9+ exposes exceptions directly on `stripe` (stripe.StripeError),
        # not on the removed stripe.error module.
        print("submit: stripe error:", str(e))
        try:  # don't leave a dangling "pending" row for a checkout that never started
            airtable_update(record_id, {"subscription_status": "checkout_failed"})
        except requests.RequestException as ae:
            print("submit: could not mark record failed:", str(ae))
        return jsonify({"error": "Could not start checkout. Please try again."}), 500

    # 3. Return Stripe checkout URL to frontend
    return jsonify({"checkout_url": session.url})


# ── Route 2: Stripe Webhook ───────────────────────────────────────
@app.route("/webhook", methods=["POST"])
def webhook():
    payload = request.get_data()
    sig_header = request.headers.get("Stripe-Signature")

    try:
        stripe.Webhook.construct_event(payload, sig_header, STRIPE_WEBHOOK_SECRET)
    except ValueError:
        return jsonify({"error": "Invalid payload"}), 400
    except stripe.SignatureVerificationError:
        return jsonify({"error": "Invalid signature"}), 400

    # Signature is verified; read the event as plain JSON so this works
    # the same on every version of the stripe library.
    event = json.loads(payload)
    event_type = event["type"]
    obj = event["data"]["object"]

    try:
        if event_type == "checkout.session.completed":
            record_id = obj.get("client_reference_id")
            if not record_id:
                print("webhook: completed session has no client_reference_id", obj.get("id"))
            else:
                paid = obj.get("payment_status") in ("paid", "no_payment_required")
                airtable_update(record_id, {
                    "subscription_status": "active" if paid else "pending",
                    "stripe_customer_id": obj.get("customer"),
                    "plan": (obj.get("metadata") or {}).get("plan"),
                })
                print(f"webhook: {record_id} -> {'active' if paid else 'pending'}")

        elif event_type == "checkout.session.expired":
            record_id = obj.get("client_reference_id")
            if record_id:
                airtable_update(record_id, {"subscription_status": "expired"})

        elif event_type in ("customer.subscription.updated", "customer.subscription.deleted"):
            # status is one of: active, past_due, canceled, unpaid, trialing, ...
            record_id = airtable_find_by_customer(obj.get("customer"))
            if record_id:
                airtable_update(record_id, {"subscription_status": obj.get("status")})
            else:
                # Can arrive before checkout.session.completed has stored the
                # customer ID; the completed event sets the status itself.
                print("webhook: no Airtable record yet for customer", obj.get("customer"))

    except requests.RequestException as e:
        # A non-2xx response makes Stripe retry the event later.
        print("webhook: airtable update failed:", str(e))
        return jsonify({"error": "Airtable update failed"}), 500

    return jsonify({"status": "ok"}), 200


# ── Route 3: Success page ─────────────────────────────────────────
@app.route("/success")
def success():
    return "<h1>You're subscribed! 🎉</h1><p>Check your email for confirmation.</p>"


# ── Route 4: Cancel page ──────────────────────────────────────────
@app.route("/cancel")
def cancel():
    return "<h1>Payment cancelled.</h1><p><a href='/'>Try again</a></p>"


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))