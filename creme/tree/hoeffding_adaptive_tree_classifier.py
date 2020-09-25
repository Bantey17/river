from creme.tree import HoeffdingTreeClassifier
from creme.utils.skmultiflow_utils import add_dict_values
from creme.utils.math import softmax

from ._nodes import InactiveLeaf
from ._nodes import InactiveLearningNodeMC
from ._nodes import FoundNode
from ._nodes import SplitNode
from ._nodes import LearningNode
from ._nodes import AdaLearningNode
from ._nodes import AdaSplitNode


class HoeffdingAdaptiveTreeClassifier(HoeffdingTreeClassifier):
    """ Hoeffding Adaptive Tree classifier.

    Parameters
    ----------
    grace_period
        Number of instances a leaf should observe between split attempts.
    split_criterion
        | Split criterion to use.
        | 'gini' - Gini
        | 'info_gain' - Information Gain
        | 'hellinger' - Helinger Distance
    split_confidence
        Allowed error in split decision, a value closer to 0 takes longer to decide.
    tie_threshold
        Threshold below which a split will be forced to break ties.
    binary_split
        If True, only allow binary splits.
    leaf_prediction: string (default='nba')
        | Prediction mechanism used at leafs.
        | 'mc' - Majority Class
        | 'nb' - Naive Bayes
        | 'nba' - Naive Bayes Adaptive
    nb_threshold
        Number of instances a leaf should observe before allowing Naive Bayes.
    nominal_attributes: list, optional
        List of Nominal attributes. If empty, then assume that all numeric attributes should
        be treated as continuous.
    bootstrap_sampling
        If True, perform bootstrap sampling in the leaf nodes.
    drift_window_threshold
        Minimum number of examples an alternate tree must observe before being considered as a
        potential replacement to the current one.
    adwin_confidence
        The delta parameter used in the nodes' ADWIN drift detectors.
    random_state
       If int, random_state is the seed used by the random number generator;
       If RandomState instance, random_state is the random number generator;
       If None, the random number generator is the RandomState instance used
       by `np.random`. Only used when ``bootstrap_sampling=True`` to direct the bootstrap sampling.

    Notes
    -----
    The Hoeffding Adaptive Tree [^1] uses ADWIN [^2] to monitor performance of branches on the tree
    and to replace them with new branches when their accuracy decreases if the new branches are
    more accurate.

    The bootstrap sampling strategy is an improvement over the original Hoeffding Adaptive Tree
    algorithm. It is enabled by default since, in general, it results in better performance.

    References
    ----------
    .. [1] Bifet, Albert, and Ricard Gavaldà. "Adaptive learning from evolving data streams."
       In International Symposium on Intelligent Data Analysis, pp. 249-260. Springer, Berlin,
       Heidelberg, 2009.
    .. [2] Bifet, Albert, and Ricard Gavaldà. "Learning from time-changing data with adaptive
       windowing." In Proceedings of the 2007 SIAM international conference on data mining,
       pp. 443-448. Society for Industrial and Applied Mathematics, 2007.

    Examples
    --------
    >>> from skmultiflow.trees import HoeffdingAdaptiveTreeClassifier
    >>> from skmultiflow.data import ConceptDriftStream
    >>> from skmultiflow.evaluation import EvaluatePrequential
    >>> # Setup the File Stream
    >>> stream = ConceptDriftStream(random_state=123456, position=25000)
    >>>
    >>> classifier = HoeffdingAdaptiveTreeClassifier()
    >>> evaluator = EvaluatePrequential(pretrain_size=200, max_samples=50000, batch_size=1,
    >>>                                 n_wait=200, max_time=1000, output_file=None,
    >>>                                 show_plot=True, metrics=['kappa', 'kappa_t', 'accuracy'])
    >>>
    >>> evaluator.evaluate(stream=stream, model=classifier)

    """
    # =============================================
    # == Hoeffding Adaptive Tree implementation ===
    # =============================================

    def __init__(self,
                 grace_period=200,
                 split_criterion='info_gain',
                 split_confidence=1e-7,
                 tie_threshold=0.05,
                 binary_split=False,
                 leaf_prediction='nba',
                 nb_threshold=0,
                 nominal_attributes=None,
                 bootstrap_sampling=True,
                 adwin_confidence=0.002,
                 drift_window_threshold=300,
                 random_state=None,
                 **kwargs):

        super().__init__(grace_period=grace_period,
                         split_criterion=split_criterion,
                         split_confidence=split_confidence,
                         tie_threshold=tie_threshold,
                         binary_split=binary_split,
                         leaf_prediction=leaf_prediction,
                         nb_threshold=nb_threshold,
                         nominal_attributes=nominal_attributes,
                         **kwargs)

        self._n_alternate_trees = 0
        self._n_pruned_alternate_trees = 0
        self._n_switch_alternate_trees = 0

        self.bootstrap_sampling = bootstrap_sampling
        self.drift_window_threshold = drift_window_threshold
        self.adwin_confidence = adwin_confidence
        self.random_state = random_state

    def reset(self):
        super().reset()
        self._n_alternate_trees = 0
        self._n_pruned_alternate_trees = 0
        self._n_switch_alternate_trees = 0

    def learn_one(self, x, y, *, sample_weight=1.):
        if self._tree_root is None:
            self._tree_root = self._new_learning_node()
            self._n_active_leaves = 1
        if isinstance(self._tree_root, InactiveLeaf):
            self._tree_root.learn_one(x, y, weight=sample_weight, tree=self)
        else:
            self._tree_root.learn_one(x, y, sample_weight, self, None, -1)

    def _filter_instance_to_leaves(self, x, split_parent, parent_branch):
        nodes = []
        self._tree_root.filter_instance_to_leaves(x, split_parent, parent_branch, nodes)
        return nodes

    # Override HoeffdingTreeClassifier
    def predict_proba_one(self, x):
        proba = {}
        if self._tree_root is not None:
            if isinstance(self._tree_root, InactiveLeaf):
                found_nodes = [self._tree_root.filter_instance_to_leaf(x, None, -1)]
            else:
                found_nodes = self._filter_instance_to_leaves(x, None, -1)
            for fn in found_nodes:
                # parent_branch == -999 means that the node is the root of an alternate tree.
                # In other words, the alternate tree is a single leaf. It is probably not accurate
                # enough to be used to predict, so skip it
                if fn.parent_branch != -999:
                    leaf_node = fn.node
                    if leaf_node is None:
                        leaf_node = fn.parent
                    dist = leaf_node.predict_one(x, tree=self)
                    # Option Tree prediction (of sorts): combine the response of all leaves reached
                    # by the instance
                    proba = add_dict_values(proba, dist, inplace=True)
        return softmax(proba)

    # Override HoeffdingTreeClassifier
    def _new_learning_node(self, initial_stats=None, parent=None, is_active=True):
        if parent is not None:
            depth = parent.depth + 1
        else:
            depth = 0
        if is_active:
            return AdaLearningNode(
                initial_stats=initial_stats, depth=depth, adwin_delta=self.adwin_confidence,
                random_state=self.random_state)
        else:
            return InactiveLearningNodeMC(initial_stats, depth=depth)

    # Override HoeffdingTreeClassifier
    def _new_split_node(self, split_test, target_stats, depth):
        return AdaSplitNode(
            split_test=split_test, stats=target_stats, depth=depth,
            adwin_delta=self.adwin_confidence, random_state=self.random_state)

    # Override river.tree.DecisionTree to include alternate trees
    def __find_learning_nodes(self, node, parent, parent_branch, found):
        if node is not None:
            if isinstance(node, LearningNode):
                found.append(FoundNode(node, parent, parent_branch))
            if isinstance(node, SplitNode):
                split_node = node
                for i in range(split_node.n_children):
                    self.__find_learning_nodes(
                        split_node.get_child(i), split_node, i, found)
                if split_node._alternate_tree is not None:
                    self.__find_learning_nodes(
                        split_node._alternate_tree, split_node, -999, found)

    def _deactivate_leaf(self, to_deactivate, parent, parent_branch):
        new_leaf = self._new_learning_node(to_deactivate.stats, parent=parent, is_active=False)
        if parent is None:
            self._tree_root = new_leaf
        else:
            # Corner case where a leaf is the alternate tree
            if parent_branch == -999:
                new_leaf.depth -= 1  # To ensure we do not skip a tree level
                parent._alternate_tree = new_leaf

            else:
                parent.set_child(parent_branch, new_leaf)
        self._n_active_leaves -= 1
        self._n_inactive_leaves += 1

    def _activate_leaf(self, to_activate, parent, parent_branch):
        new_leaf = self._new_learning_node(to_activate.stats, parent=parent)
        if parent is None:
            self._tree_root = new_leaf
        else:
            if parent_branch == -999:
                new_leaf.depth -= 1  # To ensure we do not skip a tree level
                parent._alternate_tree = new_leaf
            else:
                parent.set_child(parent_branch, new_leaf)
        self._n_active_leaves += 1
        self._n_inactive_leaves -= 1
