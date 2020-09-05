from math import sqrt, log

from creme.base import DriftDetector


class HDDM_W(DriftDetector):
    """
    Drift Detection Method based on Hoeffding’s bounds with moving weighted average-test.

    Parameters
    ----------
    drift_confidence : float (default=0.001)
        Confidence to the drift

    warning_confidence : float (default=0.005)
        Confidence to the warning

    lambda_option : float (default=0.050)
        The weight given to recent data. Smaller values mean less weight given to recent data.

    two_sided_test : bool (default=False)
        If True, will monitor error increments and decrements (two-sided). By default will only
        monitor error increments (one-sided).

    Notes
    -----
    HDDM_W is an online drift detection method based on McDiarmid's bounds. HDDM_W uses
    the EWMA statistic as estimator. It receives as input a stream of real predictions
    and returns the estimated status of the stream: STABLE, WARNING or DRIFT.

    Implementation based on MOA.

    References:
        1.  Frías-Blanco I, del Campo-Ávila J, Ramos-Jimenez G, et al.
            Online and non-parametric drift detection methods based on Hoeffding’s bounds.
            IEEE Transactions on Knowledge and Data Engineering, 2014, 27(3): 810-823.

        2. Albert Bifet, Geoff Holmes, Richard Kirkby, Bernhard Pfahringer.
           MOA: Massive Online Analysis; Journal of Machine Learning Research 11: 1601-1604, 2010.

    Examples
    --------
    >>> import numpy as np
    >>> from creme.drift import HDDM_W
    >>> np.random.seed(12345)

    >>> hddm_w = HDDM_W()

    >>> # Simulate a data stream as a normal distribution of 1's and 0's
    >>> data_stream = np.random.randint(2, size=2000)
    >>> # Change the data distribution from index 999 to 1500, simulating an
    >>> # increase in error rate (1 indicates error)
    >>> data_stream[999:1500] = 1

    >>> # Update drift detector and verify if change is detected
    >>> for i, val in enumerate(data_stream):
    ...     in_drift, in_warning = hddm_w.update(val)
    ...     if in_drift:
    ...         print(f"Change detected at index {i}, input value: {val}")
    Change detected at index 1011, input value: 1

    """

    class SampleInfo:
        def __init__(self):
            self.EWMA_estimator = -1.0
            self.independent_bounded_condition_sum = 0.

    def __init__(self,
                 drift_confidence=0.001,
                 warning_confidence=0.005,
                 lambda_option=0.050,
                 two_sided_test=False):
        super().__init__()
        super().reset()
        self.total = self.SampleInfo()
        self.sample1_decr_monitor = self.SampleInfo()
        self.sample1_incr_monitor = self.SampleInfo()
        self.sample2_decr_monitor = self.SampleInfo()
        self.sample2_incr_monitor = self.SampleInfo()
        self.incr_cutpoint = float("inf")
        self.decr_cutpoint = float("inf")
        self.width = 0
        self.delay = 0
        self.drift_confidence = drift_confidence
        self.warning_confidence = warning_confidence
        self.lambda_option = lambda_option
        self.two_sided_test = two_sided_test
        self.estimation = None

    def update(self, value):
        """Update the change detector with a single data point.

        Parameters
        ----------
        value: Input value (0 or 1)
            This parameter indicates whether the last sample analyzed was
            correctly classified or not. 1 indicates an error (miss-classification).

        Returns
        -------
        tuple
            A tuple (drift, warning) where its elements indicate if a drift or a warning is
            detected.

        """
        aux_decay_rate = 1.0 - self.lambda_option
        self.width += 1
        if self.total.EWMA_estimator < 0:
            self.total.EWMA_estimator = value
            self.total.independent_bounded_condition_sum = 1
        else:
            self.total.EWMA_estimator = self.lambda_option * \
                                        value + aux_decay_rate * self.total.EWMA_estimator
            self.total.independent_bounded_condition_sum = \
                self.lambda_option * self.lambda_option \
                + aux_decay_rate * aux_decay_rate * self.total.independent_bounded_condition_sum

        self._update_incr_statistics(value, self.drift_confidence)
        if self._monitor_mean_incr(self.drift_confidence):
            self.reset()
            self._in_concept_change = True
            self._in_warning_zone = False
        elif self._monitor_mean_incr(self.warning_confidence):
            self._in_concept_change = False
            self._in_warning_zone = True
        else:
            self._in_concept_change = False
            self._in_warning_zone = False

        self._update_decr_statistics(value, self.drift_confidence)
        if self.two_sided_test and self._monitor_mean_decr(self.drift_confidence):
            self.reset()
        self.estimation = self.total.EWMA_estimator

        return self._in_concept_change, self._in_warning_zone

    @staticmethod
    def _detect_mean_increment(sample1, sample2, confidence):
        if sample1.EWMA_estimator < 0 or sample2.EWMA_estimator < 0:
            return False
        ibc_sum = sample1.independent_bounded_condition_sum \
            + sample2.independent_bounded_condition_sum
        bound = sqrt(ibc_sum * log(1 / confidence) / 2)
        return sample2.EWMA_estimator - sample1.EWMA_estimator > bound

    def _monitor_mean_incr(self, confidence):
        return self._detect_mean_increment(
            self.sample1_incr_monitor,
            self.sample2_incr_monitor,
            confidence)

    def _monitor_mean_decr(self, confidence):
        return self._detect_mean_increment(
            self.sample2_decr_monitor,
            self.sample1_decr_monitor,
            confidence)

    def _update_incr_statistics(self, value, confidence):
        aux_decay = 1.0 - self.lambda_option
        bound = sqrt(self.total.independent_bounded_condition_sum * log(1.0 / confidence) / 2)

        if self.total.EWMA_estimator + bound < self.incr_cutpoint:
            self.incr_cutpoint = self.total.EWMA_estimator + bound
            self.sample1_incr_monitor.EWMA_estimator = self.total.EWMA_estimator
            self.sample1_incr_monitor.independent_bounded_condition_sum = \
                self.total.independent_bounded_condition_sum
            self.sample2_incr_monitor = self.SampleInfo()
            self.delay = 0
        else:
            self.delay += 1
            if self.sample2_incr_monitor.EWMA_estimator < 0:
                self.sample2_incr_monitor.EWMA_estimator = value
                self.sample2_incr_monitor.independent_bounded_condition_sum = 1
            else:
                self.sample2_incr_monitor.EWMA_estimator = self.lambda_option * \
                                                           value + aux_decay * \
                                                           self.sample2_incr_monitor.EWMA_estimator
                self.sample2_incr_monitor.independent_bounded_condition_sum = \
                    self.lambda_option * self.lambda_option + \
                    aux_decay * aux_decay * \
                    self.sample2_incr_monitor.independent_bounded_condition_sum

    def _update_decr_statistics(self, value, confidence):
        aux_decay = 1.0 - self.lambda_option
        epsilon = sqrt(self.total.independent_bounded_condition_sum * log(1.0 / confidence) / 2)

        if self.total.EWMA_estimator - epsilon > self.decr_cutpoint:
            self.decr_cutpoint = self.total.EWMA_estimator - epsilon
            self.sample1_decr_monitor.EWMA_estimator = self.total.EWMA_estimator
            self.sample1_decr_monitor.independent_bounded_condition_sum = \
                self.total.independent_bounded_condition_sum
            self.sample2_decr_monitor = self.SampleInfo()
        else:
            if self.sample2_decr_monitor.EWMA_estimator < 0:
                self.sample2_decr_monitor.EWMA_estimator = value
                self.sample2_decr_monitor.independent_bounded_condition_sum = 1
            else:
                self.sample2_decr_monitor.EWMA_estimator = \
                    self.lambda_option * value + aux_decay * \
                    self.sample2_decr_monitor.EWMA_estimator
                self.sample2_decr_monitor.independent_bounded_condition_sum = \
                    self.lambda_option * self.lambda_option \
                    + aux_decay * aux_decay \
                    * self.sample2_decr_monitor.independent_bounded_condition_sum

    def reset(self):
        """Reset the change detector.
        """
        super().reset()
        self.total = self.SampleInfo()
        self.sample1_decr_monitor = self.SampleInfo()
        self.sample1_incr_monitor = self.SampleInfo()
        self.sample2_decr_monitor = self.SampleInfo()
        self.sample2_incr_monitor = self.SampleInfo()
        self.incr_cutpoint = float("inf")
        self.decr_cutpoint = float("inf")
        self.width = 0
        self.delay = 0
