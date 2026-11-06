import json
from datetime import datetime
from html import escape
from pathlib import Path
from urllib.parse import urlparse
from uuid import uuid4
from zoneinfo import ZoneInfo

import streamlit as st

from equalstart.catalog import ROOT, load_catalog
from equalstart.agents import PROMPT_VERSION
from equalstart.eligibility import assess, cycle_status
from equalstart.providers import Fireworks, Keenable, provider_display_name
from equalstart.schema import Profile
from equalstart.storage import Store
from equalstart.hosting import SessionStore, public_demo
from equalstart.workflow import application_tasks, run_matching
from equalstart.readiness import readiness
from equalstart.preparation import outreach_drafts

st.set_page_config(page_title="Equal Start · Find your next chapter", page_icon="✳", layout="wide", initial_sidebar_state="collapsed")
st.html(f"<style>{(ROOT / 'equalstart' / 'design.css').read_text(encoding='utf-8')}</style>")


def h(value):
    return escape(str(value), quote=True)


def go(page, selected=None):
    st.session_state["page"] = page
    st.session_state["_scroll_top"] = True
    if selected is not None:
        st.session_state["selected"] = selected
    st.rerun()


@st.cache_resource
def store():
    return Store()


@st.cache_data
def catalog(revision: int):
    return load_catalog()


data = catalog((ROOT / "data" / "opportunities.json").stat().st_mtime_ns)
lookup = {r.id: r for r in data}
PUBLIC = public_demo()
if PUBLIC:
    if "visitor_store" not in st.session_state:
        st.session_state["visitor_store"] = SessionStore()
    db = st.session_state["visitor_store"]
else:
    db = store()
try:
    provider = Fireworks(db)
    config_error = False
except (ValueError, TypeError):
    provider = None
    config_error = True
st.session_state.setdefault("page", "Explore")
st.session_state.setdefault("live", bool(provider and provider.ready))

left, right = st.columns([1, 1.25], vertical_alignment="center")
with left:
    st.html('<div class="brand"><span class="brandmark">↗</span>equal start<small>OPPORTUNITY FOR EVERYONE</small></div>')
with right:
    nav_cols = st.columns(3)
    for col, title in zip(nav_cols, ["Explore", "My plan", "How it works"]):
        with col:
            if st.button(title, key=f"nav-{title}", use_container_width=True, type="primary" if st.session_state.page == title else "secondary"):
                go(title)


def trace(events):
    for event in events:
        item = event.model_dump() if hasattr(event, "model_dump") else event
        st.markdown(f"**{item['stage']}** · {item['mode']} · {item['status']} · {item['elapsed_ms']} ms")
        st.caption(item["summary"])


def funding_panel(record):
    st.html(f'<div class="fund-panel"><div class="mini-label">THE FUNDING PICTURE</div><div class="amount">{h(record.award)}</div><p>{h(next(c.text for c in record.claims if c.topic == "funding"))}</p></div>')
    st.markdown(f"**Housing:** {record.housing}  \n**Travel:** {record.travel}  \n**Application fee:** {record.fee}")
    st.caption("Funding amounts describe published support, not guaranteed awards. Payment timing and personal costs may vary.")


