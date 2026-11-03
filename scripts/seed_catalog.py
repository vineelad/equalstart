"""Rebuild the reviewed catalog from concise official-source summaries.

These are real opportunities, not fictional demo records. Missing facts remain unknown.
Run from the repository root: .venv/Scripts/python scripts/seed_catalog.py
"""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CHECKED = "2026-11-02"
records = []


def add(id, title, provider, category, summary, location, tags, award, url,
        eligibility, funding, rules=(), confirmations=(), materials=(), timing="Current application dates need confirmation.",
        status="Unknown", cycle="Current cycle unconfirmed", deadline=None, deadline_date=None, opens=None,
        housing="Unknown", travel="Unknown", upfront="Unknown", eligibility_url=None, funding_url=None, timing_url=None):
    claims = [
        {"id": f"{id}-overview", "topic": "overview", "text": summary, "url": url, "checked": CHECKED},
        {"id": f"{id}-eligibility", "topic": "eligibility", "text": eligibility, "url": eligibility_url or url, "checked": CHECKED},
        {"id": f"{id}-funding", "topic": "funding", "text": funding, "url": funding_url or url, "checked": CHECKED},
        {"id": f"{id}-timing", "topic": "timing", "text": timing, "url": timing_url or url, "checked": CHECKED},
    ]
    if materials:
        claims.append({"id": f"{id}-materials", "topic": "materials", "text": "; ".join(materials), "url": url, "checked": CHECKED})
    records.append({"id": id, "title": title, "provider": provider, "category": category, "summary": summary,
                    "location": location, "tags": tags, "award": award, "official_url": url,
                    "claims": claims, "rules": [{"field": f, "op": op, "value": v, "label": label, "claim_id": f"{id}-eligibility"} for f, op, v, label in rules],
                    "confirmations": list(confirmations), "materials": list(materials), "cycle_status": status, "cycle": cycle,
                    "deadline": deadline, "deadline_date": deadline_date, "opens_on": opens,
                    "housing": housing, "travel": travel, "upfront": upfront})


CITIZEN = ("citizenship", "in", ["US citizen", "Permanent resident"], "U.S. citizen or permanent resident")
FULL = ("full_time", "eq", True, "Full-time enrollment")
RESEARCH = ("research_career", "eq", True, "Intend to pursue a research career")

add("noaa-hollings", "Hollings Undergraduate Scholarship", "NOAA", "Scholarship",
    "Support for NOAA-related study, followed by a paid summer research internship.", "U.S. institutions and NOAA facilities",
    ["Environment", "STEM", "Research", "Social sciences"], "Up to $9,500 / academic year",
    "https://www.noaa.gov/office-education/hollings-scholarship/prospective",
    "U.S. citizens; GPA at least 3.0; qualifying second-year, five-year-program third-year, or community-college transfer standing; NOAA-related major.",
    "Academic support up to $9,500 annually and a paid internship. Check site-specific housing, travel and payment conditions.",
    rules=[("citizenship", "in", ["US citizen"], "U.S. citizenship"), ("gpa", "gte", 3.0, "Minimum 3.0 GPA"), FULL],
    confirmations=["Qualifying year or transfer pathway", "Declared major supports NOAA's mission", "Full-time enrollment through the award period"],
    materials=["Complete application and essay questions", "Provide college transcripts", "Arrange two academic references and graduation-date documentation"],
    timing="2027 application open; closes January 31, 2027 at 11:59 p.m. Eastern.", status="Open", cycle="2027",
    deadline="2027-01-31T23:59:00-05:00")

