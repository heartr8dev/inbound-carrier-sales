# Hand-recorded demo clips

The video pipeline (`scripts/generate_video.py`) treats anything under
`video/recordings/` as a finished asset — it will NOT regenerate these.
Record each clip with Loom or OBS in **1920x1080 @ 30fps**, export as H.264 MP4,
include voiceover narration directly in the recording (the muxed audio is the
narration track for these segments), and save it at the exact filename below.

> Tip: enable Loom's "high-quality" export, or in OBS set rate-control to CRF
> 18-22 and the audio bitrate to 192 kbps. Avoid cursor smoothing — the
> dashboard recording in particular benefits from precise pointer motion.

---

## 1. `happy_path.mp4` — target 90 seconds

End-to-end "happy path" carrier call. Use the web call URL from the
HappyRobot workflow editor.

Recording flow:
1. Open the web call URL in a clean browser window. Start recording.
2. Greet the agent. State you are calling from MC **123456**.
3. When asked, request a **Dallas, TX to Atlanta, GA dry van pickup**
   in the next 48 hours.
4. Listen to the offered load. Accept the agent's **first** offer
   (no negotiation).
5. Confirm the transfer message ("connecting you to a rep") plays.
6. Switch to a second tab/window with the dashboard open and show the
   freshly logged call entry (sentiment, outcome=transferred, final
   rate, lane).
7. Stop recording.

Frame budget: ~60s on the call, ~30s on the dashboard tail.

---

## 2. `negotiation.mp4` — target 60 seconds

Three-round negotiation against the engine. Same web call URL.

Recording flow:
1. Start recording. Greet, state MC **123456**.
2. Request a load (any lane returning results — Dallas-Atlanta is fine).
3. When the agent offers the loadboard rate, **counter ~10% higher**.
4. The engine should respond with round-2 language ("the best I can do
   right now is..."). Counter again, smaller delta.
5. Round 3: agree on the agent's number. Confirm the call transfers.
6. Optional 5s tail: cut to the dashboard's negotiation analytics panel
   showing the round 2/3 acceptance rate.
7. Stop recording.

The full 3-round arc + dashboard cut should land near 60s.

---

## 3. `dashboard.mp4` — target 60 seconds

Pure dashboard tour. No phone call.

Recording flow:
1. Open the dashboard at `localhost:5173` (or the deployed URL) with
   mock data already loaded (`scripts/generate_mock_calls.py`).
2. Start recording on the overview/KPI strip.
3. Scroll slowly through:
   - KPI bar (call volume, transfer rate, revenue preserved).
   - Funnel chart (verified -> matched -> negotiated -> transferred).
   - Negotiation analytics (round-acceptance bars, delta histograms).
   - Recent calls table.
4. Expand one row in the recent calls table to show the call detail
   panel (transcript, rounds, sentiment).
5. Click the MC number in the expanded row to demonstrate the
   carrier-history drill-down.
6. Stop recording.

Aim for 60s; trim in post if it runs over.

---

## Sanity checks before handing off to `generate_video.py`

- File exists at one of these exact paths:
  - `video/recordings/happy_path.mp4`
  - `video/recordings/negotiation.mp4`
  - `video/recordings/dashboard.mp4`
- `ffprobe` reports 1920x1080, ~30fps, h264, AAC audio.
- Duration is within 5 seconds of the target above (the composition
  expects the listed `duration` in `video/script.yaml`).
- Audio is audible and not clipped (recording audio is the narration
  track for these segments — there is no separate ElevenLabs WAV).