def profile_form():
    existing = st.session_state.get("profile")
    with st.expander("Your goals and circumstances", expanded=existing is None):
        st.caption("Share only what you want to. Missing eligibility details stay unknown. Your profile is kept in this session.")
        if st.button("Try Maya's sample profile", key="sample-profile"):
            st.session_state["profile"] = Profile(goal="I want summer environmental research with a stipend, housing, and travel support.", discipline="Environment", year="Sophomore", institution_type="Four-year", citizenship="US citizen", gpa=3.5, full_time=True, research_career=True)
            st.session_state["run"] = run_matching(st.session_state.profile, data)
            st.session_state["profile_revision"] = st.session_state.get("profile_revision", 0) + 1
            st.session_state["sample"] = True
            st.rerun()
        rev = st.session_state.get("profile_revision", 0)
        with st.form(f"profile-{rev}"):
            goal = st.text_area("What would you like to pursue?", value=existing.goal if existing else "", placeholder="e.g. Summer research in environmental science, with housing and travel support", max_chars=1200, height=90)
            col1, col2, col3 = st.columns(3)
            disciplines = ["Environment", "STEM", "Health", "Social sciences", "Business", "Arts and humanities", "All fields"]
            years = ["Prefer not to say", "Freshman", "Sophomore", "Junior", "Senior"]
            types = ["Prefer not to say", "Four-year", "Community college"]
            with col1:
                discipline = st.selectbox("Area of interest", disciplines, index=disciplines.index(existing.discipline) if existing and existing.discipline in disciplines else 0)
            with col2:
                year = st.selectbox("Undergraduate year", years, index=years.index(existing.year) if existing and existing.year in years else 0)
            with col3:
                institution_type = st.selectbox("Institution type", types, index=types.index(existing.institution_type) if existing and existing.institution_type in types else 0)
            c1, c2 = st.columns(2)
            with c1:
                no_upfront = st.checkbox("I need to avoid upfront costs", value=existing.no_upfront if existing else True)
            with c2:
                needs_housing = st.checkbox("I need housing support for placements", value=existing.needs_housing if existing else True)
            with st.expander("Optional eligibility details · improves screening"):
                c1, c2 = st.columns(2)
                with c1:
                    citizenships = ["Prefer not to say", "US citizen", "US national", "Permanent resident", "DACA", "International student", "Other"]
                    citizenship = st.selectbox("Citizenship or residency category", citizenships, index=citizenships.index(existing.citizenship) if existing and existing.citizenship in citizenships else 0)
                    institution = st.text_input("Institution name", value=existing.institution or "" if existing else "", max_chars=160, placeholder="Optional; helps check institution-specific awards")
                    gpa = st.text_input("GPA on a 4.0 scale", value=str(existing.gpa) if existing and existing.gpa is not None else "", max_chars=5, placeholder="Leave blank if you prefer")
                with c2:
                    def tri(label, field):
                        values = ["Not specified", "Yes", "No"]
                        current = getattr(existing, field) if existing else None
                        answer = st.selectbox(label, values, index=0 if current is None else 1 if current else 2)
                        return {"Not specified": None, "Yes": True, "No": False}[answer]
                    full_time = tri("Enrolled full time?", "full_time")
                    research_career = tri("Interested in a research career?", "research_career")
                    transfer_plans = tri("Planning community-college transfer?", "transfer_plans")
            submitted = st.form_submit_button("Find my opportunities  ↗", type="primary", use_container_width=True)
        if submitted:
            try:
                profile = Profile(goal=goal.strip(), discipline=discipline, year=None if year == "Prefer not to say" else year,
                                  institution_type=None if institution_type == "Prefer not to say" else institution_type,
                                  institution=institution.strip() or None, citizenship=None if citizenship == "Prefer not to say" else citizenship,
                                  gpa=float(gpa) if gpa.strip() else None, full_time=full_time, research_career=research_career,
                                  transfer_plans=transfer_plans, no_upfront=no_upfront, needs_housing=needs_housing)
            except ValueError:
                st.error("Enter a goal of at least three characters and, if supplied, a GPA between 0 and 4.")
                return
            st.session_state.profile = profile
            st.session_state.sample = False
            st.session_state["clarification_handled"] = False
            with st.spinner("Finding relevant opportunities and checking published criteria…"):
                st.session_state.run = run_matching(profile, data, provider if st.session_state.live else None,
                                                    search=Keenable() if st.session_state.live else None, store=db)
                st.session_state.leads = st.session_state.run.get("leads", [])
                db.log_run(st.session_state.run["run_id"], [e.model_dump() for e in st.session_state.run["events"]])
            st.rerun()


