"""Output renderers: turn a list of Claims into audit/reference artifacts."""

from vernier.renderers.latex import name_to_macro, write_numbers_tex
from vernier.renderers.markdown import write_claims_md

__all__ = ["name_to_macro", "write_numbers_tex", "write_claims_md"]
