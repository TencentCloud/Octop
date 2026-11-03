## Description: <br>
Portfolio risk management and analytics for VaR, Monte Carlo simulation, stress testing, Risk Parity, Calmar and Black-Litterman optimization, pre-trade checks, sector concentration checks, portfolio management, broker sync, and cross-portfolio correlation analysis. <br>

This skill is ready for commercial/non-commercial use. <br>

## Publisher: <br>
[mib424242](https://clawhub.ai/user/mib424242) <br>

### License/Terms of Use: <br>
MIT <br>


## Use Case: <br>
External RiskOfficer users use this skill through an agent to inspect portfolio holdings, calculate risk metrics, run simulations and stress tests, check proposed trades, and prepare optimization plans for virtual portfolios. The skill can also guide account setup and token configuration for the RiskOfficer API. <br>

### Deployment Geography for Use: <br>
Global <br>

## Known Risks and Mitigations: <br>
Risk: The skill uses an account-level RiskOfficer API token that can read sensitive portfolio data. <br>
Mitigation: Use a session environment variable when possible, avoid storing the token on disk, and revoke or rotate the token when access is no longer needed. <br>
Risk: The skill can make persistent changes in RiskOfficer, including portfolio create, update, delete, active snapshot changes, optimization apply, broker sync, and broker disconnect actions. <br>
Mitigation: Require explicit user confirmation before any persistent change, and show the proposed action and affected portfolio or broker before execution. <br>
Risk: Live broker sync or disconnect actions using sandbox=false can affect live-account data connections. <br>
Mitigation: Confirm whether the target is sandbox or live before broker actions, and require an additional confirmation for sandbox=false operations. <br>
Risk: Portfolio analysis and optimization outputs can be mistaken for direct trading instructions. <br>
Mitigation: Present outputs as RiskOfficer analysis for virtual portfolios and clarify that the skill does not place real broker orders. <br>


## Reference(s): <br>
- [RiskOfficer ClawHub Page](https://clawhub.ai/mib424242/riskofficer) <br>
- [RiskOfficer Website](https://riskofficer.tech) <br>
- [Academic and Technical References](references/academic-references.md) <br>
- [VaR and CVaR Methodology](references/methodology-var.md) <br>
- [Monte Carlo Simulation Methodology](references/methodology-monte-carlo.md) <br>
- [Stress Test Methodology](references/methodology-stress-test.md) <br>
- [Risk Parity Methodology](references/methodology-risk-parity.md) <br>
- [Calmar Ratio and Max-Calmar Optimization](references/methodology-calmar.md) <br>
- [Black-Litterman Optimization Methodology](references/methodology-black-litterman.md) <br>
- [Pre-Trade Check Methodology](references/methodology-pre-trade.md) <br>
- [Cross-Portfolio PnL Correlation Methodology](references/methodology-correlation.md) <br>
- [Aggregated Portfolio Methodology](references/methodology-aggregation.md) <br>
- [Hierarchical Risk Parity Methodology](references/methodology-hrp.md) <br>
- [Portfolio Metrics Methodology](references/methodology-metrics.md) <br>
- [Auto Portfolio Generation Methodology](references/methodology-auto-portfolio.md) <br>


## Skill Output: <br>
**Output Type(s):** [Text, Markdown, Shell commands, Configuration, Guidance] <br>
**Output Format:** [Markdown with inline shell commands and JSON API examples] <br>
**Output Parameters:** [1D] <br>
**Other Properties Related to Output:** [May include risk metrics, portfolio summaries, optimization plans, pre-trade check results, and confirmation prompts before persistent account changes.] <br>

## Skill Version(s): <br>
4.3.0 (source: server-resolved release metadata and clawhub.json) <br>

## Ethical Considerations: <br>
Users should evaluate whether this skill is appropriate for their environment, review any generated or modified files before relying on them, and apply their organization's safety, security, and compliance requirements before deployment. <br>
