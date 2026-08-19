from app import ai_client
from app.routers import analyze as analyze_router

RESUME_TEXT = """Experience
- Built REST APIs in Python using FastAPI for a fintech startup
- Wrote unit tests with pytest

Education
BS in Computer Science

Skills
Python, SQL
"""

JD_TEXT = "Looking for a backend engineer with Python, Docker, and Kubernetes experience."


def _fake_chat_json(messages, *args, **kwargs):
    system_content = messages[0]["content"]
    if "extract required skills" in system_content:
        return {"keywords": ["Python", "Docker", "Kubernetes"]}
    if "tailor resume bullets" in system_content:
        return {
            "bullets": [
                {
                    "section": "Experience",
                    "original": "- Built REST APIs in Python using FastAPI for a fintech startup",
                    "tailored": "- Built and containerized REST APIs in Python/FastAPI with Docker for a fintech startup",
                }
            ]
        }
    if "design at most" in system_content:
        return {
            "projects": [
                {
                    "title": "Containerized FastAPI Service on Kubernetes",
                    "covers_skills": ["Kubernetes"],
                    "bullets": [
                        "Deployed a FastAPI app to a local kind/minikube cluster with a Helm chart",
                        "Automated [N]+ deployment scenarios, reducing manual rollout steps by [X]%",
                    ],
                    "why_valuable": "Directly demonstrates the Kubernetes orchestration skill this JD requires",
                }
            ]
        }
    if "Screen whether a candidate" in system_content:
        return {"verdict": "PASS", "skip_reason": None, "skip_quote": None}
    raise AssertionError(f"unexpected prompt: {system_content}")


def _fake_embed(texts):
    # "docker" cluster vs "kubernetes" cluster so Kubernetes reliably fails the
    # semantic threshold and lands in gap_candidates.
    vectors = []
    for t in texts:
        if "kubernetes" in t.lower():
            vectors.append([0.0, 1.0])
        else:
            vectors.append([1.0, 0.0])
    return vectors


def _setup_resume_and_jd(client, auth_headers):
    resume_resp = client.post(
        "/resumes", json={"title": "My Resume", "raw_text": RESUME_TEXT}, headers=auth_headers
    )
    jd_resp = client.post(
        "/job-descriptions", json={"title": "Backend Role", "raw_text": JD_TEXT}, headers=auth_headers
    )
    return resume_resp.json()["id"], jd_resp.json()["id"]


def test_analyze_full_flow_with_mocked_nim(client, auth_headers, monkeypatch):
    monkeypatch.setattr(ai_client, "chat_json", _fake_chat_json)
    monkeypatch.setattr(ai_client, "embed", _fake_embed)

    resume_id, jd_id = _setup_resume_and_jd(client, auth_headers)

    resp = client.post(
        "/analyze", json={"resume_id": resume_id, "jd_id": jd_id}, headers=auth_headers
    )
    assert resp.status_code == 201
    body = resp.json()

    assert 0 <= body["ats_score"] <= 100
    assert "Python" in body["matched_keywords"]
    assert "Docker" in body["missing_keywords"]  # missing verbatim, but groundable via semantic match
    assert body["component_breakdown"]["keyword_weight"] == 0.5

    assert len(body["tailored_bullets"]) == 1
    assert "Docker" in body["tailored_bullets"][0]["tailored"]

    assert len(body["gap_flags"]) == 1
    assert body["gap_flags"][0]["title"]
    assert "Kubernetes" in body["gap_flags"][0]["covers_skills"]
    assert len(body["gap_flags"][0]["bullets"]) > 0
    assert "Kubernetes" not in body["matched_keywords"]

    assert body["screening"]["verdict"] == "PASS"
    assert body["screening"]["fit_verdict"] in {"STRONG MATCH", "SOLID MATCH", "REACH", "WEAK MATCH"}
    assert "Python" in body["screening"]["recruiter_note"]


def test_analyze_requires_auth(client):
    resp = client.post("/analyze", json={"resume_id": 1, "jd_id": 1})
    assert resp.status_code == 401


