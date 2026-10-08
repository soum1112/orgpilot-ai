"""Read-only, deterministic HR calculations; no database or LLM required."""
import csv
import math
import calendar
from collections import Counter, defaultdict
from datetime import date
from pathlib import Path
from statistics import mean

FILES = {
    'workforce': 'employee_workforce_synthetic.csv',
    'departments': 'departments.csv',
    'skills': 'employee_skills_synthetic.csv',
    'engagement': 'employee_engagement_synthetic.csv',
    'workload': 'employee_workload_synthetic.csv',
    'kpis': 'employee_kpi_monthly.csv',
}
NUMERIC = {
    'workforce': ['tenure_months', 'weekly_capacity_hours'],
    'departments': [], 'skills': [],
    'engagement': ['job_satisfaction_1_to_5', 'manager_support_1_to_5', 'work_life_balance_1_to_5', 'growth_opportunity_1_to_5'],
    'workload': ['planned_hours', 'actual_hours', 'meeting_hours', 'focus_hours', 'open_work_items', 'completed_work_items', 'overtime_hours'],
    'kpis': ['monthly_hours_worked', 'attendance_rate', 'training_hours', 'peer_review_score', 'manager_rating', 'performance_score', 'tasks_completed', 'Task_per_100h'],
}
DATES = {'skills': ['last_assessed_date'], 'engagement': ['survey_month'], 'workload': ['period_start', 'period_end'], 'kpis': ['month']}
KEYS = {'workforce': ['employee_id'], 'departments': ['department_id'], 'skills': ['employee_id', 'skill_name'], 'engagement': ['employee_id', 'survey_month'], 'workload': ['employee_id', 'period_start', 'period_end'], 'kpis': ['employee_id', 'month']}
REQUIRED = {
    'workforce': ['employee_id', 'department_code', 'department', 'job_role', 'work_location', 'employment_status'],
    'departments': ['department_id', 'department_name'],
    'skills': ['employee_id', 'skill_name', 'proficiency_level', 'required_for_role'],
    'engagement': ['employee_id'], 'workload': ['employee_id'], 'kpis': ['employee_id', 'department_id'],
}
LEVELS = {'Beginner': 1, 'Intermediate': 2, 'Advanced': 3}


def average(values):
    valid = [v for v in values if v is not None]
    return round(mean(valid), 2) if valid else None


def percentage(numerator, denominator):
    return round(100 * numerator / denominator, 1) if denominator else None


def total(values):
    valid = [v for v in values if v is not None]
    return round(sum(valid), 2) if valid else None


def iso_date(value):
    if len(value) == 7:
        value += '-01'
    if len(value) != 10 or value[4] != '-' or value[7] != '-':
        raise ValueError('Expected ISO date or month')
    return date.fromisoformat(value)


def distribution(rows, field):
    counts = Counter(r.get(field) or 'Unknown' for r in rows)
    return [{'label': str(k), 'count': n, 'percentage': percentage(n, len(rows))} for k, n in sorted(counts.items(), key=lambda item: str(item[0]))]


