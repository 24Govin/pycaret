# Module: Time Series
# Author: Antoni Baum <antoni.baum@protonmail.com>
# License: MIT
# Release: PyCaret 2.2.0
# Last modified : 25/10/2020

import time
from collections import defaultdict
from functools import partial

import numpy as np  # type: ignore
import pandas as pd  # type: ignore
from scipy.stats import rankdata  # type: ignore

from pycaret.internal.pycaret_experiment import TimeSeriesExperiment
from pycaret.internal.utils import check_if_global_is_not_none
from pycaret.internal.experiment_logger.experiment_logger import ExperimentLogger

from typing import List, Tuple, Any, Union, Optional, Dict, Generator
import warnings
import time

from sklearn.base import clone  # type: ignore
from sklearn.model_selection._validation import _aggregate_score_dicts  # type: ignore
from sklearn.model_selection import check_cv, ParameterGrid, ParameterSampler  # type: ignore
from sklearn.model_selection._search import _check_param_grid  # type: ignore
from sklearn.metrics._scorer import get_scorer, _PredictScorer  # type: ignore

from joblib import Parallel, delayed  # type: ignore

from sktime.utils.validation.forecasting import check_y_X  # type: ignore
from sktime.forecasting.model_selection import SlidingWindowSplitter  # type: ignore

warnings.filterwarnings("ignore")

_CURRENT_EXPERIMENT = None
_CURRENT_EXPERIMENT_EXCEPTION = (
    "_CURRENT_EXPERIMENT global variable is not set. Please run setup() first."
)
_CURRENT_EXPERIMENT_DECORATOR_DICT = {
    "_CURRENT_EXPERIMENT": _CURRENT_EXPERIMENT_EXCEPTION
}


def setup(
    data: Union[pd.Series, pd.DataFrame],
    preprocess: bool = True,
    imputation_type: str = "simple",
    #        transform_target: bool = False,
    #        transform_target_method: str = "box-cox",
    fold_strategy: Union[str, Any] = "timeseries",  # added in pycaret==2.2
    fold: int = 3,
    fh: Union[List[int], int, np.ndarray] = 1,
    seasonal_parameter: Optional[Union[int, str]] = None,
    n_jobs: Optional[int] = -1,
    use_gpu: bool = False,
    custom_pipeline: Union[
        Any, Tuple[str, Any], List[Any], List[Tuple[str, Any]]
    ] = None,
    html: bool = True,
    session_id: Optional[int] = None,
    log_experiment: bool = False,
    experiment_name: Optional[str] = None,
    loggers: Optional[List[ExperimentLogger]] = None,
    log_plots: Union[bool, list] = False,
    log_profile: bool = False,
    log_data: bool = False,
    verbose: bool = True,
    profile: bool = False,
    profile_kwargs: Dict[str, Any] = None,
):
    """
    This function initializes the training environment and creates the transformation
    pipeline. Setup function must be called before executing any other function. It takes
    two mandatory parameters: ``data`` and ``target``. All the other parameters are
    optional.

    Example
    -------
    >>> from pycaret.datasets import get_data
    >>> airline = get_data('airline')
    >>> from pycaret.time_series import setup
    >>> exp_name = setup(data=airline, fh=12)


    data : pandas.Series or pandas.DataFrame
        Shape (n_samples, 1), where n_samples is the number of samples.


    preprocess: bool, default = True
        When set to False, no transformations are applied except for train_test_split
        and custom transformations passed in ``custom_pipeline`` param. Data must be
        ready for modeling (no missing values, no dates, categorical data encoding),
        when preprocess is set to False.


    imputation_type: str, default = 'simple'
        The type of imputation to use. Can be either 'simple' or 'iterative'.


    fold_strategy: str or sklearn CV generator object, default = 'kfold'
        Choice of cross validation strategy. Possible values are:

        * 'expanding'
        * 'rolling'
        * 'sliding'


    fold: int, default = 3
        Number of folds to be used in cross validation. Must be at least 2. This is
        a global setting that can be over-written at function level by using ``fold``
        parameter. Ignored when ``fold_strategy`` is a custom object.


    fh: int, list or np.array, default = 1
        Number of steps ahead to take to evaluate forecast.


    seasonal_parameter: int or str, default = None
        Seasonal periods in timeseries data. If not provided the frequency of the data
        index is map to a seasonal period as follows:

        * "S": 60
        * "T": 60
        * 'H': 24
        * 'D': 7
        * 'W': 52
        * 'M': 12
        * 'Q': 4
        * 'A': 1
        * 'Y': 1

        Alternatively you can provide a custom seasonal parameter by passing it as an integer.


    n_jobs: int, default = -1
        The number of jobs to run in parallel (for functions that supports parallel
        processing) -1 means using all processors. To run all functions on single
        processor set n_jobs to None.


    use_gpu: bool or str, default = False
        When set to True, it will use GPU for training with algorithms that support it,
        and fall back to CPU if they are unavailable. When set to 'force', it will only
        use GPU-enabled algorithms and raise exceptions when they are unavailable. When
        False, all algorithms are trained using CPU only.

        GPU enabled algorithms:

        - Extreme Gradient Boosting, requires no further installation

        - CatBoost Regressor, requires no further installation
        (GPU is only enabled when data > 50,000 rows)

        - Light Gradient Boosting Machine, requires GPU installation
        https://lightgbm.readthedocs.io/en/latest/GPU-Tutorial.html

        - Linear Regression, Lasso Regression, Ridge Regression, K Neighbors Regressor,
        Random Forest, Support Vector Regression, Elastic Net requires cuML >= 0.15
        https://github.com/rapidsai/cuml


    custom_pipeline: (str, transformer) or list of (str, transformer), default = None
        When passed, will append the custom transformers in the preprocessing pipeline
        and are applied on each CV fold separately and on the final fit. All the custom
        transformations are applied after 'train_test_split' and before pycaret's internal
        transformations.


    html: bool, default = True
        When set to False, prevents runtime display of monitor. This must be set to False
        when the environment does not support IPython. For example, command line terminal,
        Databricks Notebook, Spyder and other similar IDEs.


    session_id: int, default = None
        Controls the randomness of experiment. It is equivalent to 'random_state' in
        scikit-learn. When None, a pseudo random number is generated. This can be used
        for later reproducibility of the entire experiment.


    log_experiment: bool, default = False
        When set to True, all metrics and parameters are logged on the ``MLFlow`` server.


    experiment_name: str, default = None
        Name of the experiment for logging. Ignored when ``log_experiment`` is not True.


    log_plots: bool or list, default = False
        When set to True, certain plots are logged automatically in the ``MLFlow`` server.
        To change the type of plots to be logged, pass a list containing plot IDs. Refer
        to documentation of ``plot_model``. Ignored when ``log_experiment`` is not True.


    log_profile: bool, default = False
        When set to True, data profile is logged on the ``MLflow`` server as a html file.
        Ignored when ``log_experiment`` is not True.


    log_data: bool, default = False
        When set to True, dataset is logged on the ``MLflow`` server as a csv file.
        Ignored when ``log_experiment`` is not True.


    verbose: bool, default = True
        When set to False, Information grid is not printed.


    profile: bool, default = False
        When set to True, an interactive EDA report is displayed.


    profile_kwargs: dict, default = {} (empty dict)
        Dictionary of arguments passed to the ProfileReport method used
        to create the EDA report. Ignored if ``profile`` is False.


    Returns:
        Global variables that can be changed using the ``set_config`` function.

    """

    exp = TimeSeriesExperiment()
    set_current_experiment(exp)
    return exp.setup(
        data=data,
        preprocess=preprocess,
        imputation_type=imputation_type,
        fold_strategy=fold_strategy,
        fold=fold,
        fh=fh,
        seasonal_period=seasonal_parameter,
        n_jobs=n_jobs,
        use_gpu=use_gpu,
        custom_pipeline=custom_pipeline,
        html=html,
        session_id=session_id,
        log_experiment=log_experiment,
        experiment_name=experiment_name,
        loggers=loggers,
        log_plots=log_plots,
        log_profile=log_profile,
        log_data=log_data,
        verbose=verbose,
        profile=profile,
        profile_kwargs=profile_kwargs,
    )


