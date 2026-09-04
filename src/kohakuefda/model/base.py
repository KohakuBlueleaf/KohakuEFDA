"""Base model configuration shared by every domain object."""

from pydantic import BaseModel, ConfigDict


class EfdaModel(BaseModel):
    """Pydantic base: strict fields, arbitrary types allowed for ``Fraction``."""

    model_config = ConfigDict(arbitrary_types_allowed=True, extra="forbid")
