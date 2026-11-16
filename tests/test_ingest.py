from io import BytesIO

import pytest
from pypdf import PdfWriter
from pypdf.generic import DecodedStreamObject, DictionaryObject, NameObject

from rag.ingest import parse, split
from rag.adapters import RemoteGenerator


def pdf(text=None):
    writer = PdfWriter()
    page = writer.add_blank_page(width=300, height=200)
    if text:
        font = DictionaryObject(
            {
                NameObject("/Type"): NameObject("/Font"),
                NameObject("/Subtype"): NameObject("/Type1"),
                NameObject("/BaseFont"): NameObject("/Helvetica"),
            }
        )
        page[NameObject("/Resources")] = DictionaryObject(
            {NameObject("/Font"): DictionaryObject({NameObject("/F1"): font})}
        )
        stream = DecodedStreamObject()
        stream.set_data(b"BT /F1 12 Tf 10 80 Td (Synthetic PDF marker PINE-61) Tj ET")
        page[NameObject("/Contents")] = writer._add_object(stream)
    data = BytesIO()
    writer.write(data)
    return data.getvalue()


def test_pdf_upload_retrieve_and_download(rig):
    from tests.test_api import file, ask

    a = rig.login("admin")
    e = rig.login("employee")
    raw = pdf(True)
    doc = a.post(
        "/api/admin/documents",
        json={**file("fixture.pdf", raw), "dept": "运营部", "title": "PDF marker", "public": True},
    ).json()["id"]
    ans = ask(e, "Synthetic PDF marker")
    assert "PINE-61" in ans["answer"] and ans["refs"][0]["page"] == 1
    assert e.get(f"/api/documents/{doc}/versions/1/download").content == raw


@pytest.mark.parametrize(
    "filename,raw",
    [
        ("scan.pdf", pdf()),
        ("broken.pdf", b"broken"),
        ("bad.md", b"\xff"),
        ("empty.txt", b" "),
        ("bad.zip", b"not a txt"),
    ],
)
def test_rejected_files(filename, raw):
    with pytest.raises(ValueError):
        parse(filename, raw)


def test_chunk_offsets_overlap():
    pages = ["甲" * 470, "second page"]
    rows = list(split(pages))
    assert [(p, s, e) for p, s, e, b in rows] == [(1, 0, 420), (1, 360, 470), (2, 0, 11)]
    assert all(body == pages[p - 1][s:e] for p, s, e, body in rows)


def test_real_adapter_contract(monkeypatch):
    import httpx

    seen = []

    def capture(url, **kwargs):
        seen.append(kwargs)
        return httpx.Response(
            200,
            json={"choices": [{"message": {"content": "grounded reply"}}]},
            request=httpx.Request("POST", url),
        )

    monkeypatch.setattr(httpx, "post", capture)
    adapter = RemoteGenerator("https://example.invalid/chat", "fixture", "test-only-token")
    assert adapter.generate("question", [{"body": "authorized only"}]) == "grounded reply"
    payload = seen[0]["json"]
    assert (
        "tools" not in payload
        and "authorized only" in str(payload)
        and "test-only-token" not in str(payload)
    )
