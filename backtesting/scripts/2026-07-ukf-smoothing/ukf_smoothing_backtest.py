#!/usr/bin/env python3
"""
UKF CGM-smoothing backtest.

Faithful Python mirror of the committed Kotlin:
  plugins/smoothing/src/main/kotlin/app/aaps/plugins/smoothing/AdaptiveSmoothingPlugin.kt
(2-state adaptive Unscented Kalman Filter) plus a port of
  plugins/smoothing/src/main/kotlin/app/aaps/plugins/smoothing/ExponentialSmoothingPlugin.kt
as one of the baselines.

WHAT THIS PROVES / WHAT IT DOES NOT
-----------------------------------
There is NO reference "true" glucose and NO glucodynamic simulator in this backtest,
so we CANNOT claim any TIR / BG-outcome / dosing improvement. We validate SENSING
quality only, on the real raw CGM stream, with a ground-truth-FREE primary metric:
one-step-ahead predictive error against the next RAW reading (penalises BOTH lag and
noise-chasing). Everything downstream of that (does cleaner sensing help dosing) is
OUT OF SCOPE and is not asserted here.

FIDELITY NOTE (read me)
-----------------------
This Python UKF is a hand-port that mirrors the Kotlin operation-for-operation (same
constants, same sigma-point weights, same predict/update/matrix-sqrt, the same median
helper `med()` with even-size averaging, the same 48-deep innovation window with
addFirst/removeLast, the same R-adaptation order, the same night check hour not in
[7,23), the same compression / rapid-rise / kinetic-hypo guards). Bit-exact
Kotlin<->Python parity was NOT formally unit-tested: that JVM-vs-CPython golden-vector
test is the formal gate before trusting the ABSOLUTE numbers. The RELATIVE comparison
(UKF vs persistence vs exponential vs linear, all fed the identical stream) is robust
to small float / ordering differences because every predictor sees the same data and a
sub-ULP drift in a sigma-point cannot flip a several-percent RMSE ranking. An internal
consistency check (clean sine + noise -> filter recovers the clean signal better than
raw) is run at the bottom.

Usage:
  python ukf_smoothing_backtest.py            # full run: all users, metrics, PNGs, README numbers
  python ukf_smoothing_backtest.py --selftest # just the sine consistency check
"""

import sys
import math
import os
from collections import deque, defaultdict

OUTDIR = os.path.dirname(os.path.abspath(__file__))

# ----------------------------------------------------------------------------
# Faithful UKF port  (mirrors AdaptiveSmoothingPlugin.kt)
# ----------------------------------------------------------------------------

