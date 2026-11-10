import json
import os
import sys
import unittest
from datetime import date
from unittest import mock

os.environ.update(AIRTABLE_ID="appTEST", AIRTABLE_TOKEN="tok", RESEND_API_KEY="re_x",
                  EMAIL_FROM="LexUp <drops@example.com>", ANTHROPIC_API_KEY="sk-ant-x")
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import daily_job as J  # noqa: E402

J.SEND_DELAY = 0
MONDAY = date(2026, 11, 9)


class Resp:
    def __init__(self, code=200, body=None):
        self.status_code, self._b, self.text = code, body or {}, json.dumps(body or {})

    def json(self):
        return self._b

    def raise_for_status(self):
        if self.status_code >= 400:
            import requests
            raise requests.HTTPError(f"HTTP {self.status_code}")


def words_json(names):
    return {"words": [{"word": n, "part_of_speech": "noun", "definition": f"Meaning of {n.lower()}.",
                       "example": f"A sentence with {n.lower()}.", "clue": f"Clue for the {len(n)}-letter one"} for n in names]}


class Fake:
    """In-memory Airtable + Resend + Anthropic."""

    def __init__(self, records, pages=1):
        self.records = {r["id"]: r for r in records}
        self.pages, self.sent, self.llm_calls, self.patches = pages, [], [], []
        self.resend_code, self.patch_code = 200, 200
        self.llm_words = lambda n: words_json(["ARBITRAGE", "FIDUCIARY", "LIQUIDITY", "AMORTIZE", "SOLVENT", "EQUITY", "LEVERAGE"][:n])

    def get(self, url, params=None, **kw):
        active = [r for r in self.records.values() if r["fields"].get("subscription_status") == "active"]
        if self.pages == 1:
            return Resp(200, {"records": active})
        off = int((params or {}).get("offset", 0))
        chunk = active[off:off + 1]
        body = {"records": chunk}
        if off + 1 < len(active):
            body["offset"] = str(off + 1)
        return Resp(200, body)

    def patch(self, url, json=None, **kw):
        if self.patch_code >= 400:
            return Resp(self.patch_code)
        rid = url.rsplit("/", 1)[1]
        self.records[rid]["fields"].update(json["fields"])
        self.patches.append((rid, json["fields"]["drop_state"]))
        return Resp(200, {})

    def post(self, url, json=None, headers=None, **kw):
        if "anthropic" in url:
            self.llm_calls.append(json["messages"][0]["content"])
            return Resp(200, {"content": [{"type": "text", "text": "```json\n" + __import__("json").dumps(self.llm_words(7)) + "\n```"}]})
        if "resend" in url:
            if self.resend_code != 200:
                return Resp(self.resend_code, {"message": "nope"})
            self.sent.append((json, headers))
            return Resp(200, {"id": "em_1"})
        raise AssertionError(url)

    def state(self, rid):
        return __import__("json").loads(self.records[rid]["fields"].get("drop_state") or "{}")


def rec(rid, email, freq="daily", days="Every day", status="active", state=None, **extra):
    f = {"email": email, "frequency": freq, "delivery_days": days, "subscription_status": status,
         "vocab_area": "Finance", "job_title": "Analyst", "experience": "entry", **extra}
    if state is not None:
        f["drop_state"] = __import__("json").dumps(state)
    return {"id": rid, "fields": f}


def run_with(fake, **kw):
    with mock.patch.object(J.requests, "get", fake.get), mock.patch.object(J.requests, "patch", fake.patch), \
         mock.patch.object(J.requests, "post", fake.post):
        return J.run(today=MONDAY, **kw)


class DueTests(unittest.TestCase):
    def test_due_today(self):
        self.assertTrue(J.due_today({"frequency": "daily"}, "Monday"))
        self.assertTrue(J.due_today({"frequency": "3x", "delivery_days": "Monday, Wednesday, Friday"}, "Wednesday"))
        self.assertFalse(J.due_today({"frequency": "3x", "delivery_days": "Monday, Wednesday, Friday"}, "Tuesday"))
        self.assertTrue(J.due_today({"frequency": "weekly", "delivery_days": "Monday"}, "Monday"))
        self.assertFalse(J.due_today({"frequency": "weekly", "delivery_days": "Tuesday"}, "Monday"))
        self.assertFalse(J.due_today({}, "Monday"))