@check_if_global_is_not_none(globals(), _CURRENT_EXPERIMENT_DECORATOR_DICT)
def compare_models(
    include: Optional[List[Union[str, Any]]] = None,
    exclude: Optional[List[str]] = None,
    fold: Optional[Union[int, Any]] = None,
    round: int = 4,
    cross_validation: bool = True,
    sort: str = "smape",
    n_select: int = 1,
    budget_time: Optional[float] = None,
    turbo: bool = True,
    errors: str = "ignore",
    fit_kwargs: Optional[dict] = None,
    groups: Optional[Union[str, Any]] = None,
    verbose: bool = True,
):

    """
    This function trains and evaluates performance of all estimators available in the
    model library using cross validation. The output of this function is a score grid
    with average cross validated scores. Metrics evaluated during CV can be accessed
    using the ``get_metrics`` function. Custom metrics can be added or removed using
    ``add_metric`` and ``remove_metric`` function.


    Example
    --------
    >>> from pycaret.datasets import get_data
    >>> from pycaret.internal.pycaret_experiment import TimeSeriesExperiment
    >>> airline = get_data('airline', verbose=False)
    >>> fh, fold = np.arange(1,13), 3
    >>> exp = TimeSeriesExperiment()
    >>> exp.setup(data=airline, fh=fh, fold=fold)
    >>> master_display_exp = exp.compare_models(fold=fold, sort='mape')


    include: list of str or scikit-learn compatible object, default = None
        To train and evaluate select models, list containing model ID or scikit-learn
        compatible object can be passed in include param. To see a list of all models
        available in the model library use the ``models`` function.


    exclude: list of str, default = None
        To omit certain models from training and evaluation, pass a list containing
        model id in the exclude parameter. To see a list of all models available
        in the model library use the ``models`` function.


    fold: int or scikit-learn compatible CV generator, default = None
        Controls cross-validation. If None, the CV generator in the ``fold_strategy``
        parameter of the ``setup`` function is used. When an integer is passed,
        it is interpreted as the 'n_splits' parameter of the CV generator in the
        ``setup`` function.


    round: int, default = 4
        Number of decimal places the metrics in the score grid will be rounded to.


    cross_validation: bool, default = True
        When set to False, metrics are evaluated on holdout set. ``fold`` param
        is ignored when cross_validation is set to False.


    sort: str, default = 'smape'
        The sort order of the score grid. It also accepts custom metrics that are
        added through the ``add_metric`` function.


    n_select: int, default = 1
        Number of top_n models to return. For example, to select top 3 models use
        n_select = 3.


    budget_time: int or float, default = None
        If not None, will terminate execution of the function after budget_time
        minutes have passed and return results up to that point.


    turbo: bool, default = True
        When set to True, it excludes estimators with longer training times. To
        see which algorithms are excluded use the ``models`` function.


    errors: str, default = 'ignore'
        When set to 'ignore', will skip the model with exceptions and continue.
        If 'raise', will break the function when exceptions are raised.


    fit_kwargs: dict, default = {} (empty dict)
        Dictionary of arguments passed to the fit method of the model.


    groups: str or array-like, with shape (n_samples,), default = None
        Optional group labels when 'GroupKFold' is used for the cross validation.
        It takes an array with shape (n_samples, ) where n_samples is the number
        of rows in the training dataset. When string is passed, it is interpreted
        as the column name in the dataset containing group labels.


    verbose: bool, default = True
        Score grid is not printed when verbose is set to False.


    Returns:
        Trained model or list of trained models, depending on the ``n_select`` param.


    Warnings
    --------
    - Changing turbo parameter to False may result in very high training times with
      datasets exceeding 10,000 rows.

    - No models are logged in ``MLFlow`` when ``cross_validation`` parameter is False.

    """

    return _CURRENT_EXPERIMENT.compare_models(
        include=include,
        exclude=exclude,
        fold=fold,
        round=round,
        cross_validation=cross_validation,
        sort=sort,
        n_select=n_select,
        budget_time=budget_time,
        turbo=turbo,
        errors=errors,
        fit_kwargs=fit_kwargs,
        groups=groups,
        verbose=verbose,
    )


@check_if_global_is_not_none(globals(), _CURRENT_EXPERIMENT_DECORATOR_DICT)
def create_model(
    estimator: Union[str, Any],
    fold: Optional[Union[int, Any]] = None,
    round: int = 4,
    cross_validation: bool = True,
    fit_kwargs: Optional[dict] = None,
    verbose: bool = True,
    **kwargs,
):

    """
    This function trains and evaluates the performance of a given estimator
    using cross validation. The output of this function is a score grid with
    CV scores by fold. Metrics evaluated during CV can be accessed using the
    ``get_metrics`` function. Custom metrics can be added or removed using
    ``add_metric`` and ``remove_metric`` function. All the available models
    can be accessed using the ``models`` function.


    Example
    -------
    >>> from pycaret.datasets import get_data
    >>> airline = get_data('airline')
    >>> from pycaret.internal.pycaret_experiment import TimeSeriesExperiment
    >>> exp = TimeSeriesExperiment()
    >>> exp.setup(data=airline, fh=12)
    >>> model = exp.create_model("naive")

    TODO: Update
    estimator: str or scikit-learn compatible object
        ID of an estimator available in model library or pass an untrained
        model object consistent with scikit-learn API. Estimators available
        in the model library (ID - Name):

        * 'arima' - ARIMA
        * 'naive' - Naive
        * 'poly_trend' - PolyTrend
        * 'exp_smooth' - ExponentialSmoothing
        * 'theta' - Theta


    fold: int or scikit-learn compatible CV generator, default = None
        Controls cross-validation. If None, the CV generator in the ``fold_strategy``
        parameter of the ``setup`` function is used. When an integer is passed,
        it is interpreted as the 'n_splits' parameter of the CV generator in the
        ``setup`` function.


    round: int, default = 4
        Number of decimal places the metrics in the score grid will be rounded to.


    cross_validation: bool, default = True
        When set to False, metrics are evaluated on holdout set. ``fold`` param
        is ignored when cross_validation is set to False.


    fit_kwargs: dict, default = {} (empty dict)
        Dictionary of arguments passed to the fit method of the model.


    verbose: bool, default = True
        Score grid is not printed when verbose is set to False.


    **kwargs:
        Additional keyword arguments to pass to the estimator.


    Returns:
        Trained Model


    Warnings
    --------
    - Models are not logged on the ``MLFlow`` server when ``cross_validation`` param
      is set to False.

    """

    return _CURRENT_EXPERIMENT.create_model(
        estimator=estimator,
        fold=fold,
        round=round,
        cross_validation=cross_validation,
        fit_kwargs=fit_kwargs,
        groups=None,
        verbose=verbose,
        **kwargs,
    )


@check_if_global_is_not_none(globals(), _CURRENT_EXPERIMENT_DECORATOR_DICT)
def tune_model(
    estimator,
    fold: Optional[Union[int, Any]] = None,
    round: int = 4,
    n_iter: int = 10,
    custom_grid: Optional[Union[Dict[str, list], Any]] = None,
    optimize: str = "R2",
    custom_scorer=None,
    search_library: str = "scikit-learn",
    search_algorithm: Optional[str] = None,
    early_stopping: Any = False,
    early_stopping_max_iters: int = 10,
    choose_better: bool = False,
    fit_kwargs: Optional[dict] = None,
    return_tuner: bool = False,
    verbose: bool = True,
    tuner_verbose: Union[int, bool] = True,
    **kwargs,
):

    """
    This function tunes the hyperparameters of a given estimator. The output of
    this function is a score grid with CV scores by fold of the best selected
    model based on ``optimize`` parameter. Metrics evaluated during CV can be
    accessed using the ``get_metrics`` function. Custom metrics can be added
    or removed using ``add_metric`` and ``remove_metric`` function.


    Example
    -------
    >>> from pycaret.datasets import get_data
    >>> boston = get_data('boston')
    >>> from pycaret.regression import *
    >>> exp_name = setup(data = boston,  target = 'medv')
    >>> lr = create_model('lr')
    >>> tuned_lr = tune_model(lr)


    estimator: scikit-learn compatible object
        Trained model object


    fold: int or scikit-learn compatible CV generator, default = None
        Controls cross-validation. If None, the CV generator in the ``fold_strategy``
        parameter of the ``setup`` function is used. When an integer is passed,
        it is interpreted as the 'n_splits' parameter of the CV generator in the
        ``setup`` function.


    round: int, default = 4
        Number of decimal places the metrics in the score grid will be rounded to.


    n_iter: int, default = 10
        Number of iterations in the grid search. Increasing 'n_iter' may improve
        model performance but also increases the training time.


    custom_grid: dictionary, default = None
        To define custom search space for hyperparameters, pass a dictionary with
        parameter name and values to be iterated. Custom grids must be in a format
        supported by the defined ``search_library``.


    optimize: str, default = 'R2'
        Metric name to be evaluated for hyperparameter tuning. It also accepts custom
        metrics that are added through the ``add_metric`` function.


    custom_scorer: object, default = None
        custom scoring strategy can be passed to tune hyperparameters of the model.
        It must be created using ``sklearn.make_scorer``. It is equivalent of adding
        custom metric using the ``add_metric`` function and passing the name of the
        custom metric in the ``optimize`` parameter.
        Will be deprecated in future.


    search_library: str, default = 'scikit-learn'
        The search library used for tuning hyperparameters. Possible values:

        - 'scikit-learn' - default, requires no further installation
            https://github.com/scikit-learn/scikit-learn

        - 'scikit-optimize' - ``pip install scikit-optimize``
            https://scikit-optimize.github.io/stable/

        - 'tune-sklearn' - ``pip install tune-sklearn ray[tune]``
            https://github.com/ray-project/tune-sklearn

        - 'optuna' - ``pip install optuna``
            https://optuna.org/


    search_algorithm: str, default = None
        The search algorithm depends on the ``search_library`` parameter.
        Some search algorithms require additional libraries to be installed.
        If None, will use search library-specific default algorithm.

        - 'scikit-learn' possible values:
            - 'random' : random grid search (default)
            - 'grid' : grid search

        - 'scikit-optimize' possible values:
            - 'bayesian' : Bayesian search (default)

        - 'tune-sklearn' possible values:
            - 'random' : random grid search (default)
            - 'grid' : grid search
            - 'bayesian' : ``pip install scikit-optimize``
            - 'hyperopt' : ``pip install hyperopt``
            - 'optuna' : ``pip install optuna``
            - 'bohb' : ``pip install hpbandster ConfigSpace``

        - 'optuna' possible values:
            - 'random' : randomized search
            - 'tpe' : Tree-structured Parzen Estimator search (default)


    early_stopping: bool or str or object, default = False
        Use early stopping to stop fitting to a hyperparameter configuration
        if it performs poorly. Ignored when ``search_library`` is scikit-learn,
        or if the estimator does not have 'partial_fit' attribute. If False or
        None, early stopping will not be used. Can be either an object accepted
        by the search library or one of the following:

        - 'asha' for Asynchronous Successive Halving Algorithm
        - 'hyperband' for Hyperband
        - 'median' for Median Stopping Rule
        - If False or None, early stopping will not be used.


    early_stopping_max_iters: int, default = 10
        Maximum number of epochs to run for each sampled configuration.
        Ignored if ``early_stopping`` is False or None.


    choose_better: bool, default = False
        When set to True, the returned object is always better performing. The
        metric used for comparison is defined by the ``optimize`` parameter.


    fit_kwargs: dict, default = {} (empty dict)
        Dictionary of arguments passed to the fit method of the tuner.


    return_tuner: bool, default = False
        When set to True, will return a tuple of (model, tuner_object).


    verbose: bool, default = True
        Score grid is not printed when verbose is set to False.


    tuner_verbose: bool or in, default = True
        If True or above 0, will print messages from the tuner. Higher values
        print more messages. Ignored when ``verbose`` param is False.


    **kwargs:
        Additional keyword arguments to pass to the optimizer.


    Returns:
        Trained Model and Optional Tuner Object when ``return_tuner`` is True.


    Warnings
    --------
    - Using 'grid' as ``search_algorithm`` may result in very long computation.
      Only recommended with smaller search spaces that can be defined in the
      ``custom_grid`` parameter.

    - ``search_library`` 'tune-sklearn' does not support GPU models.

    """

    return _CURRENT_EXPERIMENT.tune_model(
        estimator=estimator,
        fold=fold,
        round=round,
        n_iter=n_iter,
        custom_grid=custom_grid,
        optimize=optimize,
        custom_scorer=custom_scorer,
        search_library=search_library,
        search_algorithm=search_algorithm,
        early_stopping=early_stopping,
        early_stopping_max_iters=early_stopping_max_iters,
        choose_better=choose_better,
        fit_kwargs=fit_kwargs,
        groups=groups,
        return_tuner=return_tuner,
        verbose=verbose,
        tuner_verbose=tuner_verbose,
        **kwargs,
    )


