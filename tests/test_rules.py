from app.domains.meridian.rules import ParsedDoc, check, normalize_unit, post_process
from app.domains.meridian.schemas import LLMExtraction, MeridianFields, QuantityTotal


def doc(kind, qty=None, totals=()):
    ext = LLMExtraction(document_type=kind, fields=MeridianFields(total_quantity=qty),
                        quantity_totals=[QuantityTotal(value=v, unit=u) for v, u in totals])
    return post_process(ext)


def test_match_120():
    r = check([doc("commercial_invoice", 120, [(120, "CTNS")]), doc("packing_list", 120, [(120, "cartons")])])
    assert r.status == "Match"


def test_120_and_120_point_0_match():
    r = check([doc("commercial_invoice", "120.0", [("120.0", "ctns")]), doc("packing_list", 120, [(120, "CTN")])])
    assert r.status == "Match"


def test_thousands_separator():
    r = check([doc("commercial_invoice", "1,200", [("1,200", "PCS")]), doc("packing_list", 1200, [(1200, "pieces")])])
    assert r.status == "Match"


def test_mismatch_120_vs_118():
    r = check([doc("commercial_invoice", 120, [(120, "CTNS")]), doc("packing_list", 118, [(118, "CTNS")])])
    assert r.status == "Mismatch" and "118" in r.reason


def test_unit_clash_cartons_vs_pieces_no_pack_size_guess():
    r = check([doc("commercial_invoice", 1440, [(1440, "PCS")]), doc("packing_list", 120, [(120, "CTNS")])])
    assert r.status == "Mismatch" and "Units differ" in r.reason


def test_two_totals_compares_like_with_like():
    pl = doc("packing_list", None, [(50, "CARTONS"), (1200, "PCS")])
    assert pl.fields.total_quantity == 50  # documented: shipping-unit total wins the field
    r = check([doc("commercial_invoice", 1200, [(1200, "PCS")]), pl])
    assert r.status == "Match"


def test_item_rows_listed_with_the_total_are_ignored():
    pl = doc("packing_list", 205, [(101, "PKGS"), (104, "PKGS"), (205, "PKGS")])
    assert pl.fields.total_quantity == 205
    assert [(t.value, t.unit) for t in pl.totals] == [(205, "package")]


def test_item_rows_cannot_cause_a_false_mismatch():
    invoice = doc("commercial_invoice", 2400, [(1199, "PCS"), (1201, "PCS"), (2400, "PCS")])
    packing = doc("packing_list", 2400, [(1200, "PCS"), (1200, "PCS"), (2400, "PCS")])
    assert check([invoice, packing]).status == "Match"


def test_stated_total_wins_when_the_list_only_has_rows():
    assert doc("packing_list", 205, [(101, "PKGS"), (104, "PKGS")]).fields.total_quantity == 205


def test_two_units_stay_separate_and_shipping_unit_wins():
    pl = doc("packing_list", 1200, [(50, "CARTONS"), (1200, "PCS")])
    assert pl.fields.total_quantity == 50 and len(pl.totals) == 2


def test_weight_does_not_flip_status():
    a = doc("commercial_invoice", 75, [(75, "CTNS")])
    b = doc("packing_list", 75, [(75, "CTNS")])
    a.fields.total_weight_kg, b.fields.total_weight_kg = 520.0, 515.5
    assert check([a, b]).status == "Match"


def test_pounds_converted():
    ext = LLMExtraction(document_type="commercial_invoice",
                        fields=MeridianFields(total_quantity=120, total_weight_kg="1,897.0"), weight_unit="LB")
    assert post_process(ext).fields.total_weight_kg == 860.46


def test_incomplete_and_not_applicable():
    assert check([doc("commercial_invoice", 10, [(10, "CTNS")])]).status == "Incomplete"
    assert check([doc("packing_list", 10, [(10, "CTNS")])]).status == "Incomplete"
    assert check([doc("delivery_receipt", 10, [(10, "CTNS")])]).status == "Not applicable"


def test_missing_quantity_is_flagged():
    assert check([doc("commercial_invoice"), doc("packing_list", 5, [(5, "CTNS")])]).status == "Mismatch"


def test_unit_normalization():
    assert normalize_unit("CTNS") == normalize_unit("Cartons") == "carton"
    assert normalize_unit("pcs") == normalize_unit("Pieces") == "piece"


def test_reason_has_no_names():
    r = check([doc("commercial_invoice", 120, [(120, "CTNS")]), doc("packing_list", 118, [(118, "CTNS")])])
    assert "<" not in r.reason and "@" not in r.reason
