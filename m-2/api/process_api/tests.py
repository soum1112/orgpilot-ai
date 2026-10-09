from rest_framework.test import APISimpleTestCase

CONTRACT = {"finding_id", "domain", "title", "metric", "actual_value", "target_value", "unit",
            "severity", "scope", "evidence", "limitations"}


class ProcessApiTests(APISimpleTestCase):
    def get(self, name):
        r = self.client.get(f"/api/process/{name}/")
        self.assertEqual(r.status_code, 200)
        body = r.json()
        self.assertEqual(body["status"], "ok")
        self.assertIn("source_files", body["meta"])
        self.assertIn("warnings", body["meta"])
        return body["data"]

    def test_overview_has_cases_and_contract_findings(self):
        d = self.get("overview")
        self.assertGreater(d["overview"]["total_cases"], 0)
        self.assertTrue(d["findings"])
        self.assertTrue(CONTRACT <= set(d["findings"][0]))

    def test_stages_bottlenecks_anomalies(self):
        self.assertTrue(self.get("stages")["stages"])
        self.assertEqual(self.get("bottlenecks")["bottlenecks"][0]["rank"], 1)
        self.assertIn("out_of_order_cases", self.get("anomalies")["anomalies"]["counts"])
