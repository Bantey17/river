<p align="center">
  <img height="200px" src="https://docs.google.com/drawings/d/e/2PACX-1vSl80T4MnWRsPX3KvlB2kn6zVdHdUleG_w2zBiLS7RxLGAHxiSYTnw3LZtXh__YMv6KcIOYOvkSt9PB/pub?w=447&h=182" alt="river_logo">
</p>

<p align="center">
  <!-- Travis -->
  <a href="https://travis-ci.org/river-ml/river">
    <img src="https://img.shields.io/travis/river-ml/river/master.svg?style=flat-square" alt="travis">
  </a>
  <!-- Codecov -->
  <a href="https://codecov.io/gh/river-ml/river">
    <img src="https://img.shields.io/codecov/c/gh/river-ml/river.svg?style=flat-square" alt="codecov">
  </a>
  <!-- Documentation -->
  <a href="https://river-ml.github.io/">
    <img src="https://img.shields.io/website?label=documentation&style=flat-square&url=https%3A%2F%2Friver-ml.github.io%2F" alt="documentation">
  </a>
  <!-- Gitter -->
  <a href="https://gitter.im/river-ml/community?utm_source=share-link&utm_medium=link&utm_campaign=share-link">
    <img src="https://img.shields.io/gitter/room/river-ml/community?color=blueviolet&style=flat-square" alt="gitter">
  </a>
  <!-- PyPI -->
  <a href="https://pypi.org/project/river">
    <img src="https://img.shields.io/pypi/v/river.svg?label=release&color=blue&style=flat-square" alt="pypi">
  </a>
  <!-- PePy -->
  <a href="https://pepy.tech/project/river">
    <img src="https://img.shields.io/badge/dynamic/json?style=flat-square&maxAge=86400&label=downloads&query=%24.total_downloads&url=https%3A%2F%2Fapi.pepy.tech%2Fapi%2Fprojects%2Friver" alt="pepy">
  </a>
  <!-- License -->
  <a href="https://opensource.org/licenses/BSD-3-Clause">
    <img src="https://img.shields.io/badge/License-BSD%203--Clause-blue.svg?style=flat-square" alt="bsd_3_license">
  </a>
</p>

<p align="center">
  River is a Python library for <a href="https://www.wikiwand.com/en/Online_machine_learning">online machine learning</a>. It is the result of a merger between <a href="https://github.com/MaxHalford/creme">creme</a> and <a href="https://github.com/scikit-multiflow/scikit-multiflow">scikit-multiflow</a>. River's ambition is to be the go-to library for doing machine learning on streaming data.
</p>

## ⚡️Quickstart

As a quick example, we'll train a logistic regression to classify the [website phishing dataset](http://archive.ics.uci.edu/ml/datasets/Website+Phishing). Here's a look at the first observation in the dataset.

```python
>>> from pprint import pprint
>>> from river import datasets

>>> dataset = datasets.Phishing()

>>> for x, y in dataset:
...     pprint(x)
...     print(y)
...     break
{'age_of_domain': 1,
 'anchor_from_other_domain': 0.0,
 'empty_server_form_handler': 0.0,
 'https': 0.0,
 'ip_in_url': 1,
 'is_popular': 0.5,
 'long_url': 1.0,
 'popup_window': 0.0,
 'request_from_other_domain': 0.0}
True

```

Now let's run the model on the dataset in a streaming fashion. We sequentially interleave predictions and model updates. Meanwhile, we update a performance metric to see how well the model is doing.

```python
>>> from river import compose
>>> from river import linear_model
>>> from river import metrics
>>> from river import preprocessing

>>> model = compose.Pipeline(
...     preprocessing.StandardScaler(),
...     linear_model.LogisticRegression()
... )

>>> metric = metrics.Accuracy()

>>> for x, y in dataset:
...     y_pred = model.predict_one(x)      # make a prediction
...     metric = metric.update(y, y_pred)  # update the metric
...     model = model.learn_one(x, y)      # make the model learn

>>> metric
Accuracy: 89.20%

```

## 🛠 Installation

`river` is intended to work with **Python 3.6 or above**. Installation can be done with `pip`:

```sh
pip install river
```