def card(record, match):
    with st.container(border=True):
        state = match.cycle_status if match else cycle_status(record)
        cls = "amber" if state in ("Upcoming", "Unknown", "Confirm closing time") else "gray" if state == "Closed" else ""
        when = record.deadline.strftime("%b %d, %Y") if record.deadline else record.deadline_date.strftime("%b %d, %Y") if record.deadline_date else "Check provider"
        st.html(f'''<div class="op-card"><div class="provider">{h(record.provider)}</div>
<span class="badge">{h(record.category)}</span><span class="badge {cls}">{h(state)}</span>
<h3>{h(record.title)}</h3><p>{h(record.summary)}</p><div class="funding">{h(record.award)}</div>
<div class="card-meta"><span>{h(record.location)}</span><span>{h(when)}</span></div></div>''')
        if match:
            st.html(f'<div class="card-fit">{h(match.status)} · Relevance {match.score}/100</div><div class="score"><div style="width:{match.score}%"></div></div>')
            if match.barriers:
                st.caption(match.barriers[0])
            state_info = readiness(record, match, st.session_state.get("run", {}).get("findings", []))
            st.markdown(f"**{state_info['label']}**")
            st.caption(state_info["next_step"])
            met = sum(criterion.state == "Met" for criterion in match.criteria)
            unknown = sum(criterion.state == "Unknown" for criterion in match.criteria)
            st.caption(f"Recorded checks: {met} met · {unknown} need confirmation")
            if state_info["supported"] or state_info["unresolved"]:
                st.caption(f"Retrieved evidence: {state_info['supported']} supported · {state_info['unresolved']} unresolved")
            else:
                st.caption(state_info["evidence"])
        else:
            st.caption("Add your profile to check eligibility and financial barriers.")
        c1, c2 = st.columns([3, 1])
        with c1:
            if st.button("View opportunity  ↗", key=f"detail-{record.id}", use_container_width=True):
                go("Details", record.id)
        with c2:
            saved = record.id in db.saved()
            if st.button("Saved" if saved else "Save", key=f"save-{record.id}", disabled=saved, use_container_width=True):
                db.save(record.id)
                st.rerun()


def clarify_profile():
    question = st.session_state.get("run", {}).get("clarification")
    if not question or st.session_state.get("clarification_handled"):
        return
    with st.container(border=True):
        st.markdown("**One detail could help us check the requirements**")
        st.caption("Optional. Skipping keeps this unknown and does not make you ineligible.")
        answer = st.selectbox(question["prompt"], ["Prefer not to say"]+question["options"], key=f"clarify-{question['field']}")
        if st.button("Continue with this answer", key="answer-clarification"):
            profile_data = st.session_state.profile.model_dump()
            if answer != "Prefer not to say":
                profile_data[question["field"]] = {"Yes": True, "No": False}.get(answer, answer)
            profile = Profile.model_validate(profile_data)
            st.session_state.profile = profile
            st.session_state["clarification_handled"] = True
            st.session_state["profile_revision"] = st.session_state.get("profile_revision", 0)+1
            with st.spinner("Updating the shortlist and source checks…"):
                st.session_state.run = run_matching(profile, data, provider if st.session_state.live else None,
                                                    search=Keenable() if st.session_state.live else None,
                                                    store=db, allow_clarification=False)
                st.session_state.leads = st.session_state.run.get("leads", [])
                db.log_run(st.session_state.run["run_id"], [e.model_dump() for e in st.session_state.run["events"]])
            st.rerun()


def compare_options(records, matches):
    with st.expander("Compare your options"):
        selected = st.multiselect("Choose up to three opportunities", [record.id for record in records if record.id in matches],
                                  format_func=lambda rid: lookup[rid].title, max_selections=3)
        if selected:
            columns = st.columns(len(selected))
            for col, rid in zip(columns, selected):
                record, match = lookup[rid], matches[rid]
                state_info = readiness(record, match, st.session_state.get("run", {}).get("findings", []))
                with col:
                    st.markdown(f"**{record.title}**")
                    st.write(record.award)
                    st.caption(f"Housing: {record.housing}")
                    st.caption(f"Travel: {record.travel}")
                    st.caption(f"Upfront costs: {record.upfront}")
                    st.write(state_info["label"])
                    st.caption(state_info["evidence"])
                    sources = [source for source in st.session_state.get("run", {}).get("snapshots", []) if source.opportunity_id == rid]
                    if sources:
                        st.caption("Source receipt: " + max(source.retrieved_at for source in sources).isoformat())
                    for barrier in match.barriers:
                        st.warning(barrier)
                    st.link_button("Read official conditions", str(record.official_url), key=f"compare-source-{rid}")


