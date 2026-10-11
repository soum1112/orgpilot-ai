"""One URL space for every module. Each module keeps its own urls.py; this file only mounts them."""
from django.http import JsonResponse
from django.urls import include, path


def root(request):
    return JsonResponse({
        "service": "OrgPilot AI",
        "endpoints": {
            "hr": "/api/hr/overview/  (and departments, skills-gaps, workload, engagement, kpis, insights, ...)",
            "process": "/api/process/overview/  (and stages, bottlenecks, anomalies)",
            "ai": "/api/ai/health/  /api/ai/findings/  POST /api/ai/analyze/  POST /api/ai/recommendations/",
        },
    })


urlpatterns = [
    path("", root),
    path("api/hr/", include("hr.urls")),                  # Member 1
    path("api/process/", include("process_api.urls")),    # Member 2
    path("api/ai/", include("ai_insights.urls")),         # Member 4
]
