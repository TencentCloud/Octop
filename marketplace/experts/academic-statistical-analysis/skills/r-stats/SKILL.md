---
name: openclaw-r-stats
metadata:
  openclaw:
    emoji: "📊"
    requires:
      bins:
        - Rscript
        - bash
description: >
  82 statistical analysis methods in R — regression, survival, Bayesian,
  meta-analysis, causal inference, SEM, IRT, clinical trial design, and more.
  JSON spec driven, reproducible, with mandatory effect sizes and assumption checks.
  Use when: user asks for statistical analysis, hypothesis testing, regression,
  ANOVA, t-test, chi-square, correlation, survival analysis, Cox regression,
  meta-analysis, propensity score, causal inference, SEM, IRT, power analysis,
  sample size calculation, time series forecasting, mixed models, Bayesian analysis,
  ROC/AUC, agreement/reliability, zero-inflated models, penalized regression,
  LASSO, group sequential design, or mentions R packages like ggplot2, brms,
  survival, metafor, lavaan, glmnet, mice, lme4, gee, dagitty, tmle.
  Multilingual triggers — EN: statistics, regression, significance, predict;
  ZH: 统计分析, 回归, 检验, 预测, 显著性, 生存分析, 元分析, 贝叶斯;
  JA: 統計分析, 回帰, 検定, 予測; KO: 통계분석, 회귀, 검정;
  ES: análisis estadístico, regresión; FR: analyse statistique, régression;
  DE: statistische Analyse, Regression; PT: análise estatística, regressão;
  RU: статистический анализ, регрессия; AR: تحليل إحصائي.
---

# OpenClaw R Stats

## When to Use

User asks for any statistical analysis, hypothesis testing, group comparison,
prediction, association, survival analysis, meta-analysis, causal inference,
power/sample size, or mentions R statistical packages.

## What This Skill Does NOT Do

- Claim causality from observational data (use "associated with")
- Run large exploratory fishing without clear user intent
- Silently ignore assumption violations
- Report only p-values (always include effect sizes and CIs)

## Pre-Flight (Mandatory)

1. Confirm dataset exists and is readable
2. Run schema inspection: `bash {baseDir}/scripts/run-rstats.sh schema --data <path>`
3. Report: rows, columns, types, missing values
4. If missing > 5%, warn. If n < 30, warn small sample.

## Environment Setup

First time or errors: `bash {baseDir}/scripts/run-rstats.sh doctor`

Install by profile (only when needed):

| Profile | Script | Methods |
|---------|--------|---------|
| Core | `install-core.R` | t-test, regression, ANOVA, chi-sq |
| Survival | `install-survival.R` | KM, Cox, competing risks, RMST |
| Missing | `install-missing.R` | MICE, MCAR test |
| Mixed | `install-mixed.R` | LMM, GLMM, GEE, ICC |
| Bayes | `install-bayes.R` | brms, Bayes factors |
| Causal | `install-causal.R` | PSM, IPTW, IV, DiD, RDD, TMLE |
| Meta | `install-meta.R` | meta-analysis, NMA |
| SEM | `install-sem.R` | SEM, CFA, lavaan |
| Diagnostic | `install-diagnostic.R` | ROC, kappa, alpha |
| Advanced | `install-advanced.R` | GAM, quantile, zero-inflated |
| Power | `install-power.R` | power/sample size |

## Workflow

1. Determine analysis type (see references/METHOD_TABLE.md)
2. Inspect dataset schema
3. Build JSON spec:
```json
{
  "dataset_path": "<path>",
  "analysis_type": "<type>",
  "outcome": "<column>",
  "predictors": ["<col1>"],
  "hypothesis": "<plain language>",
  "alpha": 0.05,
  "seed": 42,
  "output_dir": "<path>"
}
```
4. Save as .json, run: `bash {baseDir}/scripts/run-rstats.sh analyze --spec <path>`
5. Read summary.json + report.md
6. Present: Summary → Statistics → Interpretation → Plots → Assumptions → Caveats

## Analysis Selection

For the complete 82-method table with user intent mapping,
see **references/METHOD_TABLE.md**.

Quick lookup — most common:

| Intent | analysis_type |
|--------|--------------|
| Compare 2 groups | `ttest` or `wilcoxon` |
| Compare 3+ groups | `anova` or `kruskal` |
| Categorical association | `chisq` or `fisher` |
| Predict continuous | `linear_regression` |
| Predict binary | `logistic_regression` |
| Survival curves | `kaplan_meier` |
| Survival regression | `cox_regression` |
| Meta-analysis | `meta_analysis` |
| Causal effect | `propensity_match` or `did` |
| Power/sample size | `power_analysis` |

## Automatic Method Switching

- Non-normal + n < 30 → `wilcoxon` over `ttest`
- Unequal variance → Welch t-test (`equal_var: false`)
- Expected cells < 5 → `fisher` over `chisq`
- Overdispersion in Poisson → suggest negative binomial
- Heteroscedastic residuals → robust SE warning

## Reporting Rules (Non-Negotiable)

Every analysis MUST include:
- Sample size (n) and missing data handling
- Method name and rationale
- Point estimates with confidence intervals
- Effect sizes (Cohen's d, η², R², OR, HR, etc.)
- Assumption check results
- Limitations

Language: "associated with" / "evidence suggests" — NEVER "proves" / "causes"

## Spec Field Reference

See **references/SPEC_REFERENCE.md** for required/optional fields per analysis_type.