class RunTests(unittest.TestCase):
    def test_sends_only_to_who_is_due(self):
        fake = Fake([
            rec("recA", "a@x.co"),
            rec("recB", "b@x.co", freq="weekly", days="Tuesday"),
            rec("recC", "c@x.co", state={"last_sent": "2026-11-09", "words_seen": []}),
            rec("recD", "d@x.co", freq="3x", days="Monday, Wednesday, Friday"),
            rec("recE", "e@x.co", status="pending"),
            rec("recF", "f@x.co", status="canceled"),
        ])
        sent, failed = run_with(fake)
        self.assertEqual((sent, failed), (2, 0))
        self.assertEqual(sorted(p[0]["to"][0] for p in fake.sent), ["a@x.co", "d@x.co"])

    def test_email_payload_and_state(self):
        fake = Fake([rec("recA", "a@x.co")])
        run_with(fake)
        body, headers = fake.sent[0]
        self.assertEqual(body["from"], "LexUp <drops@example.com>")
        self.assertIn("ARBITRAGE", body["html"])
        self.assertTrue(body["subject"].startswith("LexUp:"))
        self.assertEqual(headers["Idempotency-Key"], "lexup-recA-2026-11-09")
        st = fake.state("recA")
        self.assertEqual(st["last_sent"], "2026-11-09")
        self.assertEqual(st["words_seen"], ["ARBITRAGE", "FIDUCIARY", "LIQUIDITY", "AMORTIZE", "SOLVENT"])

    def test_claim_is_written_before_sending(self):
        fake = Fake([rec("recA", "a@x.co")])
        order = []
        orig_patch, orig_post = fake.patch, fake.post
        fake.patch = lambda *a, **k: (order.append("claim/save"), orig_patch(*a, **k))[1]
        fake.post = lambda url, **k: (order.append("send") if "resend" in url else None, orig_post(url, **k))[1]
        run_with(fake)
        self.assertEqual(order[0], "claim/save")
        self.assertLess(order.index("claim/save"), order.index("send"))

    def test_rerun_same_day_sends_nothing(self):
        fake = Fake([rec("recA", "a@x.co")])
        run_with(fake)
        run_with(fake)
        self.assertEqual(len(fake.sent), 1)

    def test_no_word_repeats_and_avoid_list_in_prompt(self):
        fake = Fake([rec("recA", "a@x.co", state={"last_sent": "2026-11-08", "words_seen": ["ARBITRAGE", "FIDUCIARY"]})])
        run_with(fake)
        html = fake.sent[0][0]["html"]
        self.assertNotIn(">ARBITRAGE", html)
        self.assertIn("ARBITRAGE, FIDUCIARY", fake.llm_calls[0])
        self.assertEqual(fake.state("recA")["words_seen"][:2], ["ARBITRAGE", "FIDUCIARY"])
        self.assertEqual(len(fake.state("recA")["words_seen"]), 2 + 5)

    def test_resend_failure_releases_claim(self):
        fake = Fake([rec("recA", "a@x.co", state={"last_sent": "2026-11-08", "words_seen": ["OLD"]})])
        fake.resend_code = 500
        sent, failed = run_with(fake)
        self.assertEqual((sent, failed), (0, 1))
        self.assertEqual(fake.state("recA"), {"last_sent": "2026-11-08", "words_seen": ["OLD"]})

    def test_rate_limit_stops_run(self):
        fake = Fake([rec("recA", "a@x.co"), rec("recB", "b@x.co")])
        fake.resend_code = 429
        sent, failed = run_with(fake)
        self.assertEqual((sent, failed), (0, 1))  # stopped after the first 429

    def test_claim_failure_means_no_email(self):
        fake = Fake([rec("recA", "a@x.co")])
        fake.patch_code = 422  # e.g. the drop_state field doesn't exist yet
        sent, failed = run_with(fake)
        self.assertEqual((sent, failed), (0, 1))
        self.assertEqual(fake.sent, [])

    def test_bad_ai_output_is_filtered_and_retried_then_fails_cleanly(self):
        fake = Fake([rec("recA", "a@x.co")])
        bad = {"words": [{"word": "two words", "definition": "x", "clue": "y"},
                         {"word": "OK", "definition": "x", "clue": "y"},
                         {"word": "SELFCLUED", "definition": "x", "clue": "a selfclued clue"},
                         {"word": "GOODWORD", "definition": "", "clue": "y"}]}
        fake.llm_words = lambda n: bad
        sent, failed = run_with(fake)
        self.assertEqual((sent, failed), (0, 1))
        self.assertEqual(len(fake.llm_calls), 2)  # one retry
        self.assertEqual(fake.sent, [])
        self.assertEqual(fake.state("recA"), {})

    def test_identical_profiles_share_one_ai_call(self):
        fake = Fake([rec("recA", "a@x.co"), rec("recB", "b@x.co"), rec("recC", "c@x.co", vocab_area="Law")])
        run_with(fake)
        self.assertEqual(len(fake.llm_calls), 2)
        self.assertEqual(len(fake.sent), 3)

    def test_paging(self):
        fake = Fake([rec(f"rec{i}", f"{i}@x.co") for i in range(4)], pages=2)
        sent, _ = run_with(fake)
        self.assertEqual(sent, 4)

    def test_dry_run_sends_and_saves_nothing(self):
        fake = Fake([rec("recA", "a@x.co")])
        cwd = os.getcwd()
        import tempfile
        with tempfile.TemporaryDirectory() as d:
            os.chdir(d)
            try:
                sent, failed = run_with(fake, dry_run=True)
                self.assertTrue(os.path.exists("dry_run/recA.html"))
            finally:
                os.chdir(cwd)
        self.assertEqual((sent, failed), (1, 0))
        self.assertEqual((fake.sent, fake.patches), ([], []))

    def test_max_per_run(self):
        fake = Fake([rec(f"rec{i}", f"{i}@x.co") for i in range(5)])
        with mock.patch.object(J, "MAX_PER_RUN", 2):
            sent, _ = run_with(fake)
        self.assertEqual(sent, 2)


if __name__ == "__main__":
    unittest.main()
