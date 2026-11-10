"""Lexicon explorer and linter, for language access coordinators (PRD section 2).

explore(lang): every approved phrase next to its English source, so a reviewer who reads
both languages can check the whole lexicon in one pass.
lint(lang): problems that would make clean translations fail or, worse, pass wrongly:
missing keys or variants, templates that do not read back to their own intent, negation
markers in positive templates (or missing from negative ones)."""
from __future__ import annotations

import itertools

from pydantic import BaseModel

from stentor.intent.schema import ACTION_VERB, ROUTE_ACTIONS, Action, AlertIntent, Hazard, Instruction
from stentor.lexicon import load, meta


class PhraseRow(BaseModel):
    section: str  # hazard | action | instruction | headline | other
    key: str
    variant: str
    en: str
    text: str
    match: list[str] = []


class LexiconView(BaseModel):
    lang: str
    name: str
    english_name: str
    dir: str
    reviewed_by: str
    negation_markers: list[str]
    rows: list[PhraseRow]


class LintFinding(BaseModel):
    severity: str  # error | warning
    where: str
    message: str


class LintReport(BaseModel):
    lang: str
    ok: bool
    errors: int
    warnings: int
    checked_templates: int
    findings: list[LintFinding]


def explore(lang: str) -> LexiconView:
    lx, en = load(lang), load("en")
    rows: list[PhraseRow] = []
    for h, spec in en.hazards.items():
        other = lx.hazards.get(h, {})
        rows.append(PhraseRow(section="hazard", key=h, variant="name", en=spec["name"], text=other.get("name", ""),
                              match=other.get("terms", [])))
    for a, spec in en.actions.items():
        other = lx.actions.get(a, {})
        for v, tpl in spec["text"].items():
            rows.append(PhraseRow(section="action", key=a, variant=v or "plain", en=tpl,
                                  text=other.get("text", {}).get(v, ""), match=other.get("match", [])))
    for k, spec in en.instructions.items():
        other = lx.instructions.get(k, {})
        for v, tpl in spec["text"].items():
            rows.append(PhraseRow(section="instruction", key=k, variant=v, en=tpl,
                                  text=other.get("text", {}).get(v, ""), match=other.get("match", [])))
    for key in ("headline", "headline_place", "headline_distance", "headline_all_clear", "headline_all_clear_place", "event_name"):
        rows.append(PhraseRow(section="headline", key=key, variant="", en=en.opt(key, ""), text=lx.opt(key, "")))
    rows.append(PhraseRow(section="other", key="info", variant="", en=en.info["text"], text=lx.info.get("text", "")))
    rows.append(PhraseRow(section="other", key="expires", variant="", en=en.expires["text"], text=lx.expires.get("text", "")))
    m = meta(lang)
    return LexiconView(lang=lang, name=m["name"], english_name=m["english_name"], dir=m["dir"],
                       reviewed_by=m["reviewed_by"], negation_markers=lx.negation_markers, rows=rows)


def _ph(counter: dict, kinds: str) -> list[str]:
    out = []
    for k in kinds:
        counter[k] = counter.get(k, 0) + 1
        out.append(f"⟦{k}{counter[k]}⟧")
    return out


