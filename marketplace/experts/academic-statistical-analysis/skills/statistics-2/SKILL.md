---
name: pywayne-statistics
description: Comprehensive statistical testing library with 37+ methods for normality tests, location tests, correlation tests, time series tests, and model diagnostics. Use when performing hypothesis testing, A/B testing, data quality checks, time series analysis, or regression model validation. All methods return unified TestResult objects with consistent interface including p-value, statistic, confidence interval, and effect size.
---

# Pywayne Statistics

Comprehensive statistical testing library for hypothesis testing, A/B testing, and data analysis.

## Quick Start

```python
from pywayne.statistics import NormalityTests, LocationTests
import numpy as np

# Test data normality
nt = NormalityTests()
data = np.random.normal(0, 1, 100)
result = nt.shapiro_wilk(data)
print(f"p-value: {result.p_value:.4f}, is_normal: {not result.reject_null}")

# Compare two groups
lt = LocationTests()
group_a = np.random.normal(100, 15, 50)
group_b = np.random.normal(105, 15, 50)
result = lt.two_sample_ttest(group_a, group_b)
print(f"Significant difference: {result.reject_null}")
```

## Test Categories

### NormalityTests (`NormalityTests`)

Test if data follows a normal distribution or other specified distributions.

| Method | Description | Use Case |
|---------|-------------|-----------|
| `shapiro_wilk` | Shapiro-Wilk test | Small-medium samples (n ≤ 5000) |
| `ks_test_normal` | K-S normality test | Medium-large samples |
| `ks_test_two_sample` | Two-sample K-S test | Compare two sample distributions |
| `anderson_darling` | Anderson-Darling test | Tail-sensitive normality test |
| `dagostino_pearson` | D'Agostino-Pearson K² | Based on skewness and kurtosis |
| `jarque_bera` | Jarque-Bera test | Large samples, regression residuals |
| `chi_square_goodness_of_fit` | Chi-square goodness-of-fit | Categorical data |
| `lilliefors_test` | Lilliefors test | Unknown parameters K-S test |

**Example:**
```python
from pywayne.statistics import NormalityTests

nt = NormalityTests()
result = nt.shapiro_wilk(data)
if result.p_value < 0.05:
    print("Data is NOT normally distributed")
else:
    print("Data follows normal distribution")
```

### LocationTests (`LocationTests`)

Compare means or medians across groups (parametric and non-parametric).

| Method | Description | Use Case |
|---------|-------------|-----------|
| `one_sample_ttest` | One-sample t-test | Compare sample mean to a value |
| `two_sample_ttest` | Two-sample t-test | Compare two independent group means |
| `paired_ttest` | Paired t-test | Compare before/after measurements |
| `one_way_anova` | One-way ANOVA | Compare 3+ group means |
| `mann_whitney_u` | Mann-Whitney U test | Non-parametric two-sample test |
| `wilcoxon_signed_rank` | Wilcoxon signed-rank | Non-parametric paired test |
| `kruskal_wallis` | Kruskal-Wallis H test | Non-parametric multi-group test |

**Example (A/B Testing):**
```python
from pywayne.statistics import LocationTests, NormalityTests

lt = LocationTests()
nt = NormalityTests()

# Check normality first
if nt.shapiro_wilk(control).p_value > 0.05:
    result = lt.two_sample_ttest(control, treatment)
else:
    result = lt.mann_whitney_u(control, treatment)

print(f"Effect significant: {result.reject_null}")
```

### CorrelationTests (`CorrelationTests`)

Test correlation between variables and independence of categorical variables.

| Method | Description | Use Case |
|---------|-------------|-----------|
| `pearson_correlation` | Pearson correlation | Linear relationship |
| `spearman_correlation` | Spearman's rank | Monotonic relationship |
| `kendall_tau` | Kendall's tau | Rank correlation, small samples |
| `chi_square_independence` | Chi-square independence | Categorical variables |
| `fisher_exact_test` | Fisher's exact test | 2×2 contingency table |
| `mcnemar_test` | McNemar's test | Paired categorical data |

**Example:**
```python
from pywayne.statistics import CorrelationTests

ct = CorrelationTests()
result = ct.pearson_correlation(x, y)
print(f"Correlation: {result.statistic:.3f}, p-value: {result.p_value:.4f}")
```

### TimeSeriesTests (`TimeSeriesTests`)

Test time series properties: stationarity, autocorrelation, cointegration.

| Method | Description | Use Case |
|---------|-------------|-----------|
| `adf_test` | Augmented Dickey-Fuller | Unit root test for stationarity |
| `kpss_test` | KPSS test | Stationarity test (complements ADF) |
| `ljung_box_test` | Ljung-Box Q test | Overall autocorrelation |
| `runs_test` | Runs test | Randomness testing |
| `arch_test` | ARCH effect test | Heteroscedasticity |
| `granger_causality` | Granger causality | Causal relationship |
| `engle_granger_cointegration` | Engle-Granger cointegration | Long-term equilibrium |
| `breusch_godfrey_test` | Breusch-Godfrey | Higher-order autocorrelation |

