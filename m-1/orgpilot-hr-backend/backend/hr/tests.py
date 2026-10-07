import csv
import json
import shutil
import tempfile
from pathlib import Path
from django.conf import settings
from django.test import SimpleTestCase, override_settings
from .analytics import FILES, HRAnalytics, get_hr_ai_context
from .urls import SECTIONS


class AnalyticsTests(SimpleTestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        for filename in FILES.values():
            shutil.copy(settings.HR_DATA_DIR / filename, self.root / filename)

    def edit(self, table, function):
        path = self.root / FILES[table]
        with path.open() as stream:
            reader = csv.DictReader(stream)
            fields, rows = reader.fieldnames, list(reader)
        function(rows)
        with path.open('w', newline='') as stream:
            writer = csv.DictWriter(stream, fieldnames=fields)
            writer.writeheader()
            writer.writerows(rows)

    def analytics(self, filters=None):
        return HRAnalytics(self.root, filters)

    def codes(self, analytics):
        return {w['code'] for w in analytics.warnings}

    def test_workforce(self):
        overview = self.analytics().overview()
        self.assertEqual(overview['total_employees'], 126)
        self.assertEqual(overview['active_employees'], 125)
        self.assertEqual(overview['department_count'], 10)

    def test_missing_employee(self):
        self.edit('workforce', lambda rows: rows[0].update(employee_id=''))
        analytics = self.analytics()
        self.assertEqual(analytics.overview()['total_employees'], 125)
        self.assertIn('unknown_employee', self.codes(analytics))
        self.assertIn('excluded_invalid_key', self.codes(analytics))

    def test_duplicate_employee(self):
        self.edit('workforce', lambda rows: rows.append(rows[0].copy()))
        analytics = self.analytics()
        self.assertEqual(analytics.overview()['total_employees'], 126)
        self.assertIn('duplicate_record', self.codes(analytics))

    def test_workload_calculation(self):
        self.edit('workload', lambda rows: rows[0].update(planned_hours='30', actual_hours='50', overtime_hours='0'))
        row = self.analytics().workload()['by_employee'][0]
        self.assertEqual(row['utilization_percentage'], 125)
        self.assertEqual(row['derived_excess_over_plan_hours'], 20)
        self.assertEqual(row['classification'], 'overloaded')

    def test_overtime_observations(self):
        self.assertEqual(sum(w['affected_rows'] for w in self.analytics().warnings if w['code'] == 'overtime_review'), 38)

    def test_underutilized(self):
        self.edit('workload', lambda rows: rows[0].update(actual_hours='20'))
        self.assertEqual(self.analytics().workload()['by_employee'][0]['classification'], 'underutilized')

    def test_zero_capacity(self):
        self.edit('workforce', lambda rows: rows[0].update(weekly_capacity_hours='0'))
        self.assertIsNone(self.analytics().workload()['by_employee'][0]['utilization_percentage'])

    def test_engagement_mean(self):
        self.edit('engagement', lambda rows: [r.update(job_satisfaction_1_to_5='3') for r in rows])
        self.assertEqual(self.analytics().report()['engagement']['average'], 3)

    def test_missing_engagement(self):
        self.edit('engagement', lambda rows: rows[0].update(job_satisfaction_1_to_5=''))
        analytics = self.analytics()
        self.assertEqual(analytics.report()['engagement']['sample_size'], 125)
        self.assertIn('missing_value', self.codes(analytics))

    def test_invalid_engagement(self):
        self.edit('engagement', lambda rows: rows[0].update(job_satisfaction_1_to_5='6'))
        analytics = self.analytics()
        self.assertEqual(analytics.report()['engagement']['sample_size'], 125)
        self.assertIn('invalid_numeric', self.codes(analytics))

    def test_skills(self):
        skills = self.analytics().skills()
        self.assertEqual(skills['gap_count'], 85)
        self.assertEqual(skills['required_records'], 260)
        self.assertEqual(skills['gap_percentage'], 32.7)

    def test_unknown_proficiency(self):
        self.edit('skills', lambda rows: next(r for r in rows if r['required_for_role'] == 'Yes').update(proficiency_level='Expert'))
        analytics = self.analytics()
        self.assertIn('unknown_label', self.codes(analytics))
        self.assertEqual(analytics.skills()['unknown_required_records'], 1)
        self.assertEqual(analytics.skills()['assessable_required_records'], 259)

    def test_kpi_duplicates(self):
        self.edit('kpis', lambda rows: rows.append(rows[0].copy()))
        analytics = self.analytics()
        self.assertEqual(analytics.report()['kpis']['sample_size'], 1134)
        self.assertIn('duplicate_record', self.codes(analytics))

    def test_duplicate_record_id(self):
        self.edit('kpis', lambda rows: rows[1].update(kpi_record_id=rows[0]['kpi_record_id']))
        self.assertEqual(self.analytics().report()['kpis']['sample_size'], 1133)

    def test_invalid_date(self):
        self.edit('kpis', lambda rows: rows[0].update(month='2026-99'))
        analytics = self.analytics()
        self.assertEqual(analytics.report()['kpis']['sample_size'], 1133)
        self.assertIn('invalid_date', self.codes(analytics))

    def test_invalid_numeric(self):
        self.edit('kpis', lambda rows: (rows[0].update(performance_score='NaN'), rows[1].update(performance_score='-1')))
        report = self.analytics().report()
        self.assertEqual(report['kpis']['sample_size'], 1132)
        json.dumps(report, allow_nan=False)

    def test_date_filters(self):
        report = self.analytics({'department': 'ENG', 'start': '2026-01', 'end': '2026-01'}).report()
        self.assertEqual(len(report['kpis']['trend']), 1)
        self.assertEqual(report['engagement']['sample_size'], 0)
        self.assertGreater(report['overview']['total_employees'], 0)

    def test_bad_filters(self):
        for filters in [{'start': 'no'}, {'start': '2026-09', 'end': '2026-01'}, {'proficiency': 'Expert'}, {'extra': 'x'}]:
            with self.assertRaises(ValueError):
                self.analytics(filters)

    def test_insight_benchmark(self):
        report = self.analytics().report()
        insight = next(i for i in report['insights'] if i['category'] == 'kpis' and i['affected_group'] == 'Customer Support')
        self.assertEqual(insight['benchmark'], report['kpis']['average'])
        self.assertLess(insight['difference'], 0)
        self.assertEqual(insight['polarity'], 'negative')

    def test_severity_and_evidence(self):
        insights = self.analytics().report()['insights']
        self.assertTrue(any(i['severity'] == 'high' and i['category'] == 'skills' for i in insights))
        self.assertTrue(all(i['evidence'] for i in insights))
        self.assertTrue(any(i['category'] == 'data_quality' for i in insights))

    def test_kpi_decline(self):
        def change(rows):
            for row in rows:
                row['performance_score'] = '20' if row['month'] == '2026-01' else '10'
        self.edit('kpis', change)
        insight = next(i for i in self.analytics().report()['insights'] if i['category'] == 'kpi_trend')
        self.assertEqual(insight['difference'], -10)
        self.assertEqual(insight['polarity'], 'negative')

    def test_empty_sources(self):
        with tempfile.TemporaryDirectory() as root:
            report = HRAnalytics(root).report()
            self.assertEqual(report['overview']['total_employees'], 0)
            self.assertIsNone(report['engagement']['average'])
            self.assertTrue(any(i['category'] == 'coverage' and i['confidence'] == 'low' for i in report['insights']))
            json.dumps(report, allow_nan=False)

    def test_missing_columns(self):
        (self.root / FILES['engagement']).write_text('employee_id\nEMP0001\n')
        analytics = self.analytics()
        self.assertIn('missing_column', self.codes(analytics))
        self.assertEqual(analytics.report()['engagement']['sample_size'], 0)

    def test_ai_context(self):
        context = get_hr_ai_context(self.root)
        self.assertIn('department_comparisons', context)
        self.assertIn('average_kpi', context['key_metrics'])
        self.assertNotIn('employee_name', json.dumps(context))
        json.dumps(context, allow_nan=False)

    def test_invalid_period(self):
        self.edit('workload', lambda rows: rows[0].update(period_end='2026-01-01'))
        analytics = self.analytics()
        self.assertIn('invalid_period', self.codes(analytics))
        self.assertIsNone(analytics.workload()['by_employee'][0]['utilization_percentage'])


    def test_missing_department_name_column(self):
        (self.root / FILES['departments']).write_text('department_id\nENG\n')
        analytics = self.analytics()
        self.assertIn('missing_column', self.codes(analytics))
        self.assertEqual(analytics.report()['overview']['total_employees'], 126)

    def test_all_required_columns_missing_individually(self):
        from .analytics import REQUIRED, NUMERIC, DATES
        for table, filename in FILES.items():
            original = (self.root / filename).read_text()
            for field in set(REQUIRED[table] + NUMERIC[table] + DATES.get(table, [])):
                with self.subTest(table=table, field=field):
                    import io
                    reader = csv.DictReader(io.StringIO(original))
                    fields = [name for name in reader.fieldnames if name != field]
                    with (self.root / filename).open('w', newline='') as stream:
                        writer = csv.DictWriter(stream, fieldnames=fields, extrasaction='ignore')
                        writer.writeheader()
                        writer.writerows(reader)
                    analytics = self.analytics()
                    self.assertIn('missing_column', self.codes(analytics))
                    json.dumps(analytics.report(), allow_nan=False)
            (self.root / filename).write_text(original)

    def test_paired_planned_actual_denominator(self):
        def change(rows):
            for row in rows:
                row.update(planned_hours='', actual_hours='')
            rows[0].update(planned_hours='20', actual_hours='30')
            rows[1].update(planned_hours='40', actual_hours='')
            rows[2].update(planned_hours='', actual_hours='80')
        self.edit('workload', change)
        workload = self.analytics().workload()
        comparison = workload['planned_actual_comparison']
        self.assertEqual(comparison['sample_size'], 1)
        self.assertEqual(comparison['difference_hours'], 10)
        self.assertEqual(comparison['actual_vs_planned_percentage'], 150)
        self.assertEqual(workload['actual_hours_sample_size'], 2)
        self.assertEqual(workload['planned_hours_sample_size'], 2)

    def test_source_date_precision(self):
        self.edit('kpis', lambda rows: rows[0].update(month='2026-01-01'))
        self.edit('skills', lambda rows: rows[0].update(last_assessed_date='2026-01'))
        analytics = self.analytics()
        self.assertIn('invalid_date', self.codes(analytics))
        self.assertEqual(analytics.report()['kpis']['sample_size'], 1133)

    def test_kpi_improvement(self):
        def change(rows):
            for row in rows:
                row['performance_score'] = '10' if row['month'] == '2026-01' else '20'
        self.edit('kpis', change)
        insight = next(i for i in self.analytics().report()['insights'] if i['category'] == 'kpi_trend')
        self.assertEqual(insight['polarity'], 'positive')
        self.assertEqual(insight['difference'], 10)
        self.assertEqual(insight['evidence'][0]['time_window']['month'], {'start': '2026-01', 'end': '2026-09'})

    def test_low_engagement_signal(self):
        self.edit('engagement', lambda rows: [row.update(job_satisfaction_1_to_5='1') for row in rows])
        insights = self.analytics().report()['insights']
        self.assertTrue(any(i['title'] == 'Low engagement band' and i['value'] == 1 for i in insights))

    def test_small_group_insufficient_data(self):
        self.edit('engagement', lambda rows: rows.__delitem__(slice(1, None)))
        insights = self.analytics().report()['insights']
        small = [i for i in insights if i['category'] == 'engagement']
        self.assertEqual(len(small), 1)
        self.assertEqual(small[0]['confidence'], 'low')
        self.assertEqual(small[0]['polarity'], 'neutral')

    def test_tenure_arithmetic(self):
        self.edit('workforce', lambda rows: [row.update(tenure_months='24') for row in rows])
        self.assertEqual(self.analytics().overview()['average_tenure_months'], 24)

    def test_quality_evidence_has_source_rows(self):
        insight = next(i for i in self.analytics().report()['insights'] if i['category'] == 'data_quality')
        self.assertTrue(insight['evidence'][0]['row_numbers'])
        self.assertEqual(insight['value'], 38)


class APITests(SimpleTestCase):
    def test_endpoints(self):
        for section in SECTIONS:
            response = self.client.get('/api/hr/' + section + '/')
            self.assertEqual(response.status_code, 200)
            self.assertEqual(set(response.json()), {'status', 'data', 'metadata', 'warnings'})

    def test_invalid_query(self):
        self.assertEqual(self.client.get('/api/hr/overview/?start=bad').status_code, 400)

    def test_method(self):
        self.assertEqual(self.client.post('/api/hr/overview/').status_code, 405)

    def test_missing_sources(self):
        with tempfile.TemporaryDirectory() as root, override_settings(HR_DATA_DIR=Path(root)):
            response = self.client.get('/api/hr/dashboard/')
            self.assertEqual(response.status_code, 200)
            self.assertTrue(response.json()['warnings'])

    def test_malformed_department_source_is_partial_success(self):
        with tempfile.TemporaryDirectory() as root:
            for filename in FILES.values():
                shutil.copy(settings.HR_DATA_DIR / filename, Path(root) / filename)
            (Path(root) / FILES['departments']).write_text('department_id\nENG\n')
            with override_settings(HR_DATA_DIR=Path(root)):
                for section in SECTIONS:
                    response = self.client.get('/api/hr/' + section + '/')
                    self.assertEqual(response.status_code, 200)
                    self.assertTrue(response.json()['warnings'])
