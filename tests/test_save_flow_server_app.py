
import webvtt


def test_save_edits_updates_vtts_using_artifacts(app_with_artifacts):
    ctx = app_with_artifacts
    client = ctx.client
    v0 = ctx.vtt_dir / "0.vtt"
    v1 = ctx.vtt_dir / "1.vtt"
    v2 = ctx.vtt_dir / "2.vtt"

    # Read the first caption times from actual files to construct precise edits
    c0 = list(webvtt.read(str(v0)))
    c1 = list(webvtt.read(str(v1)))
    c2 = list(webvtt.read(str(v2)))
    assert c0 and c1 and c2, "Expected at least one caption in 0.vtt, 1.vtt, 2.vtt"

    changes = [
        {"start": c0[0].start, "end": c0[0].end, "speaker": "Speaker 1", "text": "edited-0", "originalText": c0[0].text, "vttFile": "0.vtt", "captionIdx": "0"},
        {"start": c1[0].start, "end": c1[0].end, "speaker": "Speaker 2", "text": "edited-1", "originalText": c1[0].text, "vttFile": "1.vtt", "captionIdx": "0"},
        {"start": c2[0].start, "end": c2[0].end, "speaker": "Speaker 3", "text": "edited-2", "originalText": c2[0].text, "vttFile": "2.vtt", "captionIdx": "0"},
    ]

    resp = client.post(f"/save_transcript_edits/{ctx.basename}", json={"changes": changes})
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data.get("success") is True

    # Re-read and assert updates persisted
    nc0 = list(webvtt.read(str(v0)))
    nc1 = list(webvtt.read(str(v1)))
    nc2 = list(webvtt.read(str(v2)))
    assert nc0 and nc0[0].text.strip() == "edited-0"
    assert nc1 and nc1[0].text.strip() == "edited-1"
    assert nc2 and nc2[0].text.strip() == "edited-2"


def test_save_single_edit_first_speaker_only(app_with_artifacts):
    """Sanity check: only modify 0.vtt's first caption and verify it persists.

    This helps isolate whether multi-speaker edits were masking a simpler bug.
    """
    ctx = app_with_artifacts
    client = ctx.client
    v0 = ctx.vtt_dir / "0.vtt"

    # Read first caption from 0.vtt to construct precise edit
    c0 = list(webvtt.read(str(v0)))
    assert c0, "Expected at least one caption in 0.vtt"
    original = c0[0].text

    changes = [
        {"start": c0[0].start, "end": c0[0].end, "speaker": "Speaker 1", "text": "edited-only-0", "originalText": original, "vttFile": "0.vtt", "captionIdx": "0"},
    ]

    resp = client.post(f"/save_transcript_edits/{ctx.basename}", json={"changes": changes})
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data.get("success") is True

    # Re-read and assert update persisted for 0.vtt only
    nc0 = list(webvtt.read(str(v0)))
    assert nc0 and nc0[0].text.strip() == "edited-only-0"
