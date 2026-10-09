"""Process Intelligence endpoints. All numbers come from analytics/process_kpis.py; data is read from data/."""
import sys
from functools import lru_cache
from pathlib import Path

from rest_framework.response import Response
from rest_framework.views import APIView

M2_DIR = Path(__file__).resolve().parents[2]         # the m-2 folder
DATA_DIR = M2_DIR / "data"                          # CSV files
sys.path.insert(0, str(M2_DIR / "analytics"))       # process_kpis.py
from process_kpis import ProcessAnalytics  # noqa: E402


@lru_cache(maxsize=1)
def analytics():
    return ProcessAnalytics.from_files(DATA_DIR)


class _Base(APIView):
    def payload(self, pa):
        raise NotImplementedError

    def get(self, request):
        try:
            pa = analytics()
        except FileNotFoundError as e:
            return Response({"status": "error", "message": f"Data file not found: {e.filename}"}, status=503)
        except ValueError as e:
            return Response({"status": "error", "message": str(e)}, status=422)
        return Response(pa.envelope(self.payload(pa)))


class Overview(_Base):
    def payload(self, pa):
        return {"overview": pa.overview(), "findings": pa.findings()}


class Stages(_Base):
    def payload(self, pa):
        return {"stages": pa.stages_summary()}


class Bottlenecks(_Base):
    def payload(self, pa):
        return {"bottlenecks": pa.bottlenecks()}


class Anomalies(_Base):
    def payload(self, pa):
        return {"anomalies": pa.anomalies()}