def explore():
    c1, c2 = st.columns([1.25, 1], vertical_alignment="center")
    with c1:
        st.html('''<section class="hero"><div class="eyebrow">YOUR AMBITION BELONGS HERE</div>
<h1>Your next chapter.<br><em>Within reach.</em></h1>
<p>Find scholarships and funded experiences that fit your goals, your circumstances, and the future you want to build.</p>
<div class="trustline"><span>U.S. opportunities</span><span>Official sources</span><span>Costs made clear</span></div></section>''')
    with c2:
        st.html('''<div class="hero-art"><div class="art-label">A LITTLE DIRECTION. MORE POSSIBILITY.</div>
<div class="paper-card primary"><span class="badge">FUND YOUR EDUCATION</span><b>A scholarship that fits your path</b><small>See the requirements. Understand the support.</small><span class="art-icon">↗</span></div>
<div class="paper-card secondary"><span class="badge amber">BUILD YOUR EXPERIENCE</span><b>Research. Learn. Go further.</b><small>Look beyond the stipend to the real costs.</small></div></div>''')
    st.html('<div class="intro-strip"><strong>Potential is everywhere. Access should be, too.</strong><span>You bring the ambition. We help you find a way in.</span></div>')
    profile_form()
    profile = st.session_state.get("profile")
    if profile:
        clarify_profile()
    if st.session_state.get("sample"):
        st.info("Showing Maya's fictional sample profile with real catalog opportunities. Edit the profile to make this yours.")
    st.html('<div class="section-head"><h2>Find your way forward</h2><span>Small steps. Real possibilities.</span></div><p class="section-sub">Explore the reviewed catalog, or add your goals for a personalized shortlist.</p>')
    f1, f2, f3, f4 = st.columns([1.2, 1, 1, 1])
    with f1:
        keyword = st.text_input("Search catalog", placeholder="Provider, subject, or keyword")
    with f2:
        category = st.selectbox("Opportunity type", ["All types", "Scholarship", "Research", "Internship"])
    with f3:
        cycle = st.selectbox("Application status", ["Current and upcoming", "Open only", "All cycles"])
    with f4:
        eligibility = st.selectbox("Eligibility", ["Potential matches", "All outcomes", "Needs confirmation", "Screened criteria met"], disabled=profile is None)
    matches = {m.opportunity_id: m for m in st.session_state.get("run", {}).get("matches", [])}
    order = [m.opportunity_id for m in st.session_state.get("run", {}).get("matches", [])] or list(lookup)
    visible = []
    for id in order:
        record = lookup[id]
        match = matches.get(id)
        state = match.cycle_status if match else cycle_status(record)
        if keyword and keyword.lower() not in (record.title + " " + record.provider + " " + record.summary + " " + " ".join(record.tags)).lower():
            continue
        if category != "All types" and record.category != category:
            continue
        if cycle == "Open only" and state != "Open":
            continue
        if cycle == "Current and upcoming" and state == "Closed":
            continue
        if match and ((eligibility == "Potential matches" and match.status == "Not eligible") or (eligibility not in ("Potential matches", "All outcomes") and match.status != eligibility)):
            continue
        visible.append((record, match))
    if profile:
        compare_options([record for record, _ in visible], matches)
        view = st.radio("Explore view", ["Recommended next steps", "Browse reviewed catalog"], horizontal=True)
        if view == "Recommended next steps":
            selected_ids = set(st.session_state.get("run", {}).get("selected_ids", []))
            visible = [(record, match) for record, match in visible if record.id in selected_ids][:3]
            st.caption("Up to three prioritized options. Confirm conditions before applying; these are not award or eligibility guarantees.")
    st.caption(f"{len(visible)} opportunities shown · {len(data)} reviewed records · unknown cycles require confirmation")
    if not visible:
        st.html('<div class="empty"><h3>No confirmed route from this shortlist yet.</h3><p>The catalog may lack your subject, cycles may be closed, or recorded conditions may not fit. Browse the catalog or review separate discovery leads. We keep eligibility restrictions intact.</p></div>')
    for start in range(0, len(visible), 3):
        cols = st.columns(3)
        for col, pair in zip(cols, visible[start:start+3]):
            with col:
                card(*pair)
    if st.session_state.get("run"):
        with st.expander("How this shortlist was made"):
            trace(st.session_state.run["events"])
            if st.session_state.run.get("flagged_claims"):
                st.warning("Evidence needs additional review: " + ", ".join(st.session_state.run["flagged_claims"]))
            st.caption("Research stopped: " + st.session_state.run.get("stop_reason", "Local matching completed"))
            st.json(st.session_state.run.get("research_trace", []))
            st.download_button("Download research activity", json.dumps(st.session_state.run.get("research_trace", []), indent=2),
                               file_name="equal-start-research.json", mime="application/json")
    with st.expander("Search beyond the reviewed catalog"):
        st.caption("Keenable returns discovery leads. These are not verified recommendations and are not added to your eligible shortlist.")
        query = st.text_input("Search official U.S. opportunity pages", value=(profile.goal if profile else "undergraduate scholarships funded research USA"), max_chars=500)
        if st.button("Search with Keenable", key="web-search"):
            try:
                with st.spinner("Searching for discovery leads…"):
                    st.session_state.leads = Keenable().search(query + " undergraduate USA")
            except Exception:
                st.warning("Live search is unavailable. Your reviewed catalog and saved plan are still available.")
        for lead in st.session_state.get("leads", []):
            st.markdown(f"**{lead.get('title', 'Discovery lead')}**")
            st.caption(str(lead.get("snippet", ""))[:600])
            st.link_button("Open source to verify", lead["url"])