**Example:**
```python
from pywayne.statistics import TimeSeriesTests

tst = TimeSeriesTests()
adf_result = tst.adf_test(time_series_data)
kpss_result = tst.kpss_test(time_series_data)

if adf_result.reject_null:
    print("Series is stationary")
else:
    print("Series has unit root (non-stationary)")
```

### ModelDiagnostics (`ModelDiagnostics`)

Regression model diagnostics: heteroscedasticity, autocorrelation, multicollinearity.

| Method | Description | Use Case |
|---------|-------------|-----------|
| `breusch_pagan_test` | Breusch-Pagan | Heteroscedasticity test |
| `white_test` | White's test | General heteroscedasticity |
| `goldfeld_quandt_test` | Goldfeld-Quandt | Structural break heteroscedasticity |
| `durbin_watson_test` | Durbin-Watson | First-order autocorrelation |
| `variance_inflation_factor` | VIF | Multicollinearity diagnosis |
| `levene_test` | Levene's test | Homogeneity of variance |
| `bartlett_test` | Bartlett's test | Homogeneity (normal assumption) |
| `residual_normality_test` | Residual normality | Regression assumption check |

**Example:**
```python
from pywayne.statistics import ModelDiagnostics

md = ModelDiagnostics()
residuals = y - model.predict(X)

# Check assumptions
bp_result = md.breusch_pagan_test(residuals, X)
dw_result = md.durbin_watson_test(residuals)

if bp_result.reject_null:
    print("Warning: Heteroscedasticity detected")
```

## TestResult Object

All test methods return a unified `TestResult` object:

```python
result = nt.shapiro_wilk(data)

# Access results
result.test_name        # Test method name
result.statistic        # Test statistic value
result.p_value          # P-value
result.reject_null      # True if null hypothesis is rejected
result.critical_value   # Critical value (if applicable)
result.confidence_interval # Tuple (lower, upper) if applicable
result.effect_size      # Effect size if applicable
result.additional_info  # Dict with additional information
```

## Utility Functions

### `list_all_tests()`

List all available test methods across all modules.

```python
from pywayne.statistics import list_all_tests
print(list_all_tests())
```

### `show_test_usage(method_name)`

Display usage and documentation for a specific test.

```python
from pywayne.statistics import show_test_usage
show_test_usage('shapiro_wilk')
```

## Method Selection Guide

### Normality Tests

| Sample Size | Recommended Method |
|-------------|-------------------|
| n < 30 | Shapiro-Wilk |
| 30 ≤ n ≤ 300 | Shapiro-Wilk, D'Agostino-Pearson |
| n > 300 | Jarque-Bera, Kolmogorov-Smirnov |

### Location Tests

| Condition | Parametric | Non-parametric |
|-----------|-------------|----------------|
| Normal data | t-test, ANOVA | - |
| Non-normal data | - | Mann-Whitney U, Kruskal-Wallis |
| Paired data | Paired t-test | Wilcoxon signed-rank |

## Multiple Testing Correction

When performing multiple tests, apply p-value correction:

```python
from statsmodels.stats.multitest import multipletests

p_values = [r.p_value for r in results]
rejected, p_corrected, _, _ = multipletests(
    p_values, alpha=0.05, method='fdr_bh'
)
```

## Common Applications

### Data Quality Check

```python
def data_quality_check(data):
    nt = NormalityTests()
    lt = LocationTests()

    normality = nt.shapiro_wilk(data)

    # Outlier detection (IQR)
    Q1, Q3 = np.percentile(data, [25, 75])
    IQR = Q3 - Q1
    outliers = data[(data < Q1 - 1.5*IQR) | (data > Q3 + 1.5*IQR)]

    return {
        'size': len(data),
        'is_normal': not normality.reject_null,
        'p_value': normality.p_value,
        'outliers': len(outliers)
    }
```

### A/B Testing Workflow

```python
def ab_test_analysis(control, treatment):
    nt = NormalityTests()
    lt = LocationTests()

    # Check normality
    norm_c = nt.shapiro_wilk(control[:100])
    norm_t = nt.shapiro_wilk(treatment[:100])

    # Choose appropriate test
    if norm_c.p_value > 0.05 and norm_t.p_value > 0.05:
        result = lt.two_sample_ttest(control, treatment)
    else:
        result = lt.mann_whitney_u(control, treatment)

    return {
        'test_used': result.test_name,
        'p_value': result.p_value,
        'significant': result.reject_null,
        'effect_size': result.effect_size
    }
```

### Regression Model Diagnostics

```python
def diagnose_model(y, X, model):
    md = ModelDiagnostics()
    residuals = y - model.predict(X)

    return {
        'heteroscedasticity_bp': md.breusch_pagan_test(residuals, X).reject_null,
        'autocorrelation_dw': md.durbin_watson_test(residuals).statistic,
        'residuals_normal': md.residual_normality_test(residuals).p_value,
        'vif_max': max(md.variance_inflation_factor(X))
    }
```

## Notes

- All methods accept `np.ndarray` or list as input
- All methods return `TestResult` with consistent interface
- Always validate test assumptions before applying parametric tests
- Apply multiple testing correction when performing several tests
- Report effect sizes alongside p-values for complete interpretation