add("cooke-transfer", "Undergraduate Transfer Scholarship", "Jack Kent Cooke Foundation", "Scholarship",
    "Help completing a bachelor's degree after community college, with transition advising.", "Accredited U.S. four-year institutions",
    ["All fields", "Transfer", "Tuition"], "Up to $55,000 / year",
    "https://www.jkcf.org/our-scholarships/undergraduate-transfer-scholarship/how-to-apply/",
    "Community-college sophomore by January 1, 2027, or qualifying recent graduate; GPA 3.5; transfer in fall 2027; unmet financial need.",
    "Last-dollar educational funding up to $55,000 annually, based on costs and other aid; transition and career advising included.",
    rules=[("institution_type", "eq", "Community college", "Community-college transfer pathway"), ("gpa", "gte", 3.5, "Minimum 3.5 GPA"), ("transfer_plans", "eq", True, "Plan to transfer to a four-year institution")],
    confirmations=["Sophomore status or qualifying graduation date", "Fall 2027 full-time bachelor's enrollment", "Financial review including family income limit of $95,000", "Prior four-year enrollment restrictions"],
    materials=["Complete the Common App for Transfer scholarship application"],
    timing="Application opened August 19, 2026; closes December 9, 2026 at 11:59 p.m. Eastern.",
    status="Open", cycle="Fall 2027 transfer", deadline="2026-12-09T23:59:00-05:00")

add("goldwater", "Goldwater Scholarship", "Goldwater Foundation", "Scholarship",
    "Academic funding for undergraduates pursuing research in natural science, mathematics, or engineering.", "Accredited U.S. institutions",
    ["STEM", "Research", "Tuition"], "Up to $7,500 / academic year",
    "https://goldwaterscholarship.gov/students/overview/",
    "Sophomore or junior by remaining terms; GPA 3.0; full-time study while supported; U.S. citizen, national, or permanent resident; research career intent.",
    "Up to $7,500 annually for eligible academic costs after other aid. Campus nomination is required.",
    rules=[("citizenship", "in", ["US citizen", "US national", "Permanent resident"], "Citizenship, national or permanent-resident status"), ("gpa", "gte", 3.0, "Minimum 3.0 GPA"), FULL, RESEARCH],
    confirmations=["Sophomore or junior definition based on remaining semesters", "Eligible research field and career", "Campus nomination and earlier campus deadline"],
    materials=["Contact your campus representative", "Complete the application and research essay", "Obtain campus nomination"],
    timing="National nominations use the last Friday in January, 5 p.m. Central. Confirm the cycle and earlier campus deadline.")

for id, title, program, min_gpa in [("doe-suli", "Science Undergraduate Laboratory Internships", "suli", 3.0), ("doe-cci", "Community College Internships", "cci", 2.7)]:
    add(id, title, "U.S. Department of Energy", "Research" if program == "suli" else "Internship",
        "On-site research or technical projects with scientists and engineers at U.S. national laboratories.", "U.S. DOE national laboratories",
        ["STEM", "Environment", "Research", "Community college"], "$650 / week + housing support",
        f"https://science.osti.gov/wdts/{program}/Eligibility",
        f"U.S. citizen or permanent resident; minimum GPA {min_gpa}; college coursework and enrollment criteria; age 18 by start. " + ("Community-college enrollment required; below 3.0 needs a GPA waiver statement." if program == "cci" else "Full-time undergraduate enrollment or qualifying recent graduation."),
        "Weekly stipend, housing arrangements or allowance, and qualifying domestic round-trip travel reimbursement. Upfront travel costs may remain.",
        rules=[CITIZEN, ("gpa", "gte", min_gpa, f"Minimum {min_gpa} GPA")] + ([FULL] if program == "suli" else [("institution_type", "eq", "Community college", "Community-college enrollment")]),
        confirmations=["At least one matriculated semester, 6 STEM credits and 12 total credits", "Age 18 by internship start", "Participation limits and full-term availability"] + (["GPA waiver statement if GPA is below 3.0"] if program == "cci" else []),
        housing="Allowance or arranged", travel="Reimbursed", upfront="Reimbursement barrier",
        funding_url=f"https://science.osti.gov/wdts/{program}/Benefits")

