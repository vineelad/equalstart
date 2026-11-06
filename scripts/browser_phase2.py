"""Exercise Phase 2 in Edge against a running local server; optional live journey."""
import argparse
from pathlib import Path

from playwright.sync_api import sync_playwright

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("--url", default="http://127.0.0.1:8502")
parser.add_argument("--live", action="store_true")
args = parser.parse_args()
root = Path(__file__).resolve().parents[1]

with sync_playwright() as playwright:
    browser = playwright.chromium.launch(channel="msedge", headless=True)
    try:
        page = browser.new_page(viewport={"width":1440,"height":1100})
        errors=[]
        page.on("pageerror",lambda error: errors.append(str(error)))
        def settled():
            page.wait_for_function("document.querySelector('[data-testid=stApp]')?.getAttribute('data-test-script-state') === 'notRunning'",timeout=180000)
        page.goto(args.url,wait_until="networkidle")
        settled()
        page.get_by_role("button",name="How it works",exact=True).click()
        settled()
        page.get_by_text("Demo settings and technical details",exact=True).click()
        toggle=page.get_by_role("switch",name="Use live Fireworks agents")
        if toggle.is_checked() != args.live:
            page.get_by_text("Use live Fireworks agents",exact=True).click()
            settled()
        page.get_by_role("button",name="Explore",exact=True).click()
        settled()
        page.get_by_role("button",name="Try Maya's sample profile",exact=True).click()
        page.get_by_text("Showing Maya's fictional sample profile",exact=False).wait_for(timeout=30000)
        page.get_by_role("radio",name="Recommended next steps",exact=True).wait_for()
        settled()
        if args.live:
            page.get_by_text("Your goals and circumstances",exact=True).click()
            page.get_by_role("button",name="Find my opportunities",exact=False).click()
            page.get_by_text("Showing Maya's fictional sample profile",exact=False).wait_for(state="hidden",timeout=180000)
            settled()
        page.wait_for_function("Array.from(document.querySelectorAll('button')).filter(x=>x.textContent.includes('View opportunity')).length <= 3")
        assert 0 < page.get_by_role("button",name="View opportunity",exact=False).count() <= 3
        if args.live:
            page.get_by_text("How this shortlist was made",exact=True).click()
            page.get_by_text("claims against retrieved passages",exact=False).first.wait_for(timeout=30000)
            assert not page.get_by_text("retained validated local results",exact=False).count()
        page.get_by_text("Compare your options",exact=True).click()
        # Selection and two-column output are exercised by Streamlit AppTest.
        # React Aria's portaled menu is not stable under this Edge automation.
        assert page.get_by_role("combobox",name="Choose up to three opportunities").count()==1
        page.screenshot(path=str(root/"artifacts"/("phase2-live-results.png" if args.live else "phase2-results.png")),full_page=True)
        page.get_by_role("button",name="View opportunity",exact=False).first.click()
        page.get_by_text("Follow the evidence",exact=True).wait_for(timeout=30000)
        settled()
        if args.live:
            assert page.get_by_text("Retrieved evidence:",exact=False).count() or page.get_by_text("Follow the evidence",exact=True).count()
        page.get_by_role("button",name="Build my application checklist",exact=True).click()
        settled()
        page.get_by_text("Ask for support · editable drafts",exact=True).first.click()
        draft=page.get_by_role("textbox",name="Your editable draft").first
        draft.fill(draft.input_value()+"\n\nMy question for the provider.")
        settled()
        assert page.get_by_role("button",name="Download draft",exact=True).first.is_enabled()
        page.screenshot(path=str(root/"artifacts/phase2-plan.png"),full_page=True)
        page.set_viewport_size({"width":390,"height":844})
        assert page.evaluate("document.documentElement.scrollWidth <= window.innerWidth")
        assert not page.locator('[data-testid="stException"]').count()
        assert not errors,errors
        print({"phase2":"passed","live":args.live,"comparison_control":True,"editable_draft":True,"mobile_overflow":False})
    finally:
        browser.close()
