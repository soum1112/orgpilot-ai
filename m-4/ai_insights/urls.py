from django.urls import path

from . import views

urlpatterns = [
    path("health/", views.Health.as_view()),
    path("findings/", views.Findings.as_view()),
    path("analyze/", views.Analyze.as_view()),
    path("recommendations/", views.Recommendations.as_view()),
]
