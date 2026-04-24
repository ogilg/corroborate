"""Core round-trip + collision + renderer tests."""

from __future__ import annotations

import json

import pytest

from corroborate import (
    Claim,
    ClaimSet,
    load_all,
    name_to_macro,
    write_claims_md,
    write_numbers_tex,
)


def test_register_returns_value(tmp_path):
    claims = ClaimSet(source="test.py")
    v = claims.register("x", 0.5, "stmt.", used_in=["abstract"])
    assert v == 0.5
    assert len(claims.claims) == 1
    c = claims.claims[0]
    assert c.name == "x"
    assert c.source == "test.py"
    assert c.computed_at  # non-empty


def test_duplicate_name_raises():
    claims = ClaimSet(source="test.py")
    claims.register("dup", 1, "a.")
    with pytest.raises(ValueError, match="Duplicate"):
        claims.register("dup", 2, "b.")


def test_save_and_load_roundtrip(tmp_path):
    cs = ClaimSet(source="test.py")
    cs.register("alpha", 0.1, "A.", used_in=["fig:foo"],
                data_paths=["data/a.json"], derivation="read foo")
    cs.register("beta", 2, "B.", source="manual: note")
    cs.save(tmp_path / "sc.json")

    claims = load_all(tmp_path)
    assert len(claims) == 2
    names = {c.name for c in claims}
    assert names == {"alpha", "beta"}
    alpha = next(c for c in claims if c.name == "alpha")
    assert alpha.data_paths == ("data/a.json",)
    assert alpha.derivation == "read foo"
    beta = next(c for c in claims if c.name == "beta")
    assert beta.source == "manual: note"


def test_cross_sidecar_name_collision(tmp_path):
    a = ClaimSet(source="a.py")
    a.register("same", 1, "A.")
    a.save(tmp_path / "a.json")
    b = ClaimSet(source="b.py")
    b.register("same", 2, "B.")
    b.save(tmp_path / "b.json")
    with pytest.raises(ValueError, match="collision"):
        load_all(tmp_path)


def test_name_to_macro_rules():
    assert name_to_macro("Gemma probe heldout r") == "gemmaProbeHeldoutR"
    assert name_to_macro("CREAK truth Cohen's d") == "creakTruthCohensD"
    assert name_to_macro("phase1 baseline") == "phaseoneBaseline"
    assert name_to_macro("c=+0.03") == "cZeroZerothree"


def test_macro_collision_raises(tmp_path):
    # Two distinct names that slug to the same macro.
    cs = ClaimSet(source="t.py")
    cs.register("Foo bar", 1, "A.")
    cs.register("Foo-bar!", 2, "B.")
    cs.save(tmp_path / "t.json")
    claims = load_all(tmp_path)
    with pytest.raises(ValueError, match="collision"):
        write_numbers_tex(claims, tmp_path / "out.tex")


def test_numbers_tex_content(tmp_path):
    cs = ClaimSet(source="t.py")
    cs.register("Alpha one", 0.864, "A.", used_in=["fig:x"])
    cs.save(tmp_path / "t.json")
    claims = load_all(tmp_path)
    out = tmp_path / "numbers.tex"
    write_numbers_tex(claims, out)
    body = out.read_text()
    assert "\\newcommand{\\alphaOne}{0.864}" in body


def test_claims_md_content(tmp_path):
    cs = ClaimSet(source="t.py")
    cs.register("Alpha", 0.5, "Some statement.", used_in=["abstract"],
                data_paths=["d.json"], derivation="read x")
    cs.save(tmp_path / "t.json")
    claims = load_all(tmp_path)
    out = tmp_path / "claims.md"
    write_claims_md(claims, out, title="Test")
    body = out.read_text()
    assert "# Test" in body
    assert "`Alpha`" in body
    assert "Some statement." in body
    assert "read x" in body
    assert "d.json" in body


# -----------------------------------------------------------------------------
# Structured values (row dicts and table dict-of-dicts).
# -----------------------------------------------------------------------------


def test_register_accepts_row_dict():
    cs = ClaimSet(source="t.py")
    cs.register("Gemma probe metrics", {"held_out_r": 0.905, "cross_topic_r": 0.756}, "stmt.")
    assert cs.claims[0].value == {"held_out_r": 0.905, "cross_topic_r": 0.756}


def test_register_accepts_table_dict():
    cs = ClaimSet(source="t.py")
    cs.register(
        "Character probe",
        {
            "goodness": {"baseline_r": 0.376, "probe_r": 0.671, "best_layer": 20},
            "humor":    {"baseline_r": 0.395, "probe_r": 0.687, "best_layer": 16},
        },
        "stmt.",
    )
    assert cs.claims[0].value["goodness"]["baseline_r"] == 0.376
    assert cs.claims[0].value["humor"]["best_layer"] == 16


