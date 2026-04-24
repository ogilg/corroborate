"""Output renderers: turn a list of Claims into audit/reference artifacts."""

from corroborate.renderers.latex import name_to_macro, write_numbers_tex
from corroborate.renderers.markdown import write_claims_md

__all__ = ["name_to_macro", "write_numbers_tex", "write_claims_md"]
