from app.normalize import ALIASES, CANONICAL_FORMS, canonicalize_word


def test_canonicalize_word_maps_known_aliases():
    assert canonicalize_word("k8s") == "kubernetes"
    assert canonicalize_word("K8s") == "kubernetes"
    assert canonicalize_word("JS") == "javascript"
    assert canonicalize_word("postgres") == "postgresql"


def test_canonicalize_word_passes_through_unknown_words_lowercased():
    assert canonicalize_word("Python") == "python"
    assert canonicalize_word("Docker") == "docker"


def test_aliases_table_has_at_least_fifteen_entries():
    assert len(ALIASES) >= 15


def test_alias_targets_are_not_further_aliased():
    """An alias's canonical form shouldn't itself need remapping -- otherwise
    two skills could collapse into each other transitively by accident."""
    for canonical in ALIASES.values():
        assert canonical not in ALIASES


def test_canonical_forms_set_matches_alias_values():
    assert CANONICAL_FORMS == set(ALIASES.values())
