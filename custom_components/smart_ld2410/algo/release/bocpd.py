"""Bayesian online changepoint detection over the still channel (Adams & MacKay).

Each run length carries a Normal-Gamma posterior per gate, whose prior is the
learned floor and spread. The run-length posterior is truncated at
``MAX_RUN_S``; a change is declared on the rising edge of the probability that
the current run began within the last ``RECENT_RUN_S``.
"""

from __future__ import annotations

from collections.abc import Sequence
from math import exp, lgamma, log, log1p, pi

TICK_S = 0.1
"""Spacing of the sample-and-hold grid the detector steps on."""

MAX_RUN_S = 60.0
RECENT_RUN_S = 2.0
DECLARE_MASS = 0.5
KAPPA0 = 0.01
ALPHA0 = 1.0

_MAX_RUN = round(MAX_RUN_S / TICK_S)
_RECENT = round(RECENT_RUN_S / TICK_S)


def _student_norm(nu: float) -> float:
    return lgamma((nu + 1) / 2) - lgamma(nu / 2) - 0.5 * log(nu * pi)


_KAPPA = [KAPPA0 + run + 1.0 for run in range(_MAX_RUN)]
_ALPHA = [ALPHA0 + (run + 1.0) / 2.0 for run in range(_MAX_RUN)]
_NU = [2.0 * alpha for alpha in _ALPHA]
_SCALE = [(kappa + 1.0) / (alpha * kappa) for kappa, alpha in zip(_KAPPA, _ALPHA)]
_LOG_NORM = [_student_norm(nu) for nu in _NU]
_HALF_NU1 = [(nu + 1) / 2 for nu in _NU]
_PRIOR_NU = 2.0 * ALPHA0
_PRIOR_NORM = _student_norm(_PRIOR_NU)
_PRIOR_SCALE = (KAPPA0 + 1.0) / (ALPHA0 * KAPPA0)


def _log_sum_exp(values: Sequence[float]) -> float:
    top = max(values)
    return top + log(sum(exp(value - top) for value in values))


class RunLengthPosterior:
    """The run-length posterior and the per-run Normal-Gamma statistics."""

    __slots__ = ("_above", "_log_p", "_log_stay", "_log_hazard", "_mu", "_beta", "_ticks")

    def __init__(self, hazard_s: float) -> None:
        """Start with no observations, at a constant hazard of one tick per ``hazard_s``."""
        self._log_hazard = log(TICK_S / hazard_s)
        self._log_stay = log1p(-TICK_S / hazard_s)
        self._log_p: list[float] = []
        self._mu: list[list[float]] = []
        self._beta: list[list[float]] = []
        self._above = False
        self._ticks = 0

    def step(
        self,
        observed: Sequence[float],
        floor: Sequence[float],
        spread: Sequence[float],
    ) -> int | None:
        """Fold one tick; return how many ticks ago a newly declared change began."""
        runs = len(self._log_p)
        grow = [0.0] * runs
        fresh = 0.0
        mu_next: list[list[float]] = []
        beta_next: list[list[float]] = []
        for dim, x in enumerate(observed):
            mu0 = floor[dim]
            beta0 = ALPHA0 * spread[dim] ** 2
            prior_s2 = beta0 * _PRIOR_SCALE
            fresh += _PRIOR_NORM - 0.5 * log(prior_s2) - (_PRIOR_NU + 1) / 2 * log1p(
                (x - mu0) ** 2 / (_PRIOR_NU * prior_s2)
            )
            if runs:
                mus = self._mu[dim]
                betas = self._beta[dim]
                for run, (mu, beta) in enumerate(zip(mus, betas)):
                    s2 = beta * _SCALE[run]
                    grow[run] += (
                        _LOG_NORM[run]
                        - 0.5 * log(s2)
                        - _HALF_NU1[run] * log1p((x - mu) ** 2 / (_NU[run] * s2))
                    )
                mu_next.append(
                    [(KAPPA0 * mu0 + x) / (KAPPA0 + 1.0)]
                    + [(k * mu + x) / (k + 1.0) for mu, k in zip(mus, _KAPPA)]
                )
                beta_next.append(
                    [beta0 + KAPPA0 * (x - mu0) ** 2 / (2 * (KAPPA0 + 1.0))]
                    + [
                        beta + k * (x - mu) ** 2 / (2 * (k + 1.0))
                        for mu, beta, k in zip(mus, betas, _KAPPA)
                    ]
                )
            else:
                mu_next.append([(KAPPA0 * mu0 + x) / (KAPPA0 + 1.0)])
                beta_next.append([beta0 + KAPPA0 * (x - mu0) ** 2 / (2 * (KAPPA0 + 1.0))])
        joint = [self._log_hazard + fresh] + [
            self._log_stay + log_p + g for log_p, g in zip(self._log_p, grow)
        ]
        if len(joint) > _MAX_RUN:
            joint[_MAX_RUN - 1] = _log_sum_exp(joint[_MAX_RUN - 1 :])
            del joint[_MAX_RUN:]
            for column in (*mu_next, *beta_next):
                del column[_MAX_RUN:]
        total = _log_sum_exp(joint)
        self._log_p = [value - total for value in joint]
        self._mu = mu_next
        self._beta = beta_next
        recent = self._log_p[:_RECENT]
        mass = sum(exp(value) for value in recent)
        declared = None
        if mass > DECLARE_MASS and not self._above and self._ticks >= _RECENT:
            declared = recent.index(max(recent))
        self._above = mass > DECLARE_MASS
        self._ticks += 1
        return declared
