from river.utils.skmultiflow_utils import add_dict_values, normalize_values_in_dict

from ._nodes import (
    AdaLearningNodeClassifier,
    AdaSplitNodeClassifier,
    FoundNode,
    LearningNode,
    SplitNode,
)
from .hoeffding_tree_classifier import HoeffdingTreeClassifier
from .splitter import Splitter


class HoeffdingAdaptiveTreeClassifier(HoeffdingTreeClassifier):
    """Hoeffding Adaptive Tree classifier.

    Parameters
    ----------
    grace_period
        Number of instances a leaf should observe between split attempts.
    max_depth
        The maximum depth a tree can reach. If `None`, the tree will grow indefinitely.
    split_criterion
        Split criterion to use.</br>
        - 'gini' - Gini</br>
        - 'info_gain' - Information Gain</br>
        - 'hellinger' - Helinger Distance</br>
    split_confidence
        Allowed error in split decision, a value closer to 0 takes longer to decide.
    tie_threshold
        Threshold below which a split will be forced to break ties.
    leaf_prediction
        Prediction mechanism used at leafs.</br>
        - 'mc' - Majority Class</br>
        - 'nb' - Naive Bayes</br>
        - 'nba' - Naive Bayes Adaptive</br>
    nb_threshold
        Number of instances a leaf should observe before allowing Naive Bayes.
    nominal_attributes
        List of Nominal attributes. If empty, then assume that all numeric attributes should
        be treated as continuous.
    splitter
        The Splitter or Attribute Observer (AO) used to monitor the class statistics of numeric
        features and perform splits. Splitters are available in the `tree.splitter` module.
        Different splitters are available for classification and regression tasks. Classification
        and regression splitters can be distinguished by their property `is_target_class`.
        This is an advanced option. Special care must be taken when choosing different splitters.
        By default, `tree.splitter.GaussianSplitter` is used if `splitter` is `None`.
    bootstrap_sampling
        If True, perform bootstrap sampling in the leaf nodes.
    drift_window_threshold
        Minimum number of examples an alternate tree must observe before being considered as a
        potential replacement to the current one.
    adwin_confidence
        The delta parameter used in the nodes' ADWIN drift detectors.
    seed
       If int, `seed` is the seed used by the random number generator;</br>
       If RandomState instance, `seed` is the random number generator;</br>
       If None, the random number generator is the RandomState instance used
       by `np.random`. Only used when `bootstrap_sampling=True` to direct the
       bootstrap sampling.</br>
    kwargs
        Other parameters passed to `tree.HoeffdingTree`. Check the `tree` module documentation
        for more information.

    Notes
    -----
    The Hoeffding Adaptive Tree [^1] uses ADWIN [^2] to monitor performance of branches on the tree
    and to replace them with new branches when their accuracy decreases if the new branches are
    more accurate.

    The bootstrap sampling strategy is an improvement over the original Hoeffding Adaptive Tree
    algorithm. It is enabled by default since, in general, it results in better performance.

    References
    ----------
    [^1]: Bifet, Albert, and Ricard Gavaldà. "Adaptive learning from evolving data streams."
       In International Symposium on Intelligent Data Analysis, pp. 249-260. Springer, Berlin,
       Heidelberg, 2009.
    [^2]: Bifet, Albert, and Ricard Gavaldà. "Learning from time-changing data with adaptive
       windowing." In Proceedings of the 2007 SIAM international conference on data mining,
       pp. 443-448. Society for Industrial and Applied Mathematics, 2007.

    Examples
    --------
    >>> from river import synth
    >>> from river import evaluate
    >>> from river import metrics
    >>> from river import tree

    >>> gen = synth.ConceptDriftStream(stream=synth.SEA(seed=42, variant=0),
    ...                                drift_stream=synth.SEA(seed=42, variant=1),
    ...                                seed=1, position=500, width=50)
    >>> # Take 1000 instances from the infinite data generator
    >>> dataset = iter(gen.take(1000))

    >>> model = tree.HoeffdingAdaptiveTreeClassifier(
    ...     grace_period=100,
    ...     split_confidence=1e-5,
    ...     leaf_prediction='nb',
    ...     nb_threshold=10,
    ...     seed=0
    ... )

    >>> metric = metrics.Accuracy()

    >>> evaluate.progressive_val_score(dataset, model, metric)
    Accuracy: 91.09%

    """

    # =============================================
    # == Hoeffding Adaptive Tree implementation ===
    # =============================================

    def __init__(
        self,
        grace_period: int = 200,
        max_depth: int = None,
        split_criterion: str = "info_gain",
        split_confidence: float = 1e-7,
        tie_threshold: float = 0.05,
        leaf_prediction: str = "nba",
        nb_threshold: int = 0,
        nominal_attributes: list = None,
        splitter: Splitter = None,
        bootstrap_sampling: bool = True,
        drift_window_threshold: int = 300,
        adwin_confidence: float = 0.002,
        seed=None,
        **kwargs
    ):

        super().__init__(
            grace_period=grace_period,
            max_depth=max_depth,
            split_criterion=split_criterion,
            split_confidence=split_confidence,
            tie_threshold=tie_threshold,
            leaf_prediction=leaf_prediction,
            nb_threshold=nb_threshold,
            nominal_attributes=nominal_attributes,
            splitter=splitter,
            **kwargs
        )

        self._n_alternate_trees = 0
        self._n_pruned_alternate_trees = 0
        self._n_switch_alternate_trees = 0

        self.bootstrap_sampling = bootstrap_sampling
        self.drift_window_threshold = drift_window_threshold
        self.adwin_confidence = adwin_confidence
        self.seed = seed

    def learn_one(self, x, y, *, sample_weight=1.0):
        # Updates the set of observed classes
        self.classes.add(y)

        self._train_weight_seen_by_model += sample_weight

        if self._tree_root is None:
            self._tree_root = self._new_learning_node()
            self._n_active_leaves = 1
        self._tree_root.learn_one(
            x, y, sample_weight=sample_weight, tree=self, parent=None, parent_branch=-1
        )

        if self._train_weight_seen_by_model % self.memory_estimate_period == 0:
            self._estimate_model_size()

        return self

    # Override HoeffdingTreeClassifier
    def predict_proba_one(self, x):
        proba = {c: 0.0 for c in self.classes}
        if self._tree_root is not None:
            found_nodes = self._filter_instance_to_leaves(x, None, -1)
            for fn in found_nodes:
                # parent_branch == -999 means that the node is the root of an alternate tree.
                # In other words, the alternate tree is a single leaf. It is probably not accurate
                # enough to be used to predict, so skip it
                if fn.parent_branch != -999:
                    leaf_node = fn.node
                    if leaf_node is None:
                        leaf_node = fn.parent
                    dist = leaf_node.leaf_prediction(x, tree=self)
                    # Option Tree prediction (of sorts): combine the response of all leaves reached
                    # by the instance
                    proba = add_dict_values(proba, dist, inplace=True)
            proba = normalize_values_in_dict(proba)

        return proba

    def _filter_instance_to_leaves(self, x, split_parent, parent_branch):
        nodes = []
        self._tree_root.filter_instance_to_leaves(x, split_parent, parent_branch, nodes)
        return nodes

    def _new_learning_node(self, initial_stats=None, parent=None):
        if parent is not None:
            depth = parent.depth + 1
        else:
            depth = 0

        return AdaLearningNodeClassifier(
            stats=initial_stats,
            depth=depth,
            splitter=self.splitter,
            adwin_delta=self.adwin_confidence,
            seed=self.seed,
        )

    def _new_split_node(self, split_test, target_stats=None, depth=0, **kwargs):
        return AdaSplitNodeClassifier(
            split_test=split_test,
            stats=target_stats,
            depth=depth,
            adwin_delta=self.adwin_confidence,
            seed=self.seed,
        )

    # Override river.tree.BaseHoeffdingTree to include alternate trees
    def __find_learning_nodes(self, node, parent, parent_branch, found):
        if node is not None:
            if isinstance(node, LearningNode):
                found.append(FoundNode(node, parent, parent_branch))
            if isinstance(node, SplitNode):
                split_node = node

                for i in range(split_node.n_children):
                    self.__find_learning_nodes(
                        split_node.get_child(i), split_node, i, found
                    )
                if split_node._alternate_tree is not None:  # noqa
                    self.__find_learning_nodes(
                        split_node._alternate_tree, split_node, -999, found  # noqa
                    )

    @classmethod
    def _unit_test_params(cls):
        return {"seed": 1}