def detail():
    record = lookup.get(st.session_state.get("selected"))
    if not record:
        go("Explore")
    if st.button("← Back to opportunities"):
        go("Explore")
    st.html(f'<div class="eyebrow">{h(record.provider)} · {h(record.category)}</div><div class="detail-title">{h(record.title)}</div>')
    st.write(record.summary)
    st.caption(f"{record.location} · {record.cycle} · {cycle_status(record)}")
    c1, c2 = st.columns([1.5, 1])
    with c2:
        funding_panel(record)
        st.link_button("Visit official opportunity  ↗", str(record.official_url), use_container_width=True, type="primary")
        if st.button("Save to my plan", key="save-detail", use_container_width=True):
            db.save(record.id)
            st.success("Saved to My plan.")
        if st.button("Build my application checklist", key="build-plan", use_container_width=True):
            with st.spinner("Organizing the published application steps…"):
                tasks, event = application_tasks(record, provider if st.session_state.live else None)
            db.save(record.id)
            st.session_state.setdefault("plans", {})[record.id] = [t.model_dump(mode="json") for t in tasks]
            db.save_plan(record.id, [t.model_dump(mode="json") for t in tasks])
            db.log_run(str(uuid4()), [event.model_dump()])
            st.session_state.setdefault("planning_events", {})[record.id] = event
            go("My plan")
    with c1:
        st.subheader("Could this be your next step?")
        profile = st.session_state.get("profile")
        if profile:
            match = assess(profile, record)
            st.markdown(f"**{match.status}** · local relevance score {match.score}/100")
            st.caption("A relevance score is a transparent heuristic, not a probability of winning. Criteria met does not mean selected.")
            for criterion in match.criteria:
                icon = "✓" if criterion.state == "Met" else "×" if criterion.state == "Not met" else "?"
                st.markdown(f"**{icon} {criterion.label}** — {criterion.state}")
                if criterion.claim_id:
                    claim = next(c for c in record.claims if c.id == criterion.claim_id)
                    st.caption(f"{criterion.detail} [Source]({claim.url})")
                else:
                    st.caption(criterion.detail)
            if match.barriers:
                st.subheader("Plan for the real costs")
                for barrier in match.barriers:
                    st.warning(barrier)
            with st.expander("See relevance score components"):
                st.json(match.components)
        else:
            st.info("Add your profile on Explore to see which recorded criteria match your circumstances.")
            for item in record.rules:
                st.markdown(f"- {item.label}")
            for item in record.confirmations:
                st.markdown(f"- Confirm: {item}")
        st.subheader("Dates to keep in mind")
        timing = next(c for c in record.claims if c.topic == "timing")
        st.write(timing.text)
        if record.deadline:
            central = record.deadline.astimezone(ZoneInfo("America/Chicago"))
            st.caption("Application deadline in Chicago: " + central.strftime("%b %d, %Y · %I:%M %p %Z"))
        elif record.deadline_date:
            st.caption("Date only: confirm the exact closing time and timezone with the provider.")
        st.subheader("Follow the evidence")
        st.caption("Catalog summaries were reviewed against provider pages. They are not a fresh verification on every visit.")
        for claim in record.claims:
            with st.expander(f"{claim.topic.title()} · checked {claim.checked}"):
                if claim.id in st.session_state.get("run", {}).get("flagged_claims", []):
                    st.warning("The evidence agent flagged this summary for additional confirmation.")
                st.write(claim.text)
                st.link_button("Read provider source", str(claim.url), key=f"claim-{claim.id}")
                st.caption(f"Evidence reference: {claim.id}")
                finding = next((item for item in st.session_state.get("run", {}).get("findings", []) if item["claim_id"] == claim.id), None)
                if finding:
                    st.markdown(f"**Retrieved evidence: {finding['status']}**")
                    source = next((source for source in st.session_state.run.get("snapshots", []) if source.id == finding["snapshot_id"]), None)
                    if finding["quote"]:
                        st.text(finding["quote"])
                    if source:
                        st.caption(f"Source receipt {source.id} · retrieved {source.retrieved_at.isoformat()}")
                        st.link_button("Open cited provider page", str(source.url), key=f"grounded-{claim.id}")
                    st.caption("A located passage supports review; it does not establish complete eligibility. Contradicted or missing facts need provider confirmation.")
        if st.button("Refresh this source with Keenable", key="refresh-source"):
            try:
                with st.spinner("Fetching the current official page…"):
                    fresh = Keenable().fetch(str(record.official_url), {urlparse(str(record.official_url)).hostname})
                st.session_state["fresh-source"] = {"id": record.id, "content": fresh.get("content", ""), "time": datetime.now(ZoneInfo("America/Chicago")).isoformat()}
            except Exception:
                st.warning("Source refresh could not finish. Use the official link above; the stored catalog has not changed.")
        fresh = st.session_state.get("fresh-source", {})
        if fresh.get("id") == record.id:
            st.caption("Fresh page retrieved " + fresh["time"] + ". Review for changes; this does not automatically update catalog facts.")
            with st.expander("Inspect refreshed page text"):
                st.text(fresh["content"][:16000])


