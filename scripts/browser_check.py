"""Visual and interaction smoke check against an already-running local demo."""
from pathlib import Path
import sys

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "artifacts"
OUT.mkdir(exist_ok=True)

with sync_playwright() as p:
    browser = p.chromium.launch(channel="msedge", headless=True)
    page = browser.new_page(viewport={"width": 1440, "height": 1100}, device_scale_factor=1)
    errors = []
    page.on("pageerror", lambda error: errors.append(str(error)))
    def settled():
        page.wait_for_function("document.querySelector('[data-testid=stApp]')?.getAttribute('data-test-script-state') === 'notRunning'", timeout=90000)
    page.goto("http://127.0.0.1:8501", wait_until="networkidle")
    page.get_by_text("20 reviewed records", exact=False).first.wait_for()
    settled()
    page.screenshot(path=str(OUT / "desktop-home.png"), full_page=True)
    page.get_by_role("button", name="How it works", exact=True).click()
    settled()
    page.get_by_text("Demo settings and technical details", exact=True).click()
    toggle = page.get_by_role("switch", name="Use live Fireworks agents")
    if toggle.count() and "--live" not in sys.argv:
        if toggle.is_checked():
            page.get_by_text("Use live Fireworks agents", exact=True).click()
    elif not toggle.count() and "--live" not in sys.argv:
        checkbox = page.get_by_role("checkbox", name="Use live Fireworks agents")
        if checkbox.is_checked():
            page.get_by_text("Use live Fireworks agents", exact=True).click()
    page.get_by_role("button", name="Explore", exact=True).click()
    page.get_by_role("button", name="Try Maya's sample profile", exact=True).wait_for()
    settled()
    page.get_by_role("button", name="Try Maya's sample profile", exact=True).click()
    page.get_by_text("Showing Maya's fictional sample profile", exact=False).wait_for()
    settled()
    if "--live" in sys.argv:
        page.get_by_text("Your goals and circumstances", exact=True).click()
        page.get_by_role("button", name="Find my opportunities", exact=False).click()
        page.get_by_text("Finding relevant opportunities and checking published criteria", exact=False).wait_for(timeout=15000)
        settled()
        page.get_by_text("Showing Maya's fictional sample profile", exact=False).wait_for(state="hidden", timeout=90000)
        page.get_by_text("How this shortlist was made", exact=True).click()
        page.get_by_text("Discovery", exact=True).wait_for(timeout=90000)
        assert page.get_by_text("Fireworks", exact=False).count() >= 3
        assert not page.get_by_text("Fallback", exact=False).count()
    page.get_by_text("Find your way forward", exact=True).evaluate("el => el.scrollIntoView({block:'start'})")
    page.screenshot(path=str(OUT / "desktop-results.png"), full_page=True)
    page.get_by_role("button", name="View opportunity", exact=False).first.click()
    page.get_by_text("Follow the evidence", exact=True).wait_for()
    page.screenshot(path=str(OUT / "desktop-detail.png"), full_page=True)
    page.get_by_role("button", name="Build my application checklist", exact=True).click()
    page.get_by_text("One step closer.", exact=True).wait_for(timeout=90000)
    page.screenshot(path=str(OUT / "desktop-plan.png"), full_page=True)
    assert page.get_by_role("button", name="Download my plan", exact=False).count()
    page.get_by_role("button", name="Explore", exact=True).click()
    page.get_by_text("Your next chapter.", exact=False).first.wait_for()
    page.set_viewport_size({"width": 390, "height": 844})
    page.evaluate("document.querySelector('[data-testid=stMain]').scrollTo(0,0)")
    page.screenshot(path=str(OUT / "mobile-home.png"), full_page=True)
    assert page.evaluate("document.documentElement.scrollWidth <= window.innerWidth"), "Horizontal overflow"
    assert not errors, errors
    assert not page.locator('[data-testid="stException"]').count()
    print({"browser_errors": errors, "screenshots": 5, "desktop_and_mobile": "passed", "live_mode": "--live" in sys.argv})
    browser.close()
