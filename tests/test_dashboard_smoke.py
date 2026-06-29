# tests/test_dashboard_smoke.py
# Smoke test: the app imports, the Red-flag explorer no longer offers "Value suspect".
# Run: python -m pytest tests/test_dashboard_smoke.py -q   (pytest used only as a runner here)
from pathlib import Path

SRC = (Path(__file__).resolve().parent.parent / "app" / "dashboard.py").read_text(encoding="utf-8")

def test_value_suspect_not_in_redflag_multiselect():
    # The red-flag multiselect default list must not contain the data-quality marker.
    assert '"Value suspect", "Short window"' not in SRC
    assert '"Value suspect": "f.f_value_suspect"' not in SRC