def test_analyze_404_for_other_users_resume(client, auth_headers, monkeypatch):
    monkeypatch.setattr(ai_client, "chat_json", _fake_chat_json)
    monkeypatch.setattr(ai_client, "embed", _fake_embed)

    resp = client.post("/analyze", json={"resume_id": 9999, "jd_id": 9999}, headers=auth_headers)
    assert resp.status_code == 404


def test_extract_jd_keywords_parses_mocked_response(monkeypatch):
    monkeypatch.setattr(ai_client, "chat_json", _fake_chat_json)
    keywords = analyze_router.extract_jd_keywords(JD_TEXT)
    assert keywords == ["Python", "Docker", "Kubernetes"]


def test_generate_tailored_bullets_empty_when_no_groundable_keywords():
    assert analyze_router.generate_tailored_bullets(RESUME_TEXT, []) == []


def test_extract_jd_keywords_caps_input_length(monkeypatch):
    """Regression test: a JD pasted from a job board can carry tens of thousands
    of characters of unrelated page chrome. Sending all of it risked the model
    spiraling into a runaway response that kept truncating even after growing
    the token budget to its ceiling (observed live: 36K+ characters, still
    truncated). The prompt sent to the model must be capped."""
    captured = {}

    def fake_chat_json(messages, *args, **kwargs):
        captured["user_content"] = messages[1]["content"]
        return {"keywords": ["Python"]}

    monkeypatch.setattr(ai_client, "chat_json", fake_chat_json)
    huge_jd = "Apply now\nAdd to cart\n" + ("Software Engineer role. " * 2000)
    analyze_router.extract_jd_keywords(huge_jd)
    assert len(captured["user_content"]) <= analyze_router.MAX_JD_CHARS


def test_extract_jd_keywords_caps_output_length(monkeypatch):
    monkeypatch.setattr(
        ai_client,
        "chat_json",
        lambda *a, **kw: {"keywords": [f"skill-{i}" for i in range(100)]},
    )
    keywords = analyze_router.extract_jd_keywords(JD_TEXT)
    assert len(keywords) == analyze_router.MAX_KEYWORDS


def test_generate_tailored_bullets_filters_ungrounded_and_junk_entries(monkeypatch):
    """Regression test: the model sometimes returns filler entries like
    {"original": "None", "tailored": "None"} for sections it has nothing to say
    about, or an 'original' that isn't actually verbatim in the resume. Both
    should be dropped, not just entries with empty strings."""

    def fake_chat_json(messages, *args, **kwargs):
        return {
            "bullets": [
                {"section": "Experience", "original": "None", "tailored": "None"},
                {
                    "section": "Experience",
                    "original": "Wrote unit tests with pytest",
                    "tailored": "Wrote unit tests with pytest",  # no-op, same text
                },
                {
                    "section": "Experience",
                    "original": "Text that was never actually on the resume",
                    "tailored": "Fabricated rewrite",
                },
                {
                    "section": "Experience",
                    "original": "Wrote unit tests with pytest",
                    "tailored": "Wrote unit tests with pytest and containerized them with Docker",
                },
            ]
        }

    monkeypatch.setattr(ai_client, "chat_json", fake_chat_json)
    bullets = analyze_router.generate_tailored_bullets(RESUME_TEXT, ["Docker"])
    assert len(bullets) == 1
    assert bullets[0]["original"] == "Wrote unit tests with pytest"


def test_generate_tailored_bullets_never_targets_the_summary_paragraph(monkeypatch):
    """Regression: generate_summary_tailoring owns the Summary/Objective paragraph.
    If generate_tailored_bullets also independently rewrites it, the two produce
    conflicting versions of the same text — observed live: one landed in the
    resume, the other fell into the unmatched 'Suggested additions' pile."""
    monkeypatch.setattr(
        ai_client,
        "chat_json",
        lambda *a, **kw: {
            "bullets": [
                {
                    "section": "Summary",
                    "original": "Backend engineer with 3 years building APIs.",
                    "tailored": "Backend engineer with 3 years building Python APIs.",
                }
            ]
        },
    )
    bullets = analyze_router.generate_tailored_bullets(RESUME_WITH_SUMMARY, ["Python"])
    assert bullets == []