@check_if_global_is_not_none(globals(), _CURRENT_EXPERIMENT_DECORATOR_DICT)
def ensemble_model(
    estimator,
    method: str = "Bagging",
    fold: Optional[Union[int, Any]] = None,
    n_estimators: int = 10,
    round: int = 4,
    choose_better: bool = False,
    optimize: str = "R2",
    fit_kwargs: Optional[dict] = None,
    groups: Optional[Union[str, Any]] = None,
    verbose: bool = True,
) -> Any:

    """
    This function ensembles a given estimator. The output of this function is
    a score grid with CV scores by fold. Metrics evaluated during CV can be
    accessed using the ``get_metrics`` function. Custom metrics can be added
    or removed using ``add_metric`` and ``remove_metric`` function.


    Example
    --------
    >>> from pycaret.datasets import get_data
    >>> boston = get_data('boston')
    >>> from pycaret.regression import *
    >>> exp_name = setup(data = boston,  target = 'medv')
    >>> dt = create_model('dt')
    >>> bagged_dt = ensemble_model(dt, method = 'Bagging')


    estimator: scikit-learn compatible object
        Trained model object


    method: str, default = 'Bagging'
        Method for ensembling base estimator. It can be 'Bagging' or 'Boosting'.


    fold: int or scikit-learn compatible CV generator, default = None
        Controls cross-validation. If None, the CV generator in the ``fold_strategy``
        parameter of the ``setup`` function is used. When an integer is passed,
        it is interpreted as the 'n_splits' parameter of the CV generator in the
        ``setup`` function.


    n_estimators: int, default = 10
        The number of base estimators in the ensemble. In case of perfect fit, the
        learning procedure is stopped early.


    round: int, default = 4
        Number of decimal places the metrics in the score grid will be rounded to.


    choose_better: bool, default = False
        When set to True, the returned object is always better performing. The
        metric used for comparison is defined by the ``optimize`` parameter.


    optimize: str, default = 'R2'
        Metric to compare for model selection when ``choose_better`` is True.


    fit_kwargs: dict, default = {} (empty dict)
        Dictionary of arguments passed to the fit method of the model.


    groups: str or array-like, with shape (n_samples,), default = None
        Optional group labels when GroupKFold is used for the cross validation.
        It takes an array with shape (n_samples, ) where n_samples is the number
        of rows in training dataset. When string is passed, it is interpreted as
        the column name in the dataset containing group labels.


    verbose: bool, default = True
        Score grid is not printed when verbose is set to False.


    Returns:
        Trained Model

    """

    return _CURRENT_EXPERIMENT.ensemble_model(
        estimator=estimator,
        method=method,
        fold=fold,
        n_estimators=n_estimators,
        round=round,
        choose_better=choose_better,
        optimize=optimize,
        fit_kwargs=fit_kwargs,
        groups=groups,
        verbose=verbose,
    )


@check_if_global_is_not_none(globals(), _CURRENT_EXPERIMENT_DECORATOR_DICT)
def blend_models(
    estimator_list: list,
    method: str = "mean",
    fold: Optional[Union[int, Any]] = None,
    round: int = 4,
    choose_better: bool = False,
    optimize: str = "MAPE_ts",
    weights: Optional[List[float]] = None,
    fit_kwargs: Optional[dict] = None,
    groups: Optional[Union[str, Any]] = None,
    verbose: bool = True,
):

    """
    This function trains a EnsembleForecaster for select models passed in the
    ``estimator_list`` param. The output of this function is a score grid with
    CV scores by fold. Metrics evaluated during CV can be accessed using the
    ``get_metrics`` function. Custom metrics can be added or removed using
    ``add_metric`` and ``remove_metric`` function.


    Example
    --------
    >>> from pycaret.datasets import get_data
    >>> from pycaret.internal.pycaret_experiment import TimeSeriesExperiment
    >>> import numpy as np
    >>> airline_data = get_data('airline', verbose=False)
    >>> fh = np.arange(1,13)
    >>> fold = 3
    >>> exp = TimeSeriesExperiment()
    >>> exp.setup(data=y, fh=fh, fold=fold)
    >>> arima_model = exp.create_model("arima")
    >>> naive_model = exp.create_model("naive")
    >>> ts_blender = exp.blend_models([arima_model, naive_model], optimize='MAPE_ts')


    estimator_list: list of sktime compatible estimators
        List of model objects


    method: str, default = 'mean'
        Method to average the individual predictions to form a final prediction.
        Available Methods:

        * 'mean' - Mean of individual predictions
        * 'median' - Median of individual predictions
        * 'voting' - Vote individual predictions based on the provided weights.


    fold: int or scikit-learn compatible CV generator, default = None
        Controls cross-validation. If None, the CV generator in the ``fold_strategy``
        parameter of the ``setup`` function is used. When an integer is passed,
        it is interpreted as the 'n_splits' parameter of the CV generator in the
        ``setup`` function.


    round: int, default = 4
        Number of decimal places the metrics in the score grid will be rounded to.


    choose_better: bool, default = False
        When set to True, the returned object is always better performing. The
        metric used for comparison is defined by the ``optimize`` parameter.


    optimize: str, default = 'MAPE_ts'
        Metric to compare for model selection when ``choose_better`` is True.


    weights: list, default = None
        Sequence of weights (float or int) to weight the occurrences of predicted class
        labels (hard voting) or class probabilities before averaging (soft voting). Uses
        uniform weights when None.


    fit_kwargs: dict, default = {} (empty dict)
        Dictionary of arguments passed to the fit method of the model.


    groups: str or array-like, with shape (n_samples,), default = None
        Optional group labels when GroupKFold is used for the cross validation.
        It takes an array with shape (n_samples, ) where n_samples is the number
        of rows in training dataset. When string is passed, it is interpreted as
        the column name in the dataset containing group labels.


    verbose: bool, default = True
        Score grid is not printed when verbose is set to False.


    Returns:
        Trained Model


    """

    return _CURRENT_EXPERIMENT.blend_models(
        estimator_list=estimator_list,
        fold=fold,
        round=round,
        choose_better=choose_better,
        optimize=optimize,
        weights=weights,
        fit_kwargs=fit_kwargs,
        groups=groups,
        verbose=verbose,
    )