def tracker():
    st.html('<div class="eyebrow" style="margin-top:45px">MAKE POSSIBILITY A PLAN</div><div class="detail-title">One step closer.</div>')
    st.write("Your saved opportunities and the next small steps to pursue them.")
    saved = db.saved()
    st.caption("Saved for this browser session. Download your checklist before leaving; a restart or lost session clears it." if PUBLIC else "Saved locally on this computer for this single-user demo. Your profile is not saved with the checklist.")
    if not saved:
        st.html('<div class="empty"><h3>Your next chapter starts with a save.</h3><p>Explore an opportunity and save it here to turn your ambition into a plan.</p></div>')
        if st.button("Explore opportunities", type="primary"):
            go("Explore")
        return
    exported = []
    for id, completed in saved.items():
        if id not in lookup:
            continue
        record = lookup[id]
        tasks = db.plan(id)
        if tasks is None:
            tasks = [t.model_dump(mode="json") for t in application_tasks(record)[0]]
        with st.container(border=True):
            c1, c2 = st.columns([4, 1])
            with c1:
                st.subheader(record.title)
                st.caption(record.provider + " · " + cycle_status(record))
            with c2:
                if st.button("Remove", key=f"remove-{id}", use_container_width=True):
                    db.remove(id)
                    st.rerun()
            done = []
            task_labels = {item["id"]:item["text"] for item in tasks}
            for task in tasks:
                if st.checkbox(task["text"], value=task["id"] in completed, key=f"task-{id}-{task['id']}"):
                    done.append(task["id"])
                st.caption(task["kind"] + (f" · [Source]({task['source_url']})" if task.get("source_url") else ""))
                if task.get("depends_on"):
                    st.caption("Prepare first: " + " · ".join(task_labels.get(dep, "Earlier preparation step") for dep in task["depends_on"]))
                if task.get("suggested_date"):
                    st.caption("Suggested preparation date: " + str(task["suggested_date"]) + " · not a provider deadline")
                if task.get("effort"):
                    st.caption(task["effort"])
            if set(done) != set(completed):
                db.tasks(id, done)
            st.progress(len(done)/len(tasks), text=f"{len(done)} of {len(tasks)} steps complete")
            st.link_button("Official application information  ↗", str(record.official_url))
            with st.expander("Ask for support · editable drafts"):
                st.caption("Use the official page to locate the right contact. These drafts are suggestions, not published requirements. Review and send them yourself.")
                drafts = outreach_drafts(record)
                draft_type = st.selectbox("What would you like to ask?", list(drafts), key=f"draft-type-{id}")
                draft = st.text_area("Your editable draft", value=drafts[draft_type], height=240, key=f"draft-{id}-{draft_type}")
                st.download_button("Download draft", draft, file_name=f"{id}-support-request.txt", key=f"draft-download-{id}")
            if id in st.session_state.get("planning_events", {}):
                with st.expander("Checklist preparation details"):
                    trace([st.session_state.planning_events[id]])
            exported.append({"opportunity": record.title, "official_url": str(record.official_url), "cycle": record.cycle, "tasks": [{**t, "complete": t["id"] in done} for t in tasks]})
    st.download_button("Download my plan · JSON", json.dumps(exported, indent=2, ensure_ascii=False), file_name="equal-start-plan.json", mime="application/json", use_container_width=True)
    markdown = "# My Equal Start application plan\n\n"
    for item in exported:
        markdown += f"## {item['opportunity']}\n\n{item['official_url']}\n\n"
        markdown += "\n".join(f"- [{'x' if t['complete'] else ' '}] {t['text']} ({t['kind']})" for t in item["tasks"]) + "\n\n"
    st.download_button("Download printable checklist · Markdown", markdown, file_name="equal-start-plan.md", mime="text/markdown", use_container_width=True)
    with st.expander("Manage local saved data"):
        st.caption("Clearing removes your saved opportunities and checklist progress.")
        clear = st.checkbox("Clear all my saved opportunities and checklist progress")
        if st.button("Clear saved data", disabled=not clear):
            db.clear_saved()
            st.session_state.pop("plans", None)
            st.rerun()


