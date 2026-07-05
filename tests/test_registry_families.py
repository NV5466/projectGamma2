from gamma_app.registry import ALLOWED_FAMILIES, is_mechanical_only_id, read_seed_registry_entries, validate_registry_families


def test_seed_registry_uses_only_allowed_electrical_families():
    errors = validate_registry_families("seed_registry.yaml")
    assert errors == []
    families = {entry["family"] for entry in read_seed_registry_entries("seed_registry.yaml")}
    assert families <= ALLOWED_FAMILIES


def test_mechanical_only_names_are_blocked():
    assert is_mechanical_only_id("unspecified_bearing_fault")
    assert is_mechanical_only_id("broken_rotor_bar_sidebands")
    assert not is_mechanical_only_id("high_speed_input_bounce")