@check_if_global_is_not_none(globals(), _CURRENT_EXPERIMENT_DECORATOR_DICT)
def stack_models(
    estimator_list: list,
    meta_model=None,
    fold: Optional[Union[int, Any]] = None,
    round: int = 4,
    restack: bool = True,
    choose_better: bool = False,
    optimize: str = "R2",
    fit_kwargs: Optional[dict] = None,
    groups: Optional[Union[str, Any]] = None,
    verbose: bool = True,
):

    """
    This function trains a meta model over select estimators passed in
    the ``estimator_list`` parameter. The output of this function is a
    score grid with CV scores by fold. Metrics evaluated during CV can
    be accessed using the ``get_metrics`` function. Custom metrics
    can be added or removed using ``add_metric`` and ``remove_metric``
    function.


    Example
    --------
    >>> from pycaret.datasets import get_data
    >>> boston = get_data('boston')
    >>> from pycaret.regression import *
    >>> exp_name = setup(data = boston,  target = 'medv')
    >>> top3 = compare_models(n_select = 3)
    >>> stacker = stack_models(top3)


    estimator_list: list of scikit-learn compatible objects
        List of trained model objects


    meta_model: scikit-learn compatible object, default = None
        When None, Linear Regression is trained as a meta model.


    fold: int or scikit-learn compatible CV generator, default = None
        Controls cross-validation. If None, the CV generator in the ``fold_strategy``
        parameter of the ``setup`` function is used. When an integer is passed,
        it is interpreted as the 'n_splits' parameter of the CV generator in the
        ``setup`` function.


    round: int, default = 4
        Number of decimal places the metrics in the score grid will be rounded to.


    restack: bool, default = True
        When set to False, only the predictions of estimators will be used as
        training data for the ``meta_model``.


    choose_better: bool, default = False
        When set to True, the returned object is always better performing. The
        metric used for comparison is defined by the ``optimize`` parameter.


    optimize: str, default = 'R2'
        Metric to compare for model selection when ``choose_better`` is True.


    fit_kwargs: dict, default = {} (empty dict)
        Dictionary of arguments passed to the fit method of the model.


    groups: str or array-like, with shape (n_samples,), default = None
        Optional group labels when GroupKFold is used for the cross validation.
        It takes an array with shape (n_samples, ) where n_samples is the number
        of rows in training dataset. When string is passed, it is interpreted as
        the column name in the dataset containing group labels.


    verbose: bool, default = True
        Score grid is not printed when verbose is set to False.


    Returns:
        Trained Model

    """

    return _CURRENT_EXPERIMENT.stack_models(
        estimator_list=estimator_list,
        meta_model=meta_model,
        fold=fold,
        round=round,
        restack=restack,
        choose_better=choose_better,
        optimize=optimize,
        fit_kwargs=fit_kwargs,
        groups=groups,
        verbose=verbose,
    )


@check_if_global_is_not_none(globals(), _CURRENT_EXPERIMENT_DECORATOR_DICT)
def plot_model(
    estimator,
    plot: str = "residuals",
    scale: float = 1,
    save: bool = False,
    fold: Optional[Union[int, Any]] = None,
    fit_kwargs: Optional[dict] = None,
    groups: Optional[Union[str, Any]] = None,
    use_train_data: bool = False,
    verbose: bool = True,
    display_format: Optional[str] = None,
) -> str:

    """
    This function analyzes the performance of a trained model on holdout set.
    It may require re-training the model in certain cases.


    Example
    --------
    >>> from pycaret.datasets import get_data
    >>> boston = get_data('boston')
    >>> from pycaret.regression import *
    >>> exp_name = setup(data = boston,  target = 'medv')
    >>> lr = create_model('lr')
    >>> plot_model(lr, plot = 'residual')


    estimator: scikit-learn compatible object
        Trained model object


    plot: str, default = 'residual'
        List of available plots (ID - Name):

        * 'residuals' - Residuals Plot
        * 'error' - Prediction Error Plot
        * 'cooks' - Cooks Distance Plot
        * 'rfe' - Recursive Feat. Selection
        * 'learning' - Learning Curve
        * 'vc' - Validation Curve
        * 'manifold' - Manifold Learning
        * 'feature' - Feature Importance
        * 'feature_all' - Feature Importance (All)
        * 'parameter' - Model Hyperparameter
        * 'tree' - Decision Tree


    scale: float, default = 1
        The resolution scale of the figure.


    save: bool, default = False
        When set to True, plot is saved in the current working directory.


    fold: int or scikit-learn compatible CV generator, default = None
        Controls cross-validation. If None, the CV generator in the ``fold_strategy``
        parameter of the ``setup`` function is used. When an integer is passed,
        it is interpreted as the 'n_splits' parameter of the CV generator in the
        ``setup`` function.


    fit_kwargs: dict, default = {} (empty dict)
        Dictionary of arguments passed to the fit method of the model.


    groups: str or array-like, with shape (n_samples,), default = None
        Optional group labels when GroupKFold is used for the cross validation.
        It takes an array with shape (n_samples, ) where n_samples is the number
        of rows in training dataset. When string is passed, it is interpreted as
        the column name in the dataset containing group labels.


    use_train_data: bool, default = False
        When set to true, train data will be used for plots, instead
        of test data.


    verbose: bool, default = True
        When set to False, progress bar is not displayed.


    display_format: str, default = None
        To display plots in Streamlit (https://www.streamlit.io/), set this to 'streamlit'.
        Currently, not all plots are supported.


    Returns:
        None

    """

    return _CURRENT_EXPERIMENT.plot_model(
        estimator=estimator,
        plot=plot,
        scale=scale,
        save=save,
        fold=fold,
        fit_kwargs=fit_kwargs,
        groups=groups,
        verbose=verbose,
        use_train_data=use_train_data,
        display_format=display_format,
    )


@check_if_global_is_not_none(globals(), _CURRENT_EXPERIMENT_DECORATOR_DICT)
def evaluate_model(
    estimator,
    fold: Optional[Union[int, Any]] = None,
    fit_kwargs: Optional[dict] = None,
    groups: Optional[Union[str, Any]] = None,
    use_train_data: bool = False,
):

    """
    This function displays a user interface for analyzing performance of a trained
    model. It calls the ``plot_model`` function internally.

    Example
    --------
    >>> from pycaret.datasets import get_data
    >>> boston = get_data('boston')
    >>> from pycaret.regression import *
    >>> exp_name = setup(data = boston,  target = 'medv')
    >>> lr = create_model('lr')
    >>> evaluate_model(lr)


    estimator: scikit-learn compatible object
        Trained model object


    fold: int or scikit-learn compatible CV generator, default = None
        Controls cross-validation. If None, the CV generator in the ``fold_strategy``
        parameter of the ``setup`` function is used. When an integer is passed,
        it is interpreted as the 'n_splits' parameter of the CV generator in the
        ``setup`` function.


    fit_kwargs: dict, default = {} (empty dict)
        Dictionary of arguments passed to the fit method of the model.


    groups: str or array-like, with shape (n_samples,), default = None
        Optional group labels when GroupKFold is used for the cross validation.
        It takes an array with shape (n_samples, ) where n_samples is the number
        of rows in training dataset. When string is passed, it is interpreted as
        the column name in the dataset containing group labels.


    use_train_data: bool, default = False
        When set to true, train data will be used for plots, instead
        of test data.


    Returns:
        None


    Warnings
    --------
    -   This function only works in IPython enabled Notebook.

    """

    return _CURRENT_EXPERIMENT.evaluate_model(
        estimator=estimator,
        fold=fold,
        fit_kwargs=fit_kwargs,
        groups=groups,
        use_train_data=use_train_data,
    )


@check_if_global_is_not_none(globals(), _CURRENT_EXPERIMENT_DECORATOR_DICT)
def interpret_model(
    estimator,
    plot: str = "summary",
    feature: Optional[str] = None,
    observation: Optional[int] = None,
    use_train_data: bool = False,
    save: bool = False,
    **kwargs,
):

    """
    This function analyzes the predictions generated from a tree-based model. It is
    implemented based on the SHAP (SHapley Additive exPlanations). For more info on
    this, please see https://shap.readthedocs.io/en/latest/


    Example
    --------
    >>> from pycaret.datasets import get_data
    >>> boston = get_data('boston')
    >>> from pycaret.regression import *
    >>> exp = setup(data = boston,  target = 'medv')
    >>> xgboost = create_model('xgboost')
    >>> interpret_model(xgboost)


    estimator: scikit-learn compatible object
        Trained model object


    plot: str, default = 'summary'
        Type of plot. Available options are: 'summary', 'correlation', and 'reason'.


    feature: str, default = None
        Feature to check correlation with. This parameter is only required when ``plot``
        type is 'correlation'. When set to None, it uses the first column in the train
        dataset.


    observation: int, default = None
        Observation index number in holdout set to explain. When ``plot`` is not
        'reason', this parameter is ignored.


    use_train_data: bool, default = False
        When set to true, train data will be used for plots, instead
        of test data.


    save: bool, default = False
        When set to True, Plot is saved as a 'png' file in current working directory.


    **kwargs:
        Additional keyword arguments to pass to the plot.


    Returns:
        None

    """

    return _CURRENT_EXPERIMENT.interpret_model(
        estimator=estimator,
        plot=plot,
        feature=feature,
        observation=observation,
        use_train_data=use_train_data,
        save=save,
        **kwargs,
    )


