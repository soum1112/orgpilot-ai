"""Tests for the AI layer. Run from the repo root:  python backend/manage.py test ai_insights
The model is always mocked or pointed at a dead port, so no Ollama is needed."""
import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from unittest import mock

from django.test import SimpleTestCase, override_settings

from ai_insights import adapters, fallback, llm, retrieval, service, validators

DEAD = "http://127.0.0.1:9"      # nothing listens here -> instant "connection refused"

FINDING = {
    "finding_id": "PROC-001", "domain": "process", "title": "Manager approval often exceeds its target",
    "metric": "mean_stage_elapsed_hours", "actual_value": 30.2, "target_value": 24.0, "benchmark_value": None,
    "unit": "hours", "severity": "high",
    "scope": {"period": "2026-01 to 2026-09", "population": "HR-TAL-001 cases (463)"},
    "evidence": [{"source_file": "process_event_log.csv", "description": "Mean 30.2h vs 24h target.", "record_ids": []}],
    "limitations": ["Observed delay does not establish the cause"], "data_source": "synthetic demo data",
    "retrieval_hints": {"process_id": "HR-TAL-001", "keywords": ["approval"]},
}
EXCERPT = {"chunk_id": "DOC#1", "source_file": "DOC.docx", "section": "5 Review", "page": None,
           "text": "Review completed within 3 business days.", "score": 1.0, "doc_code": None}
GOOD = {"summary": "Approval takes 30.2 hours against a 24 hour target.",
        "key_points": ["Target is 24 hours"],
        "recommendations": [{"action": "Check approval ownership", "rationale": "Gap to the target",
                             "expected_benefit_hypothesis": "May shorten waiting", "risks": ["Rushed approvals"],
                             "supporting_policy_chunk_ids": ["DOC#1"]}],
        "limitations": ["Cause not established"]}


class AdapterTests(SimpleTestCase):
    def setUp(self):
        adapters.clear_cache()

    def test_all_modules_use_the_shared_shape(self):
        bundle = adapters.collect_findings()
        self.assertEqual(set(bundle["modules"].values()), {"ok"}, bundle["warnings"])
        ids = [f["finding_id"] for f in bundle["findings"]]
        self.assertEqual(len(ids), len(set(ids)), "finding ids must be unique across modules")
        self.assertEqual({f["domain"] for f in bundle["findings"]}, {"hr", "process", "business"})
        needed = {"finding_id", "domain", "title", "metric", "actual_value", "target_value", "unit", "severity",
                  "scope", "evidence", "limitations", "data_source"}
        for f in bundle["findings"]:
            self.assertTrue(needed <= set(f), f["finding_id"])
            self.assertIn(f["severity"], adapters.SEVERITIES)
            self.assertTrue(f["limitations"], f["finding_id"])
            self.assertIn(f["data_source"], (adapters.SYNTHETIC, adapters.PUBLIC))

    def test_numbers_are_passed_through_unchanged(self):
        from process_api.views import analytics
        original = {f["finding_id"]: f for f in analytics().findings()}
        for f in adapters.process_findings():
            self.assertEqual(f["actual_value"], original[f["finding_id"]]["actual_value"])
            self.assertEqual(f["target_value"], original[f["finding_id"]]["target_value"])

    def test_hr_benchmark_is_not_presented_as_a_target(self):
        for f in adapters.hr_findings():
            self.assertIsNone(f["target_value"])

    def test_one_failing_module_does_not_break_the_others(self):
        with mock.patch.dict(adapters.MODULES, {"hr": mock.Mock(side_effect=RuntimeError("boom"))}):
            adapters.clear_cache()
            bundle = adapters.collect_findings()
        self.assertTrue(bundle["modules"]["hr"].startswith("error"))
        self.assertEqual(bundle["modules"]["process"], "ok")
        self.assertTrue(any("hr" in w for w in bundle["warnings"]))
        self.assertTrue(bundle["findings"])


class RetrievalTests(SimpleTestCase):
    def setUp(self):
        retrieval.reset_index()

    def test_index_reads_documents_and_chunks_have_sources(self):
        idx = retrieval.get_index()
        self.assertGreater(len(idx.files), 0, idx.warnings)
        for c in idx.chunks[:50]:
            self.assertTrue(c["source_file"] and c["section"] and c["chunk_id"])

    def test_search_prefers_the_document_named_by_the_finding(self):
        res = retrieval.get_index().search("Consolidate review CHRO planning", doc_code="HR-TAL-001")
        self.assertTrue(res)
        self.assertEqual(res[0]["doc_code"], "HR-TAL-001")

    def test_gibberish_returns_nothing_and_never_invents(self):
        self.assertEqual(retrieval.get_index().search("zzqx qwvb plmk"), [])
        self.assertEqual(retrieval.get_index().search(""), [])

    def test_missing_folder_is_a_warning_not_a_crash(self):
        idx = retrieval.PolicyIndex(["/no/such/folder"])
        self.assertEqual(idx.chunks, [])
        self.assertTrue(idx.warnings)
        self.assertEqual(idx.search("approval"), [])