add("nih-sip", "NIH Summer Internship Program", "National Institutes of Health", "Research",
    "Full-time biomedical, behavioral, and social-science research with NIH investigators.", "NIH campuses in the United States",
    ["Health", "STEM", "Social sciences", "Research"], "Paid stipend; amount varies",
    "https://www.training.nih.gov/research-training/pb/sip/",
    "U.S. citizen or permanent resident; qualifying enrollment at least half time; age and full-program availability conditions apply.",
    "Stipend depends on education. Housing is not provided; interns arrange their own accommodation and need health insurance.",
    rules=[CITIZEN], confirmations=["At least half-time enrollment", "Published age rule for summer 2027", "Health insurance and full-time in-person availability"],
    materials=["Submit coursework and grades", "Prepare a CV or resume and personal statement", "Provide two reference contacts", "Complete NIH's eligibility screener and application", "Identify relevant investigators; outreach is recommended by NIH"],
    timing="2027 application open; application due January 26 at noon Eastern. Reference letters have a separate February 2 noon deadline.",
    status="Open", cycle="Summer 2027", deadline="2027-01-26T12:00:00-05:00", housing="Not provided")

add("nih-ugsp", "NIH Undergraduate Scholarship Program", "National Institutes of Health", "Scholarship",
    "Need-based academic support with paid NIH research service commitments.", "U.S. four-year institutions; NIH service placements",
    ["Health", "STEM", "Social sciences", "Research", "Tuition"], "Up to $20,000 / academic year",
    "https://www.training.nih.gov/research-training/pb/ugsp/",
    "Citizen or permanent resident; full-time four-year study; 3.3 GPA OR top 5%; certified exceptional financial need; qualifying transfer or junior/senior standing.",
    "Up to $20,000 for academic and living costs. Each supported year carries paid summer and post-graduation NIH service obligations.",
    rules=[CITIZEN, FULL, RESEARCH], confirmations=["3.3 GPA OR top-five-percent class rank", "Exceptional Financial Need certified by financial aid office", "Qualifying transfer or junior/senior standing", "Ability to fulfill paid service obligations and background check"],
    materials=["Complete NIH's eligibility screener and scholarship application", "Arrange Exceptional Financial Need certification"],
    timing="Opens January 5, 2027. Application due March 31 at noon Eastern; references and financial-need forms have later separate deadlines.",
    status="Upcoming", cycle="2027", opens="2027-01-05", deadline="2027-03-31T12:00:00-04:00")

add("ncsa-reu", "NCSA Summer Research Experience", "University of Illinois Urbana-Champaign", "Research",
    "Ten weeks of mentored research in machine learning and open-source scientific tools.", "Urbana-Champaign, Illinois",
    ["STEM", "Research", "Computing", "Open source"], "$700 / week + housing + meals",
    "https://reu.ncsa.illinois.edu/",
    "Citizen or permanent resident; associate or bachelor's enrollment in any major/year; good standing; age 18; Python and some machine-learning exposure.",
    "Weekly stipend, program-arranged paid housing, a meal plan and one round trip. Travel payment timing needs confirmation.",
    rules=[CITIZEN], confirmations=["Age 18 by start and good academic standing", "Python experience and exposure to machine learning", "Full-time availability and required campus residence"],
    timing="Applications November 15, 2026 through February 15, 2027; program May 24–July 30, 2027. Closing time not stated.",
    status="Upcoming", cycle="Summer 2027", opens="2026-11-15", deadline_date="2027-02-15", housing="Provided", travel="Supported; timing unknown")

add("cmu-reuse", "REUSE Software Engineering Research", "Carnegie Mellon University", "Research",
    "Paid software-engineering research; the published FAQ welcomes applicants with limited prior research.", "Pittsburgh, Pennsylvania",
    ["STEM", "Research", "Computing"], "$7,000 stipend + meals + housing",
    "https://www.cmu.edu/scs/s3d/reuse/faq.html",
    "Undergraduate enrollment; published graduation-date and age rules. Students on visas at U.S. institutions may need CPT or OPT.",
    "$7,000 stipend, $1,400 meal allowance, paid campus housing and travel compensation in the published 2026 cycle.",
    confirmations=["Next cycle's eligibility and graduation cutoff", "Age 18 by program start", "Work authorization if applicable"],
    materials=["Arrange one required reference letter", "Submit transcript with the ETAP application"],
    timing="Published deadline was February 1, 2026 at 11:59 p.m. Eastern; next cycle is unconfirmed.", status="Closed", cycle="2026 archive",
    deadline="2026-02-01T23:59:00-05:00", housing="Provided", travel="Supported; timing unknown")

