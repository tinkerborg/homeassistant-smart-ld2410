"""Entry filter: an entry must begin at the room's own entry gates (spec 24 §1).

A person walking in lights the near gates; activity originating beyond an
intervening wall physically cannot. Clearing this filter is also what earns an
occupancy its ownership, which the presence stages then hold the room on.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from ..roles import ADMIT, ROLE_ENTRY_FILTER, EntryVerdict, Stage
from ..types import RESULT_REJECTED_LEADING_EDGE

if TYPE_CHECKING:
    from ..context import DetectorContext


class LeadingEdge(Stage):
    """Refuses entry to a candidate whose leading gate is beyond ``lead_gate_max``."""

    __slots__ = ()

    role = ROLE_ENTRY_FILTER
    expects = ("run_score",)

    def accumulate(self, context: DetectorContext) -> None:
        """Nothing to accumulate: the leading edge is a shared statistic."""

    def verdict(self, context: DetectorContext) -> EntryVerdict:
        """Judge where the candidate's activity began."""
        lead_gate_max = self._config.lead_gate_max
        leading_gate = context.leading_gate
        if lead_gate_max >= 0 and (
            leading_gate is None or leading_gate > lead_gate_max
        ):
            return EntryVerdict(RESULT_REJECTED_LEADING_EDGE)
        return ADMIT
