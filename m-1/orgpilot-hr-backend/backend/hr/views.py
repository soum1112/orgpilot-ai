import logging
from datetime import datetime, timezone
from django.conf import settings
from django.http import JsonResponse
from .analytics import HRAnalytics
logger = logging.getLogger(__name__)


def endpoint(request, section):
    metadata = {'generated_at': datetime.now(timezone.utc).isoformat()}
    def error(message, status):
        return JsonResponse({'status': 'error', 'data': None, 'metadata': metadata, 'warnings': [], 'message': message}, status=status)
    if request.method != 'GET':
        response = error('GET required', 405)
        response['Allow'] = 'GET'
        return response
    try:
        analytics = HRAnalytics(settings.HR_DATA_DIR, request.GET.dict())
    except ValueError:
        return error('Invalid filters. Use department, role, skill, proficiency, start/end (YYYY-MM or YYYY-MM-DD).', 400)
    except Exception:
        logger.exception('HR source loading failed')
        return error('HR analytics temporarily unavailable.', 500)
    try:
        report = analytics.report()
        metadata.update(report.pop('metadata'))
        return JsonResponse({'status': 'success', 'data': report if section == 'dashboard' else report[section], 'metadata': metadata, 'warnings': analytics.warnings}, json_dumps_params={'allow_nan': False})
    except Exception:
        logger.exception('HR analytics failed')
        return error('HR analytics temporarily unavailable.', 500)