@check_if_global_is_not_none(globals(), _CURRENT_EXPERIMENT_DECORATOR_DICT)
def predict_model(
    estimator,
    data: Optional[pd.DataFrame] = None,
    round: int = 4,
    verbose: bool = True,
) -> pd.DataFrame:

    """
    This function predicts ``Label`` using a trained model. When ``data`` is
    None, it predicts label on the holdout set.


    Example
    -------
    >>> from pycaret.datasets import get_data
    >>> boston = get_data('boston')
    >>> from pycaret.regression import *
    >>> exp_name = setup(data = boston,  target = 'medv')
    >>> lr = create_model('lr')
    >>> pred_holdout = predict_model(lr)
    >>> pred_unseen = predict_model(lr, data = unseen_dataframe)


    estimator: scikit-learn compatible object
        Trained model object


    data : pandas.DataFrame
        Shape (n_samples, n_features). All features used during training
        must be available in the unseen dataset.


    round: int, default = 4
        Number of decimal places to round predictions to.


    verbose: bool, default = True
        When set to False, holdout score grid is not printed.


    Returns:
        pandas.DataFrame


    Warnings
    --------
    - The behavior of the ``predict_model`` is changed in version 2.1 without backward
      compatibility. As such, the pipelines trained using the version (<= 2.0), may not
      work for inference with version >= 2.1. You can either retrain your models with a
      newer version or downgrade the version for inference.


    """

    return _CURRENT_EXPERIMENT.predict_model(
        estimator=estimator,
        data=data,
        round=round,
        verbose=verbose,
    )


@check_if_global_is_not_none(globals(), _CURRENT_EXPERIMENT_DECORATOR_DICT)
def finalize_model(
    estimator,
    fit_kwargs: Optional[dict] = None,
    groups: Optional[Union[str, Any]] = None,
    model_only: bool = True,
) -> Any:

    """
    This function trains a given estimator on the entire dataset including the
    holdout set.


    Example
    --------
    >>> from pycaret.datasets import get_data
    >>> boston = get_data('boston')
    >>> from pycaret.regression import *
    >>> exp_name = setup(data = boston,  target = 'medv')
    >>> lr = create_model('lr')
    >>> final_lr = finalize_model(lr)


    estimator: scikit-learn compatible object
        Trained model object


    fit_kwargs: dict, default = {} (empty dict)
        Dictionary of arguments passed to the fit method of the model.


    groups: str or array-like, with shape (n_samples,), default = None
        Optional group labels when GroupKFold is used for the cross validation.
        It takes an array with shape (n_samples, ) where n_samples is the number
        of rows in training dataset. When string is passed, it is interpreted as
        the column name in the dataset containing group labels.


    model_only: bool, default = True
        When set to False, only model object is re-trained and all the
        transformations in Pipeline are ignored.


    Returns:
        Trained Model


    """

    return _CURRENT_EXPERIMENT.finalize_model(
        estimator=estimator,
        fit_kwargs=fit_kwargs,
        groups=groups,
        model_only=model_only,
    )


@check_if_global_is_not_none(globals(), _CURRENT_EXPERIMENT_DECORATOR_DICT)
def deploy_model(
    model,
    model_name: str,
    authentication: dict,
    platform: str = "aws",
):

    """
    This function deploys the transformation pipeline and trained model on cloud.


    Example
    -------
    >>> from pycaret.datasets import get_data
    >>> boston = get_data('boston')
    >>> from pycaret.regression import *
    >>> exp_name = setup(data = boston,  target = 'medv')
    >>> lr = create_model('lr')
    >>> deploy_model(model = lr, model_name = 'lr-for-deployment', platform = 'aws', authentication = {'bucket' : 'S3-bucket-name'})


    Amazon Web Service (AWS) users:
        To deploy a model on AWS S3 ('aws'), environment variables must be set in your
        local environment. To configure AWS environment variables, type ``aws configure``
        in the command line. Following information from the IAM portal of amazon console
        account is required:

        - AWS Access Key ID
        - AWS Secret Key Access
        - Default Region Name (can be seen under Global settings on your AWS console)

        More info: https://docs.aws.amazon.com/cli/latest/userguide/cli-configure-envvars.html


    Google Cloud Platform (GCP) users:
        To deploy a model on Google Cloud Platform ('gcp'), project must be created
        using command line or GCP console. Once project is created, you must create
        a service account and download the service account key as a JSON file to set
        environment variables in your local environment.

        More info: https://cloud.google.com/docs/authentication/production


    Microsoft Azure (Azure) users:
        To deploy a model on Microsoft Azure ('azure'), environment variables for connection
        string must be set in your local environment. Go to settings of storage account on
        Azure portal to access the connection string required.

        More info: https://docs.microsoft.com/en-us/azure/storage/blobs/storage-quickstart-blobs-python?toc=%2Fpython%2Fazure%2FTOC.json


    model: scikit-learn compatible object
        Trained model object


    model_name: str
        Name of model.


    authentication: dict
        Dictionary of applicable authentication tokens.

        When platform = 'aws':
        {'bucket' : 'S3-bucket-name'}

        When platform = 'gcp':
        {'project': 'gcp-project-name', 'bucket' : 'gcp-bucket-name'}

        When platform = 'azure':
        {'container': 'azure-container-name'}


    platform: str, default = 'aws'
        Name of the platform. Currently supported platforms: 'aws', 'gcp' and 'azure'.


    Returns:
        None

    """

    return _CURRENT_EXPERIMENT.deploy_model(
        model=model,
        model_name=model_name,
        authentication=authentication,
        platform=platform,
    )


@check_if_global_is_not_none(globals(), _CURRENT_EXPERIMENT_DECORATOR_DICT)
def save_model(model, model_name: str, model_only: bool = False, verbose: bool = True):

    """
    This function saves the transformation pipeline and trained model object
    into the current working directory as a pickle file for later use.

    Example
    -------
    >>> from pycaret.datasets import get_data
    >>> boston = get_data('boston')
    >>> from pycaret.regression import *
    >>> exp_name = setup(data = boston,  target = 'medv')
    >>> lr = create_model('lr')
    >>> save_model(lr, 'saved_lr_model')


    model: scikit-learn compatible object
        Trained model object


    model_name: str
        Name of the model.


    model_only: bool, default = False
        When set to True, only trained model object is saved instead of the
        entire pipeline.


    verbose: bool, default = True
        Success message is not printed when verbose is set to False.


    Returns:
        Tuple of the model object and the filename.

    """

    return _CURRENT_EXPERIMENT.save_model(
        model=model, model_name=model_name, model_only=model_only, verbose=verbose
    )


@check_if_global_is_not_none(globals(), _CURRENT_EXPERIMENT_DECORATOR_DICT)
def load_model(
    model_name,
    platform: Optional[str] = None,
    authentication: Optional[Dict[str, str]] = None,
    verbose: bool = True,
):

    """
    This function loads a previously saved pipeline.

    Example
    -------
    >>> from pycaret.regression import load_model
    >>> saved_lr = load_model('saved_lr_model')


    model_name: str
        Name of the model.


    platform: str, default = None
        Name of the cloud platform. Currently supported platforms:
        'aws', 'gcp' and 'azure'.


    authentication: dict, default = None
        dictionary of applicable authentication tokens.

        when platform = 'aws':
        {'bucket' : 'S3-bucket-name'}

        when platform = 'gcp':
        {'project': 'gcp-project-name', 'bucket' : 'gcp-bucket-name'}

        when platform = 'azure':
        {'container': 'azure-container-name'}


    verbose: bool, default = True
        Success message is not printed when verbose is set to False.


    Returns:
        Trained Model

    """

    return _CURRENT_EXPERIMENT.load_model(
        model_name=model_name,
        platform=platform,
        authentication=authentication,
        verbose=verbose,
    )


@check_if_global_is_not_none(globals(), _CURRENT_EXPERIMENT_DECORATOR_DICT)
def automl(optimize: str = "R2", use_holdout: bool = False, turbo: bool = True) -> Any:

    """
    This function returns the best model out of all trained models in
    current session based on the ``optimize`` parameter. Metrics
    evaluated can be accessed using the ``get_metrics`` function.


    Example
    -------
    >>> from pycaret.datasets import get_data
    >>> boston = get_data('boston')
    >>> from pycaret.regression import *
    >>> exp_name = setup(data = boston,  target = 'medv')
    >>> top3 = compare_models(n_select = 3)
    >>> tuned_top3 = [tune_model(i) for i in top3]
    >>> blender = blend_models(tuned_top3)
    >>> stacker = stack_models(tuned_top3)
    >>> best_mae_model = automl(optimize = 'MAE')


    optimize: str, default = 'R2'
        Metric to use for model selection. It also accepts custom metrics
        added using the ``add_metric`` function.


    use_holdout: bool, default = False
        When set to True, metrics are evaluated on holdout set instead of CV.


    turbo: bool, default = True
        When set to True and use_holdout is False, only models created with default fold
        parameter will be considered. If set to False, models created with a non-default
        fold parameter will be scored again using default fold settings, so that they can be
        compared.


    Returns:
        Trained Model


    """

    return _CURRENT_EXPERIMENT.automl(
        optimize=optimize, use_holdout=use_holdout, turbo=turbo
    )