def test_analyze_returns_502_when_ai_response_is_unparseable(client, auth_headers, monkeypatch):
    import json

    def _broken_chat_json(*args, **kwargs):
        raise json.JSONDecodeError("Unterminated string", "doc", 0)

    monkeypatch.setattr(ai_client, "chat_json", _broken_chat_json)
    monkeypatch.setattr(ai_client, "embed", _fake_embed)

    resume_id, jd_id = _setup_resume_and_jd(client, auth_headers)
    resp = client.post(
        "/analyze", json={"resume_id": resume_id, "jd_id": jd_id}, headers=auth_headers
    )
    assert resp.status_code == 502
    assert "detail" in resp.json()


def test_generate_gap_flags_empty_when_no_gap_candidates():
    assert analyze_router.generate_gap_flags(JD_TEXT, []) == []


def test_generate_gap_flags_consolidates_multiple_skills_per_project(monkeypatch):
    def fake_chat_json(messages, *args, **kwargs):
        return {
            "projects": [
                {
                    "title": "Full-Stack Task Tracker",
                    "covers_skills": ["React", "Node.js", "PostgreSQL", "Docker"],
                    "bullets": [
                        "Built and containerized a task tracker with a React frontend, Node.js API, and PostgreSQL",
                    ],
                    "why_valuable": "Covers four required skills in one coherent, buildable project.",
                },
                {
                    "title": "Kubernetes Deployment Pipeline",
                    "covers_skills": ["Kubernetes", "CI/CD"],
                    "bullets": [
                        "Set up a CI/CD pipeline that deploys the task tracker to a local Kubernetes cluster",
                    ],
                    "why_valuable": "Directly demonstrates the orchestration and CI/CD skills this JD requires.",
                },
            ]
        }

    monkeypatch.setattr(ai_client, "chat_json", fake_chat_json)
    projects = analyze_router.generate_gap_flags(
        JD_TEXT, ["React", "Node.js", "PostgreSQL", "Docker", "Kubernetes", "CI/CD"]
    )
    assert len(projects) == 2
    covered = {skill for p in projects for skill in p["covers_skills"]}
    assert covered == {"React", "Node.js", "PostgreSQL", "Docker", "Kubernetes", "CI/CD"}


def test_generate_gap_flags_drops_incomplete_entries(monkeypatch):
    monkeypatch.setattr(
        ai_client,
        "chat_json",
        lambda *a, **kw: {
            "projects": [
                {"title": "Missing skills field", "bullets": ["x"], "why_valuable": "y"},
                {
                    "title": "Complete entry",
                    "covers_skills": ["Docker"],
                    "bullets": ["x"],
                    "why_valuable": "y",
                },
            ]
        },
    )
    projects = analyze_router.generate_gap_flags(JD_TEXT, ["Docker"])
    assert len(projects) == 1
    assert projects[0]["title"] == "Complete entry"


def test_list_analyses_returns_history_with_titles(client, auth_headers, monkeypatch):
    monkeypatch.setattr(ai_client, "chat_json", _fake_chat_json)
    monkeypatch.setattr(ai_client, "embed", _fake_embed)

    resume_id, jd_id = _setup_resume_and_jd(client, auth_headers)
    client.post("/analyze", json={"resume_id": resume_id, "jd_id": jd_id}, headers=auth_headers)

    resp = client.get("/analyses", headers=auth_headers)
    assert resp.status_code == 200
    body = resp.json()
    assert len(body) == 1
    assert body[0]["resume_title"] == "My Resume"
    assert body[0]["jd_title"] == "Backend Role"
    assert "ats_score" in body[0]


def test_list_analyses_requires_auth(client):
    resp = client.get("/analyses")
    assert resp.status_code == 401


