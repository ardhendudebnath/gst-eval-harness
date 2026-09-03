import pytest

from harness.collect.openfoodfacts import (
    _clean_packaging,
    _clean_quantity,
    _dedupe_key,
    _describe,
    _out_of_scope,
)
from harness.schema import out_of_scope_term


# --- description assembly -------------------------------------------------


def test_brand_is_not_repeated_when_name_already_carries_it():
    assert _describe({"product_name": "Tata Salt", "brands": "Tata", "quantity": "1 kg"}) == (
        "Tata Salt, 1 kg"
    )


def test_brand_is_prepended_when_absent_from_name():
    assert _describe({"product_name": "Bourbon", "brands": "Britannia", "quantity": "50 g"}) == (
        "Britannia Bourbon, 50 g"
    )


def test_missing_product_name_yields_nothing():
    assert _describe({"product_name": "", "brands": "Tata"}) == ""


def test_container_word_is_kept_material_is_not():
    assert _describe(
        {"product_name": "Atta", "brands": "X", "quantity": "5 kg", "packaging": "Pouch"}
    ) == "X Atta, 5 kg, pouch"
    # "Plastic" is a material and "India" is dirty data; neither is a container.
    assert _describe(
        {"product_name": "Atta", "brands": "X", "quantity": "5 kg", "packaging": "Plastic"}
    ) == "X Atta, 5 kg"


# --- field cleaning -------------------------------------------------------


@pytest.mark.parametrize("raw", ["75", "1", "", None, "abc"])
def test_quantity_without_a_unit_is_dropped(raw):
    assert _clean_quantity(raw) == ""


@pytest.mark.parametrize("raw", ["1 kg", "250 ml", "45gm", "52.5 g", "6 pcs"])
def test_quantity_with_a_unit_is_kept(raw):
    assert _clean_quantity(raw) == raw


def test_packaging_handles_off_language_prefix_and_case():
    assert _clean_packaging("en:Bottle") == "bottle"
    assert _clean_packaging("Plastic, Pouch") == "pouch"
    assert _clean_packaging("India") == ""


# --- scope screening ------------------------------------------------------


def test_out_of_scope_family_is_caught_via_category_not_description():
    # A listing can name nothing excluded while its category does.
    product = {"product_name": "Old Monk 7 Year", "categories": "Rums, Spirits"}
    assert out_of_scope_term("Old Monk 7 Year, 750 ml") is None
    assert _out_of_scope("Old Monk 7 Year, 750 ml", product) is not None


def test_tobacco_is_now_in_scope():
    # Settled at 40%, biris 18%. The excise duty introduced alongside is a
    # separate levy and does not change which GST slab applies.
    assert out_of_scope_term("Gold Flake cigarette, pack of 20") is None
    assert out_of_scope_term("Biris, bundle of 25") is None


def test_aerated_drinks_are_now_in_scope():
    # Excluded until the Gazette showed Schedule VII never held them. They sit
    # in Schedule III at 40%, having moved off the now-abolished 28% slab,
    # which makes them unusually sharp stale-slab examples.
    product = {
        "product_name": "Thums up",
        "categories": "Carbonated waters, Colas, Sweetened beverages",
    }
    assert _out_of_scope("Thums up, 250 ml", product) is None


def test_cement_is_now_in_scope():
    # Schedule II, 18%, down from 28%.
    assert out_of_scope_term("Ambuja Cement OPC 53 grade, 50 kg bag") is None


def test_alcohol_is_out_of_scope():
    assert out_of_scope_term("Kingfisher beer 650 ml") == "beer"


def test_word_boundary_prevents_false_positives():
    # "rum" inside "rumali", "cola" inside "chocolate".
    assert out_of_scope_term("Rumali Roti 6 pcs") is None
    assert out_of_scope_term("Cadbury Dairy Milk chocolate 50 g") is None


@pytest.mark.parametrize(
    "text",
    ["Beers", "Wines", "Rums", "Liquors", "Vodkas"],
)
def test_plural_category_names_are_caught(text):
    # Catalogue categories are written in the plural, and a bare \b anchor
    # silently fails against every one of them.
    assert out_of_scope_term(text) is not None


def test_baking_soda_is_in_scope():
    # Bare "soda" is not a scope term precisely so this stays labellable.
    assert out_of_scope_term("Baking soda 100 g") is None


def test_in_scope_product_passes():
    assert _out_of_scope("Tata Salt, 1 kg", {"categories": "Table salts, Groceries"}) is None


# --- dedupe ---------------------------------------------------------------


def test_near_duplicates_share_a_key():
    assert _dedupe_key("Parle-G Biscuit, 45gm") == _dedupe_key("parle g biscuit 45gm")


def test_distinct_products_do_not_collide():
    assert _dedupe_key("Tata Salt, 1 kg") != _dedupe_key("Tata Salt, 2 kg")