def lint(lang: str) -> LintReport:
    from stentor.render.template import render
    from stentor.verify.backparse import parse_lexicon

    lx, en = load(lang), load("en")
    findings: list[LintFinding] = []
    err = lambda where, msg: findings.append(LintFinding(severity="error", where=where, message=msg))  # noqa: E731
    warn = lambda where, msg: findings.append(LintFinding(severity="warning", where=where, message=msg))  # noqa: E731

    for h in Hazard:
        if h.value not in lx.hazards:
            err(f"hazards.{h.value}", "missing hazard")
    for a in Action:
        spec = lx.actions.get(a.value)
        if not spec:
            err(f"actions.{a.value}", "missing action")
            continue
        if not spec.get("match"):
            err(f"actions.{a.value}", "no match phrases: the action can never be found in a translation")
        for v in en.actions[a.value]["text"]:
            if v not in spec.get("text", {}):
                err(f"actions.{a.value}", f"missing variant '{v or 'plain'}'")
        for v, tpl in spec.get("text", {}).items():
            if lx.negation_hits(tpl):
                err(f"actions.{a.value}.{v or 'plain'}", "negation marker inside an action template")
    for k, spec in en.instructions.items():
        mine = lx.instructions.get(k)
        if not mine:
            err(f"instructions.{k}", "missing instruction")
            continue
        for v in spec["text"]:
            tpl = mine.get("text", {}).get(v)
            if tpl is None:
                err(f"instructions.{k}", f"missing variant '{v}'")
                continue
            hits = lx.negation_hits(tpl)
            if v.startswith("neg") and hits == 0:
                err(f"instructions.{k}.{v}", "negated template without a negation marker")
            if v.startswith("pos") and hits:
                err(f"instructions.{k}.{v}", "positive template contains a negation marker")
            for kind in (v.split("|")[1] if "|" in v else ""):
                if "{" + kind + "}" not in tpl:
                    err(f"instructions.{k}.{v}", f"template has no {{{kind}}} slot")
    for key in ("headline", "headline_place", "headline_distance", "headline_all_clear", "headline_all_clear_place", "event_name"):
        if not lx.opt(key):
            err(key, "missing")
    if not lx.negation_markers:
        err("negation_markers", "no negation markers: dropped 'do not' could never be detected")
    if lx.reviewed_by == "unreviewed":
        warn("reviewed_by", "not reviewed by a native speaker yet")

    checked = 0
    if not any(f.severity == "error" for f in findings):
        for hz, act in itertools.product(Hazard, Action):
            for variant in en.actions[act.value]["text"]:
                c: dict = {}
                kinds, _, role = variant.partition(":")
                phs = _ph(c, kinds)
                obj = (role or "via") if "P" in kinds and act in ROUTE_ACTIONS else None
                intent = AlertIntent(hazard=hz, action=act, instructions=[Instruction(verb=ACTION_VERB[act], object=obj, negated=False, placeholders=phs)],
                                     area_refs=[p for p in phs if "P" in p], time_refs=[p for p in phs if "T" in p],
                                     number_refs=[p for p in phs if "N" in p])
                checked += 1
                _round_trip(intent, lang, f"actions.{act.value}.{variant or 'plain'} ({hz.value})", findings, render, parse_lexicon)
        for key, spec in en.instructions.items():
            for v in spec["text"]:
                c = {}
                kinds = v.split("|")[1] if "|" in v else ""
                verb, _, obj = key.partition(":")
                ins = Instruction(verb=verb, object=obj or None, negated=v.startswith("neg"), placeholders=_ph(c, kinds))
                intent = AlertIntent(hazard=Hazard.FLOOD, action=Action.EVACUATE_NOW,
                                     instructions=[Instruction(verb="evacuate", negated=False), ins],
                                     area_refs=[p for p in ins.placeholders if "P" in p], time_refs=[p for p in ins.placeholders if "T" in p],
                                     info_refs=[p for p in ins.placeholders if "U" in p])
                checked += 1
                _round_trip(intent, lang, f"instructions.{key}.{v}", findings, render, parse_lexicon)
    errors = sum(1 for f in findings if f.severity == "error")
    return LintReport(lang=lang, ok=errors == 0, errors=errors, warnings=len(findings) - errors,
                      checked_templates=checked, findings=findings)


def _round_trip(intent: AlertIntent, lang: str, where: str, findings: list[LintFinding], render, parse) -> None:
    out = render(intent, lang)
    if not out.ok:
        findings.append(LintFinding(severity="error", where=where, message="cannot render: " + "; ".join(out.uncovered)))
        return
    back = parse(out.text, lang).intent
    want = sorted(i.model_dump_json() for i in intent.instructions)
    got = sorted(i.model_dump_json() for i in back.instructions)
    if (back.hazard, back.action) != (intent.hazard, intent.action) or want != got:
        findings.append(LintFinding(severity="error", where=where,
                                    message=f"'{out.text}' reads back as {back.hazard.value}/{back.action.value} "
                                            f"{[(i.verb, i.object, i.negated) for i in back.instructions]}"))