There are [wheels available](https://pypi.org/project/river/#files) for Linux, MacOS, and Windows, which means that in most cases you won't have to build `river` from source.

You can install the latest development version from GitHub as so:

```sh
pip install git+https://github.com/river-ml/river --upgrade
```

Or, through SSH:

```sh
pip install git+ssh://git@github.com/river-ml/river.git --upgrade
```

## 🧠 Philosophy

Machine learning is often done in a batch setting, whereby a model is fitted to a dataset in one go. This results in a static model which has to be retrained in order to learn from new data. In many cases, this isn't elegant nor efficient, and usually incurs [a fair amount of technical debt](https://research.google/pubs/pub43146/). Indeed, if you're using a batch model, then you need to think about maintaining a training set, monitoring real-time performance, model retraining, etc.

With `river`, we encourage a different approach, which is to continuously learn a stream of data. This means that the model process one observation at a time, and can therefore be updated on the fly. This allows to learn from massive datasets that don't fit in main memory. Online machine learning also integrates nicely in cases where new data is constantly arriving. It shines in many use cases, such as time series forecasting, spam filtering, recommender systems, CTR prediction, and IoT applications. If you're bored with retraining models and want to instead build dynamic models, then online machine learning (and therefore `river`!) might be what you're looking for.

Here are some benefits of using `river` (and online machine learning in general):

- **Incremental**: models can update themselves in real-time.
- **Adaptive**: models can adapt to [concept drift](https://www.wikiwand.com/en/Concept_drift).
- **Production-ready**: working with data streams makes it simple to replicate production scenarios during model development.
- **Efficient**: models don't have to be retrained and require little compute power, which [lowers their carbon footprint](https://arxiv.org/abs/1907.10597)
- **Fast**: when the goal is to learn and predict with a single instance at a time, then `river` is a order of magnitude faster than PyTorch, Tensorflow, and scikit-learn.

## 🔥 Features

- Linear models with a wide array of optimizers
- Nearest neighbors, decision trees, naïve Bayes
- [Progressive model validation](https://hunch.net/~jl/projects/prediction_bounds/progressive_validation/coltfinal.pdf)
- Model pipelines as a first-class citizen
- Anomaly detection
- Recommender systems
- Time series forecasting
- Imbalanced learning
- Clustering
- Feature extraction and selection
- Online statistics and metrics
- Built-in datasets
- And [much more](https://river-ml.github.io/content/api.html)

## 🔗 Useful links

- [Documentation](https://river-ml.github.io/)
- [Benchmarks](https://github.com/river-ml/river/tree/master/benchmarks)
- [Issue tracker](https://github.com/river-ml/river/issues)
- [Package releases](https://pypi.org/project/river/#history)

## 👁️ Media

- PyData Amsterdam 2019 presentation ([slides](https://maxhalford.github.io/slides/river-pydata/), [video](https://www.youtube.com/watch?v=P3M6dt7bY9U&list=PLGVZCDnMOq0q7_6SdrC2wRtdkojGBTAht&index=11))
- [Toulouse Data Science Meetup presentation](https://maxhalford.github.io/slides/river-tds/)
- [Machine learning for streaming data with river](https://towardsdatascience.com/machine-learning-for-streaming-data-with-river-dacf5fb469df)
- [Hong Kong Data Science Meetup presentation](https://maxhalford.github.io/slides/hkml2020.pdf)

## 👍 Contributing

Feel free to contribute in any way you like, we're always open to new ideas and approaches. You can also take a look at the [issue tracker](https://github.com/river-ml/river/issues) and the [icebox](https://github.com/river-ml/river/projects/2) to see if anything takes your fancy. Please check out the [contribution guidelines](https://github.com/river-ml/river/blob/master/CONTRIBUTING.md) if you want to bring modifications to the code base. You can view the list of people who have contributed [here](https://github.com/river-ml/river/graphs/contributors).

## 💬 Citation

Please use the following citation if you want to reference river in a scientific publication:

```
@software{river,
  title = {{river}, a {P}ython library for online machine learning},
  author = {Halford, Max and Bolmier, Geoffrey and Sourty, Raphael and Vaysse, Robin and Zouitine, Adil},
  url = {https://github.com/river-ml/river},
  version = {0.6.1},
  date = {2020-06-10},
  year = {2019}
}
```

Note that in the future we will probably publish a dedicated research paper.

## 📝 License

`river` is free and open-source software licensed under the [3-clause BSD license](https://github.com/river-ml/river/blob/master/LICENSE).