class ValidatorTests(SimpleTestCase):
    def check(self, obj, task="recommendations"):
        return validators.validate(obj, FINDING, [EXCERPT], task)

    def test_good_output_passes(self):
        clean, notes = self.check(GOOD)
        self.assertEqual(clean["recommendations"][0]["supporting_policy_chunk_ids"], ["DOC#1"])

    def test_invented_number_is_rejected(self):
        bad = dict(GOOD, summary="Approval could be cut by 45 percent.")
        with self.assertRaises(validators.OutputRejected):
            self.check(bad)

    def test_rounded_numbers_from_the_evidence_are_accepted(self):
        self.check(dict(GOOD, summary="About 30 hours against 24 hours."))

    def test_causal_claim_is_rejected(self):
        with self.assertRaises(validators.OutputRejected):
            self.check(dict(GOOD, summary="The delay is caused by understaffing."))

    def test_unknown_citation_is_dropped(self):
        rec = dict(GOOD["recommendations"][0], supporting_policy_chunk_ids=["DOC#1", "FAKE#9"])
        clean, notes = self.check(dict(GOOD, recommendations=[rec]))
        self.assertEqual(clean["recommendations"][0]["supporting_policy_chunk_ids"], ["DOC#1"])
        self.assertTrue(any("FAKE#9" in n for n in notes))

    def test_malformed_shapes_are_rejected(self):
        for bad in ({}, {"summary": ""}, dict(GOOD, recommendations="nope"), dict(GOOD, recommendations=[{"x": 1}]),
                    dict(GOOD, recommendations=[])):
            with self.assertRaises(validators.OutputRejected, msg=str(bad)):
                self.check(bad)

    def test_analyze_does_not_need_recommendations(self):
        self.check(dict(GOOD, recommendations=[]), task="analyze")


class FallbackTests(SimpleTestCase):
    def test_fallback_has_no_invented_numbers(self):
        out = fallback.build(FINDING, [EXCERPT], "recommendations")
        allowed = validators.allowed_numbers(FINDING, [EXCERPT], None) + [6.2]   # 30.2 - 24 computed by code
        for text in [out["summary"], *out["key_points"]]:
            for n in validators.extract_numbers(text):
                self.assertTrue(validators._supported(n, allowed), (text, n))
        self.assertTrue(out["recommendations"])
        self.assertIn("fallback", out["limitations"][-1])

    def test_fallback_handles_missing_value(self):
        f = dict(FINDING, actual_value=None, target_value=None)
        self.assertIn("did not produce a value", fallback.build(f, [], "analyze")["summary"])


class FakeOllama(BaseHTTPRequestHandler):
    reply = json.dumps(GOOD)

    def log_message(self, *a):
        pass

    def _send(self, obj):
        body = json.dumps(obj).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        self._send({"models": [{"name": "qwen2.5:7b-instruct"}]})

    def do_POST(self):
        self.rfile.read(int(self.headers.get("Content-Length", 0)))
        self._send({"message": {"role": "assistant", "content": FakeOllama.reply}})


class LLMClientTests(SimpleTestCase):
    def test_health_when_offline(self):
        with override_settings(OLLAMA_URL=DEAD):
            h = llm.health()
        self.assertFalse(h["reachable"])
        self.assertTrue(h["detail"])

    def test_chat_when_offline_raises_unavailable(self):
        with override_settings(OLLAMA_URL=DEAD, OLLAMA_TIMEOUT=2):
            with self.assertRaises(llm.LLMUnavailable):
                llm.chat_json("s", "u")

    def test_against_a_fake_ollama_server(self):
        server = HTTPServer(("127.0.0.1", 0), FakeOllama)
        threading.Thread(target=server.serve_forever, daemon=True).start()
        try:
            with override_settings(OLLAMA_URL=f"http://127.0.0.1:{server.server_port}"):
                self.assertTrue(llm.health()["model_available"])
                self.assertEqual(llm.chat_json("s", "u")["summary"], GOOD["summary"])
                FakeOllama.reply = "not json at all"
                with self.assertRaises(llm.LLMBadOutput):
                    llm.chat_json("s", "u")
                FakeOllama.reply = "Sure! " + json.dumps(GOOD) + " Hope this helps."
                self.assertEqual(llm.chat_json("s", "u")["summary"], GOOD["summary"])
        finally:
            FakeOllama.reply = json.dumps(GOOD)
            server.shutdown()

    def test_parse_json_object_rejects_lists(self):
        with self.assertRaises(llm.LLMBadOutput):
            llm.parse_json_object("[1, 2]")


def good_for(finding_id):
    """A valid model answer that quotes the REAL numbers of the finding."""
    f, _ = adapters.get_finding(finding_id)
    return dict(GOOD, summary=f"Measured {f['actual_value']} {f['unit']} against {f['target_value']} {f['unit']}.",
                key_points=[], recommendations=[], limitations=["Cause not established"])