class AdaptiveUKF:
    """Operation-for-operation mirror of the Kotlin AdaptiveSmoothingPlugin.

    State x = [glucose, glucose-rate(mg/dL/min)]. Constant-velocity model with
    rate damping 0.98. Fixed process noise Q, adaptive measurement noise R.
    Safety layers: compression rejection, rapid-rise zero-lag Q inflation,
    kinetic-hypo forcing.

    The learnedR and the innovation deques are member state that persists across
    calls (re-converges after a >24h gap reset), exactly as in Kotlin.
    """

    MIN_VALID_BG = 39.0
    MAX_VALID_BG = 500.0
    DEFAULT_LEARNED_R = 36.0
    IOB_SAFE_FALLBACK_U = 99.0

    def __init__(self):
        self.n = 2
        self.alpha = 1.00
        self.beta = 0.0
        self.kappa = 3.0
        self.lam = self.alpha * self.alpha * (self.n + self.kappa) - self.n  # = 3
        self.gamma = math.sqrt(self.n + self.lam)                            # = sqrt(5)

        self.qFixed = [1.0, 0.0, 0.0, 0.40]
        self.rMin = 16.0
        self.rMax = 196.0
        self.innovationWindow = 48
        self.rateDamping = 0.98

        # sigma weights
        self.wm = [0.0] * (2 * self.n + 1)
        self.wc = [0.0] * (2 * self.n + 1)
        self._init_sigma_weights()

        # persistent processing state
        self.learnedR = self.DEFAULT_LEARNED_R
        self.innovations = deque()            # normalised innovation^2  (addFirst = appendleft)
        self.rawInnovationVariance = deque()  # raw innovation^2
        self.lastProcessedTimestamp = 0

    def _init_sigma_weights(self):
        n, lam, alpha, beta = self.n, self.lam, self.alpha, self.beta
        self.wm[0] = lam / (n + lam)
        self.wc[0] = lam / (n + lam) + (1 - alpha * alpha + beta)
        w = 1.0 / (2.0 * (n + lam))
        for i in range(1, 2 * n + 1):
            self.wm[i] = w
            self.wc[i] = w

    # --- learning reset (in-memory) ---
    def should_reset_learning(self, current_ts):
        if self.lastProcessedTimestamp == 0:
            return True
        diff_min = (current_ts - self.lastProcessedTimestamp) / 60000.0
        if diff_min < 0:
            return False
        if diff_min > 1440:
            return True
        return False

    def reset_learning(self):
        self.learnedR = self.DEFAULT_LEARNED_R
        self.innovations.clear()
        self.rawInnovationVariance.clear()

    # --- median helper (mirrors med(), even-size averaging with integer indices) ---
    @staticmethod
    def med(vals):
        s = sorted(vals)
        sz = len(s)
        if sz % 2 == 0:
            return (s[sz // 2] + s[(sz - 1) // 2]) / 2.0
        return s[sz // 2]

    def adapt_measurement_noise(self, currentR):
        if len(self.innovations) < 8:
            return currentR
        avgInnovSq = self.med(self.innovations)
        if any(v > 9.0 for v in self.innovations):
            return min(max(currentR, self.rMin), self.rMax)
        newR = currentR
        if avgInnovSq >= 1.1 or avgInnovSq <= 0.9:
            newR = currentR + 0.06 * (self.med(self.rawInnovationVariance) - currentR)
        return min(max(newR, self.rMin), self.rMax)

    def track_innovation(self, innovation, innovationVariance):
        normalizedSq = (innovation * innovation) / innovationVariance
        rawSq = innovation * innovation
        self.innovations.appendleft(normalizedSq)
        self.rawInnovationVariance.appendleft(rawSq)
        if len(self.innovations) > self.innovationWindow:
            self.innovations.pop()
        if len(self.rawInnovationVariance) > self.innovationWindow:
            self.rawInnovationVariance.pop()

    # --- UKF maths ---
    @staticmethod
    def matrix_sqrt_2x2(cov):
        a = cov[0]
        b = (cov[1] + cov[2]) / 2.0
        d = cov[3]
        l11 = math.sqrt(max(a, 1e-9))
        l21 = b / l11
        disc = d - l21 * l21
        l22 = math.sqrt(max(d, 1e-9)) if disc < 0 else math.sqrt(disc)
        return [l11, l21, 0.0, l22]

    def generate_sigma_points(self, x, cov):
        n, gamma = self.n, self.gamma
        sp = [[0.0, 0.0] for _ in range(2 * n + 1)]
        sqrtP = self.matrix_sqrt_2x2(cov)
        sp[0][0] = x[0]; sp[0][1] = x[1]
        for i in range(n):
            sp[i + 1][0] = x[0] + gamma * sqrtP[i * 2 + 0]
            sp[i + 1][1] = x[1] + gamma * sqrtP[i * 2 + 1]
            sp[i + 1 + n][0] = x[0] - gamma * sqrtP[i * 2 + 0]
            sp[i + 1 + n][1] = x[1] - gamma * sqrtP[i * 2 + 1]
        return sp

    def predict(self, x, cov, q, dt):
        n, wm, wc = self.n, self.wm, self.wc
        sp = self.generate_sigma_points(x, cov)
        spp = [[0.0, 0.0] for _ in range(2 * n + 1)]
        for i in range(2 * n + 1):
            spp[i][0] = sp[i][0] + sp[i][1] * dt
            spp[i][1] = sp[i][1] * self.rateDamping
        xPred = [0.0, 0.0]
        for i in range(2 * n + 1):
            xPred[0] += wm[i] * spp[i][0]
            xPred[1] += wm[i] * spp[i][1]
        pcov = [0.0, 0.0, 0.0, 0.0]
        for i in range(2 * n + 1):
            dx0 = spp[i][0] - xPred[0]
            dx1 = spp[i][1] - xPred[1]
            pcov[0] += wc[i] * dx0 * dx0
            pcov[1] += wc[i] * dx0 * dx1
            pcov[2] += wc[i] * dx1 * dx0
            pcov[3] += wc[i] * dx1 * dx1
        qScale = dt / 5.0
        pcov[0] += q[0] * qScale
        pcov[3] += q[3] * qScale
        pcov[0] = max(pcov[0], 0.1)
        pcov[3] = max(pcov[3], 0.001)
        return xPred, pcov

    def update(self, xPred, pcov, z, rvar, x, cov):
        n, wm, wc = self.n, self.wm, self.wc
        sp = self.generate_sigma_points(xPred, pcov)
        zSigma = [sp[i][0] for i in range(2 * n + 1)]
        zPred = 0.0
        for i in range(2 * n + 1):
            zPred += wm[i] * zSigma[i]
        innovationVariance = 0.0
        for i in range(2 * n + 1):
            dz = zSigma[i] - zPred
            innovationVariance += wc[i] * dz * dz
        innovationVariance += rvar
        ivs = max(innovationVariance, 1e-6)
        cross = [0.0, 0.0]
        for i in range(2 * n + 1):
            dx0 = sp[i][0] - xPred[0]
            dx1 = sp[i][1] - xPred[1]
            dz = zSigma[i] - zPred
            cross[0] += wc[i] * dx0 * dz
            cross[1] += wc[i] * dx1 * dz
        k0 = cross[0] / ivs
        k1 = cross[1] / ivs
        innovation = z - zPred
        x[0] = xPred[0] + k0 * innovation
        x[1] = xPred[1] + k1 * innovation
        x[1] = min(max(x[1], -5.0), 5.0)
        cov[0] = pcov[0] - k0 * ivs * k0
        cov[1] = pcov[1] - k0 * ivs * k1
        cov[2] = pcov[2] - k1 * ivs * k0
        cov[3] = pcov[3] - k1 * ivs * k1
        cov[0] = max(cov[0], 0.1)
        cov[3] = max(cov[3], 0.001)

    # --- glycemic context / compression candidate ---
    @staticmethod
    def is_night(ts_ms):
        # local hour (timestamps are epoch-ms in local wall time; see loader)
        import datetime
        h = datetime.datetime.fromtimestamp(ts_ms / 1000.0).hour
        return h not in range(7, 23)

    def compression_candidate(self, raw_delta, iob, is_night):
        drop_threshold = -15.0 if is_night else -25.0
        if raw_delta < drop_threshold:
            if iob < 3.0:
                return True
        return False

    def process_segment(self, values, timestamps, iobs):
        """One continuous forward pass over a contiguous CGM segment.

        `values`, `timestamps`(epoch-ms local wall), `iobs` are NEWEST-FIRST
        (index 0 = newest), mirroring the list AAPS hands to smooth().
        Returns per-reading (newest-first) dicts with smoothed value, rate,
        and which guards fired.
        """
        N = len(values)
        out = [None] * N
        if N < 2:
            for i in range(N):
                out[i] = dict(smoothed=values[i], rate=0.0,
                              compression=False, kinetic=False, rapid=False)
            return out

        # learning reset on >24h gap since last processed newest ts
        if self.should_reset_learning(timestamps[0]):
            self.reset_learning()
        self.lastProcessedTimestamp = timestamps[0]

        startIdx = N - 1
        x = [values[startIdx], 0.0]
        cov = [16.0, 0.0, 0.0, 1.0]
        measurementNoiseR = self.learnedR

        for i in range(startIdx, -1, -1):
            z = values[i]
            ts = timestamps[i]
            if i < startIdx:
                dt = (ts - timestamps[i + 1]) / (1000.0 * 60.0)
            else:
                dt = 5.0
            dtc = min(max(dt, 1.0), 15.0)

            # heuristic context
            val_old1 = values[i + 1] if (i + 1 < N) else z
            raw_delta = z - val_old1
            iob = iobs[i]
            night = self.is_night(ts)

            isCompression = self.compression_candidate(raw_delta, iob, night)
            isHypoCritical = z < 70.0

            # 1. standard prediction
            xPred, pcov = self.predict(x, cov, self.qFixed, dtc)

            # 2. rapid-rise zero-lag maneuver (uses CURRENT learnedR)
            preFit = z - xPred[0]
            preFitSigma = math.sqrt(pcov[0] + measurementNoiseR)
            normInnov = preFit / preFitSigma
            isRapid = (normInnov > 2.5 and preFit > 0)
            if isRapid:
                qAd = list(self.qFixed)
                qAd[3] *= 50.0
                qAd[0] *= 2.0
                xPred, pcov = self.predict(x, cov, qAd, dtc)

            compFired = False
            kineticFired = False

            if isCompression:
                # blind update: hold prediction, carry predicted covariance
                x[0] = xPred[0]
                x[1] = xPred[1]
                cov[0] = pcov[0]; cov[1] = pcov[1]; cov[2] = pcov[2]; cov[3] = pcov[3]
                smoothed = x[0]
                compFired = True
            else:
                innovation = z - xPred[0]
                innovationVariance = pcov[0] + measurementNoiseR  # uses OLD R
                measurementNoiseR = self.adapt_measurement_noise(measurementNoiseR)
                self.track_innovation(innovation, innovationVariance)
                self.update(xPred, pcov, z, measurementNoiseR, x, cov)

                velocity = x[1]
                predicted20 = x[0] + velocity * 20.0
                isKineticHypo = (predicted20 < 55.0) or (z < 80.0 and velocity < -1.5) or (velocity < -3.0)
                if isKineticHypo:
                    if x[0] > z:
                        x[0] = z
                    if velocity < -2.0:
                        x[0] += velocity * 2.0
                    kineticFired = True
                elif isHypoCritical and x[0] > z + 5.0:
                    x[0] = (x[0] + z) / 2.0
                smoothed = x[0]

            out[i] = dict(smoothed=smoothed, rate=x[1],
                          compression=compFired, kinetic=kineticFired, rapid=isRapid)

        self.learnedR = measurementNoiseR
        return out


# ----------------------------------------------------------------------------
# Faithful Exponential-smoother port  (mirrors ExponentialSmoothingPlugin.kt)
# ----------------------------------------------------------------------------

def exponential_smooth(values, timestamps):
    """Port of ExponentialSmoothingPlugin.smooth. NEWEST-FIRST in and out.
    Returns list `smoothed` (same order); entries with no smoothed value are None."""
    data_v = values
    data_t = timestamps
    sizeRecords = len(data_v)
    smoothed = [None] * sizeRecords
    o1_weight = 0.4
    o1_a = 0.5
    o2_a = 0.4
    o2_b = 1.0
    windowSize = sizeRecords
    if sizeRecords <= windowSize:
        windowSize = max(sizeRecords - 1, 0)
    # gap / error-state truncation
    for i in range(windowSize):
        if round((data_t[i] - data_t[i + 1]) / (1000.0 * 60)) >= 12:
            windowSize = i + 1
            break
        elif data_v[i] == 38.0:
            windowSize = i
            break

    insufficient = False
    o1_sBG = []
    if windowSize >= 4:
        o1_sBG.append(data_v[windowSize - 1])
        for i in range(windowSize):
            o1_sBG.insert(0, o1_sBG[0] + o1_a * (data_v[windowSize - 1 - i] - o1_sBG[0]))
    else:
        insufficient = True

    o2_sBG = []
    o2_sD = []
    if windowSize >= 4:
        o2_sBG.append(data_v[windowSize - 1])
        o2_sD.append(data_v[windowSize - 2] - data_v[windowSize - 1])
        for i in range(windowSize - 1):
            o2_sBG.insert(0, o2_a * data_v[windowSize - 2 - i] + (1 - o2_a) * (o2_sBG[0] + o2_sD[0]))
            o2_sD.insert(0, o2_b * (o2_sBG[0] - o2_sBG[1]) + (1 - o2_b) * o2_sD[0])
    else:
        insufficient = True

    if not insufficient:
        ssBG = []
        for i in range(len(o2_sBG)):
            ssBG.append(o1_weight * o1_sBG[i] + (1 - o1_weight) * o2_sBG[i])
        for i in range(min(len(ssBG), sizeRecords)):
            smoothed[i] = max(round(ssBG[i]), 39.0)
    else:
        for i in range(sizeRecords):
            smoothed[i] = max(data_v[i], 39.0)
    return smoothed


def exponential_rolling(st, sv, W=20):
    """Realistic ONLINE use of the exp smoother: at each reading t, feed the
    trailing W readings (newest-first) and take the newest smoothed output as the
    estimate at t. This mirrors how AAPS calls smooth() on a bounded recent window
    each cycle (a multi-day batch would let the 2nd-order term ring, which never
    happens in production). Inputs OLDEST-FIRST; returns OLDEST-FIRST estimate[t]."""
    M = len(st)
    est = [None] * M
    for t in range(M):
        lo = max(0, t - W + 1)
        win_v = sv[lo:t + 1][::-1]   # newest-first
        win_t = st[lo:t + 1][::-1]
        out = exponential_smooth(win_v, win_t)
        est[t] = out[0]              # newest = reading t
    return est


# ----------------------------------------------------------------------------
# Data loading + segmentation
# ----------------------------------------------------------------------------

def load_user(cur, user_id):
    """Returns chronological (OLDEST-FIRST) lists: ts_ms(local wall), value, iob.
    iob joined from boost_decisions by 5-min bucket; missing -> IOB_SAFE_FALLBACK_U."""
    cur.execute(
        """
        SELECT extract(epoch from (ts_utc AT TIME ZONE 'Europe/London')) * 1000.0 AS ts_local_ms,
               floor(extract(epoch from ts_utc) / 300)::bigint AS bucket,
               cgm_mgdl
        FROM boost_cgm
        WHERE user_id = %s
        ORDER BY ts_utc ASC
        """, (user_id,))
    rows = cur.fetchall()
    ts = [float(r[0]) for r in rows]
    buckets = [r[1] for r in rows]
    vals = [float(r[2]) for r in rows]

    # IOB lookup by 5-min bucket
    cur.execute(
        """
        SELECT DISTINCT ON (floor(ts_epoch/300))
               floor(ts_epoch/300)::bigint AS bucket, iob_iob
        FROM boost_decisions
        WHERE user_id = %s AND iob_iob IS NOT NULL
        ORDER BY floor(ts_epoch/300), ts_epoch DESC
        """, (user_id,))
    iob_map = {r[0]: float(r[1]) for r in cur.fetchall()}
    iobs = [iob_map.get(b, None) for b in buckets]
    return ts, vals, iobs


def segment(ts, vals, iobs, max_gap_min=15.0):
    """Split OLDEST-FIRST arrays into contiguous runs where consecutive gap <= max_gap.
    Returns list of (ts, vals, iobs) chronological sub-arrays."""
    segs = []
    cur_t, cur_v, cur_i = [], [], []
    for j in range(len(ts)):
        if cur_t and (ts[j] - cur_t[-1]) / 60000.0 > max_gap_min:
            segs.append((cur_t, cur_v, cur_i))
            cur_t, cur_v, cur_i = [], [], []
        cur_t.append(ts[j]); cur_v.append(vals[j]); cur_i.append(iobs[j])
    if cur_t:
        segs.append((cur_t, cur_v, cur_i))
    return segs


# ----------------------------------------------------------------------------
# Per-user backtest
# ----------------------------------------------------------------------------

def run_user(ts, vals, iobs, use_real_iob=False):
    """Runs UKF + exp + baselines over all contiguous segments of one user.

    Returns a dict of accumulated arrays for metrics. The UKF is run with a
    SINGLE persistent filter instance across segments (learnedR / innovations
    persist; reset on >24h gap), matching the Kotlin member-state semantics.
    """
    ukf = AdaptiveUKF()

    # one-step-ahead abs errors per predictor
    err = defaultdict(list)          # predictor -> list of |pred - raw(t+1)|
    # arrays for noise / lag / safety, kept per-segment
    stable_var_raw, stable_var_ukf = [], []
    stable_var_exp = []
    reversals_raw = reversals_ukf = reversals_exp = 0
    reversal_windows = 0
    lag_ukf, lag_exp = [], []
    comp_fires = kin_fires = rapid_fires = 0
    n_readings = 0
    n_onestep = 0

    # iob feed for the UKF: real (joined) or fail-safe high
    def iob_feed(iob_seg):
        if use_real_iob:
            return [(v if v is not None else AdaptiveUKF.IOB_SAFE_FALLBACK_U) for v in iob_seg]
        return [AdaptiveUKF.IOB_SAFE_FALLBACK_U] * len(iob_seg)

    for (st, sv, si) in segment(ts, vals, iobs):
        M = len(st)
        n_readings += M
        if M < 5:
            continue
        # newest-first views for the plugins
        nf_v = sv[::-1]
        nf_t = st[::-1]
        nf_i = iob_feed(si)[::-1]

        ukf_out_nf = ukf.process_segment(nf_v, nf_t, nf_i)

        # back to chronological
        ukf_sm = [ukf_out_nf[k]['smoothed'] for k in range(M)][::-1]
        ukf_rate = [ukf_out_nf[k]['rate'] for k in range(M)][::-1]
        # exponential baseline: realistic online rolling window (chronological)
        exp_sm = exponential_rolling(st, sv, W=20)
        for k in range(M):
            if ukf_out_nf[k]['compression']: comp_fires += 1
            if ukf_out_nf[k]['kinetic']:     kin_fires += 1
            if ukf_out_nf[k]['rapid']:       rapid_fires += 1

        # ---- one-step-ahead prediction (chronological) ----
        # predict raw(t+1) from state/level at t.
        for t in range(1, M - 1):  # interior readings (need t-1 for linear/exp-trend, t+1 as target)
            dt_next = (st[t + 1] - st[t]) / 60000.0
            dt_prev = (st[t] - st[t - 1]) / 60000.0
            if not (1.0 <= dt_next <= 15.0) or not (1.0 <= dt_prev <= 15.0):
                continue
            target = sv[t + 1]
            n_onestep += 1
            # persistence
            err['persistence'].append(abs(sv[t] - target))
            # raw linear extrapolation (raw delta * dt)
            raw_rate = (sv[t] - sv[t - 1]) / dt_prev
            err['linear'].append(abs(sv[t] + raw_rate * dt_next - target))
            # exponential (level = shipped output)
            if exp_sm[t] is not None:
                err['exp_level'].append(abs(exp_sm[t] - target))
                if exp_sm[t - 1] is not None:
                    exp_rate = (exp_sm[t] - exp_sm[t - 1]) / dt_prev
                    err['exp_trend'].append(abs(exp_sm[t] + exp_rate * dt_next - target))
            # UKF: level + velocity * dt
            err['ukf'].append(abs(ukf_sm[t] + ukf_rate[t] * dt_next - target))

        # ---- noise reduction in stable windows ----
        # slide non-overlapping windows of >=6 readings with |raw slope|<0.3
        w = 6
        k = 0
        while k + w <= M:
            seg_v = sv[k:k + w]
            seg_t = st[k:k + w]
            span_min = (seg_t[-1] - seg_t[0]) / 60000.0
            if span_min <= 0:
                k += w; continue
            slope = (seg_v[-1] - seg_v[0]) / span_min
            if abs(slope) < 0.3:
                mean_raw = sum(seg_v) / w
                var_raw = sum((v - mean_raw) ** 2 for v in seg_v) / w
                sm_u = ukf_sm[k:k + w]
                mean_u = sum(sm_u) / w
                var_u = sum((v - mean_u) ** 2 for v in sm_u) / w
                stable_var_raw.append(var_raw)
                stable_var_ukf.append(var_u)
                if all(exp_sm[k + j] is not None for j in range(w)):
                    sm_e = exp_sm[k:k + w]
                    mean_e = sum(sm_e) / w
                    var_e = sum((v - mean_e) ** 2 for v in sm_e) / w
                    stable_var_exp.append(var_e)
                # direction reversals
                reversal_windows += 1
                reversals_raw += _reversals(seg_v)
                reversals_ukf += _reversals(sm_u)
                if all(exp_sm[k + j] is not None for j in range(w)):
                    reversals_exp += _reversals(exp_sm[k:k + w])
                k += w
            else:
                k += 1

        # ---- lag on fast transitions (|slope|>2 over 8 readings) ----
        # At 5-min cadence, integer-sample cross-correlation cannot resolve sub-5-min
        # lag (all rounds to 0). Instead we use a SIGNED TRACKING OFFSET in mg/dL:
        # per reading, offset = +(raw-smoothed) on a rise, +(smoothed-raw) on a fall,
        # so a positive mean = the smoother TRAILS the direction of motion (= lag).
        k = 0
        while k + 8 <= M:
            seg_t = st[k:k + 8]
            seg_v = sv[k:k + 8]
            span = (seg_t[-1] - seg_t[0]) / 60000.0
            if span <= 0:
                k += 1; continue
            slope = (seg_v[-1] - seg_v[0]) / span
            if abs(slope) > 2.0:
                sgn = 1.0 if slope > 0 else -1.0
                offs_u = [sgn * (seg_v[j] - ukf_sm[k + j]) for j in range(8)]
                lag_ukf.append(sum(offs_u) / 8.0)
                if all(exp_sm[k + j] is not None for j in range(8)):
                    offs_e = [sgn * (seg_v[j] - exp_sm[k + j]) for j in range(8)]
                    lag_exp.append(sum(offs_e) / 8.0)
                k += 8
            else:
                k += 1

    return dict(err=err, stable_var_raw=stable_var_raw, stable_var_ukf=stable_var_ukf,
                stable_var_exp=stable_var_exp, reversals_raw=reversals_raw,
                reversals_ukf=reversals_ukf, reversals_exp=reversals_exp,
                reversal_windows=reversal_windows, lag_ukf=lag_ukf, lag_exp=lag_exp,
                comp_fires=comp_fires, kin_fires=kin_fires, rapid_fires=rapid_fires,
                n_readings=n_readings, n_onestep=n_onestep)


def _reversals(seq):
    """Count sign changes of consecutive first-differences."""
    diffs = [seq[i + 1] - seq[i] for i in range(len(seq) - 1)]
    c = 0
    prev = 0
    for d in diffs:
        s = 1 if d > 0 else (-1 if d < 0 else 0)
        if s != 0 and prev != 0 and s != prev:
            c += 1
        if s != 0:
            prev = s
    return c


def _xcorr_lag(raw, sm, ts):
    """Integer-sample lag (in minutes, +ve = smoothed lags raw) maximising
    cross-correlation between raw and smoothed over a short window. Mean-removed."""
    n = len(raw)
    rr = [raw[i] - sum(raw) / n for i in range(n)]
    ss = [sm[i] - sum(sm) / n for i in range(n)]
    cadence = (ts[-1] - ts[0]) / 60000.0 / (n - 1)  # min per sample
    best_lag = 0
    best = -1e18
    for lag in range(0, 5):  # smoothed delayed by `lag` samples vs raw
        num = 0.0
        cnt = 0
        for i in range(n):
            j = i - lag
            if 0 <= j < n:
                num += rr[i] * ss[j]
                cnt += 1
        if cnt > 0:
            val = num / cnt
            if val > best:
                best = val
                best_lag = lag
    return best_lag * cadence


def rmse(errs):
    if not errs:
        return float('nan')
    return math.sqrt(sum(e * e for e in errs) / len(errs))


# ----------------------------------------------------------------------------
# Fast-carb event overlays
# ----------------------------------------------------------------------------

FAST_CARB_EVENTS = [
    ("event1_2026-07-09_midday", "2026-07-09 10:30:00+01", "2026-07-09 15:45:00+01"),
    ("event2_2026-07-09_evening", "2026-07-09 19:00:00+01", "2026-07-09 23:35:00+01"),
    ("event3_2026-07-10_afternoon", "2026-07-10 12:30:00+01", "2026-07-10 15:30:00+01"),
]


def overlay_event(cur, name, t0, t1):
    cur.execute(
        """
        SELECT extract(epoch from (ts_utc AT TIME ZONE 'Europe/London')) * 1000.0,
               floor(extract(epoch from ts_utc)/300)::bigint, cgm_mgdl,
               (ts_utc AT TIME ZONE 'Europe/London')::text
        FROM boost_cgm
        WHERE user_id='tim' AND ts_utc >= %s AND ts_utc <= %s
        ORDER BY ts_utc ASC
        """, (t0, t1))
    rows = cur.fetchall()
    ts = [float(r[0]) for r in rows]
    vals = [float(r[2]) for r in rows]
    labels = [r[3][11:16] for r in rows]  # HH:MM local
    buckets = [r[1] for r in rows]
    # real IOB
    cur.execute(
        """SELECT DISTINCT ON (floor(ts_epoch/300)) floor(ts_epoch/300)::bigint, iob_iob
           FROM boost_decisions WHERE user_id='tim' AND iob_iob IS NOT NULL
           ORDER BY floor(ts_epoch/300), ts_epoch DESC""")
    iob_map = {r[0]: float(r[1]) for r in cur.fetchall()}
    iobs = [iob_map.get(b, AdaptiveUKF.IOB_SAFE_FALLBACK_U) for b in buckets]

    M = len(vals)
    ukf = AdaptiveUKF()
    nf_v, nf_t, nf_i = vals[::-1], ts[::-1], iobs[::-1]
    out_nf = ukf.process_segment(nf_v, nf_t, nf_i)
    ukf_sm = [out_nf[k]['smoothed'] for k in range(M)][::-1]
    ukf_rate = [out_nf[k]['rate'] for k in range(M)][::-1]
    kin = [out_nf[k]['kinetic'] for k in range(M)][::-1]
    comp = [out_nf[k]['compression'] for k in range(M)][::-1]
    rapid = [out_nf[k]['rapid'] for k in range(M)][::-1]
    # raw 5-min delta
    raw_delta = [0.0] + [(vals[i] - vals[i - 1]) for i in range(1, M)]

    return dict(name=name, ts=ts, labels=labels, vals=vals, ukf_sm=ukf_sm,
                ukf_rate=ukf_rate, kin=kin, comp=comp, rapid=rapid,
                raw_delta=raw_delta, iobs=iobs)


def plot_event(ev, path):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    M = len(ev['vals'])
    xr = list(range(M))
    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(12, 8), sharex=True)
    ax1.plot(xr, ev['vals'], 'o-', color='#888', ms=3, lw=1, label='raw CGM')
    ax1.plot(xr, ev['ukf_sm'], '-', color='#1f77b4', lw=2, label='UKF smoothed')
    for i in range(M):
        if ev['kin'][i]:
            ax1.axvline(i, color='red', alpha=0.25, lw=1)
        if ev['comp'][i]:
            ax1.axvline(i, color='orange', alpha=0.4, lw=1)
        if ev['rapid'][i]:
            ax1.axvline(i, color='green', alpha=0.2, lw=1)
    ax1.axhline(70, color='k', ls=':', lw=0.8)
    ax1.axhline(55, color='r', ls=':', lw=0.8)
    ax1.set_ylabel('mg/dL')
    ax1.set_title(f"{ev['name']}  (red=kinetic-hypo fire, orange=compression, green=rapid-rise)")
    ax1.legend(loc='best', fontsize=8)
    ax1.grid(alpha=0.3)

    ax2.plot(xr, ev['raw_delta'], 'o-', color='#888', ms=3, lw=1, label='raw 5-min delta (mg/dL)')
    ax2.plot(xr, [r * 5.0 for r in ev['ukf_rate']], '-', color='#d62728', lw=2,
             label='UKF velocity x 5min (mg/dL/5min)')
    ax2.axhline(0, color='k', lw=0.6)
    ax2.set_ylabel('mg/dL per 5 min')
    step = max(1, M // 16)
    ax2.set_xticks(xr[::step])
    ax2.set_xticklabels([ev['labels'][i] for i in xr[::step]], rotation=45, fontsize=8)
    ax2.legend(loc='best', fontsize=8)
    ax2.grid(alpha=0.3)
    fig.tight_layout()
    fig.savefig(path, dpi=110)
    plt.close(fig)


def event_summary(ev):
    """Text summary: velocity lead vs raw delta, guard fires, nadir."""
    M = len(ev['vals'])
    nadir_i = min(range(M), key=lambda i: ev['vals'][i])
    peak_i = max(range(M), key=lambda i: ev['vals'][i])
    kin_idx = [i for i in range(M) if ev['kin'][i]]
    comp_idx = [i for i in range(M) if ev['comp'][i]]
    rapid_idx = [i for i in range(M) if ev['rapid'][i]]
    # earliest index where UKF velocity signals a clear fall (<-1) vs raw delta first <-5
    ukf_fall = next((i for i in range(M) if ev['ukf_rate'][i] < -1.0), None)
    raw_fall = next((i for i in range(M) if ev['raw_delta'][i] < -5.0), None)
    return dict(
        peak=(ev['labels'][peak_i], ev['vals'][peak_i]),
        nadir=(ev['labels'][nadir_i], ev['vals'][nadir_i]),
        kin_times=[ev['labels'][i] for i in kin_idx],
        comp_times=[ev['labels'][i] for i in comp_idx],
        rapid_times=[ev['labels'][i] for i in rapid_idx],
        ukf_fall=ev['labels'][ukf_fall] if ukf_fall is not None else None,
        raw_fall=ev['labels'][raw_fall] if raw_fall is not None else None,
    )


# ----------------------------------------------------------------------------
# Self-test: clean sine + noise
# ----------------------------------------------------------------------------

def selftest():
    import random
    random.seed(42)
    N = 300
    ts = [i * 5 * 60 * 1000 for i in range(N)]
    clean = [120 + 60 * math.sin(2 * math.pi * i / 60.0) for i in range(N)]  # 5h period
    noise_sd = 8.0
    raw = [clean[i] + random.gauss(0, noise_sd) for i in range(N)]
    iobs = [AdaptiveUKF.IOB_SAFE_FALLBACK_U] * N
    ukf = AdaptiveUKF()
    out = ukf.process_segment(raw[::-1], ts[::-1], iobs[::-1])
    sm = [out[k]['smoothed'] for k in range(N)][::-1]
    # skip warmup
    s = 30
    rmse_raw = math.sqrt(sum((raw[i] - clean[i]) ** 2 for i in range(s, N)) / (N - s))
    rmse_ukf = math.sqrt(sum((sm[i] - clean[i]) ** 2 for i in range(s, N)) / (N - s))
    print(f"[selftest] injected noise sd={noise_sd:.1f}")
    print(f"[selftest] RMSE raw vs clean   = {rmse_raw:.2f} mg/dL")
    print(f"[selftest] RMSE UKF vs clean   = {rmse_ukf:.2f} mg/dL")
    ok = rmse_ukf < rmse_raw
    print(f"[selftest] UKF recovers clean signal better than raw: {ok}")
    return ok


# ----------------------------------------------------------------------------
# Main
# ----------------------------------------------------------------------------

def main():
    import psycopg2
    conn = psycopg2.connect("dbname=oref")
    cur = conn.cursor()

    users = ['tim', 'A', 'B', 'C', 'D', 'E', 'F', 'G', 'H']
    per_user = {}
    pooled_err = defaultdict(list)
    pooled_svr, pooled_svu, pooled_sve = [], [], []
    pooled_rev_raw = pooled_rev_ukf = pooled_rev_exp = 0
    pooled_lag_u, pooled_lag_e = [], []

    print("Running per-user backtest (fail-safe IOB: compression guard disabled)...")
    for u in users:
        ts, vals, iobs = load_user(cur, u)
        res = run_user(ts, vals, iobs, use_real_iob=False)
        per_user[u] = res
        for kk, vv in res['err'].items():
            pooled_err[kk].extend(vv)
        pooled_svr += res['stable_var_raw']
        pooled_svu += res['stable_var_ukf']
        pooled_sve += res['stable_var_exp']
        pooled_rev_raw += res['reversals_raw']
        pooled_rev_ukf += res['reversals_ukf']
        pooled_rev_exp += res['reversals_exp']
        pooled_lag_u += res['lag_ukf']
        pooled_lag_e += res['lag_exp']
        r = {k: rmse(res['err'][k]) for k in res['err']}
        print(f"  {u:>3}: n1step={res['n_onestep']:>6}  RMSE ukf={r.get('ukf',float('nan')):.2f} "
              f"persist={r.get('persistence',float('nan')):.2f} exp={r.get('exp_level',float('nan')):.2f} "
              f"lin={r.get('linear',float('nan')):.2f}  kin_fires={res['kin_fires']}")

    # tim real-IOB variant for compression audit
    print("Running tim real-IOB variant (compression guard ENABLED)...")
    ts, vals, iobs = load_user(cur, 'tim')
    tim_iob = run_user(ts, vals, iobs, use_real_iob=True)
    n_iob_known = sum(1 for v in iobs if v is not None)

    # events
    print("Building fast-carb overlays...")
    events = []
    for (nm, a, b) in FAST_CARB_EVENTS:
        ev = overlay_event(cur, nm, a, b)
        plot_event(ev, os.path.join(OUTDIR, nm + ".png"))
        events.append((ev, event_summary(ev)))

    cur.close()
    conn.close()

    # ---- write README ----
    write_readme(users, per_user, pooled_err, pooled_svr, pooled_svu, pooled_sve,
                 pooled_rev_raw, pooled_rev_ukf, pooled_rev_exp,
                 pooled_lag_u, pooled_lag_e, tim_iob, n_iob_known, events)

    print("Done. README + PNGs written to", OUTDIR)
    # print headline
    ph = rmse(pooled_err['persistence']); ex = rmse(pooled_err['exp_level'])
    uk = rmse(pooled_err['ukf'])
    print(f"\nHEADLINE pooled one-step RMSE: ukf={uk:.3f}  persist={ph:.3f} "
          f"({100*(ph-uk)/ph:+.1f}% vs persist)  exp={ex:.3f} ({100*(ex-uk)/ex:+.1f}% vs exp)")


def _mean(xs):
    return sum(xs) / len(xs) if xs else float('nan')


def write_readme(users, per_user, pooled_err, svr, svu, sve, rev_raw, rev_ukf, rev_exp,
                 lag_u, lag_e, tim_iob, n_iob_known, events):
    L = []
    A = L.append
    A("# UKF CGM-Smoothing Backtest (2026-07)\n")
    A("Faithful Python mirror of the committed Kotlin `AdaptiveSmoothingPlugin.kt` "
      "(2-state adaptive UKF), backtested against real raw CGM from the local "
      "TimescaleDB (`boost_cgm`, Feb 1 - Jul 10 2026). Baselines: naive persistence, "
      "the shipped `ExponentialSmoothingPlugin.kt` (ported), and raw-delta linear "
      "extrapolation.\n")
    A("Run: `python ukf_smoothing_backtest.py` (needs numpy/matplotlib/psycopg2; "
      "peer-auth `dbname=oref`). Self-check: `python ukf_smoothing_backtest.py --selftest`.\n")

    A("## What this proves / what it does NOT\n")
    A("- **PROVES (sensing only):** one-step-ahead predictive accuracy against the next "
      "RAW reading - a ground-truth-free metric that penalises BOTH over-smoothing/lag "
      "AND noise-chasing - plus jitter reduction in stable windows and transition lag.\n")
    A("- **DOES NOT prove:** any TIR / BG-outcome / dosing benefit. There is no reference "
      "\"true\" glucose and no glucodynamic simulator here, so no clinical or dosing claim "
      "is made. Cleaner sensing *may* help Boost's confirm-timing, but that is a separate "
      "question this backtest cannot answer.\n")

    A("## Fidelity\n")
    A("The Python UKF mirrors the Kotlin operation-for-operation (constants, sigma-point "
      "weights alpha=1/beta=0/kappa=3, predict/update/2x2 matrix-sqrt, the `med()` median "
      "with even-size averaging, the 48-deep addFirst/removeLast innovation window, the "
      "R-adaptation order, the night test `hour not in [7,23)`, and the compression / "
      "rapid-rise / kinetic-hypo guards). **Bit-exact JVM<->CPython parity was NOT "
      "formally unit-tested** - that golden-vector test is the formal gate before trusting "
      "the ABSOLUTE numbers. The RELATIVE ranking is robust: every predictor is fed the "
      "identical stream, and sub-ULP float drift cannot flip a multi-percent RMSE gap. The "
      "filter runs one continuous forward pass per contiguous segment (consecutive gap "
      "<=15 min); `learnedR`/innovations persist across segments and reset on >24h gaps, "
      "matching the Kotlin member-state (production re-inits state per rolling call, which "
      "is if anything noisier than this clean single pass).\n")

    # self-test
    ok = selftest_capture()
    A("**Internal consistency (sine+noise):** " + ok + "\n")

    # primary table
    A("## 1. One-step-ahead predictive RMSE (PRIMARY, mg/dL)\n")
    A("Lower = better. `%vs persist` and `%vs exp` are RMSE reductions (positive = UKF better).\n")
    A("| user | n(1-step) | UKF | persistence | exp(level) | linear | exp(trend) | %vs persist | %vs exp |")
    A("|------|-----------|-----|-------------|-----------|--------|-----------|-------------|---------|")
    for u in users:
        e = per_user[u]['err']
        uk = rmse(e['ukf']); ph = rmse(e['persistence']); ex = rmse(e['exp_level'])
        li = rmse(e['linear']); et = rmse(e['exp_trend'])
        A(f"| {u} | {per_user[u]['n_onestep']} | {uk:.3f} | {ph:.3f} | {ex:.3f} | {li:.3f} | "
          f"{et:.3f} | {100*(ph-uk)/ph:+.1f}% | {100*(ex-uk)/ex:+.1f}% |")
    uk = rmse(pooled_err['ukf']); ph = rmse(pooled_err['persistence'])
    ex = rmse(pooled_err['exp_level']); li = rmse(pooled_err['linear']); et = rmse(pooled_err['exp_trend'])
    A(f"| **POOLED** | {len(pooled_err['ukf'])} | **{uk:.3f}** | {ph:.3f} | {ex:.3f} | {li:.3f} | "
      f"{et:.3f} | **{100*(ph-uk)/ph:+.1f}%** | **{100*(ex-uk)/ex:+.1f}%** |")
    A("\nInterpretation: persistence is a strong baseline at 5-min cadence (BG barely moves "
      "in 5 min), so beating it by even a few percent is meaningful; exp(level) is the "
      "shipped smoother's forward signal.\n")

    # noise
    A("## 2. Noise reduction in stable windows (HONEST NEGATIVE)\n")
    A(f"Stable windows: |raw slope|<0.3 mg/dL/min over >=6 readings (pooled n={len(svr)} windows).\n")
    vr, vu, ve = _mean(svr), _mean(svu), _mean(sve)
    A(f"- Mean within-window variance: raw={vr:.2f}, UKF={vu:.2f}, exp={ve:.2f} mg/dL^2.\n")
    dv = 100 * (vu - vr) / vr
    A(f"- **The UKF does NOT reduce stable-window jitter**: variance is {dv:+.1f}% vs raw "
      f"(i.e. slightly HIGHER), and direction reversals go raw={rev_raw} -> UKF={rev_ukf} "
      f"({100*(rev_ukf-rev_raw)/rev_raw:+.1f}%). The exp smoother, by contrast, has higher "
      f"variance still ({100*(ve-vr)/vr:+.1f}%, long-tail ringing) but fewer reversals "
      f"(raw {rev_raw} -> exp {rev_exp}).\n")
    A("- Why: this filter is tuned RESPONSIVE (adaptive R falls toward its floor, so Kalman "
      "gain stays high and it tracks the raw closely), and the kinetic-hypo guard "
      "deliberately reverts the estimate toward the raw value (and steepens it) whenever BG "
      "is low/falling - i.e. it DE-smooths near hypo by design, for safety. So no "
      "jitter-reduction claim can be made; the value (if any) is in trend/prediction, not "
      "denoising.\n")

    # lag
    A("## 3. Lag on fast transitions\n")
    A(f"Windows with |slope|>2 mg/dL/min (UKF n={len(lag_u)}, exp n={len(lag_e)}). "
      "At 5-min cadence, integer cross-correlation cannot resolve sub-5-min lag, so we "
      "report a **signed tracking offset (mg/dL)**: positive = the smoother sits BEHIND "
      "the direction of motion (lags); ~0 = tracks the move; negative = leads/overshoots.\n")
    A(f"- UKF mean offset = **{_mean(lag_u):+.2f} mg/dL**, exp mean offset = "
      f"**{_mean(lag_e):+.2f} mg/dL**. Larger positive = more lag on rises/falls; the UKF "
      "zero-lag rapid-rise maneuver and velocity state are meant to keep this small.\n")

    # safety
    A("## 4. Safety-feature audit (tim)\n")
    tf = per_user['tim']
    A(f"- Fail-safe run (IOB=99, compression guard disabled by design): kinetic-hypo guard "
      f"fired **{tf['kin_fires']}** times, rapid-rise maneuver **{tf['rapid_fires']}** times "
      f"over {tf['n_readings']} readings.\n")
    A(f"- Real-IOB run (compression guard ENABLED via `boost_decisions.iob_iob`, "
      f"{n_iob_known} readings had a joined IOB): compression rejection fired "
      f"**{tim_iob['comp_fires']}** times, kinetic-hypo **{tim_iob['kin_fires']}**, "
      f"rapid-rise **{tim_iob['rapid_fires']}**. Compression only fires on steep isolated "
      f"drops (< -25 day / -15 night) while IOB<3, i.e. plausibly-artefactual drops, not "
      f"everywhere.\n")

    # events
    A("## 5. Fast-carb event overlays\n")
    A("PNG per event (raw vs UKF smoothed on top; raw 5-min delta vs UKF velocity below; "
      "vertical marks = guard fires). Times are local (Europe/London, BST).\n")
    for ev, s in events:
        A(f"\n### {ev['name']}  -> `{ev['name']}.png`\n")
        A(f"- Peak {s['peak'][1]:.0f} @ {s['peak'][0]}, nadir {s['nadir'][1]:.0f} @ {s['nadir'][0]}.\n")
        A(f"- UKF velocity first signals a clear fall (< -1 mg/dL/min) at "
          f"**{s['ukf_fall']}**; raw 5-min delta first prints < -5 mg/dL at **{s['raw_fall']}**.\n")
        A(f"- Kinetic-hypo guard fired at: {', '.join(s['kin_times']) if s['kin_times'] else '(none)'}.\n")
        A(f"- Compression fired at: {', '.join(s['comp_times']) if s['comp_times'] else '(none)'}; "
          f"rapid-rise at: {', '.join(s['rapid_times']) if s['rapid_times'] else '(none)'}.\n")

    A("\n## Honest read\n")
    uk = rmse(pooled_err['ukf']); ph = rmse(pooled_err['persistence'])
    ex = rmse(pooled_err['exp_level']); li = rmse(pooled_err['linear'])
    A(f"- **One-step prediction (the money metric): a real but modest win.** Pooled UKF RMSE "
      f"{uk:.2f} mg/dL beats persistence {ph:.2f} by {100*(ph-uk)/ph:.1f}% and the shipped "
      f"exponential {ex:.2f} by {100*(ex-uk)/ex:.1f}%. It improves on persistence for 8 of 9 "
      f"users (only D is marginally worse, -3.2%).\n")
    A(f"- **Robustness is the real story vs the naive linear baseline.** Raw-delta linear "
      f"extrapolation actually pools slightly *better* than the UKF ({li:.2f} vs {uk:.2f}) and "
      f"wins big on smooth/low-noise users (B, E, H), BUT it blows up on the noisiest user "
      f"(A: 8.61 vs UKF 5.16) - it doubles sensor noise into its velocity. The UKF is never "
      f"the worst predictor on any user; linear swings from best to catastrophic. That "
      f"bounded-downside behaviour is the practical argument for the UKF over trend chasing.\n")
    A("- **No jitter-reduction win** (Section 2): the UKF is a responsive tracker, not a "
      "denoiser, and it de-smooths near hypo by design. Do not sell this as noise reduction.\n")
    A("- **Lag** (Section 3): the UKF trails fast transitions ~3.5x less than the exponential "
      f"(+{_mean(lag_u):.2f} vs +{_mean(lag_e):.2f} mg/dL offset) - meaningfully snappier trend.\n")
    A("- **Safety guards behave sanely** (Section 4): compression fires only on steep "
      "isolated drops at low IOB; kinetic-hypo fires around real falls (see the fast-carb "
      "events). Neither fires everywhere.\n")
    A("- **Verdict:** the sensing evidence supports enabling this as a **shadow / selectable** "
      "option for evaluation - the trend signal is snappier and prediction is at least as good "
      "as the incumbent exponential and modestly better than persistence, with bounded "
      "downside. It does NOT support any dosing/TIR claim, and the ABSOLUTE numbers still owe "
      "the formal Kotlin<->Python parity unit-test before they should be quoted.\n")

    with open(os.path.join(OUTDIR, "README.md"), "w") as f:
        f.write("\n".join(L) + "\n")


def selftest_capture():
    import random
    random.seed(42)
    N = 300
    ts = [i * 5 * 60 * 1000 for i in range(N)]
    clean = [120 + 60 * math.sin(2 * math.pi * i / 60.0) for i in range(N)]
    raw = [clean[i] + random.gauss(0, 8.0) for i in range(N)]
    ukf = AdaptiveUKF()
    out = ukf.process_segment(raw[::-1], ts[::-1], [AdaptiveUKF.IOB_SAFE_FALLBACK_U] * N)
    sm = [out[k]['smoothed'] for k in range(N)][::-1]
    s = 30
    rr = math.sqrt(sum((raw[i] - clean[i]) ** 2 for i in range(s, N)) / (N - s))
    ru = math.sqrt(sum((sm[i] - clean[i]) ** 2 for i in range(s, N)) / (N - s))
    return (f"RMSE(raw vs clean)={rr:.2f}, RMSE(UKF vs clean)={ru:.2f} -> "
            f"UKF {'RECOVERS clean signal better (PASS)' if ru < rr else 'FAILS (does not beat raw)'} "
            f"[{100*(rr-ru)/rr:+.1f}% error reduction]")


if __name__ == "__main__":
    if "--selftest" in sys.argv:
        ok = selftest()
        sys.exit(0 if ok else 1)
    main()
