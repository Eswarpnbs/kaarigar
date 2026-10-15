# Kaarigar — AI quality co-pilot for small factories

**One photo of a good part, one phone, zero training.**

Kaarigar helps small discrete-parts factories (10–100 workers) catch defects, find out *why* they happen, act on them,
and prevent them — using a phone instead of expensive inspection systems.

> "We didn't invent golden samples. We found them taped to a factory wall in Bengaluru.
> Kaarigar turns that wall into an AI inspector."

🌐 **Live demo:** https://kaarigar-510716.web.app (Firebase Hosting → Cloud Run)  
Backup link: https://kaarigar-1092998207528.asia-south1.run.app
Press **▶ Try the demo** (machine story) or **▶ Real factory part (Peenya)** (real photo, supplier story).

---

## The loop: Detect → Diagnose → Act → Verify → Predict

| Step | What Kaarigar does | Who decides |
|---|---|---|
| **Detect** | Compares a phone photo with golden samples; marks the defect, its type, severity and location | Gemini (vision) + verifier; location computed in code |
| **Diagnose** | Finds the root cause with evidence: machine health, Factory Memory (past defects), supplier history, SOPs. Exact 5 Whys, 6M categories, recurring-problem check | Evidence gathered in code; Gemini reasons; citations validated in code |
| **Act** | Work order (priority computed in code) + 8D report draft | Gemini drafts; **a supervisor approves or rejects** |
| **Verify** | Schedules a re-check after the fix | Code |
| **Predict** | Forecasts machine vibration and the hours left before the ISO damage zone | **BigQuery ML** (ARIMA_PLUS); Gemini only explains |

**Also:** 📷 inspect your own part (guided capture + photo-quality gate in code) · 🏷️ supplier scorecard (rules in code) · 📲 installable phone app (PWA) · EN/ಕನ್ನಡ/हिन्दी/తెలుగు interface · 🎙 voice reports in Telugu / Kannada / Hindi / English with spoken answers in the worker's language ·
📏 caliper check (photo of the display → OK / NOT OK against tolerance) · 🏭 Live Factory Map.

## Design principles
- **Compute in code, LLM explains.** Locations, priorities, tolerances, recurrence, forecasts and confidence caps
  are deterministic. Gemini reads, reasons and writes — it never decides a number.
- **AI informs, humans decide.** Nothing is approved without a supervisor, verified by Firebase Authentication and recorded in Firestore (who, when).
- **Safety first.** A missed defect is worse than a false alarm; when unsure, Kaarigar asks for a retake or a human check.
- **Two looks, two readers.** A flagged part gets an independent second look (disagreement → "please check by eye"); caliper readings are cross-checked by Cloud Vision OCR at the display position (disagreement → retake).
- **Protected live demo.** A budget guard limits paid AI calls (per visitor and per day, counted in Firestore); cached demo paths stay free.
- **Calibrated confidence.** Thin evidence (no machine signal, fewer than 2 similar cases, no recurrence) caps confidence at 70% and requires a human check.
- **Honest data.** Machine sensor data is **SIMULATED**; past defect records and SOPs are **SYNTHETIC samples**. Every screen says so.

## Architecture
## Security and secrets
- **No secrets in this repository.** Server credentials come from the Cloud Run service identity (Application Default Credentials); there are no service-account keys, `.env` files or client secrets in Git.
- The `apiKey` in `app/static/index.html` and `firebase-messaging-sw.js` is the **Firebase web configuration**, which is public by design: it only identifies the Firebase project. It is **restricted to our own domains** in Google Cloud, and every sensitive action is protected server-side: supervisor approvals require a **verified Firebase Authentication token**, and live AI calls pass through a **per-visitor budget guard** (Firestore counters).

## Judge guide: test Kaarigar in 3 minutes
**Live app:** https://kaarigar-510716.web.app (no login needed; works on a phone).

1. **Golden sample wall (home screen).** Tap any pinned part. Kaarigar compares it with its golden sample, locates the defect, and diagnoses the root cause. Watch the **route card** at the top get stamped (Detect, Diagnose, Act…) and the **agent reasoning** panel on the right. Drag the **spot-the-difference slider** under the result.
2. **▶ Watch the full loop.** The complete Detect → Diagnose → Act → Verify → Predict → Prevent → Learn flow. To approve the work order, click **Sign in as demo supervisor** (one click, Firebase Authentication).
3. **💬 Ask Kaarigar** (ADK agent team). Try: *"Which machine worries you most, and why?"* · *"Which supplier causes most of our problems?"* · *"What is waiting for my approval?"* · *"Have we seen scratches on flange nuts before?"* Switch the header to **ಕನ್ನಡ / हिन्दी / తెలుగు** and ask again.
4. **📷 Inspect your own part.** Two photos of any small object (one good, one scratched or different), with the live camera's guided capture.
5. Also try **🏷️ Quality Passport** (QR code), **📒 Import paper register** (sample page: `docs/sample_register.png`), **📏 Check a measurement**, **🎙 Report a problem by voice**.

### Known limits (so nothing surprises you)
- **Live AI calls:** 80 per hour and 600 per day per visitor (budget guard). Cached demo paths (the wall, *Watch the full loop*) are always instant and unlimited.
- **Timing:** a live inspection takes about 20–40 s; *Ask Kaarigar* about 5–15 s.
- **If Gemini is busy,** Kaarigar retries automatically and falls back to Flash-Lite; the cached demo paths keep working.
- **Data labels:** machine sensor data is **simulated** and seed defect records are **synthetic** (labelled throughout the app). Factory photos are **real**, from two Bengaluru shops, used with written permission (names, faces, and logos hidden).
