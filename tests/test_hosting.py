from equalstart.hosting import SessionStore
from equalstart.catalog import ROOT
from streamlit.testing.v1 import AppTest


def test_visitors_have_separate_plans_but_share_budget(tmp_path):
    path = tmp_path / "shared.sqlite3"
    first, second = SessionStore(path), SessionStore(path)
    first.save_plan("award", [{"id": "essay", "text": "My next step"}])
    first.tasks("award", ["essay"])
    assert second.saved() == {}
    assert second.plan("award") is None
    second.save("other")
    call = first.reserve(0.02)
    first.settle(call, 0.01)
    first.clear_saved()
    assert first.plan("award") is None
    assert second.saved() == {"other": []}
    assert second.spent() == 0.01
    with first.connect() as con:
        assert con.execute("SELECT COUNT(*) FROM saved").fetchone()[0] == 0


def test_plan_values_cannot_mutate_another_store_view(tmp_path):
    db = SessionStore(tmp_path / "shared.sqlite3")
    plan = [{"id": "essay"}]
    db.save_plan("award", plan)
    plan[0]["id"] = "changed"
    retrieved = db.plan("award")
    retrieved[0]["id"] = "changed again"
    assert db.plan("award") == [{"id": "essay"}]


def test_cloud_entrypoint_hides_usage_and_other_visitors(monkeypatch, tmp_path):
    monkeypatch.setenv("EQUALSTART_PUBLIC", "1")
    monkeypatch.setenv("FIREWORKS_API_KEY", "")
    monkeypatch.setenv("NEBIUS_API_KEY", "")
    monkeypatch.setenv("EQUALSTART_DB_PATH", str(tmp_path / "cloud.sqlite3"))
    app = AppTest.from_file(ROOT / "streamlit_app.py", default_timeout=30).run()
    assert not app.exception
    app.session_state["visitor_store"].save("noaa-hollings")
    other = AppTest.from_file(ROOT / "streamlit_app.py", default_timeout=30).run()
    assert not other.exception
    assert other.session_state["visitor_store"].saved() == {}
    next(b for b in app.button if b.key == "nav-How it works").click().run()
    assert not app.exception
    assert not any("spent or reserved" in str(item.value) for item in app.markdown)
    assert not app.json
    assert not any("full evaluation" in str(item.label) for item in app.get("download_button"))
