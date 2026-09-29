#!/usr/bin/env python3
"""Beacon's major peak / valley pair, ported from the Pine v4 source
(claude/raw/w15_0022_beacon_source_20260929.pine) exactly as registered in Amendment A. Used only
by the reported variant "MR-Beacon".

Pine semantics kept: a comparison with na is false; `var` values start at 0.0; `x[1]` is the value
committed on the previous bar; new_peak / new_valley are per-bar flags. Everything at bar t uses
U/L at bars <= t (a minor peak is confirmed one bar late, U[t] < U[t-1], so nothing looks ahead).
"""
from __future__ import annotations

import numpy as np


def beacon_pair(U: np.ndarray, L: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    n = len(U)
    pm = np.zeros(n)
    vm = np.zeros(n)
    peak_minor = valley_minor = 0.0
    peak_major = valley_major = 0.0
    for t in range(n):
        if t >= 2:
            u0, u1, u2 = U[t], U[t - 1], U[t - 2]
            l0, l1, l2 = L[t], L[t - 1], L[t - 2]
            if u1 > u2 and u0 < u1:
                peak_minor = u1
            if l1 < l2 and l0 > l1:
                valley_minor = l1
        new_peak = peak_minor > peak_major          # peak_major is still the previous bar's value ([1])
        new_valley = valley_minor < valley_major
        if new_peak or new_valley:                   # Pine: both majors take the current minors
            peak_major, valley_major = peak_minor, valley_minor
        pm[t], vm[t] = peak_major, valley_major
    return pm, vm
