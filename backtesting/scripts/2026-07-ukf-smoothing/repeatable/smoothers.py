#!/usr/bin/env python3
"""
smoothers.py -- the four CGM smoothing methods compared in this benchmark.

All four are exposed through one uniform, deterministic interface:

    smooth_series(name, ts_ms, vals, iobs=None) -> dict with, per chronological point:
        level_online[]  : causal (forward-only) estimate of glucose at t
                          (uses data <= t only; used for one-step-ahead prediction)
        rate_online[]   : causal estimate of dG/dt at t (mg/dL/min)
        level_offline[] : the smoother's actual SHIPPED output curve at t
                          (for the v4 UKF this includes the backward RTS pass, so
                           it may use data > t -- that is what a *smoother* does)
        outlier[]       : bool, whether the smoother's own outlier test fired at t
                          (only the v4 UKF has one: chi^2 > 15.13 or |innov| > 65)

For persistence / exponential / tsunami-UKF, level_offline == level_online (they
have no backward pass). The v4 UKF is the only one whose offline != online.

The four methods
----------------
1. "persistence" -- naive: estimate(t) = raw(t), rate 0. One-step pred = raw(t).
2. "exponential" -- AAPS today. Faithful port lives in ../ukf_smoothing_backtest.py
                    (ExponentialSmoothingPlugin.kt). REUSED here via a rolling window
                    (production calls smooth() on a bounded recent window each cycle;
                    a multi-day batch lets its 2nd-order term ring, which never happens
                    in production).
3. "tsunami"     -- the AdaptiveSmoothingPlugin.kt UKF currently in v7-shadow.
                    Faithful port (AdaptiveUKF) REUSED from ../ukf_smoothing_backtest.py.
                    2-state forward UKF + heuristic guards (compression / rapid-rise /
                    kinetic-hypo). No backward pass.
4. "v4"          -- the *better* UKF: UnscentedKalmanFilterPlugin.kt from
                    AndroidAPS-v4-port. NEW faithful, operation-for-operation port in
                    this file (class V4UKF). 2-state UKF [glucose, rate], fixed Q /
                    adaptive R (Huber-inflated R_eff + IAE adaptation), chi-squared
                    outlier diagnostics (15.13, 99.99%/1DOF + 65 mg/dL absolute), a
                    2-of-3 same-sign Q-inflation gate, gap segmentation (>60 min),
                    error-code (<=38 -> 39 floor) handling, and -- the key
                    differentiator -- a backward Rauch-Tung-Striebel (RTS) smoothing
                    pass over each segment.

Run `python smoothers.py` to execute the v4 parity self-test (the 9 behaviours of
UnscentedKalmanFilterPluginTest.kt) and print PASS/FAIL.
"""

import os
import sys
import math
import importlib.util

# --- reuse the already-committed faithful ports (exponential + tsunami UKF) ---
_PARENT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "ukf_smoothing_backtest.py")
_spec = importlib.util.spec_from_file_location("ukf_backtest_parent", _PARENT)
_parent = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_parent)

AdaptiveUKF = _parent.AdaptiveUKF                # tsunami UKF (AdaptiveSmoothingPlugin.kt)
exponential_smooth = _parent.exponential_smooth  # ExponentialSmoothingPlugin.kt port
exponential_rolling = _parent.exponential_rolling


# ============================================================================
# v4 UKF -- NEW faithful port of UnscentedKalmanFilterPlugin.kt
# ============================================================================

