from typing import Annotated, Literal
from pydantic import Field
from ruleforge.domain.models import StrictModel
from ruleforge.rules.dsl import RuleDSL

class SourceSpan(StrictModel):
    id: str
    run_id: str
    role: Literal["armor_table", "light_armor", "ability_modifier"]
    json_pointer: str = Field(pattern="^/data/elements/[0-9]+/text$")
    page_pointer: str = Field(pattern="^/data/elements/[0-9]+/page_number$")
    physical_page: Annotated[int, Field(ge=1)]
    printed_page: str | None
    printed_page_pointer: str | None
    section: str
    quote: str = Field(min_length=1)
    quote_sha256: str = Field(pattern="^[a-f0-9]{64}$")
    element_id: str
    coordinates: list[float] | None = None

class RuleRecord(StrictModel):
    rule: RuleDSL
    sources: list[SourceSpan] = Field(min_length=3,max_length=3)
    review_status: Literal["draft","verified","rejected"] = "draft"

# The fixed three-source execution envelope remains backward compatible.
LeatherRuleRecord = RuleRecord
from ruleforge.rules.sources import SourceReference
from ruleforge.catalog.models import RuleRecord as NormalizedRuleRecord