def test_register_rejects_depth_three():
    cs = ClaimSet(source="t.py")
    with pytest.raises(TypeError, match="deeper than 2"):
        cs.register("Nested", {"a": {"b": {"c": 1}}}, "stmt.")


def test_register_rejects_bare_list():
    cs = ClaimSet(source="t.py")
    with pytest.raises(TypeError, match="scalar"):
        cs.register("Listy", [1, 2, 3], "stmt.")


def test_register_rejects_non_str_keys():
    cs = ClaimSet(source="t.py")
    with pytest.raises(TypeError, match="keys must be str"):
        cs.register("Bad", {1: 0.5}, "stmt.")


def test_register_rejects_empty_dict():
    cs = ClaimSet(source="t.py")
    with pytest.raises(ValueError, match="empty"):
        cs.register("Empty", {}, "stmt.")


def test_numbers_tex_flattens_row(tmp_path):
    cs = ClaimSet(source="t.py")
    cs.register("Gemma probe metrics",
                {"held_out_r": 0.905, "cross_topic_r": 0.756},
                "stmt.")
    cs.save(tmp_path / "t.json")
    claims = load_all(tmp_path)
    out = tmp_path / "numbers.tex"
    write_numbers_tex(claims, out)
    body = out.read_text()
    assert "\\newcommand{\\gemmaProbeMetricsHeldOutR}{0.905}" in body
    assert "\\newcommand{\\gemmaProbeMetricsCrossTopicR}{0.756}" in body


def test_numbers_tex_flattens_table(tmp_path):
    cs = ClaimSet(source="t.py")
    cs.register(
        "Character probe",
        {
            "goodness": {"baseline_r": 0.376, "probe_r": 0.671},
            "humor":    {"baseline_r": 0.395, "probe_r": 0.687},
        },
        "stmt.",
    )
    cs.save(tmp_path / "t.json")
    claims = load_all(tmp_path)
    out = tmp_path / "numbers.tex"
    write_numbers_tex(claims, out)
    body = out.read_text()
    assert "\\newcommand{\\characterProbeGoodnessBaselineR}{0.376}" in body
    assert "\\newcommand{\\characterProbeGoodnessProbeR}{0.671}" in body
    assert "\\newcommand{\\characterProbeHumorBaselineR}{0.395}" in body
    assert "\\newcommand{\\characterProbeHumorProbeR}{0.687}" in body


def test_numbers_tex_cell_collides_with_scalar(tmp_path):
    cs = ClaimSet(source="t.py")
    cs.register("Gemma probe metrics held out r", 0.9, "scalar.")
    cs.register("Gemma probe metrics", {"held_out_r": 0.9}, "row.")
    cs.save(tmp_path / "t.json")
    claims = load_all(tmp_path)
    with pytest.raises(ValueError, match="collision"):
        write_numbers_tex(claims, tmp_path / "out.tex")


def test_claims_md_renders_table_inline(tmp_path):
    cs = ClaimSet(source="t.py")
    cs.register(
        "Character probe",
        {
            "goodness": {"baseline_r": 0.376, "probe_r": 0.671},
            "humor":    {"baseline_r": 0.395, "probe_r": 0.687},
        },
        "Per-character probe r.",
    )
    cs.save(tmp_path / "t.json")
    claims = load_all(tmp_path)
    out = tmp_path / "claims.md"
    write_claims_md(claims, out)
    body = out.read_text()
    # one row for the claim (header + separator + 1 claim row = 3 table lines)
    assert body.count("\n|") <= 4
    assert "**goodness**: baseline_r=0.376, probe_r=0.671" in body
    assert "**humor**: baseline_r=0.395, probe_r=0.687" in body


def test_roundtrip_structured_value(tmp_path):
    cs = ClaimSet(source="t.py")
    table = {
        "goodness": {"baseline_r": 0.376, "best_layer": 20},
        "humor":    {"baseline_r": 0.395, "best_layer": 16},
    }
    cs.register("Character probe", table, "stmt.")
    cs.save(tmp_path / "t.json")
    claims = load_all(tmp_path)
    assert len(claims) == 1
    assert claims[0].value == table


def test_audit_detects_cell_drift():
    # Claim-level equality: changing a cell flips value inequality.
    c1 = Claim(name="T", value={"a": {"x": 1}}, statement="s.", source="t.py")
    c2 = Claim(name="T", value={"a": {"x": 2}}, statement="s.", source="t.py")
    assert c1.value != c2.value
