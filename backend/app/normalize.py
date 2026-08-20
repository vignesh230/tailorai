"""Keyword canonicalization applied before hard-keyword matching. A small,
hand-picked alias table maps common abbreviations/synonyms to one canonical
form (e.g. "k8s" and "kubernetes" must count as the same keyword), so a
resume or JD that spells a skill differently isn't scored as a mismatch.
Deliberately small -- add an entry as new equivalences come up."""

ALIASES: dict[str, str] = {
    "k8s": "kubernetes",
    "js": "javascript",
    "ts": "typescript",
    "postgres": "postgresql",
    "psql": "postgresql",
    "py": "python",
    "golang": "go",
    "reactjs": "react",
    "nodejs": "node",
    "vuejs": "vue",
    "mongo": "mongodb",
    "tf": "terraform",
    "gcp": "googlecloud",
    "csharp": "c#",
    "cpp": "c++",
}


CANONICAL_FORMS: set[str] = set(ALIASES.values())


def canonicalize_word(word: str) -> str:
    """Lowercase a single word and map it through the alias table if known.
    Unknown words are returned lowercased, unchanged -- callers apply their
    own stemming/suffix-handling on top of this."""
    return ALIASES.get(word.lower(), word.lower())