def how():
    st.html('<div class="eyebrow" style="margin-top:45px">BUILT AROUND YOUR NEXT STEP</div><div class="detail-title">Clarity, before commitment.</div>')
    st.write("Equal Start pairs a reviewed opportunity catalog with specialist agents. Every recommendation keeps eligibility, uncertainty, and financial barriers visible.")
    for number, title, text in [
        ("01", "Discover a direction", "Your goals guide retrieval from the reviewed U.S. catalog."),
        ("02", "Look for evidence", "Bounded research retrieves reviewed official pages. The Evidence agent compares claims with exact passages; missing and conflicting information stays visible."),
        ("03", "Check the fit", "Deterministic rules enforce known eligibility. AI can refine ordering, never override a failed rule."),
        ("04", "Make a plan", "The planning agent sequences published materials. General preparation advice is labeled separately."),
    ]:
        with st.container(border=True):
            st.markdown(f"**{number} · {title}**")
            st.write(text)
    st.subheader("What you can expect")
    st.markdown("- U.S. opportunities and scholarships for U.S. study, with program-specific residency rules.\n- Direct links to official sources and dates of catalog review.\n- Clear differences between support provided upfront, reimbursements, and unknown costs.\n- No guarantee of eligibility, selection, or full financial coverage.")
    st.caption("This is a capstone prototype with a small curated catalog. Local scores are explainable heuristics. It does not submit applications or contact providers.")
    with st.expander("Agent evaluation scorecards"):
        reports = []
        for report_path in sorted((ROOT / "docs" / "evals").glob("*/results.json"), reverse=True):
            try:
                report = json.loads(report_path.read_text(encoding="utf-8"))
                if report["metadata"].get("finished_utc") and report["metadata"].get("live"):
                    reports.append((report_path, report))
            except (ValueError, KeyError):
                continue
        if reports:
            report_path, report = reports[0]
            st.caption("Latest completed live run: " + report["metadata"]["run_id"] + ". Synthetic cases with fixed labels; see the evaluation guide for scope and limitations.")
            if report["metadata"].get("prompt_version") != PROMPT_VERSION:
                st.warning("This report evaluates an earlier prompt version. Rerun evaluations before using it as evidence for the current agents.")
            st.dataframe([{"Agent": s["agent"], "Mode": s["mode"], "Task cases": f"{s['task_passes']}/{s['evaluations']}",
                           "Contract validity": f"{s['contract_rate']:.0%}", "Task pass rate": f"{s['task_pass_rate']:.1%}",
                           "p50 latency ms": round(s["latency_p50_ms"]), "Gate": "PASS" if s["release_gate"] else "FAIL"}
                          for s in report["summaries"]], hide_index=True, use_container_width=True)
            st.caption("Phase 2 evaluations include tool decisions and claim support against supplied source passages. Original regression runs assess stored-summary ambiguity. Neither proves complete eligibility or real-world factual accuracy.")
            st.caption("Release gates apply to live agents. Baseline rows provide comparison, not release readiness.")
            if not PUBLIC:
                st.download_button("Download full evaluation results", json.dumps(report, indent=2), file_name="equalstart-agent-evals.json", mime="application/json")
        else:
            st.caption("No completed live evaluation report yet. Run the evaluation suite described in evals/README.txt.")
    with st.expander("Demo settings and technical details"):
        if config_error:
            st.warning("Model configuration needs attention. Local matching is available.")
        available = bool(provider and provider.ready)
        st.toggle(f"Use live {provider_display_name(provider)} agents", key="live", disabled=not available)
        st.caption("Live mode sends your goal and the minimum needed profile constraints to the configured model provider. Local mode runs the same graph with deterministic stages and makes no model calls.")
        st.write(f"Model: `{provider.model if provider else 'Not configured'}`")
        if not PUBLIC:
            st.write(f"Estimated inference spent or reserved: **${db.spent():.5f} / $15.00**")
            st.caption("Persistent application ledger; not an account-wide billing guarantee. Unknown call costs retain conservative reservations. No automatic top-ups.")
        st.write("Search: Keenable, with provider credentials when configured.")
        if not PUBLIC:
            with st.expander("Recent stage records · no profile inputs"):
                st.json(db.recent_runs())
        if st.button("Clear this session's profile"):
            for key in ("profile", "run", "sample", "fresh-source", "leads"):
                st.session_state.pop(key, None)
            st.session_state.profile_revision = st.session_state.get("profile_revision", 0) + 1
            st.success("Session profile cleared. Saved checklist data is managed in My plan.")


page = st.session_state.page
if page == "Explore":
    explore()
elif page == "Details":
    detail()
elif page == "My plan":
    tracker()
else:
    how()
if st.session_state.pop("_scroll_top", False):
    # Static trusted script only; user and source text never enter executable HTML.
    st.html("""<script>requestAnimationFrame(() => {
      const main = document.querySelector('[data-testid="stMain"]');
      if (main) main.scrollTo({top:0, behavior:'instant'});
      window.scrollTo({top:0, behavior:'instant'});
    });</script>""", unsafe_allow_javascript=True)
st.html('<div class="footer"><span>equal start · Built for ambition, wherever it begins.</span><span>USA opportunities · Capstone prototype · Official sources linked</span></div>')
