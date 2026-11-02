# JSON Spec Reference

Every analysis is driven by a JSON spec. All specs share these common fields:

```json
{
  "dataset_path": "path/to/data.csv",   // required (absolute or relative to RSTATS_ROOT)
  "analysis_type": "linear_regression",  // required
  "alpha": 0.05,                         // optional, default 0.05
  "seed": 42,                            // optional, default 42
  "output_dir": "output/my_analysis"     // required
}
```

---

## Foundation

### summary
No additional required fields. Analyzes all numeric/categorical columns.

### ttest
| Field | Required | Example |
|-------|----------|---------|
| outcome | yes | `"mpg"` |
| group_var | yes | `"am"` |
| paired | no | `false` |
| equal_var | no | `false` (Welch default) |

### anova
| Field | Required | Example |
|-------|----------|---------|
| outcome | yes | `"mpg"` |
| group_var | yes | `"cyl"` |

### correlation
| Field | Required | Example |
|-------|----------|---------|
| outcome | yes | `"mpg"` |
| predictors | yes | `["wt"]` (first element used) |
| cor_method | no | `"pearson"` or `"spearman"` |

### linear_regression / logistic_regression / poisson_regression
| Field | Required | Example |
|-------|----------|---------|
| outcome | yes | `"mpg"` |
| predictors | yes | `["wt", "hp"]` |
| formula | yes | `"mpg ~ wt + hp"` |

### forecast_arima / forecast_ets
| Field | Required | Example |
|-------|----------|---------|
| outcome | yes | `"passengers"` |
| frequency | no | `12` |
| forecast_horizon | no | `24` |

---

## Non-parametric

### wilcoxon
Same as `ttest` plus: `paired` (boolean).

### kruskal
Same as `anova`. Auto Dunn post-hoc if significant. Optional: `p_adjust_method` (`"holm"`).

### chisq / fisher
| Field | Required | Example |
|-------|----------|---------|
| row_var | yes | `"exposure"` |
| col_var | yes | `"outcome"` |

### mcnemar
Same as chisq: `row_var`, `col_var`.

### friedman
| Field | Required | Example |
|-------|----------|---------|
| outcome | yes | `"score"` |
| group_var | yes | `"condition"` |
| id_var | yes | `"subject"` |

### missing_diagnostics
| Field | Required | Example |
|-------|----------|---------|
| variables | no | `["x1", "x2"]` (default: all) |

### multiple_imputation
| Field | Required | Example |
|-------|----------|---------|
| variables | no | all columns |
| m | no | `5` |
| imputation_method | no | `null` (auto) or `"pmm"` |
| downstream_analysis | no | `{"analysis_type": "linear_regression", "formula": "y ~ x1 + x2"}` |

### p_adjust
| Field | Required | Example |
|-------|----------|---------|
| p_values | yes* | `[0.001, 0.03, 0.12]` |
| labels | no | `["Test1", "Test2", "Test3"]` |
| p_adjust_method | no | `"BH"` (default) |

*Or provide `p_values_file` (CSV with p_value column), or data with p_value column.

---

## Survival + Epidemiology

### kaplan_meier
| Field | Required | Example |
|-------|----------|---------|
| time_var | yes | `"time"` |
| event_var | yes | `"status"` (1=event, 0=censored) |
| group_var | no | `"sex"` |
| time_points | no | `[180, 365, 730]` |

### cox_regression
| Field | Required | Example |
|-------|----------|---------|
| time_var | yes | `"time"` |
| event_var | yes | `"status"` |
| predictors | yes | `["age", "sex"]` |
| formula | yes | `"Surv(time, status) ~ age + sex"` |

### competing_risks
| Field | Required | Example |
|-------|----------|---------|
| time_var | yes | `"time"` |
| event_var | yes | `"event"` (0=censor, 1=main, 2=competing) |
| group_var | no | `"treatment"` |
| predictors | no | `["age", "sex"]` |
| event_of_interest | no | `1` |

