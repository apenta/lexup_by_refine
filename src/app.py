# app.py
from flask import Flask, request, jsonify
import requests
import stripe
import os

app = Flask(__name__)

AIRTABLE_ID = os.environ.get("AIRTABLE_ID")
AIRTABLE_URL = f"https://api.airtable.com/v0/{AIRTABLE_ID}/user_input"
AIRTABLE_TOKEN = os.environ.get("AIRTABLE_TOKEN")
STRIPE_SECRET = os.environ.get("STRIPE_SECRET")
STRIPE_WEBHOOK_SECRET = os.environ.get("STRIPE_WEBHOOK_SECRET")

stripe.api_key = STRIPE_SECRET
HEADERS = {
    "Authorization": f"Bearer {AIRTABLE_TOKEN}",
    "Content-Type": "application/json"
}

# ── Route 1: Receive quiz data and create Stripe Checkout Session ──
@app.route("/submit", methods=["POST"])
def submit():
    data = request.json

    # 1. Save to Airtable
    airtable_payload = {
        "fields": {
            "email": data.get("email"),
            "vocab_area": data.get("vocab_area"),
            "job_title": data.get("job_title"),
            "experience": data.get("experience"),
            "frequency": data.get("frequency"),
            "delivery_days": data.get("delivery_days"),
            "submitted_at": data.get("submitted_at"),
            "subscription_status": "pending"
        }
    }

    response = requests.post(AIRTABLE_URL, headers=HEADERS, json=airtable_payload)
    if response.status_code not in [200, 201]:
        return jsonify({"error": response.text}), 500

    # 2. Create Stripe Checkout Session
    try:
        session = stripe.checkout.Session.create(
            mode="subscription",
            payment_method_types=["card"],
            customer_email=data.get("email"),
            line_items=[{
                "price": "price_1TNE5VBSOHSMgYjBGosxns22",
                "quantity": 1
            }],                                         # ← closed the list
            success_url="https://lexup-by-refine.onrender.com/success?session_id={CHECKOUT_SESSION_ID}",
            cancel_url="https://lexup-by-refine.onrender.com/cancel",
        )
    except stripe.error.StripeError as e:
        return jsonify({"error": str(e)}), 500

    # 3. Return Stripe checkout URL to frontend
    return jsonify({"checkout_url": session.url})


# ── Route 2: Stripe Webhook ───────────────────────────────────────
@app.route("/webhook", methods=["POST"])
def webhook():
    payload = request.get_data()
    sig_header = request.headers.get("Stripe-Signature")

    try:
        event = stripe.Webhook.construct_event(
            payload, sig_header, STRIPE_WEBHOOK_SECRET
        )
    except stripe.error.SignatureVerificationError:
        return jsonify({"error": "Invalid signature"}), 400

    # Handle successful subscription payment
    if event["type"] == "checkout.session.completed":
        session = event["data"]["object"]
        customer_email = session.get("customer_email")

        # Update Airtable subscription status to "active"
        # (You'd need to look up the Airtable record by email first)
        print(f"✅ Payment confirmed for {customer_email}")

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