@override_settings(OLLAMA_URL=DEAD, OLLAMA_TIMEOUT=2)
class EndpointTests(SimpleTestCase):
    def setUp(self):
        adapters.clear_cache()
        retrieval.reset_index()

    def post(self, path, body):
        return self.client.post(path, data=json.dumps(body), content_type="application/json")

    def test_health_works_with_the_model_offline(self):
        r = self.client.get("/api/ai/health/")
        self.assertEqual(r.status_code, 200)
        d = r.json()["data"]
        self.assertFalse(d["ollama"]["reachable"])
        self.assertTrue(d["fallback_available"])
        self.assertGreater(d["policy_index"]["chunks"], 0)

    def test_findings_list_and_filters(self):
        d = self.client.get("/api/ai/findings/?domain=process").json()["data"]
        self.assertTrue(d["items"])
        self.assertTrue(all(f["domain"] == "process" for f in d["items"]))

    def test_every_finding_can_be_analyzed_without_a_model(self):
        for f in self.client.get("/api/ai/findings/").json()["data"]["items"]:
            for path in ("/api/ai/analyze/", "/api/ai/recommendations/"):
                r = self.post(path, {"finding_id": f["finding_id"]})
                self.assertEqual(r.status_code, 200, f["finding_id"])
                d = r.json()["data"]
                self.assertEqual(d["mode"], "fallback")
                self.assertTrue(d["human_review_required"])
                self.assertEqual(d["llm"]["status"], "unavailable")
                self.assertTrue(d["summary"] and d["limitations"])

    def test_bad_requests(self):
        self.assertEqual(self.post("/api/ai/analyze/", {}).status_code, 400)
        self.assertEqual(self.post("/api/ai/analyze/", {"finding_id": 5}).status_code, 400)
        self.assertEqual(self.post("/api/ai/analyze/", {"finding_id": "NOPE-1"}).status_code, 404)
        self.assertEqual(self.post("/api/ai/analyze/", {"finding_id": "PROC-001", "question": "x" * 600}).status_code, 400)
        self.assertEqual(self.post("/api/ai/analyze/", {"finding_id": "PROC-001", "use_llm": "yes"}).status_code, 400)
        r = self.client.post("/api/ai/analyze/", data="{broken", content_type="application/json")
        self.assertEqual(r.status_code, 400)

    def test_model_answer_is_used_when_valid(self):
        good = good_for("PROC-001")
        with mock.patch.object(llm, "chat_json", return_value=good):
            d = self.post("/api/ai/analyze/", {"finding_id": "PROC-001"}).json()["data"]
        self.assertEqual(d["mode"], "llm")
        self.assertEqual(d["llm"]["status"], "ok")

    def test_invented_numbers_trigger_a_retry_then_fallback(self):
        bad = dict(GOOD, summary="Delays will drop by 77 percent.", recommendations=[])
        with mock.patch.object(llm, "chat_json", return_value=bad) as m:
            d = self.post("/api/ai/analyze/", {"finding_id": "PROC-001"}).json()["data"]
        self.assertEqual(m.call_count, 2)
        self.assertEqual(d["mode"], "fallback")
        self.assertEqual(d["llm"]["status"], "rejected")
        self.assertNotIn("77", d["summary"])

    def test_malformed_model_output_falls_back(self):
        with mock.patch.object(llm, "chat_json", side_effect=llm.LLMBadOutput("broken")):
            d = self.post("/api/ai/recommendations/", {"finding_id": "PROC-001"}).json()["data"]
        self.assertEqual(d["mode"], "fallback")
        self.assertEqual(d["llm"]["status"], "bad_output")

    def test_model_can_recover_on_the_second_try(self):
        bad = dict(GOOD, summary="Cut by 77 percent.")
        ok = dict(good_for("PROC-001"), recommendations=[{
            "action": "Check approval ownership", "rationale": "Gap to the target", "risks": [],
            "expected_benefit_hypothesis": "May shorten waiting", "supporting_policy_chunk_ids": []}])
        with mock.patch.object(llm, "chat_json", side_effect=[bad, ok]):
            d = self.post("/api/ai/recommendations/", {"finding_id": "PROC-001"}).json()["data"]
        self.assertEqual(d["mode"], "llm")

    def test_use_llm_false_skips_the_model(self):
        with mock.patch.object(llm, "chat_json") as m:
            d = self.post("/api/ai/analyze/", {"finding_id": "HR-013", "use_llm": False}).json()["data"]
        m.assert_not_called()
        self.assertEqual(d["llm"]["status"], "disabled")

    def test_process_finding_gets_its_own_sop_as_evidence(self):
        d = self.post("/api/ai/recommendations/", {"finding_id": "PROC-001"}).json()["data"]
        self.assertTrue(d["policy_excerpts"])
        self.assertEqual(d["policy_excerpts"][0]["doc_code"], "HR-TAL-001")
