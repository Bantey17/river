from operator import attrgetter

from creme import base
from creme import linear_model

from ._base_tree import DecisionTree
from ._split_criterion import VarianceReductionSplitCriterion
from ._nodes import ActiveLeaf
from ._nodes import SplitNode
from ._nodes import LearningNode
from ._nodes import ActiveLearningNodeMean
from ._nodes import InactiveLearningNodeMean
from ._nodes import ActiveLearningNodeModel
from ._nodes import InactiveLearningNodeModel
from ._nodes import ActiveLearningNodeAdaptive
from ._nodes import InactiveLearningNodeAdaptive


class HoeffdingTreeRegressor(DecisionTree, base.Regressor):
    """ Hoeffding Tree regressor.

    Parameters
    ----------
    grace_period
        Number of instances a leaf should observe between split attempts.
    split_confidence
        Allowed error in split decision, a value closer to 0 takes longer to decide.
    tie_threshold
        Threshold below which a split will be forced to break ties.
    binary_split:
        If True, only allow binary splits.
    leaf_prediction
        | Prediction mechanism used at leafs.
        | 'mean' - Target mean
        | 'model' - Uses the model defined in `leaf_model`
        | 'adaptive' - Chooses between 'mean' and 'model' dynamically
    leaf_model
        The regression model used to provide responses if `leaf_prediction='model'`.
    model_selector_decay
        The exponential decaying factor applied to the learning models' squared errors, that
        are monitored if `leaf_prediction='adaptive'`. Must be between `0` and `1`. The closer
        to `1`, the more importance is going to be given to past observations. On the other hand,
        if its value approaches `0`, the recent observed errors are going to have more influence
        on the final decision.
    nominal_attributes
        List of Nominal attributes identifiers. If empty, then assume that all numeric attributes
        should be treated as continuous.
    **kwargs
        Other parameters passed to river.tree.DecisionTree.

    Notes
    -----
    The Hoeffding Tree Regressor (HTR) is an adaptation of the incremental tree algorithm of the
    same name for classification. Similarly to its classification counterpart, HTR uses the
    Hoeffding bound to control its split decisions. Differently from the classification algorithm,
    HTR relies on calculating the reduction of variance in the target space to decide among the
    split candidates. The smallest the variance at its leaf nodes, the more homogeneous the
    partitions are. At its leaf nodes, HTR fits either linear models or uses the target
    average as the predictor.

    Examples
    --------
    >>> # Imports
    >>> from skmultiflow.data import RegressionGenerator
    >>> from skmultiflow.trees import HoeffdingTreeRegressor
    >>> import numpy as np
    >>>
    >>> # Setup a data stream
    >>> stream = RegressionGenerator(random_state=1, n_samples=200)
    >>>
    >>> # Setup the Hoeffding Tree Regressor
    >>> ht_reg = HoeffdingTreeRegressor()
    >>>
    >>> # Auxiliary variables to control loop and track performance
    >>> n_samples = 0
    >>> max_samples = 200
    >>> y_pred = np.zeros(max_samples)
    >>> y_true = np.zeros(max_samples)
    >>>
    >>> # Run test-then-train loop for max_samples and while there is data
    >>> while n_samples < max_samples and stream.has_more_samples():
    >>>     X, y = stream.next_sample()
    >>>     y_true[n_samples] = y[0]
    >>>     y_pred[n_samples] = ht_reg.predict(X)[0]
    >>>     ht_reg.partial_fit(X, y)
    >>>     n_samples += 1
    >>>
    >>> # Display results
    >>> print('{} samples analyzed.'.format(n_samples))
    >>> print('Hoeffding Tree regressor mean absolute error: {}'.
    >>>       format(np.mean(np.abs(y_true - y_pred))))
    """

    _TARGET_MEAN = 'mean'
    _MODEL = 'model'
    _ADAPTIVE = 'adaptive'

    def __init__(self,
                 grace_period: int = 200,
                 split_confidence: float = 1e-7,
                 tie_threshold: float = 0.05,
                 binary_split: bool = False,
                 leaf_prediction: str = 'model',
                 leaf_model: base.Regressor = linear_model.LinearRegression(),
                 model_selector_decay: float = 0.95,
                 nominal_attributes: list = None,
                 **kwargs):
        super().__init__(**kwargs)

        self._split_criterion = 'vr'
        self.grace_period = grace_period
        self.split_confidence = split_confidence
        self.tie_threshold = tie_threshold
        self.binary_split = binary_split
        self.leaf_prediction = leaf_prediction
        self.leaf_model = leaf_model
        self.model_selector_decay = model_selector_decay
        self.nominal_attributes = nominal_attributes

    @DecisionTree.leaf_prediction.setter
    def leaf_prediction(self, leaf_prediction):
        if leaf_prediction not in {self._TARGET_MEAN, self._MODEL, self._ADAPTIVE}:
            print('Invalid leaf_prediction option "{}", will use default "{}"'.
                  format(leaf_prediction, self._MODEL))
            self._leaf_prediction = self._MODEL
        else:
            self._leaf_prediction = leaf_prediction

    @DecisionTree.split_criterion.setter
    def split_criterion(self, split_criterion):
        if split_criterion != 'vr':   # variance reduction
            print("Invalid split_criterion option {}', will use default '{}'".
                  format(split_criterion, 'vr'))
            self._split_criterion = 'vr'
        else:
            self._split_criterion = split_criterion

    def _new_learning_node(self, initial_stats=None, parent=None, is_active=True):
        """Create a new learning node.

        The type of learning node depends on the tree configuration.
        """
        if initial_stats is None:
            initial_stats = {}

        if parent is not None:
            depth = parent.depth + 1
        else:
            depth = 0

        if self.leaf_prediction in {self._MODEL, self._ADAPTIVE}:
            # TODO: change to appropriate 'clone' method
            leaf_model = self.leaf_model.__class__(**self.leaf_model._get_params())

        if is_active:
            if self.leaf_prediction == self._TARGET_MEAN:
                return ActiveLearningNodeMean(initial_stats, depth)
            elif self.leaf_prediction == self._MODEL:
                return ActiveLearningNodeModel(initial_stats, depth, leaf_model)
            else:  # adaptive learning node
                return ActiveLearningNodeAdaptive(initial_stats, depth, leaf_model)
        else:
            if self.leaf_prediction == self._TARGET_MEAN:
                return InactiveLearningNodeMean(initial_stats, depth)
            elif self.leaf_prediction == self._MODEL:
                return InactiveLearningNodeModel(initial_stats, depth, leaf_model)
            else:  # adaptive learning node
                return InactiveLearningNodeAdaptive(initial_stats, depth, leaf_model)

    def learn_one(self, x, y, *, sample_weight=1.):
        """Train the tree model on sample x and corresponding target y.

        Parameters
        ----------
        x
            Instance attributes.
        y
            Target value for sample x.
        sample_weight
            The weight of the sample.
        """

        if self._tree_root is None:
            self._tree_root = self._new_learning_node()
            self._n_active_leaves = 1

        found_node = self._tree_root.filter_instance_to_leaf(x, None, -1)
        leaf_node = found_node.node

        if leaf_node is None:
            leaf_node = self._new_learning_node()
            found_node.parent.set_child(found_node.parent_branch, leaf_node)
            self._n_active_leaves += 1

        if isinstance(leaf_node, LearningNode):
            leaf_node.learn_one(x, y, sample_weight=sample_weight, tree=self)
            if self._growth_allowed and isinstance(leaf_node, ActiveLeaf):
                if leaf_node.depth >= self.max_depth:  # Max depth reached
                    self._deactivate_leaf(leaf_node, found_node.parent, found_node.parent_branch)
                else:
                    weight_seen = leaf_node.total_weight
                    weight_diff = weight_seen - leaf_node.last_split_attempt_at
                    if weight_diff >= self.grace_period:
                        self._attempt_to_split(leaf_node, found_node.parent,
                                               found_node.parent_branch)
                        leaf_node.last_split_attempt_at = weight_seen
        # Split node encountered a previously unseen categorical value (in a multi-way test),
        # so there is no branch to sort the instance to
        elif isinstance(leaf_node, SplitNode):
            current = leaf_node
            leaf_node = self._new_learning_node(parent=current)
            branch_id = current.split_test.add_new_branch(
                x[current.split_test.get_atts_test_depends_on()[0]]
            )
            current.set_child(branch_id, leaf_node)
            self._n_active_leaves += 1
            leaf_node.learn_one(x, y, sample_weight=sample_weight, tree=self)

        if self._train_weight_seen_by_model % self.memory_estimate_period == 0:
            self._estimate_model_size()

    def predict_one(self, x):
        """Predict the target value using one of the leaf prediction strategies.

        Parameters
        ----------
        x
            Instance for which we want to predict the target.

        Returns
        -------
            Predicted target value.

        """
        if self._tree_root is not None:
            node = self._tree_root.filter_instance_to_leaf(x, None, -1).node
            if node.is_leaf():
                return node.predict_one(x, tree=self)
            else:
                # The instance sorting ended up in a Split Node, since no branch was found
                # for some of the instance's features. Use the mean prediction in this case
                return node.stats[1] / node.stats[0]
        else:
            # Model is empty
            return 0.

    def _attempt_to_split(self, node: ActiveLeaf, parent: SplitNode, parent_idx: int):
        """Attempt to split a node.

        If the target's variance is high at the leaf node, then:

        1. Find split candidates and select the top 2.
        2. Compute the Hoeffding bound.
        3. If the ratio between the merit of the second best split candidate and the merit of the
        best one is smaller than 1 minus the Hoeffding bound (or a tie breaking decision
        takes place), then:
           3.1 Replace the leaf node by a split node.
           3.2 Add a new leaf node on each branch of the new split node.
           3.3 Update tree's metrics

        Optional: Disable poor attribute. Depends on the tree's configuration.

        Parameters
        ----------
        node
            The node to evaluate.
        parent
            The node's parent in the tree.
        parent_idx
            Parent node's branch index.

        """
        split_criterion = VarianceReductionSplitCriterion()
        best_split_suggestions = node.get_best_split_suggestions(split_criterion, self)
        best_split_suggestions.sort(key=attrgetter('merit'))
        should_split = False
        if len(best_split_suggestions) < 2:
            should_split = len(best_split_suggestions) > 0
        else:
            hoeffding_bound = self._hoeffding_bound(
                split_criterion.get_range_of_merit(node.stats), self.split_confidence,
                node.total_weight)
            best_suggestion = best_split_suggestions[-1]
            second_best_suggestion = best_split_suggestions[-2]
            if best_suggestion.merit > 0.0 and \
                    (second_best_suggestion.merit / best_suggestion.merit < 1 - hoeffding_bound
                        or hoeffding_bound < self.tie_threshold):
                should_split = True
            if self.remove_poor_atts:
                poor_atts = set()
                best_ratio = second_best_suggestion.merit / best_suggestion.merit

                # Add any poor attribute to set
                for i in range(len(best_split_suggestions)):
                    if best_split_suggestions[i].split_test is not None:
                        split_atts = best_split_suggestions[i].split_test.\
                            get_atts_test_depends_on()
                        if len(split_atts) == 1:
                            if (best_split_suggestions[i].merit / best_suggestion.merit
                                    < best_ratio - 2 * hoeffding_bound):
                                poor_atts.add(split_atts[0])
                for poor_att in poor_atts:
                    node.disable_attribute(poor_att)
        if should_split:
            split_decision = best_split_suggestions[-1]
            if split_decision.split_test is None:
                # Preprune - null wins
                self._deactivate_leaf(node, parent, parent_idx)
            else:
                new_split = self._new_split_node(split_decision.split_test, node.stats, node.depth)
                for i in range(split_decision.num_splits()):
                    new_child = self._new_learning_node(
                        split_decision.resulting_stats_from_split(i), node)
                    new_split.set_child(i, new_child)
                self._n_active_leaves -= 1
                self._n_decision_nodes += 1
                self._n_active_leaves += split_decision.num_splits()
                if parent is None:
                    self._tree_root = new_split
                else:
                    parent.set_child(parent_idx, new_split)

            # Manage memory
            self._enforce_size_limit()
        elif len(best_split_suggestions) >= 2 and best_split_suggestions[-1].merit > 0 and \
                best_split_suggestions[-2].merit > 0:
            last_check_ratio = best_split_suggestions[-2].merit / best_split_suggestions[-1].merit
            last_check_vr = best_split_suggestions[-1].merit

            node.manage_memory(split_criterion, last_check_ratio, last_check_vr, hoeffding_bound)