add("hsf-scholar", "HSF Scholar Program", "Hispanic Scholarship Fund", "Scholarship",
    "Scholar support services with possible need-based funding, subject to available funds.", "Eligible U.S. four-year institutions",
    ["All fields", "Tuition", "Mentorship"], "$500–$5,000 if funded",
    "https://www.hsf.net/scholarship/",
    "Citizen, permanent resident or DACA; college GPA at least 2.5; Hispanic heritage; qualifying full-time four-year study and FAFSA submission.",
    "Scholar status does not guarantee an award. Funding ranges from $500 to $5,000 depending on need and available funds.",
    rules=[("citizenship", "in", ["US citizen", "Permanent resident", "DACA"], "Citizen, permanent resident or DACA"), ("gpa", "gte", 2.5, "Minimum 2.5 college GPA"), FULL],
    confirmations=["Voluntary heritage criterion and FAFSA requirement", "Qualifying four-year institution and funding availability"],
    timing="2026 application is closed; published deadline February 15, 2026. Next cycle unconfirmed.", status="Closed", cycle="2026 archive", deadline_date="2026-02-15")

add("udall-environment", "Udall Undergraduate Scholarship", "Udall Foundation", "Scholarship",
    "Academic support and an alumni community for environmental and Tribal public-service leadership.", "U.S. undergraduate institutions",
    ["Environment", "Social sciences", "Public service"], "Up to $7,500",
    "https://udall.gov/ourprograms/scholarship/scholarship",
    "Eligibility varies by environmental, Tribal-policy or Native-health category. Verify current standing, citizenship and nomination rules.",
    "Up to $7,500 for eligible academic expenses; the Foundation anticipates up to 65 awards in 2027.",
    confirmations=["Current 2027 eligibility criteria and category", "Campus nomination and earlier campus deadline"],
    timing="2027 program announced; verify national and campus closing dates.", cycle="2027",
    funding_url="https://www.udall.gov/ourprograms/scholarship/aboutscholarship")

add("ud-first-generation", "Constantin First-Generation Scholarship", "University of Dallas", "Scholarship",
    "Institution-specific support for current first-generation University of Dallas students.", "University of Dallas, Texas",
    ["All fields", "First generation", "Tuition"], "Amount not confirmed",
    "https://udallas.edu/admissions-aid/financial-aid/undergraduate-financial-aid/undergrad-scholarships.php",
    "Restricted to current University of Dallas first-generation students; full award conditions need confirmation.",
    "Award amount and covered expenses are not established in this catalog.",
    rules=[("institution", "eq", "University of Dallas", "Current University of Dallas enrollment")],
    confirmations=["First-generation definition and current enrollment", "Complete institution-specific award conditions"],
    timing="Spring 2027 application listed open, due November 4, 2026. University deadlines use Central time; exact time unconfirmed.",
    status="Open", cycle="Spring 2027", deadline_date="2026-11-04")

add("rankin-national", "Jeannette Rankin National Scholar Grant", "Jeannette Rankin Foundation", "Scholarship",
    "Flexible non-tuition support for women returning to education later in life.", "Accredited nonprofit U.S. institutions",
    ["All fields", "Nontraditional students", "Living costs"], "Up to $3,000 / year",
    "https://rankinfoundation.org/national-scholar-grant/",
    "Women age 35 or older with financial need pursuing a first associate or bachelor's degree, or eligible vocational study.",
    "Up to $3,000 annually, paid directly to recipients; renewal may be available for up to five years.",
    confirmations=["Age 35+ and published gender criterion", "Financial need and first-degree restrictions", "State-specific grant pathway and full eligibility survey"],
    materials=["Complete the eligibility survey and application essays", "Arrange recommendation letters"],
    timing="2026–2027 grant applications opened October 5, 2026; application and letters due February 12, 2027. Exact closing time unconfirmed.",
    status="Open", cycle="2026–2027", deadline_date="2027-02-12")