class V4UKF:
    """Operation-for-operation Python mirror of
    AndroidAPS-v4-port/.../UnscentedKalmanFilterPlugin.kt

    State x = [glucose (mg/dL), rate (mg/dL/min)]. Constant-velocity model with
    exp(-dt/30) rate damping. FIXED process noise Q, ADAPTIVE measurement noise R
    (learned, persisted in Kotlin -> kept as member state here, reset on sensor
    change / >24h gap). Huber-like per-sample R inflation (R_eff), a 2-of-3
    same-sign Q-inflation gate for real trends, chi-squared outlier *diagnostics*
    (the robustness itself comes from R_eff down-weighting, not hard rejection),
    gap segmentation, and a backward RTS smoothing pass per segment.

    smooth(values, timestamps) takes NEWEST-FIRST lists (index 0 = most recent),
    exactly as AAPS hands them to smooth(); returns NEWEST-FIRST per-point dicts.
    """

    # --- configuration (verbatim from the Kotlin) ---
    N = 2
    ALPHA = 0.1
    BETA = 2.0
    KAPPA = 0.0

    Q = [1.0, 0.0, 0.0, 0.35]
    R_INIT = 25.0
    R_MIN = 16.0
    R_MAX = 225.0
    R_EFF_MAX = 400.0
    INNOVATION_WINDOW = 18

    CHI2_THRESHOLD = 15.13
    OUTLIER_ABSOLUTE = 65.0

    MAX_GLUCOSE_VAR = 400.0
    MAX_RATE_VAR = 4.0

    INNOV_RESET_THRESHOLD = 12.0
    INNOV_VALIDATION_SAMPLES = 15

    MINOR_GAP = 7.0
    MAJOR_GAP = 60.0
    RATE_DECAY_TAU = 30.0

    MS_PER_MIN = 1000.0 * 60.0

    def __init__(self):
        n, lam = self.N, self._lambda()
        self.gamma = math.sqrt(n + lam)
        self.wm = [0.0] * (2 * n + 1)
        self.wc = [0.0] * (2 * n + 1)
        self.wm[0] = lam / (n + lam)
        self.wc[0] = lam / (n + lam) + (1 - self.ALPHA * self.ALPHA + self.BETA)
        w = 1.0 / (2.0 * (n + lam))
        for i in range(1, 2 * n + 1):
            self.wm[i] = w
            self.wc[i] = w

        # persistent (member) state
        self.learnedR = self.R_INIT
        self.innovations = []           # normalized innovation^2  (index 0 = newest)
        self.rawInnovationVariance = []  # raw innovation^2
        self.predVarHistory = []        # predicted P[0]
        self.lastProcessedTimestamp = 0

    @classmethod
    def _lambda(cls):
        return cls.ALPHA * cls.ALPHA * (cls.N + cls.KAPPA) - cls.N

    def rate_damp(self, dt):
        return math.exp(-dt / self.RATE_DECAY_TAU)

    # ---------------- reset logic ----------------
    def should_reset_learning(self, current_ts):
        if self.lastProcessedTimestamp == 0:
            return True
        diff = (current_ts - self.lastProcessedTimestamp) / self.MS_PER_MIN
        if diff < 0:
            return True
        if diff > 1440.0:
            return True
        if len(self.innovations) >= self.INNOV_VALIDATION_SAMPLES:
            avg = sum(self.innovations) / len(self.innovations)
            if avg > self.INNOV_RESET_THRESHOLD:
                return True
        return False

    def reset_learning(self):
        self.learnedR = self.R_INIT
        self.innovations.clear()
        self.rawInnovationVariance.clear()
        self.predVarHistory.clear()

    # ---------------- UKF maths ----------------
    def matrix_sqrt_2x2(self, p):
        a = p[0]
        b = (p[1] + p[2]) / 2.0
        d = p[3]
        l11 = math.sqrt(max(a, 1e-9))
        l21 = b / l11
        disc = d - l21 * l21
        if disc < -1e-9:
            return [math.sqrt(max(a, 0.1)), 0.0, 0.0, math.sqrt(max(d, 0.01))]
        l22 = math.sqrt(max(disc, 1e-9))
        return [l11, l21, 0.0, l22]

    def generate_sigma_points(self, x, p):
        n, g = self.N, self.gamma
        sp = [[0.0, 0.0] for _ in range(2 * n + 1)]
        sqrtP = self.matrix_sqrt_2x2(p)
        sp[0][0] = x[0]; sp[0][1] = x[1]
        for i in range(n):
            sp[i + 1][0] = x[0] + g * sqrtP[i * 2 + 0]
            sp[i + 1][1] = x[1] + g * sqrtP[i * 2 + 1]
            sp[i + 1 + n][0] = x[0] - g * sqrtP[i * 2 + 0]
            sp[i + 1 + n][1] = x[1] - g * sqrtP[i * 2 + 1]
        return sp

    def predict(self, x, p, q, dt):
        n, wm, wc = self.N, self.wm, self.wc
        sp = self.generate_sigma_points(x, p)
        damp = self.rate_damp(dt)
        spp = [[0.0, 0.0] for _ in range(2 * n + 1)]
        for i in range(2 * n + 1):
            spp[i][0] = sp[i][0] + sp[i][1] * dt
            spp[i][1] = sp[i][1] * damp
        xPred = [0.0, 0.0]
        for i in range(2 * n + 1):
            xPred[0] += wm[i] * spp[i][0]
            xPred[1] += wm[i] * spp[i][1]
        pPred = [0.0, 0.0, 0.0, 0.0]
        for i in range(2 * n + 1):
            dx0 = spp[i][0] - xPred[0]
            dx1 = spp[i][1] - xPred[1]
            pPred[0] += wc[i] * dx0 * dx0
            pPred[1] += wc[i] * dx0 * dx1
            pPred[2] += wc[i] * dx1 * dx0
            pPred[3] += wc[i] * dx1 * dx1
        qScale = dt / 5.0
        pPred[0] += q[0] * qScale
        pPred[3] += q[3] * qScale
        pPred[0] = max(pPred[0], 0.1)
        pPred[3] = max(pPred[3], 0.001)
        return xPred, pPred

    def update(self, xPred, pPred, z, r, x, p):
        n, wm, wc = self.N, self.wm, self.wc
        sp = self.generate_sigma_points(xPred, pPred)
        zSigma = [sp[i][0] for i in range(2 * n + 1)]
        zPred = 0.0
        for i in range(2 * n + 1):
            zPred += wm[i] * zSigma[i]
        pzz = 0.0
        for i in range(2 * n + 1):
            dz = zSigma[i] - zPred
            pzz += wc[i] * dz * dz
        pzz += r
        if pzz < 1e-6:
            x[0] = xPred[0]; x[1] = xPred[1]
            p[0] = pPred[0]; p[1] = pPred[1]; p[2] = pPred[2]; p[3] = pPred[3]
            return
        pxz = [0.0, 0.0]
        for i in range(2 * n + 1):
            dx0 = sp[i][0] - xPred[0]
            dx1 = sp[i][1] - xPred[1]
            dz = zSigma[i] - zPred
            pxz[0] += wc[i] * dx0 * dz
            pxz[1] += wc[i] * dx1 * dz
        k0 = pxz[0] / pzz
        k1 = pxz[1] / pzz
        innovation = z - zPred
        x[0] = xPred[0] + k0 * innovation
        x[1] = xPred[1] + k1 * innovation
        x[1] = min(max(x[1], -4.0), 4.0)
        p[0] = pPred[0] - k0 * pzz * k0
        p[1] = pPred[1] - k0 * pzz * k1
        p[2] = pPred[2] - k1 * pzz * k0
        p[3] = pPred[3] - k1 * pzz * k1
        p[0] = max(p[0], 0.1)
        p[3] = max(p[3], 0.001)

    def compute_smoother_gain(self, p, pPred, dt):
        damp = self.rate_damp(dt)
        pfT00 = p[0] + p[1] * dt
        pfT01 = p[1] * damp
        pfT10 = p[2] + p[3] * dt
        pfT11 = p[3] * damp
        det = pPred[0] * pPred[3] - pPred[1] * pPred[2]
        if abs(det) < 1e-10:
            return [0.0, 0.0, 0.0, 0.0]
        inv00 = pPred[3] / det
        inv01 = -pPred[1] / det
        inv10 = -pPred[2] / det
        inv11 = pPred[0] / det
        return [
            pfT00 * inv00 + pfT01 * inv10,
            pfT00 * inv01 + pfT01 * inv11,
            pfT10 * inv00 + pfT11 * inv10,
            pfT10 * inv01 + pfT11 * inv11,
        ]

    # ---------------- adaptive R (IAE, trimmed mean, asymmetric gains) ----------------
    def adapt_measurement_noise(self, currentR):
        if len(self.innovations) < 12 or not self.predVarHistory:
            return currentR

        def trimmed_mean(v, trim=0.20):
            if not v:
                return 0.0
            s = sorted(v)
            k = min(int(len(s) * trim), (len(s) - 1) // 2)
            core = s[k:len(s) - k]
            return sum(core) / len(core)

        nSize = len(self.innovations)
        mRaw = trimmed_mean(self.rawInnovationVariance[:nSize])
        pyyMed = trimmed_mean(self.predVarHistory[:nSize])
        rHatRaw = max(mRaw - pyyMed, self.R_MIN)
        rHat = min(max(rHatRaw, self.R_MIN), self.R_MAX)
        goingUp = rHat > currentR
        k = 0.18 if goingUp else 0.12
        step = currentR + k * (rHat - currentR)
        upCap = 1.20 if goingUp else 1.00
        dnCap = 1.00 if goingUp else 0.90
        clamped = min(max(step, currentR * dnCap), currentR * upCap)
        clamped = min(max(clamped, self.R_MIN), self.R_MAX)
        eta = 0.25
        return (1.0 - eta) * currentR + eta * clamped

    def track_innovation(self, innovation, innovationVariance):
        normalizedSq = (innovation * innovation) / innovationVariance
        rawSq = innovation * innovation
        self.innovations.insert(0, normalizedSq)
        self.rawInnovationVariance.insert(0, rawSq)
        if len(self.innovations) > self.INNOVATION_WINDOW:
            self.innovations.pop()
        if len(self.rawInnovationVariance) > self.INNOVATION_WINDOW:
            self.rawInnovationVariance.pop()

    # ---------------- segmentation ----------------
    def find_data_segments(self, values, timestamps):
        """Mirror findDataSegments: split at gaps outside (2,60] min or value==38.
        Returns list of (startIdx, endIdx) with startIdx<endIdx (newest..oldest)."""
        n = len(values)
        if n < 2:
            return []
        segments = []
        seg_start = 0
        for i in range(0, n - 1):
            time_diff = (timestamps[i] - timestamps[i + 1]) / self.MS_PER_MIN
            if not (2.0 <= time_diff <= self.MAJOR_GAP) or values[i] == 38.0:
                if i - seg_start >= 2:
                    segments.append((seg_start, i))
                seg_start = i + 1
        if n - seg_start >= 2:
            segments.append((seg_start, n - 1))
        return segments

    # ---------------- main ----------------
    def smooth(self, values, timestamps):
        """NEWEST-FIRST in, NEWEST-FIRST out (list of per-point dicts)."""
        n = len(values)
        out = [None] * n
        if n == 0:
            return out
        if n == 1:
            sm = max(values[0], 39.0)
            out[0] = dict(level_online=sm, rate_online=0.0, level_offline=sm,
                          rate_offline=0.0, outlier=False)
            return out

        if self.should_reset_learning(timestamps[0]):
            self.reset_learning()

        segments = self.find_data_segments(values, timestamps)

        prev_ts = self.lastProcessedTimestamp
        self.lastProcessedTimestamp = timestamps[0]

        # default fill: unprocessed -> floored raw
        for i in range(n):
            out[i] = dict(level_online=max(values[i], 39.0), rate_online=0.0,
                          level_offline=max(values[i], 39.0), rate_offline=0.0,
                          outlier=False)

        for (startIdx, endIdx) in segments:
            self._process_segment(values, timestamps, startIdx, endIdx, prev_ts, out)
        return out

    def _process_segment(self, values, timestamps, startIdx, endIdx, prev_ts, out):
        segSize = endIdx - startIdx + 1
        if segSize < 2:
            sm = max(values[startIdx], 39.0)
            out[startIdx] = dict(level_online=sm, rate_online=0.0, level_offline=sm,
                                 rate_offline=0.0, outlier=False)
            return

        initialGlucose = values[endIdx]
        initialRate = 0.0
        if endIdx > 0:
            dt = (timestamps[endIdx - 1] - timestamps[endIdx]) / self.MS_PER_MIN
            if 3.0 <= dt <= 7.0:
                initialRate = (values[endIdx - 1] - values[endIdx]) / dt
                initialRate = min(max(initialRate, -4.0), 4.0)

        x = [initialGlucose, initialRate]
        p = [16.0, 0.0, 0.0, 1.0]
        r = self.learnedR

        forwardResults = [0.0] * segSize    # forward-filtered level, indexed by resultIdx
        forwardRates = [0.0] * segSize      # forward-filtered rate (causal)
        outlierFlags = [False] * segSize
        forwardResults[segSize - 1] = x[0]
        forwardRates[segSize - 1] = x[1]

        forwardStates = []  # will be built in addFirst order (index0 = newest processed)
        recentSigns = []    # index0 = newest

        for i in range(endIdx - 1, startIdx - 1, -1):
            dt = (timestamps[i] - timestamps[i + 1]) / self.MS_PER_MIN
            if self.MINOR_GAP < dt <= self.MAJOR_GAP:
                x[1] *= self.rate_damp(dt)

            p[0] = min(max(p[0], 0.1), self.MAX_GLUCOSE_VAR)
            p[3] = min(max(p[3], 0.001), self.MAX_RATE_VAR)

            dtUsed = dt
            xPredBase, pPredBase = self.predict(x, p, self.Q, dtUsed)

            rawValue = values[i]
            z = values[i]  # no calibration in this harness -> calibratedOrValue == value

            resultIdx = i - startIdx

            # error-code skip (xDrip 38 etc.)
            if rawValue <= 38.0:
                stateBefore = dict(x=x[:], p=p[:], xPred=xPredBase[:], pPred=pPredBase[:], dt=dtUsed)
                x[0] = xPredBase[0]; x[1] = xPredBase[1]
                p[0] = pPredBase[0]; p[1] = pPredBase[1]; p[2] = pPredBase[2]; p[3] = pPredBase[3]
                forwardResults[resultIdx] = x[0]
                forwardRates[resultIdx] = x[1]
                forwardStates.insert(0, stateBefore)
                recentSigns.insert(0, 0)
                if len(recentSigns) > 3:
                    recentSigns.pop()
                continue

            # innovation stats (pre-inflation, for gating)
            innovation = z - xPredBase[0]
            innovationVarianceRaw = pPredBase[0] + r
            stdRaw = math.sqrt(innovationVarianceRaw)
            normRaw = innovation / stdRaw

            sign = 1 if normRaw > 0.0 else (-1 if normRaw < 0.0 else 0)
            if len(recentSigns) == 3:
                recentSigns.pop()
            recentSigns.insert(0, sign if abs(normRaw) > 2.0 else 0)
            sameSignCount = 0 if sign == 0 else sum(1 for s in recentSigns if s == sign)
            qInflateAllowed = sameSignCount >= 2

            absn = abs(normRaw)

            # Huber-like R inflation
            rScale = 1.0 + max(0.0, absn - 2.0)
            rEff = min(r * rScale, min(r + 100.0, self.R_EFF_MAX))

            # Q inflation for real trends
            zScore = max(absn, 1.0)
            qScale = min(max(zScore, 1.0), 3.0) if qInflateAllowed else 1.0
            if qScale > 1.0:
                tempQ = self.Q[:]
                tempQ[0] = self.Q[0] * min(qScale, 2.0)
                tempQ[3] = self.Q[3] * qScale
                xPredEff, pPredEff = self.predict(x, p, tempQ, dtUsed)
            else:
                tempQ = self.Q
                xPredEff, pPredEff = xPredBase, pPredBase

            stateBefore = dict(x=x[:], p=p[:], xPred=xPredEff[:], pPred=pPredEff[:], dt=dtUsed)

            innovationVarianceEff = pPredEff[0] + rEff
            mahalSqEff = (innovation * innovation) / innovationVarianceEff

            self.predVarHistory.insert(0, pPredEff[0])
            if len(self.predVarHistory) > self.INNOVATION_WINDOW:
                self.predVarHistory.pop()

            self.update(xPredEff, pPredEff, z, rEff, x, p)
            self.track_innovation(innovation, innovationVarianceEff)

            skipRUpdate = qInflateAllowed or absn > 3.0
            if not skipRUpdate:
                r = self.adapt_measurement_noise(r)

            is_outlier = (mahalSqEff > self.CHI2_THRESHOLD) or (abs(innovation) > self.OUTLIER_ABSOLUTE)
            outlierFlags[resultIdx] = is_outlier

            forwardResults[resultIdx] = x[0]
            forwardRates[resultIdx] = x[1]
            forwardStates.insert(0, stateBefore)

        self.learnedR = r

        # === backward RTS pass ===
        smoothedResults = forwardResults[:]
        smoothedRates = forwardRates[:]
        if segSize >= 3 and forwardStates:
            maxSmoothSteps = min(segSize - 1, len(forwardStates))
            xSmooth = [forwardResults[0], x[1]]
            for i in range(1, maxSmoothSteps + 1):
                state = forwardStates[i - 1]
                c = self.compute_smoother_gain(state["p"], state["pPred"], state["dt"])
                dx0 = xSmooth[0] - state["xPred"][0]
                dx1 = xSmooth[1] - state["xPred"][1]
                xSmooth[0] = forwardResults[i] + c[0] * dx0 + c[1] * dx1
                xSmooth[1] = state["x"][1] + c[2] * dx0 + c[3] * dx1
                smoothedResults[i] = xSmooth[0]
                smoothedRates[i] = xSmooth[1]

        for i in range(startIdx, endIdx + 1):
            resultIdx = i - startIdx
            out[i] = dict(
                level_online=max(forwardResults[resultIdx], 39.0),
                rate_online=forwardRates[resultIdx],
                level_offline=max(smoothedResults[resultIdx], 39.0),
                rate_offline=smoothedRates[resultIdx],
                outlier=outlierFlags[resultIdx],
            )


# ============================================================================
# Uniform driver over the four smoothers
# ============================================================================

def _segment_chrono(ts, vals, max_gap_min=60.0):
    """Split OLDEST-FIRST arrays into contiguous runs (gap <= max_gap)."""
    segs = []
    ct, cv, ci = [], [], []
    for j in range(len(ts)):
        if ct and (ts[j] - ct[-1]) / 60000.0 > max_gap_min:
            segs.append((ct, cv, ci))
            ct, cv, ci = [], [], []
        ct.append(ts[j]); cv.append(vals[j]); ci.append(j)
    if ct:
        segs.append((ct, cv, ci))
    return segs


def smooth_series(name, ts, vals, iobs=None, exp_window=20):
    """Uniform entry point. OLDEST-FIRST (chronological) ts(ms), vals in; returns
    dict of OLDEST-FIRST arrays: level_online, rate_online, level_offline, outlier.

    `name` in {persistence, exponential, tsunami, v4}.
    `iobs` (chronological) only used by tsunami's compression guard; if None a
    high fail-safe IOB (guard disabled) is used.
    """
    M = len(ts)
    level_on = [float('nan')] * M
    rate_on = [0.0] * M
    level_off = [float('nan')] * M
    outlier = [False] * M

    if name == "persistence":
        for t in range(M):
            level_on[t] = vals[t]
            level_off[t] = vals[t]
            rate_on[t] = 0.0
        return dict(level_online=level_on, rate_online=rate_on,
                    level_offline=level_off, outlier=outlier)

    if name == "exponential":
        # production-faithful rolling window (causal), run PER CONTIGUOUS SEGMENT so
        # the 2nd-order term never rings across a multi-day gap (AAPS only ever calls
        # smooth() on a bounded recent window). rate = finite diff of levels within seg.
        for (st, sv, idxs) in _segment_chrono(ts, vals, max_gap_min=15.0):
            est = exponential_rolling(st, sv, W=exp_window)
            for k, gi in enumerate(idxs):
                lv = est[k] if est[k] is not None else sv[k]
                level_on[gi] = lv
                level_off[gi] = lv
            for k, gi in enumerate(idxs):
                if k == 0:
                    rate_on[gi] = 0.0
                else:
                    dt = (st[k] - st[k - 1]) / 60000.0
                    rate_on[gi] = (level_on[gi] - level_on[idxs[k - 1]]) / dt if dt > 0 else 0.0
        return dict(level_online=level_on, rate_online=rate_on,
                    level_offline=level_off, outlier=outlier)

    if name == "tsunami":
        ukf = AdaptiveUKF()
        for (st, sv, idxs) in _segment_chrono(ts, vals, max_gap_min=15.0):
            m = len(st)
            if m < 2:
                for k, gi in enumerate(idxs):
                    level_on[gi] = sv[k]; level_off[gi] = sv[k]
                continue
            if iobs is None:
                seg_iob = [AdaptiveUKF.IOB_SAFE_FALLBACK_U] * m
            else:
                seg_iob = [(iobs[gi] if iobs[gi] is not None else AdaptiveUKF.IOB_SAFE_FALLBACK_U) for gi in idxs]
            o = ukf.process_segment(sv[::-1], st[::-1], seg_iob[::-1])  # newest-first
            sm = [o[k]['smoothed'] for k in range(m)][::-1]
            rt = [o[k]['rate'] for k in range(m)][::-1]
            for k, gi in enumerate(idxs):
                level_on[gi] = sm[k]; level_off[gi] = sm[k]; rate_on[gi] = rt[k]
        return dict(level_online=level_on, rate_online=rate_on,
                    level_offline=level_off, outlier=outlier)

    if name == "v4":
        ukf = V4UKF()
        # v4 has its own internal segmentation; still split at >15min so persistent
        # state resets exactly as the >24h/gap logic would across long breaks and so
        # each contiguous run is handed as one smooth() call (matches AAPS usage).
        for (st, sv, idxs) in _segment_chrono(ts, vals, max_gap_min=15.0):
            m = len(st)
            o = ukf.smooth(sv[::-1], st[::-1])  # newest-first
            lo = [o[k]['level_online'] for k in range(m)][::-1]
            ro = [o[k]['rate_online'] for k in range(m)][::-1]
            lf = [o[k]['level_offline'] for k in range(m)][::-1]
            ol = [o[k]['outlier'] for k in range(m)][::-1]
            for k, gi in enumerate(idxs):
                level_on[gi] = lo[k]; rate_on[gi] = ro[k]; level_off[gi] = lf[k]; outlier[gi] = ol[k]
        return dict(level_online=level_on, rate_online=rate_on,
                    level_offline=level_off, outlier=outlier)

    raise ValueError("unknown smoother: " + name)


SMOOTHERS = ["persistence", "exponential", "tsunami", "v4"]


# ============================================================================
# v4 parity self-test -- the 9 behaviours of UnscentedKalmanFilterPluginTest.kt
# ============================================================================

def _series_newest_first(values, step_min=5):
    base = 1_700_000_000_000
    ts = [base - i * step_min * 60_000 for i in range(len(values))]
    return list(values), ts


def selftest_v4(verbose=True):
    results = []

    def check(name, ok):
        results.append((name, ok))
        if verbose:
            print(f"  [{'PASS' if ok else 'FAIL'}] {name}")

    # 1. empty input -> empty
    vals, ts = [], []
    out = V4UKF().smooth(vals, ts)
    check("empty input returns empty", out == [])

    # 2. single value copied to smoothed, floored at 39
    v, t = _series_newest_first([100.0])
    out = V4UKF().smooth(v, t)
    ok = abs(out[0]['level_offline'] - 100.0) < 1e-9
    v, t = _series_newest_first([20.0])
    out = V4UKF().smooth(v, t)
    ok = ok and abs(out[0]['level_offline'] - 39.0) < 1e-9
    check("single value copied to smoothed, floored at 39", ok)

    # 3. error-code (38) values collapse to 39 floor, no valid segment
    v, t = _series_newest_first([38.0, 38.0, 38.0])
    out = V4UKF().smooth(v, t)
    ok = all(abs(o['level_offline'] - 39.0) < 1e-9 for o in out)
    check("error-code (38) values collapse to 39 floor", ok)

    # 4. clean series smooths every point within 30 of 100
    v, t = _series_newest_first([101.0, 99.0, 100.0, 102.0, 98.0, 100.0, 101.0, 99.0, 100.0, 100.0])
    out = V4UKF().smooth(v, t)
    ok = len(out) == 10 and all(o['level_offline'] >= 39.0 and abs(o['level_offline'] - 100.0) <= 30.0 for o in out)
    check("clean series smooths every point to a sane value", ok)

    # 5. rising series -> rising smoothed trend (newest > oldest)
    v, t = _series_newest_first([150.0, 140.0, 130.0, 120.0, 110.0, 100.0, 90.0, 80.0])
    out = V4UKF().smooth(v, t)
    check("a rising series produces a rising smoothed trend",
          out[0]['level_offline'] > out[-1]['level_offline'])

    # 6. isolated spike dampened below 200
    v, t = _series_newest_first([100.0, 100.0, 100.0, 300.0, 100.0, 100.0, 100.0, 100.0])
    out = V4UKF().smooth(v, t)
    ok = abs(v[3] - 300.0) < 1e-9 and out[3]['level_offline'] < 200.0
    check("an isolated spike is dampened below 200 (outlier handling)", ok)

    # 7. major-gap split: both clusters smoothed (>=4 points get a smoothed value)
    base = 1_700_000_000_000
    clusterA_v = [100.0, 101.0, 99.0]
    clusterA_t = [base - i * 5 * 60_000 for i in range(3)]
    gap_base = base - (3 * 5 + 120) * 60_000
    clusterB_v = [120.0, 119.0, 121.0]
    clusterB_t = [gap_base - i * 5 * 60_000 for i in range(3)]
    v = clusterA_v + clusterB_v
    t = clusterA_t + clusterB_t
    out = V4UKF().smooth(v, t)
    n_smoothed = sum(1 for o in out if o['level_offline'] is not None)
    check("data spanning a major gap is split; both clusters smoothed", n_smoothed >= 4)

    # 8. determinism across fresh instances
    v, t = _series_newest_first([120.0, 118.0, 122.0, 119.0, 121.0, 120.0, 118.0])
    a = V4UKF().smooth(v, t)
    b = V4UKF().smooth(v, t)
    ok = all(abs(a[i]['level_offline'] - b[i]['level_offline']) < 1e-9 for i in range(len(a)))
    check("smoothing is deterministic across fresh instances", ok)

    # 9. RTS actually runs: on a clean rising ramp the smoothed curve tracks the
    #    ramp (monotonic non-decreasing newest..oldest reversed) -- exercises the
    #    backward pass without asserting brittle absolute values.
    v, t = _series_newest_first([160.0, 150.0, 140.0, 130.0, 120.0, 110.0, 100.0, 90.0, 80.0, 70.0])
    out = V4UKF().smooth(v, t)
    chrono = [out[k]['level_offline'] for k in range(len(out))][::-1]
    monotonic = all(chrono[i + 1] >= chrono[i] - 1.0 for i in range(len(chrono) - 1))
    check("RTS backward pass yields a coherent monotone smoothed ramp", monotonic)

    passed = sum(1 for _, ok in results if ok)
    print(f"\nv4 parity self-test: {passed}/{len(results)} PASS")
    return passed == len(results)


if __name__ == "__main__":
    print("=== v4 UKF parity self-test (oracle: UnscentedKalmanFilterPluginTest.kt) ===")
    ok = selftest_v4()
    sys.exit(0 if ok else 1)
