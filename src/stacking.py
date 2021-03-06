import logging

"""
__file__

    stacking.py

__description__

    Stack several models together.

__author__

    Sergii Golovko < sergii.golovko@gmail.com >

"""

import logging
import numpy as np
import pandas as pd
import pickle
import os

from globals import CONFIG
from model_utils import tune_parameters, fit_and_predict, cross_validation
from model_utils import get_classifiers, get_stacking_param_grids
from model_utils import rescale_preds, score, A, B
from modelling import save_predictions
from cv_utils import get_cv

# Global directories.
BASE_DIR = os.path.join(os.path.dirname(os.path.realpath(__file__)), '..')
DATA_DIR = os.path.join(BASE_DIR, CONFIG['DATA_DIR'])
OUTPUT_DIR = os.path.join(BASE_DIR, CONFIG['OUTPUT_DIR'])
PICKLE_DIR = os.path.join(BASE_DIR, CONFIG['PICKLED_DIR'])
PRED_DIR = os.path.join(OUTPUT_DIR, CONFIG['PRED_DIR'])
METAFEATURES_DIR = os.path.join(PICKLE_DIR, CONFIG['METAFEATURES_DIR'])

# Global files.
TRAIN_FILE = os.path.join(DATA_DIR, 'train.csv')
TEST_FILE = os.path.join(DATA_DIR, 'test.csv')

# Number of rows to read from files.
TEST_NROWS = CONFIG['TEST_NROWS']
TRAIN_NROWS = CONFIG['TRAIN_NROWS']

# Stacking models.
STACKING_MODELS = ['ExtraTreesClassifier']


def filenames_in_dir(dir_, extension='.csv', keep_extension=False, sort=True):

    filenames = []
    for filename in os.listdir(dir_):
        if filename.endswith(extension):
            filenames.append(filename)

    if not keep_extension:
        filenames = [f.split(extension, 1)[0] for f in filenames]

    return filenames


def debug_metafeatures(metafeature, name):
    logging.debug('Debuging metafeatures for %s model.' % name)

    y_train = pd.read_csv(TRAIN_FILE, usecols=['is_duplicate'],
                          nrows=TRAIN_NROWS)
    y_train = y_train['is_duplicate'].values
    cv = get_cv(y_train, n_folds=5, type='kfold')

    for i, (train_ind, test_ind) in enumerate(cv):

        # Split model into training and validation sets.
        Xi, yi = metafeature[np.array(test_ind)], y_train[np.array(test_ind)]
        test_score = score(yi, Xi)
        logging.debug('Fold %d, test score: %.5f' % (i, test_score))

    logging.debug('Finished debuging.')


def load_metafeatures(metafeatures_dir=METAFEATURES_DIR, preds_dir=PRED_DIR):
    metafeatures_filenames = filenames_in_dir(metafeatures_dir, '.pickle')
    preds_filenames = filenames_in_dir(preds_dir, '.csv')

    logging.debug(metafeatures_filenames)
    logging.debug(preds_filenames)

    common_filenames = set(metafeatures_filenames).intersection(set(preds_filenames))
    # common_filenames = [f for f in common_filenames if f.startswith('XGBC')]
    logging.debug(common_filenames)

    # Load metafeatures.
    data = []
    for filename in common_filenames:
        with open((os.path.join(metafeatures_dir, filename + '.pickle')), 'rb') as file:
            try:
                metafeature = np.sum(pickle.load(file), axis=1)
            except:
                metafeature = pickle.load(file)
            # metafeature = rescale_preds(metafeature, a=B, b=A)
            debug_metafeatures(metafeature, filename)
            metafeature = rescale_preds(metafeature, a=B, b=A)
            data.append(metafeature)
    X_train = np.stack(data, axis=1)
    X_train = pd.DataFrame(X_train, columns=common_filenames)

    # Load preds.
    data = []
    ids = None
    for filename in common_filenames:
        file = os.path.join(preds_dir, filename + '.csv')
        preds = pd.read_csv(file, usecols=['is_duplicate'])
        # We need to rescale predictions back ot avoid double rescaling.
        # TODO: think about a better way to do it.
        preds = rescale_preds(preds, a=B, b=A)
        data.append(preds.values)

        if ids is None:
            ids = pd.read_csv(file, usecols=['test_id'])

    X_test = np.concatenate(data, axis=1)
    X_test = pd.DataFrame(X_test, columns=common_filenames)

    return X_train.values, X_test.values, ids


def stacking():

    logging.info('STACKING')

    X_train, X_test, test_ids = load_metafeatures()
    y_train = pd.read_csv(TRAIN_FILE, usecols=['is_duplicate'],
                          nrows=TRAIN_NROWS)
    y_train = y_train['is_duplicate'].values

    logging.info('Shape of X_train is %s' % str(X_train.shape))
    logging.info('Shape of X_test is %s' % str(X_test.shape))
    logging.info('Length of y_train is %d' % len(y_train))
    cv = get_cv(y_train, n_folds=5, type='kfold')

    names = STACKING_MODELS
    estimators = get_classifiers(names)
    par_grids = get_stacking_param_grids(names)
    preds = test_ids.copy()
    for (estimator, par_grid, name) in zip(estimators, par_grids, names):
        logging.info('Doing parameter tuning for %s model' % name)
        best_params, best_score = tune_parameters(estimator, name,
                                                  par_grid, X_train,
                                                  y_train, cv)
        estimator.set_params(**best_params)
        logging.info('Finished parameter tuning for %s model' % name)

        logging.info('Fitting %s model' % name)
        filename = 'Stacking' + name
        preds['is_duplicate'] = (
            fit_and_predict(estimator, X_train, y_train, X_test))
        save_predictions(preds, filename)
        logging.info('Finished fitting %s model' % name)

    logging.info('FINISHED STACKING')


if __name__ == '__main__':
    logging.basicConfig(level=logging.DEBUG,
                        format='%(asctime)s %(levelname)s: %(message)s',
                        datefmt='%m/%d/%Y %I:%M:%S %p')
    stacking()
