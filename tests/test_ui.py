from streamlit.testing.v1 import AppTest
from equalstart.catalog import ROOT


def test_explore_navigation_details_and_tracker(tmp_path, monkeypatch):
    monkeypatch.setenv("FIREWORKS_API_KEY", "")
    monkeypatch.setenv("EQUALSTART_DB_PATH", str(tmp_path / "ui.sqlite"))
    app = AppTest.from_file(ROOT / "app.py", default_timeout=30).run()
    assert not app.exception
    assert len(app.selectbox) >= 4
    next(b for b in app.button if b.key == "detail-noaa-hollings").click().run()
    assert not app.exception
    assert any("Could this" in s.value for s in app.subheader)
    next(b for b in app.button if b.key == "build-plan").click().run()
    assert not app.exception
    assert len(app.checkbox) >= 4
    app.checkbox[0].check().run()
    assert not app.exception
    next(b for b in app.button if b.key == "nav-How it works").click().run()
    assert not app.exception


def test_sample_profile_runs_local_graph(monkeypatch):
    monkeypatch.setenv("FIREWORKS_API_KEY", "")
    app = AppTest.from_file(ROOT / "app.py", default_timeout=30).run()
    next(b for b in app.button if b.key == "sample-profile").click().run()
    assert not app.exception
    assert app.session_state["sample"]
    assert app.session_state["run"]["events"][0].mode == "Local baseline"