add("davis-putter", "Davis-Putter Scholarship", "Davis-Putter Scholarship Fund", "Scholarship",
    "Need-based support for students active in progressive social-change organizing.", "U.S. postsecondary study; confirm full conditions",
    ["All fields", "Public service", "Social sciences"], "Up to $15,000 / year",
    "https://www.davisputter.org/apply",
    "Applicants must have financial need, postsecondary enrollment, and active involvement in the Fund's specified social-change movements.",
    "Published maximum $15,000 for 2026–2027; grants are disbursed by academic term and cannot be deferred.",
    confirmations=["Published organizing and financial-need conditions", "Eligible U.S. study and current-cycle terms"],
    materials=["Complete application and personal statement", "Provide two recommendation letters and recent transcripts", "Provide required financial-aid or equivalent financial documentation"],
    timing="The site describes annual January–April 1 applications. Confirm the next cycle; no future-year date is inferred.",
    cycle="Next cycle unconfirmed")

add("patsy-mink", "Patsy Mink Education Support Awards", "Patsy Takemoto Mink Education Foundation", "Scholarship",
    "Education and living-expense support for low-income mothers pursuing further qualifications.", "Accredited nonprofit U.S. institutions",
    ["All fields", "Student parents", "Living costs"], "Up to $5,000",
    "https://www.patsyminkfoundation.org/education-support-application",
    "Women age 17+ with minor children, qualifying family income, U.S. residence, and full-time progressive study at an eligible U.S. institution.",
    "Published 2026 awards provide up to $5,000 in two installments for school or living costs.", rules=[FULL],
    confirmations=["Age, parenthood, gender and income conditions", "Degree progression, institution rules and completion date"],
    timing="2026–2027 cycle closed August 1, 2026; 2027–2028 information expected May 2027.",
    status="Closed", cycle="2026–2027 archive", deadline_date="2026-08-01")

add("live-your-dream", "Live Your Dream Education Awards", "Soroptimist International of the Americas", "Scholarship",
    "Flexible education support for women who provide their family's main financial support.", "U.S. applicants and study pathway",
    ["All fields", "Student parents", "Living costs"], "Varies; up to $16,000 across levels",
    "https://www.soroptimist.org/our-work/live-your-dream-awards/apply-for-the-live-your-dream-awards.html",
    "Women with financial need, dependents and primary financial-provider responsibility, pursuing undergraduate or vocational study; prior awards and affiliation exclusions apply.",
    "Club, region and international awards differ. Support can cover tuition, books, transport or childcare; timing depends on the club.",
    confirmations=["Published gender, dependent-support and financial-need criteria", "U.S. residence and eligible study pathway", "No prior award, graduate degree, or excluded Soroptimist affiliation", "Current local-club application window"],
    timing="Provider describes annual August 1–November 15 applications; confirm the current local club's cycle and exact closing time.")

add("cobell-undergrad", "Cobell Undergraduate Scholarship", "Indigenous Education, Inc.", "Scholarship",
    "Degree-cost support for qualifying Tribal students at nonprofit colleges.", "Eligible nonprofit U.S. institutions",
    ["All fields", "Community college", "Tuition"], "Up to $5,000 new / $8,000 returning",
    "https://cobellscholar.org/scholarships/undergraduate/",
    "Enrollment in a federally recognized Tribe or Alaska Native Corporation and eligible associate or bachelor's study. No minimum GPA; enrollment exceptions need review.",
    "Awards can support tuition, fees, books and living costs; disbursement is divided across terms. Applicants reapply annually.",
    confirmations=["Published Tribal membership and institution conditions", "Full-time enrollment or approved exception", "Provider page conflicts on second bachelor's degrees; ask before relying on eligibility"],
    materials=["Complete the OASIS scholarship application"],
    timing="Listed opening December 15, 2026; deadline March 31, 2027 at 11:59 p.m. Mountain. Confirm timezone and cycle labeling.",
    status="Upcoming", cycle="2027 deadline; provider cycle label needs confirmation", opens="2026-12-15", deadline_date="2027-03-31")

