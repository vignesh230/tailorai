from tests.conftest import make_minimal_pdf


def test_create_and_list_resumes(client, auth_headers):
    resp = client.post(
        "/resumes", json={"title": "My Resume", "raw_text": "Experience\n- Did stuff"}, headers=auth_headers
    )
    assert resp.status_code == 201

    resp = client.get("/resumes", headers=auth_headers)
    assert resp.status_code == 200
    assert len(resp.json()) == 1
    assert resp.json()[0]["title"] == "My Resume"


def test_parse_pdf_extracts_text(client, auth_headers):
    pdf_bytes = make_minimal_pdf("Experience Software Engineer at Acme")
    resp = client.post(
        "/resumes/parse-pdf",
        files={"file": ("resume.pdf", pdf_bytes, "application/pdf")},
        headers=auth_headers,
    )
    assert resp.status_code == 200
    assert "Experience Software Engineer at Acme" in resp.json()["raw_text"]


def test_parse_pdf_requires_auth(client):
    pdf_bytes = make_minimal_pdf("hello")
    resp = client.post(
        "/resumes/parse-pdf", files={"file": ("resume.pdf", pdf_bytes, "application/pdf")}
    )
    assert resp.status_code == 401


def test_parse_pdf_rejects_non_pdf(client, auth_headers):
    resp = client.post(
        "/resumes/parse-pdf",
        files={"file": ("notes.txt", b"just some text", "text/plain")},
        headers=auth_headers,
    )
    assert resp.status_code == 400


def test_parse_pdf_rejects_corrupt_pdf(client, auth_headers):
    resp = client.post(
        "/resumes/parse-pdf",
        files={"file": ("resume.pdf", b"%PDF-1.4 not a real pdf", "application/pdf")},
        headers=auth_headers,
    )
    assert resp.status_code == 400