class HRAnalytics:
    def __init__(self, data_dir, filters=None):
        self.root = Path(data_dir)
        self.filters = filters or {}
        self.warnings = []
        self.source_counts = {}
        self.tables = {name: self.load(name) for name in FILES}
        self.validate_relationships()
        self.people = {r['employee_id']: r for r in self.tables['workforce']}
        self.apply_filters()

    def warn(self, table, field, code, message, rows):
        if rows:
            self.warnings.append({'type': 'data_quality', 'severity': 'warning', 'source': FILES[table], 'field': field, 'code': code, 'message': message, 'affected_rows': len(rows), 'row_numbers': rows[:20]})

    def load(self, table):
        try:
            with (self.root / FILES[table]).open(encoding='utf-8-sig', newline='') as stream:
                reader = csv.DictReader(stream)
                columns = reader.fieldnames or []
                raw = list(reader)
        except (OSError, UnicodeError, csv.Error):
            self.source_counts[table] = 0
            self.warn(table, 'file', 'unavailable', 'Source unavailable; related metrics may be null.', [0])
            return []
        self.source_counts[table] = len(raw)
        required = set(REQUIRED[table] + NUMERIC[table] + DATES.get(table, []))
        for field in sorted(required - set(columns)):
            self.warn(table, field, 'missing_column', 'Required column absent.', [0])
        issues = defaultdict(list)
        result, seen, record_ids = [], set(), set()
        for row_number, raw_row in enumerate(raw, 2):
            if None in raw_row:
                issues[('record', 'extra_columns')].append(row_number)
            row = {k: v.strip() if isinstance(v, str) else '' for k, v in raw_row.items() if k is not None}
            row['_row'] = row_number
            for field in sorted(required):
                row.setdefault(field, '')
                if not row.get(field):
                    issues[(field, 'missing_value')].append(row_number)
            for field in NUMERIC[table]:
                value = row.get(field)
                try:
                    number = float(value)
                    if not math.isfinite(number) or number < 0:
                        raise ValueError()
                    if field.endswith('_1_to_5') and not 1 <= number <= 5:
                        raise ValueError()
                    if field == 'attendance_rate' and number > 100:
                        raise ValueError()
                    row[field] = number
                except (TypeError, ValueError):
                    row[field] = None
                    if value:
                        issues[(field, 'invalid_numeric')].append(row_number)
            for field in DATES.get(table, []):
                try:
                    expected_length = 7 if field in ('month', 'survey_month') else 10
                    if len(row.get(field, '')) != expected_length:
                        raise ValueError('Source date precision does not match schema')
                    row['_' + field] = iso_date(row.get(field, ''))
                except ValueError:
                    row['_' + field] = None
                    if row.get(field):
                        issues[(field, 'invalid_date')].append(row_number)
            if table == 'skills':
                for field, allowed in [('proficiency_level', LEVELS), ('required_for_role', ('Yes', 'No'))]:
                    if row.get(field) not in allowed:
                        issues[(field, 'unknown_label')].append(row_number)
            key = tuple(row.get(field) for field in KEYS[table])
            if not all(key) or any(row.get('_' + field) is None for field in KEYS[table] if field in DATES.get(table, [])):
                issues[('record', 'excluded_invalid_key')].append(row_number)
                continue
            record_id = row.get({'kpis': 'kpi_record_id', 'engagement': 'survey_id', 'workload': 'record_id'}.get(table, ''))
            if key in seen or (record_id and record_id in record_ids):
                issues[('record', 'duplicate_record')].append(row_number)
                continue
            seen.add(key)
            if record_id:
                record_ids.add(record_id)
            result.append(row)
        messages = {'duplicate_record': 'Duplicate identity/period; first record retained.', 'excluded_invalid_key': 'Record excluded due to missing/invalid identity or keyed date.', 'extra_columns': 'Extra CSV fields ignored; source retained unchanged.'}
        for (field, code), rows in issues.items():
            self.warn(table, field, code, messages.get(code, 'Missing or invalid value; excluded from applicable metric denominator.'), rows)
        return result

    def validate_relationships(self):
        people = {r['employee_id']: r for r in self.tables['workforce']}
        departments = {r['department_id']: r['department_name'] for r in self.tables['departments']}
        for row in people.values():
            if departments.get(row.get('department_code')) != row.get('department'):
                self.warn('workforce', 'department', 'inconsistent_department', 'Department does not match master; original value retained.', [row['_row']])
            if row.get('manager_id') and row['manager_id'] not in people:
                self.warn('workforce', 'manager_id', 'unknown_employee', 'Manager ID is unknown.', [row['_row']])
        for table in DATES:
            unknown = [r['_row'] for r in self.tables[table] if r['employee_id'] not in people]
            self.warn(table, 'employee_id', 'unknown_employee', 'Unmatched employee excluded from company analytics.', unknown)
            self.tables[table] = [r for r in self.tables[table] if r['employee_id'] in people]
        for row in self.tables['kpis']:
            if row.get('department_id') != people[row['employee_id']].get('department_code'):
                self.warn('kpis', 'department_id', 'inconsistent_department', 'Workforce department used instead of conflicting KPI department.', [row['_row']])
        inconsistent, invalid_period = [], []
        for row in self.tables['workload']:
            actual, planned, overtime = (row.get(f) for f in ('actual_hours', 'planned_hours', 'overtime_hours'))
            if actual is not None and planned is not None and actual > planned and overtime == 0:
                inconsistent.append(row['_row'])
            if row.get('_period_start') and row.get('_period_end') and row['_period_end'] < row['_period_start']:
                invalid_period.append(row['_row'])
                row['_period_end'] = None
        self.warn('workload', 'overtime_hours', 'overtime_review', 'Actual exceeds planned with zero reported overtime. Review definitions; excess over plan is not necessarily overtime.', inconsistent)
        self.warn('workload', 'period_end', 'invalid_period', 'End precedes start; excluded from utilization and date-filtered analysis.', invalid_period)

    def apply_filters(self):
        filters = self.filters
        if set(filters) - {'department', 'role', 'start', 'end', 'skill', 'proficiency'}:
            raise ValueError('Unsupported filter')
        start = iso_date(filters['start']) if filters.get('start') else None
        end = iso_date(filters['end']) if filters.get('end') else None
        if end and len(filters['end']) == 7:
            end = end.replace(day=calendar.monthrange(end.year, end.month)[1])
        if start and end and start > end:
            raise ValueError('Reversed date range')
        if filters.get('proficiency') and filters['proficiency'] not in LEVELS:
            raise ValueError('Unknown proficiency')
        selected = [r for r in self.tables['workforce'] if (not filters.get('department') or filters['department'] in (r.get('department_code'), r.get('department'))) and (not filters.get('role') or r.get('job_role') == filters['role'])]
        self.tables['workforce'] = selected
        ids = {r['employee_id'] for r in selected}
        for table, fields in DATES.items():
            rows = [r for r in self.tables[table] if r['employee_id'] in ids]
            if start or end:
                rows = [r for r in rows if r.get('_' + fields[0]) and r.get('_' + fields[-1]) and (not start or r['_' + fields[0]] >= start) and (not end or r['_' + fields[-1]] <= end)]
            if table == 'skills':
                rows = [r for r in rows if (not filters.get('skill') or r.get('skill_name') == filters['skill']) and (not filters.get('proficiency') or r.get('proficiency_level') == filters['proficiency'])]
            self.tables[table] = rows

    def grouped(self, rows, field='department'):
        groups = defaultdict(list)
        for row in rows:
            groups[self.people[row['employee_id']].get(field) or 'Unknown'].append(row)
        return groups

    def overview(self):
        rows = self.tables['workforce']
        tenure = [r['tenure_months'] for r in rows if r['tenure_months'] is not None]
        return {'total_employees': len(rows), 'active_employees': sum(r.get('employment_status') == 'Active' for r in rows), 'department_count': len({r.get('department_code') for r in rows if r.get('department_code')}), 'by_department': distribution(rows, 'department'), 'by_role': distribution(rows, 'job_role'), 'by_location': distribution(rows, 'work_location'), 'by_status': distribution(rows, 'employment_status'), 'average_tenure_months': average(tenure), 'tenure_sample_size': len(tenure), 'new_employees_under_3_months': sum(t < 3 for t in tenure), 'tenure_distribution': [{'label': label, 'count': sum(lo <= t < hi for t in tenure)} for label, lo, hi in [('<1 year', 0, 12), ('1–3 years', 12, 36), ('3–5 years', 36, 60), ('5+ years', 60, float('inf'))]], 'snapshot_date': None}

    def scores(self, table, field, date_field):
        rows = self.tables[table]
        def summary(records):
            valid = [r for r in records if r.get(field) is not None]
            return {'average': average(r[field] for r in valid), 'sample_size': len(valid), 'employee_count': len({r['employee_id'] for r in valid})}
        groups = self.grouped(rows)
        trend = [{'month': month, **summary([r for r in rows if r[date_field] == month])} for month in sorted({r[date_field] for r in rows if r.get('_' + date_field)})]
        result = {**summary(rows), 'metric': field, 'by_department': [{'department': dep, **summary(rs)} for dep, rs in groups.items()], 'by_role': [{'role': role, **summary(rs)} for role, rs in self.grouped(rows, 'job_role').items()], 'trend': trend, 'dimensions': {f: {'average': average(r.get(f) for r in rows), 'sample_size': sum(r.get(f) is not None for r in rows)} for f in NUMERIC[table]}}
        if table == 'engagement':
            result.update({'unit': 'score 1–5', 'thresholds': {'low': '<=2', 'high': '>=4'}, 'distribution': [{'label': str(v), 'count': sum(r.get(field) == v for r in rows)} for v in range(1, 6)], 'intent_to_stay': distribution(rows, 'intent_to_stay_6_months')})
        else:
            result.update({'unit': 'points; maximum scale undocumented', 'by_employee': [{'employee_id': employee, **summary([r for r in rows if r['employee_id'] == employee])} for employee in sorted({r['employee_id'] for r in rows})], 'first_to_last_change_points': round(trend[-1]['average'] - trend[0]['average'], 2) if len(trend) > 1 and trend[-1]['average'] is not None and trend[0]['average'] is not None else None})
        return result

    def skills(self):
        rows = self.tables['skills']
        def summary(records):
            required = [r for r in records if r.get('required_for_role') == 'Yes']
            valid = [r for r in required if r.get('proficiency_level') in LEVELS]
            gaps = [r for r in valid if LEVELS[r['proficiency_level']] < 2]
            return {'records': len(records), 'employee_count': len({r['employee_id'] for r in records}), 'required_records': len(required), 'assessable_required_records': len(valid), 'gap_count': len(gaps), 'gap_percentage': percentage(len(gaps), len(valid)), 'unknown_required_records': len(required) - len(valid), 'affected_employee_count': len({r['employee_id'] for r in gaps}), 'intermediate_or_advanced_count': sum(LEVELS.get(r.get('proficiency_level'), 0) >= 2 for r in records)}
        return {**summary(rows), 'rule': 'Required-for-role skill below Intermediate. Unknown levels excluded from assessable denominator.', 'proficiency_distribution': distribution(rows, 'proficiency_level'), 'by_skill': [{'skill': skill, **summary([r for r in rows if r['skill_name'] == skill])} for skill in sorted({r['skill_name'] for r in rows})], 'by_department': [{'department': dep, **summary(rs)} for dep, rs in self.grouped(rows).items()], 'by_department_skill': [{'department': dep, 'skill': skill, **summary([r for r in rs if r['skill_name'] == skill])} for dep, rs in self.grouped(rows).items() for skill in sorted({r['skill_name'] for r in rs})]}

    def workload(self):
        records = []
        for row in self.tables['workload']:
            actual, planned = row['actual_hours'], row['planned_hours']
            weekly = self.people[row['employee_id']].get('weekly_capacity_hours')
            start, end = row.get('_period_start'), row.get('_period_end')
            capacity = weekly * ((end - start).days + 1) / 7 if weekly is not None and start and end else None
            utilization = percentage(actual, capacity) if actual is not None and capacity else None
            records.append({'employee_id': row['employee_id'], 'department': self.people[row['employee_id']].get('department') or 'Unknown', 'period_start': row['period_start'], 'period_end': row['period_end'], 'actual_hours': actual, 'planned_hours': planned, 'reported_overtime_hours': row['overtime_hours'], 'derived_excess_over_plan_hours': max(actual - planned, 0) if actual is not None and planned is not None else None, 'actual_vs_planned_percentage': percentage(actual, planned) if actual is not None and planned else None, 'capacity_hours': capacity, 'utilization_percentage': utilization, 'classification': ('overloaded' if utilization > 100 else 'underutilized' if utilization < 80 else 'balanced') if utilization is not None else 'unknown'})
        def summary(rs):
            comparable = [r for r in rs if r['actual_hours'] is not None and r['planned_hours'] is not None]
            planned_total = total(r['planned_hours'] for r in comparable)
            actual_total = total(r['actual_hours'] for r in comparable)
            comparison = {
                'sample_size': len(comparable),
                'planned_hours': planned_total,
                'actual_hours': actual_total,
                'difference_hours': round(actual_total - planned_total, 2) if comparable else None,
                'actual_vs_planned_percentage': percentage(actual_total, planned_total) if comparable else None,
            }
            paired = [r for r in rs if r['actual_hours'] is not None and r['capacity_hours'] is not None and r['capacity_hours'] > 0]
            return {'planned_actual_comparison': comparison, 'actual_hours_sample_size': sum(r['actual_hours'] is not None for r in rs), 'planned_hours_sample_size': sum(r['planned_hours'] is not None for r in rs), 'record_count': len(rs), 'employee_count': len({r['employee_id'] for r in rs}), 'actual_hours': total(r['actual_hours'] for r in rs), 'average_actual_hours': average(r['actual_hours'] for r in rs), 'planned_hours': total(r['planned_hours'] for r in rs), 'reported_overtime_hours': total(r['reported_overtime_hours'] for r in rs), 'derived_excess_over_plan_hours': total(r['derived_excess_over_plan_hours'] for r in rs), 'utilization_percentage': percentage(sum(r['actual_hours'] for r in paired), sum(r['capacity_hours'] for r in paired)), 'utilization_sample_size': len(paired), 'classification_counts': dict(Counter(r['classification'] for r in rs))}
        values = [r['utilization_percentage'] for r in records if r['utilization_percentage'] is not None]
        return {**summary(records), 'by_employee': records, 'by_department': [{'department': dep, **summary([r for r in records if r['department'] == dep])} for dep in sorted({r['department'] for r in records})], 'utilization_range_percentage_points': round(max(values) - min(values), 1) if values else None, 'rule': 'Actual / prorated weekly capacity. >100% overloaded, <80% underutilized (MVP convention). Excess over plan is distinct from reported overtime.'}

    def insights(self, engagement, workload, kpis, skills):
        result = []
        def add(category, source, group, value, benchmark, unit, n, title, polarity='negative', severity='medium', metric=None):
            dated_rows = self.tables[source]
            if source != 'departments' and group not in ('Selected population', FILES[source]):
                dated_rows = [r for r in dated_rows if self.people.get(r.get('employee_id'), {}).get('department') == group]
            time_window = {field: {
                'start': min((r[field] for r in dated_rows if r.get('_' + field)), default=None),
                'end': max((r[field] for r in dated_rows if r.get('_' + field)), default=None),
            } for field in DATES.get(source, [])}
            result.append({'id': f'HR-{len(result)+1:03d}', 'category': category, 'severity': severity, 'polarity': polarity, 'title': title, 'finding': f'{group}: {value} {unit}; benchmark {benchmark} {unit}.', 'metric': metric or category, 'value': value, 'benchmark': benchmark, 'difference': round(value - benchmark, 2) if value is not None and benchmark is not None else None, 'unit': unit, 'affected_group': group, 'sample_size': n, 'confidence': 'medium' if n >= 5 else 'low', 'evidence': [{'source': FILES[source], 'value': value, 'baseline': benchmark, 'sample_size': n, 'metric': metric or category, 'time_window': time_window, 'filters': self.filters}], 'data_quality': sorted({w['code'] for w in self.warnings if w['source'] == FILES[source]})})
        for category, block in [('engagement', engagement), ('kpis', kpis)]:
            baseline = block['average']
            for row in block['by_department']:
                value, n = row['average'], row['sample_size']
                if row['employee_count'] < 5:
                    add(category, category, row['department'], value, baseline, 'points', row['employee_count'], 'Insufficient employees for reliable comparison', 'neutral', 'info', block['metric'])
                elif value is not None and baseline and abs(value-baseline)/baseline >= 0.1:
                    add(category, category, row['department'], value, baseline, 'points', n, 'Department differs by at least 10% from selected population mean', 'positive' if value > baseline else 'negative', metric=block['metric'])
                if category == 'engagement' and value is not None and row['employee_count'] >= 5 and (value <= 2 or value >= 4):
                    add(category, category, row['department'], value, 2 if value <= 2 else 4, 'score 1–5', n, 'Low engagement band' if value <= 2 else 'High engagement band', 'negative' if value <= 2 else 'positive', metric=block['metric'])
        for row in workload['by_department']:
            value = row['utilization_percentage']
            if value is not None and (value > 100 or value < 80):
                add('workload', 'workload', row['department'], value, 100 if value > 100 else 80, '%', row['utilization_sample_size'], 'Above capacity' if value > 100 else 'Below utilization band', 'negative' if value > 100 else 'neutral', 'high' if value > 120 else 'medium', 'utilization_percentage')
        for row in skills['by_department']:
            value = row['gap_percentage']
            if value is not None:
                add('skills', 'skills', row['department'], value, 0, '%', row['assessable_required_records'], 'Required skills below Intermediate' if value else 'Assessed required skills meet threshold', 'negative' if value else 'positive', 'high' if value >= 30 else 'medium' if value else 'info', 'gap_percentage')
        trend = kpis['trend']
        if len(trend) > 1 and trend[0]['average'] and trend[-1]['average'] is not None:
            first, last = trend[0]['average'], trend[-1]['average']
            if abs(last-first)/first >= 0.1 and min(trend[0]['employee_count'], trend[-1]['employee_count']) >= 5:
                add('kpi_trend', 'kpis', 'Selected population', last, first, 'points', min(trend[0]['sample_size'], trend[-1]['sample_size']), 'First-to-last performance change of at least 10%', 'positive' if last > first else 'negative', metric='performance_score')
        for warning in self.warnings:
            source = next(key for key, filename in FILES.items() if filename == warning['source'])
            add('data_quality', source, warning['source'], warning['affected_rows'], 0, 'rows', warning['affected_rows'], warning['message'], 'neutral', 'warning', warning['code'])
            result[-1]['evidence'][0].pop('time_window', None)
            result[-1]['evidence'][0].update({'row_numbers': warning['row_numbers'], 'warning_scope': 'All source rows before filtering'})
        if not any(i['category'] != 'data_quality' for i in result):
            add('coverage', 'workforce', 'Selected population', None, None, 'records', 0, 'Insufficient data for findings', 'neutral', 'info')
        return result

    def report(self):
        engagement = self.scores('engagement', 'job_satisfaction_1_to_5', 'survey_month')
        kpis = self.scores('kpis', 'performance_score', 'month')
        workload, skills = self.workload(), self.skills()
        blocks = {'engagement': engagement, 'kpis': kpis, 'workload': workload, 'skills': skills}
        departments = [{'department': dep, 'headcount': len(rows), **{name: next((r for r in block['by_department'] if r['department'] == dep), None) for name, block in blocks.items()}} for dep, rows in self.grouped(self.tables['workforce']).items()]
        periods = {table: {field: {'start': min((r[field] for r in self.tables[table] if r.get('_'+field)), default=None), 'end': max((r[field] for r in self.tables[table] if r.get('_'+field)), default=None)} for field in fields} for table, fields in DATES.items()}
        return {'overview': self.overview(), 'departments': departments, 'engagement': engagement, 'workload': workload, 'kpis': kpis, 'skills-gaps': skills, 'insights': self.insights(engagement, workload, kpis, skills), 'data-quality': {'warnings': self.warnings, 'source_record_counts': self.source_counts, 'retained_record_counts': {name: len(rows) for name, rows in self.tables.items()}}, 'metadata': {'source': 'synthetic demo data', 'source_files': FILES, 'record_count': len(self.tables['workforce']), 'filters': self.filters, 'periods': periods, 'warning_scope': 'All source records before filters', 'date_filter_scope': 'Dated facts only; workforce is an undated snapshot'}}


def get_hr_ai_context(data_dir=None, filters=None):
    if data_dir is None:
        from django.conf import settings
        data_dir = settings.HR_DATA_DIR
    report = HRAnalytics(data_dir, filters).report()
    return {'key_metrics': {'workforce': report['overview'], 'average_engagement': report['engagement']['average'], 'average_workload_hours': report['workload']['average_actual_hours'], 'average_kpi': report['kpis']['average']}, 'findings': report['insights'], 'department_comparisons': report['departments'], 'skill_gaps': report['skills-gaps']['by_department'], 'workload_findings': report['workload']['by_department'], 'engagement_findings': report['engagement']['by_department'], 'kpi_findings': report['kpis']['by_department'], 'data_quality': report['data-quality']['warnings'], 'metadata': report['metadata'], 'instruction': 'Explain these validated findings. Do not recalculate metrics or infer causation. Raw employee records are not included.'}