@check_if_global_is_not_none(globals(), _CURRENT_EXPERIMENT_DECORATOR_DICT)
def pull(pop: bool = False) -> pd.DataFrame:
    """
    Returns last printed score grid. Use ``pull`` function after
    any training function to store the score grid in pandas.DataFrame.


    pop: bool, default = False
        If True, will pop (remove) the returned dataframe from the
        display container.


    Returns:
        pandas.DataFrame

    """
    return _CURRENT_EXPERIMENT.pull(pop=pop)


@check_if_global_is_not_none(globals(), _CURRENT_EXPERIMENT_DECORATOR_DICT)
def models(
    type: Optional[str] = None,
    internal: bool = False,
    raise_errors: bool = True,
) -> pd.DataFrame:

    """
    Returns table of models available in the model library.

    Example
    -------
    >>> from pycaret.datasets import get_data
    >>> boston = get_data('boston')
    >>> from pycaret.regression import *
    >>> exp_name = setup(data = boston,  target = 'medv')
    >>> all_models = models()


    type: str, default = None
        - linear : filters and only return linear models
        - tree : filters and only return tree based models
        - ensemble : filters and only return ensemble models


    internal: bool, default = False
        When True, will return extra columns and rows used internally.


    raise_errors: bool, default = True
        When False, will suppress all exceptions, ignoring models
        that couldn't be created.


    Returns:
        pandas.DataFrame

    """
    return _CURRENT_EXPERIMENT.models(
        type=type, internal=internal, raise_errors=raise_errors
    )


@check_if_global_is_not_none(globals(), _CURRENT_EXPERIMENT_DECORATOR_DICT)
def get_metrics(
    reset: bool = False,
    include_custom: bool = True,
    raise_errors: bool = True,
) -> pd.DataFrame:

    """
    Returns table of available metrics used for CV.


    Example
    -------
    >>> from pycaret.datasets import get_data
    >>> boston = get_data('boston')
    >>> from pycaret.regression import *
    >>> exp_name = setup(data = boston,  target = 'medv')
    >>> all_metrics = get_metrics()


    reset: bool, default = False
        When True, will reset all changes made using the ``add_metric``
        and ``remove_metric`` function.


    include_custom: bool, default = True
        Whether to include user added (custom) metrics or not.


    raise_errors: bool, default = True
        If False, will suppress all exceptions, ignoring models that
        couldn't be created.


    Returns:
        pandas.DataFrame

    """

    return _CURRENT_EXPERIMENT.get_metrics(
        reset=reset,
        include_custom=include_custom,
        raise_errors=raise_errors,
    )


@check_if_global_is_not_none(globals(), _CURRENT_EXPERIMENT_DECORATOR_DICT)
def add_metric(
    id: str,
    name: str,
    score_func: type,
    greater_is_better: bool = True,
    **kwargs,
) -> pd.Series:

    """
    Adds a custom metric to be used for CV.


    Example
    -------
    >>> from pycaret.datasets import get_data
    >>> boston = get_data('boston')
    >>> from pycaret.regression import *
    >>> exp_name = setup(data = boston,  target = 'medv')
    >>> from sklearn.metrics import explained_variance_score
    >>> add_metric('evs', 'EVS', explained_variance_score)


    id: str
        Unique id for the metric.


    name: str
        Display name of the metric.


    score_func: type
        Score function (or loss function) with signature ``score_func(y, y_pred, **kwargs)``.


    greater_is_better: bool, default = True
        Whether ``score_func`` is higher the better or not.


    **kwargs:
        Arguments to be passed to score function.


    Returns:
        pandas.Series

    """

    return _CURRENT_EXPERIMENT.add_metric(
        id=id,
        name=name,
        score_func=score_func,
        target="pred",
        greater_is_better=greater_is_better,
        **kwargs,
    )


@check_if_global_is_not_none(globals(), _CURRENT_EXPERIMENT_DECORATOR_DICT)
def remove_metric(name_or_id: str):

    """
    Removes a metric from CV.


    Example
    -------
    >>> from pycaret.datasets import get_data
    >>> boston = get_data('boston')
    >>> from pycaret.regression import *
    >>> exp_name = setup(data = boston,  target = 'mredv')
    >>> remove_metric('MAPE')


    name_or_id: str
        Display name or ID of the metric.


    Returns:
        None

    """
    return _CURRENT_EXPERIMENT.remove_metric(name_or_id=name_or_id)


@check_if_global_is_not_none(globals(), _CURRENT_EXPERIMENT_DECORATOR_DICT)
def get_logs(
    logger_id: Optional[str] = None, save: bool = False
) -> Union[pd.DataFrame, Dict[str, pd.DataFrame]]:
    """
    Returns tables with experiment logs consisting
    run details, parameter, metrics and tags based on logger data.
    Only works when ``log_experiment`` is True when initializing
    the ``setup`` function.


    Example
    -------
    >>> from pycaret.datasets import get_data
    >>> boston = get_data('boston')
    >>> from pycaret.regression import *
    >>> exp_name = setup(data = boston,  target = 'medv', log_experiment = True) 
    >>> best = compare_models()
    >>> exp_logs = get_logs()


    logger_id : str, default = None
        When set to None, a dictionary of all logger ids and dataframes is returned.
        Otherwise, a single dataframe corresponding to the logger id is returned.


    save : bool, default = False
        When set to True, csv files are saved in current directory.


    Returns:
        pandas.DataFrame or dict of [logger id, pandas.DataFrame]

    """

    return _CURRENT_EXPERIMENT.get_logs(logger_id=logger_id, save=save)


@check_if_global_is_not_none(globals(), _CURRENT_EXPERIMENT_DECORATOR_DICT)
def get_config(variable: str):

    """
    This function retrieves the global variables created when initializing the
    ``setup`` function. Following variables are accessible:

    - X: Transformed dataset (X)
    - y: Transformed dataset (y)
    - X_train: Transformed train dataset (X)
    - X_test: Transformed test/holdout dataset (X)
    - y_train: Transformed train dataset (y)
    - y_test: Transformed test/holdout dataset (y)
    - seed: random state set through session_id
    - prep_pipe: Transformation pipeline
    - fold_shuffle_param: shuffle parameter used in Kfolds
    - n_jobs_param: n_jobs parameter used in model training
    - html_param: html_param configured through setup
    - create_model_container: results grid storage container
    - master_model_container: model storage container
    - display_container: results display container
    - exp_name_log: Name of experiment
    - logging_param: log_experiment param
    - log_plots_param: log_plots param
    - USI: Unique session ID parameter
    - fix_imbalance_param: fix_imbalance param
    - fix_imbalance_method_param: fix_imbalance_method param
    - data_before_preprocess: data before preprocessing
    - target_param: name of target variable
    - gpu_param: use_gpu param configured through setup
    - fold_generator: CV splitter configured in fold_strategy
    - fold_param: fold params defined in the setup
    - fold_groups_param: fold groups defined in the setup
    - stratify_param: stratify parameter defined in the setup
    - transform_target_param: transform_target_param in setup
    - transform_target_method_param: transform_target_method_param in setup


    Example
    -------
    >>> from pycaret.datasets import get_data
    >>> boston = get_data('boston')
    >>> from pycaret.regression import *
    >>> exp_name = setup(data = boston,  target = 'medv')
    >>> X_train = get_config('X_train')


    Returns:
        Global variable


    """

    return _CURRENT_EXPERIMENT.get_config(variable=variable)


@check_if_global_is_not_none(globals(), _CURRENT_EXPERIMENT_DECORATOR_DICT)
def set_config(variable: str, value):

    """
    This function resets the global variables. Following variables are
    accessible:

    - X: Transformed dataset (X)
    - y: Transformed dataset (y)
    - X_train: Transformed train dataset (X)
    - X_test: Transformed test/holdout dataset (X)
    - y_train: Transformed train dataset (y)
    - y_test: Transformed test/holdout dataset (y)
    - seed: random state set through session_id
    - prep_pipe: Transformation pipeline
    - fold_shuffle_param: shuffle parameter used in Kfolds
    - n_jobs_param: n_jobs parameter used in model training
    - html_param: html_param configured through setup
    - create_model_container: results grid storage container
    - master_model_container: model storage container
    - display_container: results display container
    - exp_name_log: Name of experiment
    - logging_param: log_experiment param
    - log_plots_param: log_plots param
    - USI: Unique session ID parameter
    - fix_imbalance_param: fix_imbalance param
    - fix_imbalance_method_param: fix_imbalance_method param
    - data_before_preprocess: data before preprocessing
    - target_param: name of target variable
    - gpu_param: use_gpu param configured through setup
    - fold_generator: CV splitter configured in fold_strategy
    - fold_param: fold params defined in the setup
    - fold_groups_param: fold groups defined in the setup
    - stratify_param: stratify parameter defined in the setup
    - transform_target_param: transform_target_param in setup
    - transform_target_method_param: transform_target_method_param in setup


    Example
    -------
    >>> from pycaret.datasets import get_data
    >>> boston = get_data('boston')
    >>> from pycaret.regression import *
    >>> exp_name = setup(data = boston,  target = 'medv')
    >>> set_config('seed', 123)


    Returns:
        None

    """

    return _CURRENT_EXPERIMENT.set_config(variable=variable, value=value)


