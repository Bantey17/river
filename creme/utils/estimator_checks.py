"""Utilities for unit testing and sanity checking estimators."""
import copy
import functools
import math
import pickle
import random


__all__ = ['check_estimator']


def yield_datasets(model):

    from creme import compose
    from creme import datasets
    from creme import preprocessing
    from creme import stream
    from creme import utils
    from sklearn import datasets as sk_datasets

    # Classification
    if utils.inspect.isclassifier(model):
        yield datasets.Phishing()

        # Multi-class classification
        if model._multiclass:
            yield datasets.ImageSegments().take(500)

    # Regression
    if utils.inspect.isregressor(model):
        yield datasets.TrumpApproval()

    # Multi-output regression
    if utils.inspect.ismoregressor(model):

        # 1
        yield stream.iter_sklearn_dataset(sk_datasets.load_linnerud())

        # 2
        class SolarFlare:
            """One-hot encoded version of `datasets.SolarFlare`."""
            def __iter__(self):
                oh = (compose.SelectType(str) | preprocessing.OneHotEncoder()) + compose.SelectType(int)
                for x, y in datasets.SolarFlare():
                    yield oh.transform_one(x), y
        yield SolarFlare()

    # Multi-output classification
    if utils.inspect.ismoclassifier(model):
        yield datasets.Music()


def check_learn_one(model, dataset):

    klass = model.__class__

    for x, y in dataset:

        xx, yy = copy.deepcopy(x), copy.deepcopy(y)

        model = model.learn_one(x, y)

        # Check the model returns itself
        assert isinstance(model, klass)

        # Check learn_one is pure (i.e. x and y haven't changed)
        assert x == xx
        assert y == yy


def check_predict_proba_one(classifier, dataset):

    for x, y in dataset:

        xx, yy = copy.deepcopy(x), copy.deepcopy(y)

        classifier = classifier.learn_one(x, y)
        y_pred = classifier.predict_proba_one(x)

        # Check the probabilities are coherent
        assert isinstance(y_pred, dict)
        assert math.isclose(sum(y_pred.values()), 1.)
        for proba in y_pred.values():
            assert 0. <= proba <= 1.

        # Check predict_proba_one is pure (i.e. x and y haven't changed)
        assert x == xx
        assert y == yy


def check_predict_proba_one_binary(classifier, dataset):

    for x, y in dataset:
        y_pred = classifier.predict_proba_one(x)
        classifier = classifier.learn_one(x, y)
        assert set(y_pred.keys()) == {False, True}


def check_shuffling_no_impact(model, dataset):

    from creme import utils

    shuffled = copy.deepcopy(model)
    is_reg = utils.inspect.isregressor(model)
    is_moreg = utils.inspect.ismoregressor(model)

    for x, y in dataset:

        # Shuffle the features
        features = list(x.keys())
        random.shuffle(features)
        x_shuffled = {i: x[i] for i in features}

        assert x == x_shuffled  # order doesn't matter for dicts

        y_pred = model.predict_one(x)
        y_pred_shuffled = shuffled.predict_one(x_shuffled)

        if is_reg:
            try:
                assert math.isclose(y_pred, y_pred_shuffled)
            except AssertionError as e:

                for i in model['LinearRegression'].weights:
                    print(i, model['LinearRegression'].weights[i], shuffled['LinearRegression'].weights[i])

                print(y_pred, y_pred_shuffled)

                raise e
        elif is_moreg:
            for o in y_pred:
                assert math.isclose(y_pred[o], y_pred[o])
        else:
            assert y_pred == y_pred_shuffled

        model.learn_one(x, y)
        shuffled.learn_one(x_shuffled, y)


def check_debug_one(model, dataset):
    for x, y in dataset:
        model.debug_one(x)
        model.learn_one(x, y)
        model.debug_one(x)
        break


def check_pickling(model, dataset):
    assert isinstance(pickle.loads(pickle.dumps(model)), model.__class__)
    for x, y in dataset:
        model.predict_one(x)
        model.learn_one(x, y)
    assert isinstance(pickle.loads(pickle.dumps(model)), model.__class__)


def check_has_tag(model, tag):
    assert tag in model._tags


def check_repr(model):
    rep = repr(model)
    assert isinstance(rep, str)


def check_str(model):
    assert isinstance(str(model), str)


def check_tags(model):
    """Checks that the `_tags` property works."""
    assert isinstance(model._tags, set)


def check_set_params_idempotent(model):
    assert len(model.__dict__) == len(model._set_params().__dict__)


def check_init(model):
    try:
        params = model._default_params()
    except AttributeError:
        params = {}
    assert isinstance(model.__class__(**params), model.__class__)


def check_doc(model):
    assert model.__doc__


def wrapped_partial(func, *args, **kwargs):
    """

    Taken from http://louistiao.me/posts/adding-__name__-and-__doc__-attributes-to-functoolspartial-objects/

    """
    partial = functools.partial(func, *args, **kwargs)
    functools.update_wrapper(partial, func)
    return partial


def with_ignore_exception(func, exception):
    def f(*args, **kwargs):
        try:
            func(*args, **kwargs)
        except exception:
            pass
    f.__name__ = func.__name__
    return f


def yield_checks(model):
    """Generates unit tests for a given model.

    Parameters:
        model (base.Estimator)

    """

    from creme import utils

    # General checks
    yield check_repr
    yield check_str
    yield check_tags
    yield check_set_params_idempotent
    yield check_init
    yield check_doc

    # Checks that make use of datasets
    for dataset in yield_datasets(model):

        yield wrapped_partial(check_learn_one, dataset=dataset)
        yield wrapped_partial(check_pickling, dataset=dataset)
        if hasattr(model, 'debug_one'):
            yield wrapped_partial(check_debug_one, dataset=dataset)
        yield wrapped_partial(check_shuffling_no_impact, dataset=dataset)

        # Classifier checks
        if utils.inspect.isclassifier(model):

            # Some classifiers do not implement predict_proba_one
            yield with_ignore_exception(
                wrapped_partial(check_predict_proba_one, dataset=dataset),
                NotImplementedError
            )

            # Specific checks for binary classifiers
            if not model._multiclass:
                yield with_ignore_exception(
                    wrapped_partial(check_predict_proba_one_binary, dataset=dataset),
                    NotImplementedError
                )


def check_estimator(model):
    """Check if a model adheres to `creme`'s conventions.

    Parameters:
        model

    """
    for check in yield_checks(model):
        check(copy.deepcopy(model))
