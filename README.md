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

## Engineering decisions
- **Facts in code, language in Gemini.** Forecast hours, ISO 10816 vibration zones, tolerances, supplier ratings and Quality Passport status are computed in Python. Gemini explains and drafts; every citation it makes is validated in code and unsupported claims are removed.
- **Grounding without web search.** Every answer comes from the shop's own data (BigQuery sensor history, Firestore Factory Memory, SOPs, supplier records), so no outside facts are needed. Guardrails: citation validation, an evidence-strength guard (confidence capped at 70 with a human check when evidence is thin), and supervisor approval for every action.
- **Latency.** *Ask Kaarigar* answers in about 3–5 s when warm: machine health is cached and refreshed in the background every 4 minutes; routing agents run with thinking off; ADK, embeddings, Firestore and Gemini connections are warmed at startup; all five machine forecasts come from one BigQuery query (~2.7 s), cached for 5 minutes. Inspections use a 60 s timeout, three fast retries, then a Flash-Lite fallback.
- **Cost.** ₹0.46 per inspection, measured from real token usage (`evals/cost.py`); about ₹1,300 a month for a typical shop. A per-visitor budget guard (80 live calls/hour, 600/day) protects the credits; cached demo paths are free.
- **Vector search.** One shop's Factory Memory is hundreds of records, so Gemini embeddings live in Firestore with hybrid keyword + meaning search. At cluster scale (many shops sharing supplier signals), we would move to Firestore vector search or AlloyDB AI with ScaNN.
- **Agent sessions.** *Ask Kaarigar* stores conversation memory in **Agent Platform's managed session service** (Agent Engine), so follow-up questions keep their context across Cloud Run instances. If the session service is unavailable, it falls back to in-memory sessions automatically; the agents may recommend actions but never execute them.
- **Reliability.** Warm Cloud Run instance with session affinity; uptime check every 5 minutes with email alerts; budget alerts; smoke tests gate every deploy; evaluation runs use a per-call watchdog.

## Evaluation
| Benchmark | Data | Result |
|---|---|---|
| Real factory photos | 9 cases from two Bengaluru shops (written permission) | Defects caught **4/4**; good parts accepted 3/5 |
| Indian foundry castings | Kaggle, Pilot Technocast impellers, 98 pairs, one golden photo, zero training | Defects caught **96%** (95% CI 87–99%); false alarms 38% (natural casting texture) |
| MVTec AD | metal nut + screw, all 275 test images | *(results below)* |
| Predict backtest | 25 **simulated** breakdowns, 5 seeds, model retrained hourly on past data only | Bearing wear warned **10/10**, median **9.2 h** ahead; misalignment 5/10; **0/19** false alarms on healthy machines. Tool wear is not visible in vibration and is caught at inspection instead |

Reproduce: `python -m evals.run_eval <pairs dir> --tag <name>` · `python -m evals.backtest_multi 5` · `python -m evals.real_world` · `python -m evals.cost 95.08`.
