"""Battery chemistry domain values, independent of charge programs."""

from enum import Enum


class ChemistryProfile(str, Enum):
    AGM = "AGM"
    EFB = "EFB"
    CALCIUM = "CALCIUM"