### rmst
| Field | Required | Example |
|-------|----------|---------|
| time_var | yes | `"time"` |
| event_var | yes | `"status"` |
| group_var | yes | `"sex"` (binary) |
| tau | no | `365` (auto: min of group max times) |

### odds_ratio / risk_ratio / nnt
| Field | Required | Example |
|-------|----------|---------|
| exposure | yes | `"treatment"` |
| outcome | yes | `"event"` |
| exposure_level | no | `"Exposed"` |
| outcome_level | no | `"Case"` |

### incidence_rate
| Field | Required | Example |
|-------|----------|---------|
| events_var | yes | `"event"` |
| person_time_var | yes | `"person_time"` |
| group_var | yes | `"treatment"` |

### mantel_haenszel
| Field | Required | Example |
|-------|----------|---------|
| exposure | yes | `"exposure"` |
| outcome | yes | `"outcome"` |
| strata | yes | `"age_group"` |

---

## Mixed Effects + Causal

### lmm / glmm
| Field | Required | Example |
|-------|----------|---------|
| formula | yes | `"score ~ time + (1|subject)"` |
| family | glmm only | `"binomial"` or `"poisson"` |

### gee
| Field | Required | Example |
|-------|----------|---------|
| formula | yes | `"outcome ~ x1 + x2"` |
| id_var | yes | `"cluster"` |
| family | no | `"binomial"` |
| corstr | no | `"exchangeable"` |

### icc
| Field | Required | Example |
|-------|----------|---------|
| outcome | yes | `"score"` |
| group_var | yes | `"school"` |

### propensity_match
| Field | Required | Example |
|-------|----------|---------|
| treatment_var | yes | `"treated"` |
| formula | yes | `"treated ~ age + sex"` |
| outcome_var | no | `"outcome"` |
| match_method | no | `"nearest"` |
| caliper | no | `0.2` |

### propensity_weight
Same as propensity_match plus: `estimand` (`"ATE"` / `"ATT"` / `"ATO"`).

### doubly_robust
| Field | Required | Example |
|-------|----------|---------|
| treatment_var | yes | `"treated"` |
| outcome_var | yes | `"outcome"` |
| ps_formula | yes | `"treated ~ age + sex"` |
| covariates | no | `["age", "sex"]` |

### mediation_analysis
| Field | Required | Example |
|-------|----------|---------|
| treatment_var | yes | `"treatment"` |
| mediator_var | yes | `"mediator"` |
| outcome_var | yes | `"outcome"` |
| sims | no | `1000` |

### iv_regression
| Field | Required | Example |
|-------|----------|---------|
| formula | yes | `"outcome ~ endogenous \| instrument"` |
| endogenous | no | `"endogenous"` |

### did
| Field | Required | Example |
|-------|----------|---------|
| outcome | yes | `"outcome"` |
| treatment_var | yes | `"treated"` |
| time_var | yes | `"period"` |
| post_var | no | `"post"` |
| id_var | no | `"id"` |

### rdd
| Field | Required | Example |
|-------|----------|---------|
| running_var | yes | `"score"` |
| outcome | yes | `"outcome"` |
| cutoff | no | `0` |

### tmle
| Field | Required | Example |
|-------|----------|---------|
| treatment_var | yes | `"treated"` |
| outcome_var | yes | `"outcome"` |
| confounders | yes | `["age", "sex"]` |

### causal_forest
| Field | Required | Example |
|-------|----------|---------|
| treatment_var | yes | `"treated"` |
| outcome_var | yes | `"outcome"` |
| covariates | yes | `["age", "sex"]` |

### g_computation
| Field | Required | Example |
|-------|----------|---------|
| treatment_var | yes | `"treated"` |
| outcome_var | yes | `"outcome"` |
| formula | yes | `"outcome ~ treated + age + sex"` |

### dag_analysis
| Field | Required | Example |
|-------|----------|---------|
| dag_syntax | yes | `"dag { X -> Y; Z -> X; Z -> Y }"` |
| exposure | no | `"X"` |
| outcome | no | `"Y"` |

