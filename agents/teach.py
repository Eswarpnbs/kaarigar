"""
Kaarigar Teaches: a short guide for a NEW operator, built only from this shop's SOPs and past defects
(Factory Memory). Gemini writes; code validates the defect-id citations.
"""
import json
import os
import re

from pydantic import BaseModel, Field

from agents.diagnosis import MACHINES, _past, _sops
from agents.inspector import _generate

MODEL = os.environ.get("KAARIGAR_MODEL", "gemini-2.5-flash")
ID_RE = re.compile(r"\b(D\d{3}|L-[\w-]+)\b")


class Lesson(BaseModel):
    title: str
    good_part_looks_like: list[str] = Field(description="2-4 short points")
    check_before_start: list[str] = Field(description="3-5 checks before starting the machine or a batch")
    watch_during_run: list[str] = Field(description="3-5 warning signs while running: sounds, vibration, chips, marks")
    common_mistakes: list[str] = Field(description="2-4 mistakes from THIS shop's past defects, each citing its id, e.g. (D016)")
    stop_and_call: str = Field(description="when to stop the machine and call the supervisor")


PROMPT = """You are a senior machinist teaching a NEW operator in a small Indian machine shop.
Write a short, practical guide for this machine using ONLY the SOPs and this shop's past defects below.
Simple words, short points. In common_mistakes, cite past defect ids like (D016). Do not invent numbers.
MACHINE: {machine}
SOPs: {sops}
PAST DEFECTS ON THIS MACHINE: {past}"""


def teach(machine_id: str, lang_name: str = "") -> dict:
    if machine_id not in MACHINES:
        return {"status": "error", "message": f"Unknown machine {machine_id}"}
    name = MACHINES[machine_id][0]
    past = [{k: r.get(k) for k in ("defect_id", "defect_type", "description", "root_cause", "fix")}
            for r in _past() if r.get("machine_id") == machine_id][:12]
    sops = {k: v[:1500] for k, v in _sops().items()}
    lesson: Lesson = _generate(MODEL, [PROMPT.format(machine=f"{machine_id} {name}", sops=json.dumps(sops),
                                                     past=json.dumps(past, default=str)) + (f"\nWrite ALL text in {lang_name}, in simple words a new operator "
                                                     f"would use. Keep codes unchanged (M1, D016, SOP-01, numbers with units)." 
                                                     if lang_name and lang_name != "Indian English" else "")], Lesson)
    valid = {r["defect_id"] for r in past}
    kept = [m for m in lesson.common_mistakes if all(i in valid for i in ID_RE.findall(m))]   # validated in code
    removed = len(lesson.common_mistakes) - len(kept)
    lesson.common_mistakes = kept
    return {"status": "success", "machine_id": machine_id, "machine": name, "lesson": lesson.model_dump(),
            "sources": {"sops": list(sops), "past_defects": sorted(valid)}, "unsupported_points_removed": removed}