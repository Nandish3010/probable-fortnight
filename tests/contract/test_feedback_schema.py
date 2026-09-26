"""feedback_response.schema.json is the source of truth for a submission; config/feedback_form.json
(the wording the respondent sees), the Pydantic mirror, the TypeScript types and the web mock copy
of the form are all checked against it here."""
import json
import re
import typing
from pathlib import Path

import jsonschema
import pytest

from services.feedback.models import FeedbackAnswers, FeedbackSubmission

ROOT = Path(__file__).resolve().parents[2]
SCHEMA = json.loads((ROOT / "docs" / "schemas" / "feedback_response.schema.json").read_text())
FORM = json.loads((ROOT / "config" / "feedback_form.json").read_text())
TS = (ROOT / "web" / "lib" / "types.ts").read_text()
QUESTIONS = [q for s in FORM["sections"] for q in s["questions"]]
ANSWERS = SCHEMA["properties"]["answers"]


def _validator():
    return jsonschema.Draft202012Validator(SCHEMA, format_checker=jsonschema.FormatChecker())


def test_question_ids_are_unique_and_stable_shaped():
    ids = [q["id"] for q in QUESTIONS] + [q["other_id"] for q in QUESTIONS if q.get("other_id")]
    assert len(ids) == len(set(ids))
    assert all(re.match(r"^[a-e][0-9]_[a-z_]+$", i) for i in ids), ids


def test_form_version_matches_the_schema_pattern():
    assert re.match(SCHEMA["properties"]["form_version"]["pattern"], FORM["form_version"])


def test_config_and_schema_have_the_same_questions_and_options():
    expected = {q["id"] for q in QUESTIONS} | {q["other_id"] for q in QUESTIONS if q.get("other_id")}
    assert set(ANSWERS["properties"]) == expected
    assert set(ANSWERS["required"]) == {q["id"] for q in QUESTIONS if q.get("required")}
    for q in QUESTIONS:
        prop = ANSWERS["properties"][q["id"]]
        if q["type"] == "single":
            assert prop["enum"] == [o["value"] for o in q["options"]], q["id"]
        elif q["type"] == "multi":
            assert prop["items"]["enum"] == [o["value"] for o in q["options"]], q["id"]
            assert prop.get("maxItems") == q.get("max_select"), q["id"]
        elif q["type"] == "scale":
            assert (prop["minimum"], prop["maximum"]) == (q["scale"]["min"], q["scale"]["max"])
        elif q["type"] == "text":
            assert prop["maxLength"] == q["max_length"]
        elif q["type"] == "contact":
            assert {f["id"]: f["max_length"] for f in q["fields"]} == {k: v["maxLength"] for k, v in prop["properties"].items()}
        elif q["type"] == "consent":
            assert prop == {"description": q["label"], "const": True}


def test_every_show_if_rule_is_enforced_by_the_schema():
    conds = ANSWERS["allOf"]
    for q in QUESTIONS:
        if q.get("show_if"):
            s = q["show_if"]
            assert {"if": {"required": [s["question"]], "properties": {s["question"]: {"enum": s["in"]}}}, "else": {"properties": {q["id"]: False}}} in conds, q["id"]


def _literal_values(ann) -> list:
    """Every Literal value inside an annotation like `list[Literal[...]] | None`."""
    if typing.get_origin(ann) is typing.Literal:
        return list(typing.get_args(ann))
    return [v for a in typing.get_args(ann) for v in _literal_values(a)]


def test_pydantic_mirror_matches_schema():
    assert set(FeedbackSubmission.model_fields) == set(SCHEMA["properties"])
    assert set(FeedbackAnswers.model_fields) == set(ANSWERS["properties"])
    assert {k for k, f in FeedbackAnswers.model_fields.items() if f.is_required()} == set(ANSWERS["required"])
    for name, prop in ANSWERS["properties"].items():
        ann = FeedbackAnswers.model_fields[name].annotation
        enum = prop.get("enum") or prop.get("items", {}).get("enum")
        if enum:
            assert _literal_values(ann) == enum, name


def test_typescript_types_match_schema():
    body = re.search(r"export interface FeedbackAnswers \{(.*?)\n\}", TS, re.S).group(1)
    assert set(re.findall(r"^\s+(\w+)\??:", body, re.M)) == set(ANSWERS["properties"])
    sub = re.search(r"export interface FeedbackSubmission \{(.*?)\n\}", TS, re.S).group(1)
    assert set(re.findall(r"^\s+(\w+)\??:", sub, re.M)) == set(SCHEMA["properties"])


def test_web_mock_form_is_an_exact_copy_of_config():
    assert json.loads((ROOT / "web" / "mocks" / "feedback_form.json").read_text()) == FORM, "cp config/feedback_form.json web/mocks/"


def _sub(**answers):
    return {"form_version": FORM["form_version"], "mode": "interview", "source": "test", "answers": {"a1_role": "owner", "a2_business": "fmcg_brand", "e4_consent": True, **answers}}


@pytest.mark.parametrize("doc", [
    _sub(),
    _sub(c0_seen_demo="no", d1_biggest_pain="x", e1_pilot="maybe", e3_contact={"name": "n"}),
    _sub(c0_seen_demo="yes_live", c1_usefulness=1, c2_most_valuable=["own_language"], c3_blockers=["cost", "other"], c3_blockers_other="x", c4_pay_model="monthly_per_store", c5_pay_amount="over_20k"),
])
def test_valid_submissions_pass_both_validators(doc):
    _validator().validate(doc)
    FeedbackSubmission.model_validate(doc)


@pytest.mark.parametrize("doc", [
    {k: v for k, v in _sub().items() if k != "mode"},
    _sub(e4_consent=False),
    _sub(c1_usefulness=3),                        # c0 unanswered: section C hidden
    _sub(c0_seen_demo="no", c4_pay_model="one_time"),
    _sub(c0_seen_demo="yes_live", c5_pay_amount="1k_5k"),
    _sub(e3_contact={"name": "n"}),               # e1 unanswered
    _sub(c1_usefulness=6, c0_seen_demo="yes_live"),
    _sub(b4_current_actions=[]),
])
def test_invalid_submissions_fail_the_schema(doc):
    assert not _validator().is_valid(doc)