def test_list_analyses_scoped_to_current_user(client, monkeypatch):
    monkeypatch.setattr(ai_client, "chat_json", _fake_chat_json)
    monkeypatch.setattr(ai_client, "embed", _fake_embed)

    client.post("/auth/signup", json={"email": "a@example.com", "password": "pw123456"})
    token_a = client.post(
        "/auth/login", data={"username": "a@example.com", "password": "pw123456"}
    ).json()["access_token"]
    headers_a = {"Authorization": f"Bearer {token_a}"}
    resume_id, jd_id = _setup_resume_and_jd(client, headers_a)
    client.post("/analyze", json={"resume_id": resume_id, "jd_id": jd_id}, headers=headers_a)

    client.post("/auth/signup", json={"email": "b@example.com", "password": "pw123456"})
    token_b = client.post(
        "/auth/login", data={"username": "b@example.com", "password": "pw123456"}
    ).json()["access_token"]
    headers_b = {"Authorization": f"Bearer {token_b}"}

    resp = client.get("/analyses", headers=headers_b)
    assert resp.status_code == 200
    assert resp.json() == []


def test_get_analysis_by_id(client, auth_headers, monkeypatch):
    monkeypatch.setattr(ai_client, "chat_json", _fake_chat_json)
    monkeypatch.setattr(ai_client, "embed", _fake_embed)

    resume_id, jd_id = _setup_resume_and_jd(client, auth_headers)
    created = client.post(
        "/analyze", json={"resume_id": resume_id, "jd_id": jd_id}, headers=auth_headers
    ).json()

    resp = client.get(f"/analyses/{created['id']}", headers=auth_headers)
    assert resp.status_code == 200
    assert resp.json()["id"] == created["id"]
    assert resp.json()["tailored_bullets"] == created["tailored_bullets"]


def test_get_analysis_404_for_missing_or_other_users(client, auth_headers):
    resp = client.get("/analyses/9999", headers=auth_headers)
    assert resp.status_code == 404


RESUME_WITH_SUMMARY = """John Doe

Summary
Backend engineer with 3 years building APIs.
Comfortable working across the stack when needed.

Experience
- Built REST APIs in Python using FastAPI for a fintech startup

Education
BS in Computer Science

Skills
Python, SQL
"""


def test_extract_summary_paragraph_is_exact_verbatim_substring():
    extracted = analyze_router._extract_summary_paragraph(RESUME_WITH_SUMMARY)
    assert extracted is not None
    assert extracted in RESUME_WITH_SUMMARY  # must be a real substring for grounded substitution
    assert extracted == (
        "Backend engineer with 3 years building APIs.\n"
        "Comfortable working across the stack when needed."
    )


def test_extract_summary_paragraph_returns_none_when_absent():
    assert analyze_router._extract_summary_paragraph(RESUME_TEXT) is None


def test_generate_summary_tailoring_returns_empty_when_no_summary_section(monkeypatch):
    called = []
    monkeypatch.setattr(ai_client, "chat_json", lambda *a, **kw: called.append(1) or {})
    assert analyze_router.generate_summary_tailoring(RESUME_TEXT, JD_TEXT) == []
    assert called == []  # short-circuited before ever calling the model


def test_generate_summary_tailoring_returns_grounded_entry(monkeypatch):
    monkeypatch.setattr(
        ai_client,
        "chat_json",
        lambda *a, **kw: {
            "tailored_summary": "Backend engineer with 3 years building Python APIs and Docker deployments."
        },
    )
    result = analyze_router.generate_summary_tailoring(RESUME_WITH_SUMMARY, JD_TEXT)
    assert len(result) == 1
    assert result[0]["section"] == "Summary"
    assert result[0]["original"] in RESUME_WITH_SUMMARY
    assert "Docker" in result[0]["tailored"]


def test_generate_summary_tailoring_drops_unchanged_output(monkeypatch):
    original = analyze_router._extract_summary_paragraph(RESUME_WITH_SUMMARY)
    monkeypatch.setattr(ai_client, "chat_json", lambda *a, **kw: {"tailored_summary": original})
    assert analyze_router.generate_summary_tailoring(RESUME_WITH_SUMMARY, JD_TEXT) == []


def test_strip_em_dashes():
    assert analyze_router._strip_em_dashes("Built X — reducing Y") == "Built X  -  reducing Y"
    assert analyze_router._strip_em_dashes("Aug 2024 - May 2026") == "Aug 2024 - May 2026"


