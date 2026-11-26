"""
MODELS - Master Prompt V4, Part IX + X (Statistical baselines; XGBoost/LGBM + Optuna).

Baselines: persistence, majority classifier, logistic regression.
Main models: XGBoost, LightGBM with constrained Optuna search + temporal validation.
"""
import numpy as np
import xgboost as xgb
import lightgbm as lgb
import optuna
from sklearn.linear_model import LogisticRegression
from sklearn.dummy import DummyClassifier

SEED = 42


def baselines(y_train, y_val):
    """Statistical baselines: majority classifier + logistic regression (Part IX)."""
    y_tr = np.asarray(y_train); y_va = np.asarray(y_val)
    maj = DummyClassifier(strategy="most_frequent", random_state=SEED).fit(y_tr.reshape(-1,1), y_tr).predict(y_va.reshape(-1,1))
    maj_acc = float(np.mean(maj == y_va))
    lr = LogisticRegression(max_iter=1000, random_state=SEED).fit(y_tr.reshape(-1, 1), y_tr)
    lr_acc = float(np.mean(lr.predict(y_va.reshape(-1, 1)) == y_va))
    return {"majority_val_acc": maj_acc, "logreg_val_acc": lr_acc}


def optuna_search_lgb(X_train, y_train, X_val, y_val, n_trials=15, seed=SEED):
    optuna.logging.set_verbosity(optuna.logging.WARNING)
    def obj(t):
        p = dict(n_estimators=t.suggest_int("n_estimators", 50, 150),
                 learning_rate=t.suggest_float("learning_rate", 0.01, 0.2, log=True),
                 max_depth=t.suggest_int("max_depth", 3, 7),
                 num_leaves=t.suggest_int("num_leaves", 8, 64),
                 subsample=t.suggest_float("subsample", 0.6, 1.0),
                 colsample_bytree=t.suggest_float("colsample_bytree", 0.6, 1.0),
                 random_state=seed, verbose=-1)
        return float(np.mean(lgb.LGBMClassifier(**p).fit(X_train, y_train).predict(X_val) != y_val))
    st = optuna.create_study(direction="minimize"); st.optimize(obj, n_trials=n_trials)
    return st.best_params


def train_final(model, X, y):
    model.fit(X, y); return model
