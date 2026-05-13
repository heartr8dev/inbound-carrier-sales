#!/usr/bin/env python3
"""Orchestrate generation of the 5-minute HappyRobot demo video.

Pipeline per ``video/script.yaml`` segment:

* ``screen_recording``   - assume the file at ``video/recordings/<file>``
                           already exists; nothing to do.
* ``b_roll``             - generate narration WAV via ElevenLabs, generate
                           video via WaveSpeed Seedance text-to-video, mux
                           narration onto the rendered MP4 with ffmpeg.
* ``avatar_lipsync``     - generate still via OpenAI Images (gpt-image-2),
                           generate narration WAV, then hand both to
                           WaveSpeed Seedance image-to-video for lipsync.

After every segment file exists, invoke
``npx hyperframes render ./composition.html -o ./output/demo.mp4`` from
inside ``video/`` (the path the composition is authored against).

Caching: every external call is keyed by a SHA-256 of its inputs. The
cache lives in ``video/cache/`` with subdirectories per asset type. Any
segment whose final MP4 already exists *and* whose inputs hash unchanged
is skipped.

Environment variables required at runtime (NOT at import time):

* ``OPENAI_API_KEY``       - for gpt-image-2 stills.
* ``ELEVENLABS_API_KEY``   - for narration TTS.
* ``ELEVENLABS_VOICE_ID``  - chosen voice id (or set ``tts.voice_id`` in
                             ``video/script.yaml``).
* ``WAVESPEED_API_KEY``    - for Seedance text/image-to-video.

The script is intentionally side-effect-free at import time so that
``python -m py_compile scripts/generate_video.py`` succeeds without any
credentials configured.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import requests
import yaml
from dotenv import load_dotenv

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

REPO_ROOT = Path(__file__).resolve().parents[1]
VIDEO_DIR = REPO_ROOT / "video"
SCRIPT_YAML = VIDEO_DIR / "script.yaml"
COMPOSITION_HTML = VIDEO_DIR / "composition.html"
SEGMENTS_DIR = VIDEO_DIR / "segments"
RECORDINGS_DIR = VIDEO_DIR / "recordings"
OUTPUT_DIR = VIDEO_DIR / "output"
CACHE_DIR = VIDEO_DIR / "cache"
CACHE_STILLS = CACHE_DIR / "stills"
CACHE_TTS = CACHE_DIR / "tts"
CACHE_VIDEO = CACHE_DIR / "video_raw"
CACHE_META = CACHE_DIR / "meta"

for d in (SEGMENTS_DIR, OUTPUT_DIR, CACHE_STILLS, CACHE_TTS, CACHE_VIDEO, CACHE_META):
    d.mkdir(parents=True, exist_ok=True)


# ---------------------------------------------------------------------------
# WaveSpeed Seedance v2 endpoint configuration
# ---------------------------------------------------------------------------
# TODO(WaveSpeed contract): verified via wavespeed.ai/docs/rest-api that the
# base is https://api.wavespeed.ai/api/v3/{provider}/{model}, auth is
# `Authorization: Bearer ...`, and submission returns a task id polled via
# /api/v3/predictions/{id}. The provider/model slugs and exact request body
# field names below are best-effort from the Seedance 2.0 product page
# (bytedance/seedance-2.0/{text-to-video,image-to-video}); if WaveSpeed's
# live schema differs, adjust SEEDANCE_T2V_PATH / SEEDANCE_I2V_PATH and the
# payload keys in `_seedance_payload()`.

WAVESPEED_BASE = "https://api.wavespeed.ai/api/v3"
SEEDANCE_T2V_PATH = "bytedance/seedance-v2-pro/text-to-video"
SEEDANCE_I2V_PATH = "bytedance/seedance-v2-pro/image-to-video"
WAVESPEED_POLL_PATH = "predictions"  # /api/v3/predictions/{id}
WAVESPEED_POLL_INTERVAL_S = 5.0
WAVESPEED_POLL_TIMEOUT_S = 60 * 15  # 15 min max per task


# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------


@dataclass
class Segment:
    id: str
    start: str
    end: str
    narration: str
    kind: str
    duration: int
    prompt_file: str | None = None
    reference_prompt_file: str | None = None
    video_model: str | None = None
    recording_file: str | None = None


def _parse_mmss(value: str) -> int:
    m, s = value.split(":")
    return int(m) * 60 + int(s)


def load_segments(script_path: Path) -> list[Segment]:
    raw = yaml.safe_load(script_path.read_text())
    out: list[Segment] = []
    for seg in raw["segments"]:
        visual = seg["visual"]
        kind = visual["kind"]
        duration_seconds = visual.get("duration") or (
            _parse_mmss(seg["end"]) - _parse_mmss(seg["start"])
        )
        out.append(
            Segment(
                id=seg["id"],
                start=seg["start"],
                end=seg["end"],
                narration=(seg.get("narration") or "").strip(),
                kind=kind,
                duration=int(duration_seconds),
                prompt_file=visual.get("prompt"),
                reference_prompt_file=visual.get("reference_image"),
                video_model=visual.get("video_model"),
                recording_file=visual.get("file"),
            )
        )
    return out


# ---------------------------------------------------------------------------
# Cache helpers
# ---------------------------------------------------------------------------


def _sha256(*parts: str) -> str:
    h = hashlib.sha256()
    for p in parts:
        h.update(p.encode("utf-8"))
        h.update(b"\x00")
    return h.hexdigest()[:32]


def _read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8").strip()


def _is_fresh(target: Path, meta_path: Path, expected_key: str) -> bool:
    """Return True iff `target` exists and the recorded cache key matches."""
    if not target.exists() or not meta_path.exists():
        return False
    try:
        meta = json.loads(meta_path.read_text())
    except (json.JSONDecodeError, OSError):
        return False
    return meta.get("key") == expected_key


def _write_meta(meta_path: Path, key: str, extra: dict[str, Any] | None = None) -> None:
    meta = {"key": key, "ts": int(time.time())}
    if extra:
        meta.update(extra)
    meta_path.write_text(json.dumps(meta, indent=2))


# ---------------------------------------------------------------------------
# ElevenLabs TTS
# ---------------------------------------------------------------------------


def _elevenlabs_voice_id(script: dict[str, Any]) -> str:
    voice = (script.get("tts") or {}).get("voice_id")
    if voice:
        return voice
    env_name = (script.get("tts") or {}).get("voice_id_env", "ELEVENLABS_VOICE_ID")
    voice = os.environ.get(env_name)
    if not voice:
        raise RuntimeError(
            f"No ElevenLabs voice id configured. Set tts.voice_id in script.yaml "
            f"or export {env_name}."
        )
    return voice


def generate_tts(narration: str, voice_id: str, model_id: str) -> Path:
    """Render narration to WAV via ElevenLabs. Cached by (voice, model, text)."""
    key = _sha256(voice_id, model_id, narration)
    out = CACHE_TTS / f"{key}.wav"
    meta = CACHE_TTS / f"{key}.json"
    if _is_fresh(out, meta, key):
        return out

    api_key = os.environ["ELEVENLABS_API_KEY"]
    url = f"https://api.elevenlabs.io/v1/text-to-speech/{voice_id}"
    headers = {
        "xi-api-key": api_key,
        "Content-Type": "application/json",
        "Accept": "audio/wav",
    }
    payload = {
        "text": narration,
        "model_id": model_id,
        "voice_settings": {},
    }
    resp = requests.post(url, headers=headers, json=payload, timeout=120)
    resp.raise_for_status()
    out.write_bytes(resp.content)
    _write_meta(meta, key, {"voice_id": voice_id, "model_id": model_id})
    return out


# ---------------------------------------------------------------------------
# OpenAI gpt-image-2 still generation
# ---------------------------------------------------------------------------


def generate_still(prompt_text: str) -> Path:
    """Generate a 1024x1024 PNG with gpt-image-2. Cached by prompt SHA."""
    key = _sha256("gpt-image-2", "1024x1024", prompt_text)
    out = CACHE_STILLS / f"{key}.png"
    meta = CACHE_STILLS / f"{key}.json"
    if _is_fresh(out, meta, key):
        return out

    # Imported lazily so that py_compile / dry-run does not require the SDK.
    from openai import OpenAI

    client = OpenAI()
    result = client.images.generate(
        model="gpt-image-2",
        prompt=prompt_text,
        size="1024x1024",
        n=1,
    )
    # The Images API can return either a `url` or a base64 `b64_json` field
    # depending on the response_format default for the model. Handle both.
    item = result.data[0]
    if getattr(item, "b64_json", None):
        import base64

        out.write_bytes(base64.b64decode(item.b64_json))
    elif getattr(item, "url", None):
        png = requests.get(item.url, timeout=60)
        png.raise_for_status()
        out.write_bytes(png.content)
    else:
        raise RuntimeError("OpenAI image response had neither b64_json nor url.")
    _write_meta(meta, key, {"prompt_sha": key})
    return out


# ---------------------------------------------------------------------------
# WaveSpeed Seedance
# ---------------------------------------------------------------------------


def _seedance_payload(
    *,
    prompt: str,
    duration: int,
    aspect_ratio: str,
    image_url: str | None,
) -> dict[str, Any]:
    """Construct request body for Seedance v2.

    TODO(WaveSpeed contract): field names below are the documented WaveSpeed
    convention (prompt / duration / aspect_ratio / image). If the live API
    rejects any of them, consult the model's playground at
    https://wavespeed.ai/models/bytedance/seedance-2.0/<variant> and update.
    """
    body: dict[str, Any] = {
        "prompt": prompt,
        "duration": duration,
        "aspect_ratio": aspect_ratio,
        "resolution": "1080p",
    }
    if image_url is not None:
        body["image"] = image_url
    return body


def _wavespeed_submit(model_path: str, payload: dict[str, Any]) -> str:
    api_key = os.environ["WAVESPEED_API_KEY"]
    url = f"{WAVESPEED_BASE}/{model_path}"
    resp = requests.post(
        url,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        json=payload,
        timeout=60,
    )
    resp.raise_for_status()
    body = resp.json()
    # Per wavespeed.ai/docs/rest-api: {"code":200,"data":{"id":"task-...", ...}}
    task_id = body.get("data", {}).get("id") or body.get("id")
    if not task_id:
        raise RuntimeError(f"WaveSpeed submission missing task id: {body!r}")
    return task_id


def _wavespeed_poll(task_id: str) -> str:
    """Poll until the task completes; return the output video URL."""
    api_key = os.environ["WAVESPEED_API_KEY"]
    url = f"{WAVESPEED_BASE}/{WAVESPEED_POLL_PATH}/{task_id}"
    deadline = time.time() + WAVESPEED_POLL_TIMEOUT_S
    while time.time() < deadline:
        resp = requests.get(
            url,
            headers={"Authorization": f"Bearer {api_key}"},
            timeout=30,
        )
        resp.raise_for_status()
        body = resp.json()
        data = body.get("data") or body
        status = (data.get("status") or "").lower()
        if status in {"completed", "succeeded", "success"}:
            # TODO(WaveSpeed contract): output field is variously documented
            # as "outputs", "output", or "result_url". Probe all common names.
            outputs = data.get("outputs") or data.get("output")
            if isinstance(outputs, list) and outputs:
                return outputs[0]
            if isinstance(outputs, dict) and outputs.get("video"):
                return outputs["video"]
            if data.get("result_url"):
                return data["result_url"]
            raise RuntimeError(f"WaveSpeed result has no output URL: {body!r}")
        if status in {"failed", "error", "cancelled"}:
            raise RuntimeError(f"WaveSpeed task {task_id} failed: {body!r}")
        time.sleep(WAVESPEED_POLL_INTERVAL_S)
    raise TimeoutError(f"WaveSpeed task {task_id} did not complete in time.")


def _download(url: str, dest: Path) -> Path:
    resp = requests.get(url, timeout=120, stream=True)
    resp.raise_for_status()
    with dest.open("wb") as fh:
        for chunk in resp.iter_content(chunk_size=1 << 16):
            if chunk:
                fh.write(chunk)
    return dest


def generate_b_roll(prompt_text: str, duration: int) -> Path:
    """Run Seedance text-to-video. Cached by (model, prompt, duration)."""
    key = _sha256(SEEDANCE_T2V_PATH, prompt_text, str(duration), "1080p", "16:9")
    out = CACHE_VIDEO / f"{key}.mp4"
    meta = CACHE_VIDEO / f"{key}.json"
    if _is_fresh(out, meta, key):
        return out

    payload = _seedance_payload(
        prompt=prompt_text,
        duration=duration,
        aspect_ratio="16:9",
        image_url=None,
    )
    task_id = _wavespeed_submit(SEEDANCE_T2V_PATH, payload)
    video_url = _wavespeed_poll(task_id)
    _download(video_url, out)
    _write_meta(meta, key, {"task_id": task_id, "model": SEEDANCE_T2V_PATH})
    return out


def generate_avatar_clip(
    *,
    still_path: Path,
    narration_wav: Path,
    prompt_text: str,
    duration: int,
) -> Path:
    """Run Seedance image-to-video for a talking-head segment.

    TODO(WaveSpeed contract): the image-to-video endpoint accepts an `image`
    URL. Two practical paths exist:
      1) Upload `still_path` to a temporary public URL (e.g. S3 presigned)
         and pass that URL.
      2) Use WaveSpeed's media-upload helper if available.
    The branch below assumes a helper env var WAVESPEED_UPLOAD_BASE; if not
    set, raise a clear error so the caller wires up uploads. The audio
    track (narration_wav) is *additionally* attached via the "audio" field
    so Seedance can lipsync to it; verify the exact field name in
    WaveSpeed's image-to-video schema and update if needed.
    """
    still_bytes = still_path.read_bytes()
    audio_bytes = narration_wav.read_bytes()
    key = _sha256(
        SEEDANCE_I2V_PATH,
        prompt_text,
        str(duration),
        hashlib.sha256(still_bytes).hexdigest(),
        hashlib.sha256(audio_bytes).hexdigest(),
    )
    out = CACHE_VIDEO / f"{key}.mp4"
    meta = CACHE_VIDEO / f"{key}.json"
    if _is_fresh(out, meta, key):
        return out

    image_url = _upload_asset(still_path)
    audio_url = _upload_asset(narration_wav)

    payload = _seedance_payload(
        prompt=prompt_text,
        duration=duration,
        aspect_ratio="16:9",
        image_url=image_url,
    )
    # TODO(WaveSpeed contract): field name for the lipsync audio input.
    payload["audio"] = audio_url
    payload["lipsync"] = True

    task_id = _wavespeed_submit(SEEDANCE_I2V_PATH, payload)
    video_url = _wavespeed_poll(task_id)
    _download(video_url, out)
    _write_meta(
        meta,
        key,
        {"task_id": task_id, "model": SEEDANCE_I2V_PATH, "lipsync": True},
    )
    return out


def _upload_asset(path: Path) -> str:
    """Return a public URL for `path`.

    TODO(asset hosting): this stub raises so it is impossible to silently
    submit a stale upload. The recommended wiring is one of:
      - aws s3 cp + s3 presign (set ``S3_UPLOAD_BUCKET``)
      - cloudflare R2 with public-read
      - WaveSpeed's own /api/v3/uploads helper if/when published
    Whichever you pick, return a URL that WaveSpeed can fetch over the
    public internet.
    """
    explicit = os.environ.get(f"WAVESPEED_ASSET_URL__{path.name.replace('.', '_')}")
    if explicit:
        return explicit
    raise NotImplementedError(
        "Asset upload helper is not wired. Either implement _upload_asset to "
        "push to S3/R2 and return a public URL, or set the per-file env "
        f"override WAVESPEED_ASSET_URL__{path.name.replace('.', '_')}."
    )


# ---------------------------------------------------------------------------
# ffmpeg muxing
# ---------------------------------------------------------------------------


def _require_ffmpeg() -> str:
    path = shutil.which("ffmpeg")
    if not path:
        raise RuntimeError("ffmpeg is required on PATH but was not found.")
    return path


def mux_audio_onto_video(video: Path, audio: Path, out: Path) -> Path:
    """Replace the audio track of `video` with `audio` (re-encode minimal)."""
    ffmpeg = _require_ffmpeg()
    out.parent.mkdir(parents=True, exist_ok=True)
    cmd = [
        ffmpeg,
        "-y",
        "-i",
        str(video),
        "-i",
        str(audio),
        "-map",
        "0:v:0",
        "-map",
        "1:a:0",
        "-c:v",
        "copy",
        "-c:a",
        "aac",
        "-b:a",
        "192k",
        "-shortest",
        str(out),
    ]
    subprocess.run(cmd, check=True)
    return out


# ---------------------------------------------------------------------------
# Per-segment build
# ---------------------------------------------------------------------------


def build_segment(seg: Segment, script: dict[str, Any]) -> Path:
    """Materialize the final MP4 for one segment under video/segments/."""
    final = SEGMENTS_DIR / f"{seg.id}.mp4"

    if seg.kind == "screen_recording":
        src = VIDEO_DIR / (seg.recording_file or "")
        if not src.exists():
            raise FileNotFoundError(
                f"Recording missing for segment {seg.id!r}: {src}. "
                f"See video/recordings/README.md."
            )
        # For screen recordings, the canonical asset stays under recordings/;
        # the composition references it directly. We still expose a marker
        # under segments/ for parity in `_is_fresh()` checks if desired.
        return src

    tts_cfg = (script.get("tts") or {})
    voice_id = _elevenlabs_voice_id(script)
    model_id = tts_cfg.get("model_id", "eleven_turbo_v2_5")

    narration_wav: Path | None = None
    if seg.narration:
        narration_wav = generate_tts(seg.narration, voice_id, model_id)

    if seg.kind == "b_roll":
        if not seg.prompt_file:
            raise ValueError(f"b_roll segment {seg.id!r} missing prompt file.")
        prompt_text = _read_text(VIDEO_DIR / seg.prompt_file)
        raw_video = generate_b_roll(prompt_text, seg.duration)
        if narration_wav is not None:
            mux_audio_onto_video(raw_video, narration_wav, final)
        else:
            shutil.copyfile(raw_video, final)
        return final

    if seg.kind == "avatar_lipsync":
        if not seg.reference_prompt_file:
            raise ValueError(
                f"avatar_lipsync segment {seg.id!r} missing reference_image."
            )
        if narration_wav is None:
            raise ValueError(
                f"avatar_lipsync segment {seg.id!r} requires non-empty narration."
            )
        ref_prompt = _read_text(VIDEO_DIR / seg.reference_prompt_file)
        still = generate_still(ref_prompt)
        raw_video = generate_avatar_clip(
            still_path=still,
            narration_wav=narration_wav,
            prompt_text=seg.narration,
            duration=seg.duration,
        )
        # Seedance image-to-video output already has the lipsynced audio
        # baked in (driven by the input audio track); we still rewrap to
        # `segments/{id}.mp4` so the composition has a stable path.
        shutil.copyfile(raw_video, final)
        return final

    raise ValueError(f"Unknown segment kind {seg.kind!r} for {seg.id!r}.")


# ---------------------------------------------------------------------------
# HyperFrames invocation
# ---------------------------------------------------------------------------


def render_composition() -> Path:
    output_mp4 = OUTPUT_DIR / "demo.mp4"
    cmd = [
        "npx",
        "hyperframes",
        "render",
        str(COMPOSITION_HTML.relative_to(VIDEO_DIR)),
        "-o",
        str(output_mp4.relative_to(VIDEO_DIR)),
    ]
    subprocess.run(cmd, check=True, cwd=VIDEO_DIR)
    return output_mp4


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--only",
        nargs="*",
        default=None,
        help="If given, only build these segment ids (still runs the final render).",
    )
    parser.add_argument(
        "--skip-render",
        action="store_true",
        help="Build segments but skip the final hyperframes render step.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Parse the script and print the build plan without calling any APIs.",
    )
    args = parser.parse_args(argv)

    load_dotenv(REPO_ROOT / ".env", override=False)
    script = yaml.safe_load(SCRIPT_YAML.read_text())
    segments = load_segments(SCRIPT_YAML)

    selected = segments
    if args.only:
        wanted = set(args.only)
        selected = [s for s in segments if s.id in wanted]
        missing = wanted - {s.id for s in selected}
        if missing:
            print(f"Unknown segment ids: {sorted(missing)}", file=sys.stderr)
            return 2

    if args.dry_run:
        for seg in selected:
            print(f"{seg.id:24s} {seg.start}-{seg.end} {seg.kind} ({seg.duration}s)")
        return 0

    for seg in selected:
        print(f"[build] {seg.id} ({seg.kind}, {seg.duration}s)")
        path = build_segment(seg, script)
        print(f"        -> {path}")

    if args.skip_render:
        return 0

    final = render_composition()
    print(f"[render] {final}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