add("collegefund-fullcircle", "Full Circle Scholarship Program", "American Indian College Fund", "Scholarship",
    "One application for a portfolio of scholarships supporting Native college students.", "Accredited nonprofit U.S. institutions",
    ["All fields", "Tuition"], "Varies; published average $2,000–$3,000",
    "https://collegefund.org/students/scholarships/college-students/",
    "Tribal enrollment or qualifying descent; GPA 2.0; full-time study at an accredited nonprofit institution; confirm the appropriate scholarship pathway.",
    "Amounts vary by award. Funds are sent to the student's institutional financial-aid office after enrollment verification.",
    rules=[("gpa", "gte", 2.0, "Minimum 2.0 GPA"), FULL],
    confirmations=["Tribal membership or descent documentation", "Institution and current scholarship-pathway conditions"],
    materials=["Provide a digital photo and recent transcript", "Provide Tribal affiliation or descent documentation"],
    timing="Annual application opens February 1 with May 31 priority review and later application opportunities. Confirm current term and closing date.")

DREAM_STATUS = ("citizenship", "in", ["DACA", "Other"], "Potentially qualifying Dreamer status; federal-aid and visa exclusions still apply")
add("dream-national", "TheDream.US National Scholarship", "TheDream.US", "Scholarship",
    "Undergraduate tuition support for qualifying Dreamer students at U.S. Partner Colleges.", "U.S. National Partner Colleges",
    ["All fields", "Transfer", "Tuition"], "Up to $36,000 bachelor's tuition + stipend",
    "https://www.thedream.us/scholarships/national-scholarship/faqs/",
    "Qualifying Dreamer status, arrival before age 16 and November 1, 2021, continuous U.S. residence, GPA 2.5, and partner-college conditions; temporary visas and federal-aid eligibility are excluded.",
    "Up to $18,000 for an associate degree or $36,000 for a bachelor's degree, plus up to $6,000 for books and supplies; total and partner terms apply.",
    rules=[DREAM_STATUS, ("gpa", "gte", 2.5, "Minimum 2.5 college GPA")],
    confirmations=["Immigration, arrival and federal-aid eligibility conditions", "Partner college, residence and tuition-rate restrictions", "Partner admission application by scholarship deadline"],
    timing="Applications opened November 1, 2026; close February 28, 2027 at 11:59 p.m. Pacific.",
    status="Open", cycle="2027", deadline="2027-02-28T23:59:00-08:00")

add("dream-opportunity", "TheDream.US Opportunity Scholarship", "TheDream.US", "Scholarship",
    "Support to attend a designated out-of-state U.S. Partner College for qualifying Dreamers in specified states.", "Designated U.S. Opportunity Partner Colleges",
    ["All fields", "Tuition", "Living costs"], "Up to $100,000 for a bachelor's degree",
    "https://www.thedream.us/scholarships/opportunity-scholarship/",
    "Restricted Dreamer, immigration, academic, home-state and designated-college conditions apply; verify all current requirements.",
    "National-program FAQ describes up to $100,000 for tuition, required fees, campus housing and meals at selected Opportunity Partner Colleges.",
    rules=[DREAM_STATUS], confirmations=["Eligible home state and designated Partner College", "Full current immigration, academic, residence and enrollment conditions"],
    funding_url="https://www.thedream.us/scholarships/national-scholarship/faqs/",
    timing="Opportunity Scholarship applications November 1, 2026–January 31, 2027 at 11:59 p.m. Pacific; a different deadline from the National program.",
    status="Open", cycle="2027", deadline="2027-01-31T23:59:00-08:00")

if __name__ == "__main__":
    (ROOT / "data").mkdir(exist_ok=True)
    (ROOT / "data" / "opportunities.json").write_text(json.dumps(records, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Wrote {len(records)} reviewed catalog records")