@check_if_global_is_not_none(globals(), _CURRENT_EXPERIMENT_DECORATOR_DICT)
def save_config(file_name: str):

    """
    This function save all global variables to a pickle file, allowing to
    later resume without rerunning the ``setup``.


    Example
    -------
    >>> from pycaret.datasets import get_data
    >>> boston = get_data('boston')
    >>> from pycaret.regression import *
    >>> exp_name = setup(data = boston,  target = 'medv')
    >>> save_config('myvars.pkl')


    Returns:
        None

    """

    return _CURRENT_EXPERIMENT.save_config(file_name=file_name)


@check_if_global_is_not_none(globals(), _CURRENT_EXPERIMENT_DECORATOR_DICT)
def load_config(file_name: str):

    """
    This function loads global variables from a pickle file into Python
    environment.


    Example
    -------
    >>> from pycaret.regression import load_config
    >>> load_config('myvars.pkl')


    Returns:
        Global variables

    """

    return _CURRENT_EXPERIMENT.load_config(file_name=file_name)


def set_current_experiment(experiment: TimeSeriesExperiment):
    global _CURRENT_EXPERIMENT

    if not isinstance(experiment, TimeSeriesExperiment):
        raise TypeError(
            f"experiment must be a PyCaret TimeSeriesExperiment object, got {type(experiment)}."
        )
    _CURRENT_EXPERIMENT = experiment


def _get_cv_n_folds(y, cv) -> int:
    """
    Get the number of folds for time series
    cv must be of type SlidingWindowSplitter or ExpandingWindowSplitter
    TODO: Fix this inside sktime and replace this with sktime method [1]

    Ref:
    [1] https://github.com/alan-turing-institute/sktime/issues/632
    """
    n_folds = int((len(y) - cv.initial_window) / cv.step_length)
    return n_folds


def get_folds(cv, y) -> Generator[Tuple[pd.Series, pd.Series], None, None]:
    """
    Returns the train and test indices for the time series data
    """
    n_folds = _get_cv_n_folds(y, cv)
    for i in np.arange(n_folds):
        if i == 0:
            # Initial Split in sktime
            train_initial, test_initial = cv.split_initial(y)
            y_train_initial = y.iloc[train_initial]
            y_test_initial = y.iloc[test_initial]  # Includes all entries after y_train

            rolling_y_train = y_train_initial.copy(deep=True)
            y_test = y_test_initial.iloc[
                np.arange(len(cv.fh))
            ]  # filter to only what is needed
        else:
            # Subsequent Splits in sktime
            for j, (train, test) in enumerate(cv.split(y_test_initial)):
                if j == i - 1:
                    y_train = y_test_initial.iloc[train]
                    y_test = y_test_initial.iloc[test]

                    rolling_y_train = pd.concat([rolling_y_train, y_train])
                    rolling_y_train = rolling_y_train[
                        ~rolling_y_train.index.duplicated(keep="first")
                    ]

                    if isinstance(cv, SlidingWindowSplitter):
                        rolling_y_train = rolling_y_train.iloc[-cv.initial_window :]
        yield rolling_y_train.index, y_test.index


def cross_validate_ts(
    forecaster,
    y: pd.Series,
    X: Optional[Union[pd.Series, pd.DataFrame]],
    cv,
    scoring: Dict[str, Union[str, _PredictScorer]],
    fit_params,
    n_jobs,
    return_train_score,
    error_score=0,
    verbose: int = 0,
) -> Dict[str, np.array]:
    """Performs Cross Validation on time series data

    Parallelization is based on `sklearn` cross_validate function [1]
    Ref:
    [1] https://github.com/scikit-learn/scikit-learn/blob/0.24.1/sklearn/model_selection/_validation.py#L246


    Parameters
    ----------
    forecaster : [type]
        Time Series Forecaster that is compatible with sktime
    y : pd.Series
        The variable of interest for forecasting
    X : Optional[Union[pd.Series, pd.DataFrame]]
        Exogenous Variables
    cv : [type]
        [description]
    scoring : Dict[str, Union[str, _PredictScorer]]
        Scoring Dictionary. Values can be valid strings that can be converted to
        callable metrics or the callable metrics directly
    fit_params : [type]
        Fit parameters to be used when training
    n_jobs : [type]
        Number of cores to use to parallelize. Refer to sklearn for details
    return_train_score : [type]
        Should the training scores be returned. Unused for now.
    error_score : int, optional
        Unused for now, by default 0
    verbose : int
        Sets the verbosity level. Unused for now

    Returns
    -------
    [type]
        [description]

    Raises
    ------
    Error
        If fit and score raises any exceptions
    """
    try:
        # # For Debug
        # n_jobs = 1
        scoring = _get_metrics_dict_ts(scoring)
        parallel = Parallel(n_jobs=n_jobs)
        out = parallel(
            delayed(_fit_and_score)(
                forecaster=clone(forecaster),
                y=y,
                X=X,
                scoring=scoring,
                train=train,
                test=test,
                parameters=None,
                fit_params=fit_params,
                return_train_score=return_train_score,
                error_score=error_score,
            )
            for train, test in get_folds(cv, y)
        )
    # raise key exceptions
    except Exception:
        raise

    # Similar to parts of _format_results in BaseGridSearch
    (test_scores_dict, fit_time, score_time) = zip(*out)
    test_scores = _aggregate_score_dicts(test_scores_dict)

    return test_scores


def _get_metrics_dict_ts(
    metrics_dict: Dict[str, Union[str, _PredictScorer]]
) -> Dict[str, _PredictScorer]:
    """Returns a metrics dictionary in which all values are callables
    of type _PredictScorer

    Parameters
    ----------
    metrics_dict : A metrics dictionary in which some values can be strings.
        If the value is a string, the corresponding callable metric is returned
        e.g. Dictionary Value of 'neg_mean_absolute_error' will return
        make_scorer(mean_absolute_error, greater_is_better=False)
    """
    return_metrics_dict = {}
    for k, v in metrics_dict.items():
        if isinstance(v, str):
            return_metrics_dict[k] = get_scorer(v)
        else:
            return_metrics_dict[k] = v
    return return_metrics_dict


def _fit_and_score(
    forecaster,
    y: pd.Series,
    X: Optional[Union[pd.Series, pd.DataFrame]],
    scoring: Dict[str, Union[str, _PredictScorer]],
    train,
    test,
    parameters,
    fit_params,
    return_train_score,
    error_score=0,
):
    """Fits the forecaster on a single train split and scores on the test split
    Similar to _fit_and_score from `sklearn` [1] (and to some extent `sktime` [2]).
    Difference is that [1] operates on a single fold only, whereas [2] operates on all cv folds.
    Ref:
    [1] https://github.com/scikit-learn/scikit-learn/blob/0.24.1/sklearn/model_selection/_validation.py#L449
    [2] https://github.com/alan-turing-institute/sktime/blob/v0.5.3/sktime/forecasting/model_selection/_tune.py#L95

    Parameters
    ----------
    forecaster : [type]
        Time Series Forecaster that is compatible with sktime
    y : pd.Series
        The variable of interest for forecasting
    X : Optional[Union[pd.Series, pd.DataFrame]]
        Exogenous Variables
    scoring : Dict[str, Union[str, _PredictScorer]]
        Scoring Dictionary. Values can be valid strings that can be converted to
        callable metrics or the callable metrics directly
    train : [type]
        Indices of training samples.
    test : [type]
        Indices of test samples.
    parameters : [type]
        Parameter to set for the forecaster
    fit_params : [type]
        Fit parameters to be used when training
    return_train_score : [type]
        Should the training scores be returned. Unused for now.
    error_score : int, optional
        Unused for now, by default 0

    Raises
    ------
    ValueError
        When test indices do not match predicted indices. This is only for
        for internal checks and should not be raised when used by external users
    """
    if parameters is not None:
        forecaster.set_params(**parameters)

    y_train, y_test = y[train], y[test]
    X_train = None if X is None else X[train]
    X_test = None if X is None else X[test]

    start = time.time()
    forecaster.fit(y_train, X_train, **fit_params)
    fit_time = time.time() - start

    y_pred = forecaster.predict(X_test)
    if (y_test.index.values != y_pred.index.values).any():
        print(f"\t y_train: {y_train.index.values}, \n\t y_test: {y_test.index.values}")
        print(f"\t y_pred: {y_pred.index.values}")
        raise ValueError(
            "y_test indices do not match y_pred_indices or split/prediction length does not match forecast horizon."
        )

    fold_scores = {}
    start = time.time()

    scoring = _get_metrics_dict_ts(scoring)
    for scorer_name, scorer in scoring.items():
        metric = scorer._score_func(y_true=y_test, y_pred=y_pred)
        fold_scores[scorer_name] = metric
    score_time = time.time() - start

    return fold_scores, fit_time, score_time


