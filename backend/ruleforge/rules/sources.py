from typing import Annotated, Literal
from pydantic import Field, model_validator
from ruleforge.domain.models import StrictModel

Ruleset = Literal["srd-5.1"]
ReviewStatus = Literal["review_required", "approved", "rejected"]
ExecutionStatus = Literal["executable", "partially_executable", "reference_only", "unsupported"]
ValidationStatus = Literal["extracted", "validated", "review_required", "rejected"]
Identifier = Annotated[str, Field(min_length=1, max_length=200, pattern=r"^[a-zA-Z0-9_.:-]+$")]
Pointer = Annotated[str, Field(pattern=r"^(?:/(?:[^~]|~[01])*)*$", max_length=2000)]

class TableLocation(StrictModel):
    # Zero-based logical grid. Original cells (including merged ones) retain their origin.
    row: Annotated[int, Field(ge=0)]
    column: Annotated[int, Field(ge=0)]
    text: str

class SourceReference(StrictModel):
    id: Identifier
    ruleset: Ruleset = "srd-5.1"
    document_id: str = Field(pattern="^[a-f0-9]{64}$")
    run_id: Identifier
    role: str = Field(min_length=1,max_length=100,pattern=r"^[a-z][a-z0-9_.-]*$")
    fragment_type: str = Field(min_length=1,max_length=100)
    json_pointer: Pointer
    element_pointer: Pointer
    element_id: str = Field(min_length=1)
    section_hierarchy: list[str] = Field(default_factory=list,max_length=50)
    page_pointer: Pointer | None = None
    physical_page: Annotated[int, Field(ge=1)] | None = None
    printed_page: str | None = None
    printed_page_pointer: Pointer | None = None
    table_location: TableLocation | None = None
    quote: str = Field(min_length=1)
    quote_sha256: str = Field(pattern="^[a-f0-9]{64}$")
    coordinates: list[float] | None = None
    review_status: ReviewStatus = "review_required"
    schema_version: Literal["1"] = "1"

    @model_validator(mode="after")
    def known_pages_need_evidence(self):
        if (self.page_pointer is None) != (self.physical_page is None):
            raise ValueError("physical page and pointer must be provided together")
        if (self.printed_page is None) != (self.printed_page_pointer is None):
            raise ValueError("printed page and pointer must be provided together")
        return self
