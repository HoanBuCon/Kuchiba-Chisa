"""Page families: declarative rules that decide whether and how a wiki page is ingested."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass, replace


@dataclass(frozen=True)
class FamilyRule:
    """A page belongs to the first rule whose title suffix, category or explicit title matches."""

    name: str
    tier: str
    suffixes: tuple[str, ...] = ()
    categories: tuple[str, ...] = ()
    titles: tuple[str, ...] = ()
    # Parents whose direct subcategories also belong to the family (resolved at sync time).
    subcategory_parents: tuple[str, ...] = ()

    def matches(self, title: str, categories: frozenset[str]) -> bool:
        if title in self.titles:
            return True
        if any(title.endswith(f"/{suffix}") for suffix in self.suffixes):
            return True
        return bool(categories.intersection(self.categories))


@dataclass(frozen=True)
class FamilyCatalog:
    rules: tuple[FamilyRule, ...]
    excluded_suffixes: tuple[str, ...] = ()
    enabled_tiers: frozenset[str] = frozenset({"A"})

    def with_subcategories(self, subcategories: Mapping[str, Iterable[str]]) -> FamilyCatalog:
        """Expand each rule's categories with the listed subcategories of its parents."""
        rules = tuple(
            replace(
                rule,
                categories=(
                    *rule.categories,
                    *(
                        child
                        for parent in rule.subcategory_parents
                        for child in subcategories.get(parent, ())
                    ),
                ),
            )
            for rule in self.rules
        )
        return replace(self, rules=rules)

    def classify(self, title: str, categories: Iterable[str]) -> FamilyRule | None:
        """Return the owning family, or None when the page is outside the enabled text tiers."""
        if any(title.endswith(f"/{suffix}") for suffix in self.excluded_suffixes):
            return None
        names = frozenset(category.removeprefix("Category:") for category in categories)
        for rule in self.rules:
            if rule.tier in self.enabled_tiers and rule.matches(title, names):
                return rule
        return None