def test_find_verbatim_line_exact_match():
    text = "Experience\n- Built REST APIs\n"
    assert analyze_router._find_verbatim_line("- Built REST APIs", text) == "- Built REST APIs"


def test_find_verbatim_line_tolerates_whitespace_and_glyph_differences():
    """Regression: the model's copy of a bullet is often not byte-identical (a
    different bullet glyph, doubled spaces, smart quotes) even when it's
    genuinely the same line. The old exact-substring check falsely rejected
    these; the normalized match should accept them while still returning the
    real verbatim resume text."""
    text = "Experience\n•  Built  REST APIs   in Python\n"
    found = analyze_router._find_verbatim_line("- Built REST APIs in Python", text)
    assert found == "•  Built  REST APIs   in Python"  # real text, not the model's copy


def test_find_verbatim_line_rejects_fabricated_text():
    text = "Experience\n- Built REST APIs\n"
    assert analyze_router._find_verbatim_line("- Led a team of 50 engineers", text) is None


def test_compute_fit_verdict_bands():
    assert analyze_router.compute_fit_verdict(90) == "STRONG MATCH"
    assert analyze_router.compute_fit_verdict(70) == "SOLID MATCH"
    assert analyze_router.compute_fit_verdict(50) == "REACH"
    assert analyze_router.compute_fit_verdict(10) == "WEAK MATCH"


def test_build_recruiter_note_mentions_both_sides():
    note = analyze_router.build_recruiter_note(["Python", "SQL"], ["Kubernetes"])
    assert "Python" in note
    assert "Kubernetes" in note


def test_screen_jd_passes_when_verdict_pass(monkeypatch):
    monkeypatch.setattr(
        ai_client, "chat_json", lambda *a, **kw: {"verdict": "PASS", "skip_reason": None, "skip_quote": None}
    )
    result = analyze_router.screen_jd(RESUME_TEXT, JD_TEXT)
    assert result == {"verdict": "PASS", "skip_reason": None, "skip_quote": None}


def test_screen_jd_skip_with_grounded_quote(monkeypatch):
    jd = "We are unable to sponsor visas now or in the future. Must have Python experience."
    monkeypatch.setattr(
        ai_client,
        "chat_json",
        lambda *a, **kw: {
            "verdict": "SKIP",
            "skip_reason": "No visa sponsorship offered.",
            "skip_quote": "We are unable to sponsor visas now or in the future.",
        },
    )
    result = analyze_router.screen_jd(RESUME_TEXT, jd)
    assert result["verdict"] == "SKIP"
    assert result["skip_quote"] in jd


def test_screen_jd_rejects_skip_without_grounded_quote(monkeypatch):
    """Regression: a SKIP claim whose 'quote' doesn't actually appear in the JD
    text (the model inventing or paraphrasing a quote) must not be trusted —
    same grounding-by-verification principle as everywhere else in this app."""
    monkeypatch.setattr(
        ai_client,
        "chat_json",
        lambda *a, **kw: {
            "verdict": "SKIP",
            "skip_reason": "Sounds risky",
            "skip_quote": "This sentence does not appear in the job description at all.",
        },
    )
    result = analyze_router.screen_jd(RESUME_TEXT, JD_TEXT)
    assert result == {"verdict": "PASS", "skip_reason": None, "skip_quote": None}


def test_analyze_rate_limit_returns_429_after_threshold(client, auth_headers, monkeypatch):
    monkeypatch.setattr(ai_client, "chat_json", _fake_chat_json)
    monkeypatch.setattr(ai_client, "embed", _fake_embed)

    resume_id, jd_id = _setup_resume_and_jd(client, auth_headers)
    limit = int(analyze_router.ANALYZE_RATE_LIMIT.split("/")[0])

    for _ in range(limit):
        resp = client.post(
            "/analyze", json={"resume_id": resume_id, "jd_id": jd_id}, headers=auth_headers
        )
        assert resp.status_code == 201

    resp = client.post(
        "/analyze", json={"resume_id": resume_id, "jd_id": jd_id}, headers=auth_headers
    )
    assert resp.status_code == 429
    assert "detail" in resp.json()