class BaseGridSearch:
    """
    Parallelization is based predominantly on [1]. Also similar to [2]

    Ref:
    [1] https://github.com/scikit-learn/scikit-learn/blob/0.24.1/sklearn/model_selection/_search.py#L795
    [2] https://github.com/scikit-optimize/scikit-optimize/blob/v0.8.1/skopt/searchcv.py#L410
    """

    def __init__(
        self,
        forecaster,
        cv,
        n_jobs=None,
        pre_dispatch=None,
        refit: bool = False,
        refit_metric: str = "smape",
        scoring=None,
        verbose=0,
        error_score=None,
        return_train_score=None,
    ):
        self.forecaster = forecaster
        self.cv = cv
        self.n_jobs = n_jobs
        self.pre_dispatch = pre_dispatch
        self.refit = refit
        self.refit_metric = refit_metric
        self.scoring = scoring
        self.verbose = verbose
        self.error_score = error_score
        self.return_train_score = return_train_score

        self.best_params_ = {}
        self.cv_results_ = {}

    def fit(self, y, X=None, **fit_params):
        y, X = check_y_X(y, X)

        # validate cross-validator
        cv = check_cv(self.cv)
        base_forecaster = clone(self.forecaster)

        # This checker is sktime specific and only support 1 metric
        # Removing for now since we can have multiple metrics
        # TODO: Add back later if it supports multiple metrics
        # scoring = check_scoring(self.scoring)
        # Multiple metrics supported
        scorers = self.scoring  # Dict[str, Union[str, scorer]]  Not metrics container
        scorers = _get_metrics_dict_ts(scorers)
        refit_metric = self.refit_metric
        if refit_metric not in list(scorers.keys()):
            raise ValueError(
                f"Refit Metric: '{refit_metric}' is not available. ",
                f"Available Values are: {list(scorers.keys())}",
            )

        results = {}
        all_candidate_params = []
        all_out = []

        def evaluate_candidates(candidate_params):
            candidate_params = list(candidate_params)
            n_candidates = len(candidate_params)
            n_splits = _get_cv_n_folds(y, cv)

            if self.verbose > 0:
                print(  # noqa
                    f"Fitting {n_splits} folds for each of {n_candidates} "
                    f"candidates, totalling {n_candidates * n_splits} fits"
                )
                # print(f"Candidate Params: {candidate_params}")

            parallel = Parallel(
                n_jobs=self.n_jobs, verbose=self.verbose, pre_dispatch=self.pre_dispatch
            )
            out = parallel(
                delayed(_fit_and_score)(
                    forecaster=clone(base_forecaster),
                    y=y,
                    X=X,
                    scoring=scorers,
                    train=train,
                    test=test,
                    parameters=parameters,
                    fit_params=fit_params,
                    return_train_score=self.return_train_score,
                    error_score=self.error_score,
                )
                for parameters in candidate_params
                for train, test in get_folds(cv, y)
            )

            if len(out) < 1:
                raise ValueError(
                    "No fits were performed. "
                    "Was the CV iterator empty? "
                    "Were there no candidates?"
                )

            all_candidate_params.extend(candidate_params)
            all_out.extend(out)

            nonlocal results
            results = self._format_results(
                all_candidate_params, scorers, all_out, n_splits
            )
            return results

        self._run_search(evaluate_candidates)

        self.best_index_ = results["rank_test_%s" % refit_metric].argmin()
        self.best_score_ = results["mean_test_%s" % refit_metric][self.best_index_]
        self.best_params_ = results["params"][self.best_index_]

        self.best_forecaster_ = clone(base_forecaster).set_params(**self.best_params_)

        if self.refit:
            refit_start_time = time.time()
            self.best_forecaster_.fit(y, X, **fit_params)
            self.refit_time_ = time.time() - refit_start_time

        # Store the only scorer not as a dict for single metric evaluation
        self.scorer_ = scorers

        self.cv_results_ = results
        self.n_splits_ = _get_cv_n_folds(y, cv)

        self._is_fitted = True
        return self

    @staticmethod
    def _format_results(candidate_params, scorers, out, n_splits):
        """From sklearn and sktime"""
        n_candidates = len(candidate_params)
        (test_scores_dict, fit_time, score_time) = zip(*out)
        test_scores_dict = _aggregate_score_dicts(test_scores_dict)

        results = {}

        # From sklearn (with the addition of greater_is_better from sktime)
        # INFO: For some reason, sklearn func does not work with sktime metrics
        # without passing greater_is_better (as done in sktime) and processing
        # it as such.
        def _store(
            key_name,
            array,
            weights=None,
            splits=False,
            rank=False,
            greater_is_better=False,
        ):
            """A small helper to store the scores/times to the cv_results_"""
            # When iterated first by splits, then by parameters
            # We want `array` to have `n_candidates` rows and `n_splits` cols.
            array = np.array(array, dtype=np.float64).reshape(n_candidates, n_splits)
            if splits:
                for split_idx in range(n_splits):
                    # Uses closure to alter the results
                    results["split%d_%s" % (split_idx, key_name)] = array[:, split_idx]

            array_means = np.average(array, axis=1, weights=weights)
            results["mean_%s" % key_name] = array_means

            if key_name.startswith(("train_", "test_")) and np.any(
                ~np.isfinite(array_means)
            ):
                warnings.warn(
                    f"One or more of the {key_name.split('_')[0]} scores "
                    f"are non-finite: {array_means}",
                    category=UserWarning,
                )

            # Weighted std is not directly available in numpy
            array_stds = np.sqrt(
                np.average(
                    (array - array_means[:, np.newaxis]) ** 2, axis=1, weights=weights
                )
            )
            results["std_%s" % key_name] = array_stds

            if rank:
                # This section is taken from sktime
                array_means = -array_means if greater_is_better else array_means
                results["rank_%s" % key_name] = np.asarray(
                    rankdata(array_means, method="min"), dtype=np.int32
                )

        _store("fit_time", fit_time)
        _store("score_time", score_time)
        # Use one MaskedArray and mask all the places where the param is not
        # applicable for that candidate. Use defaultdict as each candidate may
        # not contain all the params
        param_results = defaultdict(
            partial(
                np.ma.MaskedArray,
                np.empty(
                    n_candidates,
                ),
                mask=True,
                dtype=object,
            )
        )
        for cand_i, params in enumerate(candidate_params):
            for name, value in params.items():
                # An all masked empty array gets created for the key
                # `"param_%s" % name` at the first occurrence of `name`.
                # Setting the value at an index also unmasks that index
                param_results["param_%s" % name][cand_i] = value

        results.update(param_results)
        # Store a list of param dicts at the key "params"
        results["params"] = candidate_params

        for scorer_name, scorer in scorers.items():
            # Computed the (weighted) mean and std for test scores alone
            _store(
                "test_%s" % scorer_name,
                test_scores_dict[scorer_name],
                splits=True,
                rank=True,
                weights=None,
                greater_is_better=True if scorer._sign == 1 else False,
            )

        return results


class ForecastingGridSearchCV(BaseGridSearch):
    def __init__(
        self,
        forecaster,
        cv,
        param_grid,
        scoring=None,
        n_jobs=None,
        refit=True,
        refit_metric: str = "smape",
        verbose=0,
        pre_dispatch="2*n_jobs",
        error_score=np.nan,
        return_train_score=False,
    ):
        super(ForecastingGridSearchCV, self).__init__(
            forecaster=forecaster,
            cv=cv,
            n_jobs=n_jobs,
            pre_dispatch=pre_dispatch,
            refit=refit,
            refit_metric=refit_metric,
            scoring=scoring,
            verbose=verbose,
            error_score=error_score,
            return_train_score=return_train_score,
        )
        self.param_grid = param_grid
        _check_param_grid(param_grid)

    def _run_search(self, evaluate_candidates):
        """Search all candidates in param_grid"""
        evaluate_candidates(ParameterGrid(self.param_grid))


class ForecastingRandomizedSearchCV(BaseGridSearch):
    def __init__(
        self,
        forecaster,
        cv,
        param_distributions,
        n_iter=10,
        scoring=None,
        n_jobs=None,
        refit=True,
        refit_metric: str = "smape",
        verbose=0,
        random_state=None,
        pre_dispatch="2*n_jobs",
        error_score=np.nan,
        return_train_score=False,
    ):
        super(ForecastingRandomizedSearchCV, self).__init__(
            forecaster=forecaster,
            cv=cv,
            n_jobs=n_jobs,
            pre_dispatch=pre_dispatch,
            refit=refit,
            refit_metric=refit_metric,
            scoring=scoring,
            verbose=verbose,
            error_score=error_score,
            return_train_score=return_train_score,
        )
        self.param_distributions = param_distributions
        self.n_iter = n_iter
        self.random_state = random_state

    def _run_search(self, evaluate_candidates):
        """Search n_iter candidates from param_distributions"""
        return evaluate_candidates(
            ParameterSampler(
                self.param_distributions, self.n_iter, random_state=self.random_state
            )
        )
