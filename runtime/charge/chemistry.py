"""Battery chemistry mapping and domain values, independent of programs."""

from enum import Enum
from typing import Union


class ChemistryProfile(str, Enum):
    AGM = "AGM"
    EFB = "EFB"
    CALCIUM = "CALCIUM"


class ProductionChemistry(str, Enum):
    """Names used by the V1/V2 production boundary."""

    CA_CA = "CA_CA"
    FLOODED = "FLOODED"
    CUSTOM = "CUSTOM"
    AGM = "AGM"
    EFB = "EFB"


PRODUCTION_TO_V3 = {
    ProductionChemistry.CA_CA: ChemistryProfile.CALCIUM,
    ProductionChemistry.FLOODED: ChemistryProfile.CALCIUM,
    ProductionChemistry.CUSTOM: ChemistryProfile.CALCIUM,
    ProductionChemistry.AGM: ChemistryProfile.AGM,
    ProductionChemistry.EFB: ChemistryProfile.EFB,
}


def map_production_chemistry(value: Union[ProductionChemistry, str]) -> ChemistryProfile:
    """Convert an explicit production label at the domain boundary.

    Unknown labels fail closed; spelling variants are normalized only at this
    boundary and are never compared as unrelated raw strings downstream.
    """

    if isinstance(value, ProductionChemistry):
        key = value
    else:
        normalized = str(value).strip().upper().replace("/", "_").replace("-", "_")
        aliases = {"CA": "CA_CA", "CALCIUM": "CA_CA"}
        key = ProductionChemistry(aliases.get(normalized, normalized))
    return PRODUCTION_TO_V3[key]