---

## Bayesian + Advanced

### bayesian_regression
| Field | Required | Example |
|-------|----------|---------|
| formula | yes | `"mpg ~ wt + hp"` |
| family | no | `"gaussian"` |
| iter | no | `2000` |
| chains | no | `4` |
| compute_loo | no | `true` |

### bayes_factor
| Field | Required | Example |
|-------|----------|---------|
| test_type | yes | `"ttest"` or `"regression"` |
| outcome | for ttest | `"mpg"` |
| group_var | for ttest | `"am"` |
| formula | for regression | `"mpg ~ wt + hp"` |

### gam
| Field | Required | Example |
|-------|----------|---------|
| formula | yes | `"y ~ s(x1) + x2 + s(x3)"` |
| method | no | `"REML"` |

### quantile_regression
| Field | Required | Example |
|-------|----------|---------|
| formula | yes | `"mpg ~ wt + hp"` |
| tau | no | `[0.25, 0.5, 0.75]` |

### robust_regression
| Field | Required | Example |
|-------|----------|---------|
| formula | yes | `"mpg ~ wt + hp"` |

### zero_inflated / hurdle
| Field | Required | Example |
|-------|----------|---------|
| formula | yes | `"count ~ x1 + x2"` |
| outcome | yes | `"count"` |
| zi_family / hurdle_dist | no | `"poisson"` or `"negbin"` |

### ordinal_regression
| Field | Required | Example |
|-------|----------|---------|
| formula | yes | `"satisfaction ~ age + income"` |
| outcome | yes | `"satisfaction"` |
| levels_order | no | `["Low", "Med", "High"]` |

### multinomial
| Field | Required | Example |
|-------|----------|---------|
| formula | yes | `"Species ~ x1 + x2"` |
| outcome | yes | `"Species"` |
| reference_level | no | `"setosa"` |

---

## Regularization

### penalized_regression
| Field | Required | Example |
|-------|----------|---------|
| outcome | yes | `"y"` |
| predictors | yes | `["x1", "x2", ...]` |
| penalty | no | `"lasso"` / `"ridge"` / `"elastic_net"` |
| family | no | `"gaussian"` / `"binomial"` |
| alpha_mix | for EN | `0.5` |
| nfolds | no | `10` |

### penalized_cox
Same as penalized_regression plus: `time_var`, `event_var` (instead of outcome).

### adaptive_lasso
Same as penalized_regression plus: `gamma` (default 1).

### group_lasso
Same as penalized_regression plus: `group` (integer vector, same length as predictors).

### ncvreg
Same as penalized_regression plus: `penalty` (`"SCAD"` or `"MCP"`).

### stability_selection
Same as penalized_regression plus: `cutoff` (default 0.75), `PFER` (default 1).

---

## Meta-analysis

### meta_analysis
| Field | Required | Example |
|-------|----------|---------|
| yi_var | yes | `"yi"` (effect size column) |
| vi_var | yes* | `"vi"` (variance column) |
| sei_var | alt* | `"sei"` (SE column, use instead of vi) |
| study_var | no | `"study"` |
| method | no | `"REML"` |

### meta_regression
Same as meta_analysis plus: `moderators` (list of column names).

### subgroup_meta
Same as meta_analysis plus: `subgroup_var`.

### network_meta
| Field | Required | Example |
|-------|----------|---------|
| treat1_var | yes | `"treat1"` |
| treat2_var | yes | `"treat2"` |
| yi_var | yes | `"yi"` |
| sei_var | yes | `"sei"` |
| reference | no | `"placebo"` |

---

## Power / Sample Size

### power_analysis
| Field | Required | Example |
|-------|----------|---------|
| power_type | yes | `"power_ttest"` / `"power_anova"` / `"power_chisq"` / `"power_correlation"` / `"power_regression"` / `"power_proportion"` |
| effect_size | yes* | `0.5` (provide 3 of 4: n, power, effect_size, alpha) |
| n | yes* | `null` (solve for this) |
| power | yes* | `0.8` |
| n_predictors | for regression | `3` |
| k | for anova | `3` |

