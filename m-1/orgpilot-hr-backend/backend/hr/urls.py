from django.urls import path
from .views import endpoint
SECTIONS = ['overview', 'departments', 'skills-gaps', 'workload', 'engagement', 'kpis', 'insights', 'data-quality', 'dashboard']
urlpatterns = [path(section+'/', endpoint, {'section': section}, name='hr-'+section) for section in SECTIONS]