### power_survival
| Field | Required | Example |
|-------|----------|---------|
| hr | yes | `0.7` |
| power | no | `0.8` |
| event_prob | no | `0.8` |
| allocation_ratio | no | `1` |

### power_mixed
| Field | Required | Example |
|-------|----------|---------|
| n_subjects | yes | `50` |
| effect_size | yes | `0.3` |
| n_timepoints | no | `5` |
| icc | no | `0.5` |

### power_equivalence
| Field | Required | Example |
|-------|----------|---------|
| design_type | no | `"non_inferiority"` or `"equivalence"` |
| margin | yes | `0.5` |
| expected_diff | no | `0` |
| sd | no | `1` |

### power_cluster
| Field | Required | Example |
|-------|----------|---------|
| effect_size | yes | `0.3` |
| icc | yes | `0.05` |
| cluster_size | no | `30` |

### adaptive_design
| Field | Required | Example |
|-------|----------|---------|
| n_stages | no | `3` |
| boundary_type | no | `"OF"` (O'Brien-Fleming) or `"P"` (Pocock) |
| effect_size | no | `0.3` |

---

## SEM

### sem
| Field | Required | Example |
|-------|----------|---------|
| model_syntax | yes | `"f1 =~ x1+x2\nf2 =~ x3+x4\nf2 ~ f1"` |
| estimator | no | `"ML"` |

### cfa
Same as sem. Model syntax defines factors only: `"visual =~ x1+x2+x3"`.

### measurement_invariance
Same as cfa plus: `group_var` (required).

### path_analysis
Same as sem. Use `":="` for indirect effects: `"indirect := a*b"`.

---

## Diagnostics

### roc_auc
| Field | Required | Example |
|-------|----------|---------|
| predictor_var | yes | `"biomarker"` |
| outcome_var | yes | `"disease"` (binary) |

### bland_altman
| Field | Required | Example |
|-------|----------|---------|
| method1_var | yes | `"method1"` |
| method2_var | yes | `"method2"` |

### kappa
| Field | Required | Example |
|-------|----------|---------|
| rater_vars | yes | `["rater1", "rater2"]` |

### cronbach_alpha
| Field | Required | Example |
|-------|----------|---------|
| item_vars | yes | `["item1", "item2", ..., "item10"]` |

---

## Longitudinal

### joint_model
| Field | Required | Example |
|-------|----------|---------|
| long_formula | yes | `"biomarker ~ time"` |
| id_var | yes | `"id"` |
| time_var | yes | `"time"` |
| event_var | yes | `"event"` |
| surv_time_var | no | `"surv_time"` |

### multistate
| Field | Required | Example |
|-------|----------|---------|
| state_var | yes | `"state"` |
| time_var | yes | `"time"` |
| id_var | yes | `"id"` |
| covariates | no | `["age"]` |
| pred_times | no | `[1, 3, 5]` |

### trajectory
| Field | Required | Example |
|-------|----------|---------|
| outcome | yes | `"score"` |
| id_var | yes | `"id"` |
| time_var | yes | `"time"` |
| max_classes | no | `4` |

---

## Psychometrics

### irt
| Field | Required | Example |
|-------|----------|---------|
| item_vars | yes | `["item1", ..., "item20"]` |
| model_type | no | `"2pl"` / `"rasch"` / `"3pl"` / `"grm"` |

### lca
| Field | Required | Example |
|-------|----------|---------|
| indicator_vars | yes | `["y1", "y2", "y3"]` |
| max_classes | no | `4` |

### multilevel_mediation
| Field | Required | Example |
|-------|----------|---------|
| treatment_var | yes | `"treatment"` |
| mediator_var | yes | `"mediator"` |
| outcome_var | yes | `"outcome"` |
| cluster_var | yes | `"school"` |
| sims | no | `500` |
