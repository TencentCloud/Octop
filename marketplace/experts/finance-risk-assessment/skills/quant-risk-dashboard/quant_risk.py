"""
Quantitative Risk Dashboard - Real-time risk management and monitoring
"""
import numpy as np
import pandas as pd
from typing import Dict, List, Optional
from datetime import datetime, timedelta
import json
import warnings
warnings.filterwarnings('ignore')


class RiskDashboard:
    """Professional risk management dashboard"""
    
    def __init__(
        self,
        initial_capital: float = 1000000,
        var_confidence: float = 0.95,
        max_position_pct: float = 0.15,
        max_drawdown_pct: float = 0.20
    ):
        self.initial_capital = initial_capital
        self.var_confidence = var_confidence
        self.max_position_pct = max_position_pct
        self.max_drawdown_pct = max_drawdown_pct
        
        self.positions = {}
        self.pnl_history = []
        self.alerts = []
        self.alert_callbacks = []
        
        # Risk limits
        self.limits = {
            'max_position_pct': max_position_pct,
            'max_sector_pct': 0.30,
            'max_leverage': 1.5,
            'max_drawdown': max_drawdown_pct,
            'max_var_pct': 0.05,
        }
        
        # Historical returns for VaR (mock - would load real data)
        self.historical_returns = np.random.normal(0.0005, 0.02, 1000)
    
    # ==================== Position Management ====================
    
    def add_position(
        self,
        symbol: str,
        shares: int,
        entry_price: float,
        current_price: float,
        sector: str = 'Other'
    ):
        """Add a position"""
        self.positions[symbol] = {
            'symbol': symbol,
            'shares': shares,
            'entry_price': entry_price,
            'current_price': current_price,
            'sector': sector,
            'market_value': shares * current_price,
            'cost_basis': shares * entry_price,
            'unrealized_pnl': shares * (current_price - entry_price),
            'return_pct': (current_price - entry_price) / entry_price
        }
        
        self._check_limits()
    
    def remove_position(self, symbol: str):
        """Remove a position"""
        if symbol in self.positions:
            del self.positions[symbol]
            self._check_limits()
    
    def update_price(self, symbol: str, price: float):
        """Update current price"""
        if symbol in self.positions:
            pos = self.positions[symbol]
            pos['current_price'] = price
            pos['market_value'] = pos['shares'] * price
            pos['unrealized_pnl'] = pos['shares'] * (price - pos['entry_price'])
            pos['return_pct'] = (price - pos['entry_price']) / pos['entry_price']
            
            self._check_limits()
    
    def get_positions(self) -> pd.DataFrame:
        """Get all positions as DataFrame"""
        if not self.positions:
            return pd.DataFrame()
        
        df = pd.DataFrame(self.positions.values())
        df = df.set_index('symbol')
        
        # Add weights
        total_mv = df['market_value'].sum()
        if total_mv > 0:
            df['weight'] = df['market_value'] / total_mv
        
        return df
    
    # ==================== Risk Metrics ====================
    
    def get_risk_metrics(self) -> Dict:
        """Calculate comprehensive risk metrics"""
        positions = self.get_positions()
        
        if positions.empty:
            return self._empty_metrics()
        
        # Current portfolio value
        portfolio_value = self.initial_capital + self._total_unrealized_pnl()
        
        # Total exposure
        total_exposure = positions['market_value'].sum()
        
        # VaR
        var_95 = self.calculate_var(0.95)
        var_99 = self.calculate_var(0.99)
        
        # CVaR
        cvar_95 = self.calculate_cvar(0.95)
        
        # Volatility
        volatility = self._calculate_volatility()
        
        # Max drawdown (simplified - would track history)
        max_dd = self._calculate_max_drawdown()
        
        # Sharpe ratio (simplified)
        sharpe = self._calculate_sharpe()
        
        # Sortino ratio
        sortino = self._calculate_sortino()
        
        # Beta (simplified - would use real market data)
        beta = 1.0
        
        # Alpha (simplified)
        alpha = self._calculate_alpha()
        
        # Win rate
        win_rate = (positions['unrealized_pnl'] > 0).mean()
        
        return {
            'portfolio_value': portfolio_value,
            'cash': self.initial_capital - total_exposure,
            'total_exposure': total_exposure,
            'total_pnl': self._total_unrealized_pnl(),
            'return_pct': self._total_unrealized_pnl() / self.initial_capital,
            'var_95': var_95,
            'var_99': var_99,
            'cvar_95': cvar_95,
            'volatility': volatility,
            'max_drawdown': max_dd,
            'sharpe_ratio': sharpe,
            'sortino_ratio': sortino,
            'beta': beta,
            'alpha': alpha,
            'win_rate': win_rate,
            'position_count': len(positions),
            'leverage': total_exposure / portfolio_value if portfolio_value > 0 else 0
        }
    
    def _empty_metrics(self) -> Dict:
        """Empty metrics when no positions"""
        return {
            'portfolio_value': self.initial_capital,
            'cash': self.initial_capital,
            'total_exposure': 0,
            'total_pnl': 0,
            'return_pct': 0,
            'var_95': 0,
            'var_99': 0,
            'cvar_95': 0,
            'volatility': 0,
            'max_drawdown': 0,
            'sharpe_ratio': 0,
            'sortino_ratio': 0,
            'beta': 1.0,
            'alpha': 0,
            'win_rate': 0,
            'position_count': 0,
            'leverage': 0
        }
    
    def calculate_var(self, confidence: float = 0.95) -> float:
        """Calculate Value at Risk"""
        positions = self.get_positions()
        
        if positions.empty:
            return 0
        
        # Portfolio value
        portfolio_value = self.initial_capital + self._total_unrealized_pnl()
        
        # Position weights
        weights = positions['weight'].values
        
        # Position volatilities (simplified - would use real data)
        volatilities = np.abs(positions['return_pct'].values) * np.sqrt(252)
        
        # Portfolio volatility
        if len(weights) > 1:
            # Simplified correlation (would use real correlation matrix)
            corr = np.eye(len(weights)) * 0.3 + 0.7
            cov = np.outer(volatilities, volatilities) * corr
            portfolio_vol = np.sqrt(weights @ cov @ weights)
        else:
            portfolio_vol = volatilities[0] if len(volatilities) > 0 else 0
        
        # VaR using parametric method
        from scipy.stats import norm
        z_score = norm.ppf(1 - confidence)
        
        var = portfolio_value * portfolio_vol * abs(z_score)
        
        return var
    
    def calculate_cvar(self, confidence: float = 0.95) -> float:
        """Calculate Conditional VaR (Expected Shortfall)"""
        var = self.calculate_var(confidence)
        
        # CVaR approximation
        from scipy.stats import norm
        z_score = norm.ppf(1 - confidence)
        
        cvar_multiplier = norm.pdf(z_score) / (1 - confidence)
        
        portfolio_value = self.initial_capital + self._total_unrealized_pnl()
        volatility = self._calculate_volatility()
        
        cvar = portfolio_value * volatility * cvar_multiplier
        
        return cvar
    
    def _calculate_volatility(self) -> float:
        """Calculate portfolio volatility"""
        positions = self.get_positions()
        
        if positions.empty:
            return 0
        
        # Weighted average volatility (simplified)
        weights = positions['weight'].values
        volatilities = np.abs(positions['return_pct'].values) * np.sqrt(252)
        
        return np.average(volatilities, weights=weights)
    
    def _calculate_max_drawdown(self) -> float:
        """Calculate maximum drawdown"""
        if not self.pnl_history:
            return 0
        
        values = [self.initial_capital] + [h['value'] for h in self.pnl_history]
        
        cummax = np.maximum.accumulate(values)
        drawdown = (np.array(values) - cummax) / cummax
        
        return float(drawdown.min())
    
    def _calculate_sharpe(self) -> float:
        """Calculate Sharpe ratio"""
        if not self.pnl_history:
            return 0
        
        returns = [h.get('return', 0) for h in self.pnl_history]
        
        if not returns or np.std(returns) == 0:
            return 0
        
        return np.mean(returns) / np.std(returns) * np.sqrt(252)
    
    def _calculate_sortino(self) -> float:
        """Calculate Sortino ratio (downside risk only)"""
        if not self.pnl_history:
            return 0
        
        returns = [h.get('return', 0) for h in self.pnl_history]
        returns = np.array(returns)
        
        downside = returns[returns < 0]
        
        if len(downside) == 0 or np.std(downside) == 0:
            return 0
        
        return np.mean(returns) / np.std(downside) * np.sqrt(252)
    
    def _calculate_alpha(self) -> float:
        """Calculate alpha (excess return over benchmark)"""
        # Simplified - would use real market data
        positions = self.get_positions()
        
        if positions.empty:
            return 0
        
        portfolio_return = self._total_unrealized_pnl() / self.initial_capital
        benchmark_return = 0.08  # Assume 8% annual
        
        return portfolio_return - benchmark_return
    
    def _total_unrealized_pnl(self) -> float:
        """Calculate total unrealized P&L"""
        return sum(pos['unrealized_pnl'] for pos in self.positions.values())
    
    # ==================== Stress Testing ====================
    
    def stress_test(self, scenarios: Dict[str, float]) -> Dict:
        """Run stress tests"""
        positions = self.get_positions()
        
        if positions.empty:
            return {}
        
        results = {}
        
        for name, shock_pct in scenarios.items():
            # Apply shock to each position
            shocked_pnl = 0
            
            for _, pos in positions.iterrows():
                position_shock = pos['market_value'] * shock_pct
                shocked_pnl += position_shock
            
            results[name] = {
                'pnl': shocked_pnl,
                'return_pct': shocked_pnl / self.initial_capital,
                'var_breach': abs(shocked_pnl) > self.calculate_var(0.95)
            }
        
        return results
    
    # ==================== Exposure Analysis ====================
    
    def sector_allocation(self) -> pd.DataFrame:
        """Get sector allocation"""
        positions = self.get_positions()
        
        if positions.empty:
            return pd.DataFrame()
        
        sector_mv = positions.groupby('sector')['market_value'].sum()
        total = sector_mv.sum()
        
        return pd.DataFrame({
            'sector': sector_mv.index,
            'market_value': sector_mv.values,
            'weight': sector_mv.values / total
        })
    
    def factor_exposure(self) -> Dict:
        """Calculate factor exposures (simplified)"""
        positions = self.get_positions()
        
        if positions.empty:
            return {}
        
        # Simplified factor exposures
        # Would use real factor models
        return {
            'momentum': np.random.uniform(-0.2, 0.2),
            'value': np.random.uniform(-0.3, 0.3),
            'size': np.random.uniform(-0.1, 0.1),
            'quality': np.random.uniform(0, 0.3),
            'volatility': np.random.uniform(-0.2, 0.2)
        }
    
    # ==================== Alerts ====================
    
    def _check_limits(self):
        """Check risk limits and trigger alerts"""
        metrics = self.get_risk_metrics()
        
        # Check drawdown
        if abs(metrics['max_drawdown']) > self.limits['max_drawdown']:
            self.add_alert(
                'critical',
                f"Max drawdown breach: {metrics['max_drawdown']:.1%}"
            )
        
        # Check VaR
        var_pct = metrics['var_95'] / metrics['portfolio_value']
        if var_pct > self.limits['max_var_pct']:
            self.add_alert(
                'warning',
                f"VaR limit breach: {var_pct:.1%}"
            )
        
        # Check position limits
        positions = self.get_positions()
        for symbol, pos in positions.iterrows():
            if pos['weight'] > self.limits['max_position_pct']:
                self.add_alert(
                    'warning',
                    f"Position limit breach: {symbol} {pos['weight']:.1%}"
                )
        
        # Check leverage
        if metrics['leverage'] > self.limits['max_leverage']:
            self.add_alert(
                'critical',
                f"Leverage limit breach: {metrics['leverage']:.2f}x"
            )
    
    def add_alert(self, level: str, message: str):
        """Add an alert"""
        alert = {
            'timestamp': datetime.now().isoformat(),
            'level': level,  # info, warning, critical
            'message': message
        }
        
        self.alerts.append(alert)
        
        # Trigger callbacks
        for callback in self.alert_callbacks:
            try:
                callback(alert)
            except:
                pass
    
    def get_alerts(self, level: str = None) -> List[Dict]:
        """Get alerts"""
        if level:
            return [a for a in self.alerts if a['level'] == level]
        return self.alerts
    
    def clear_alerts(self):
        """Clear all alerts"""
        self.alerts = []
    
    def set_alert_callback(self, callback):
        """Set alert callback function"""
        self.alert_callbacks.append(callback)
    
    # ==================== Reports ====================
    
    def generate_report(self, format: str = 'dict') -> Dict:
        """Generate risk report"""
        metrics = self.get_risk_metrics()
        positions = self.get_positions()
        sectors = self.sector_allocation()
        factors = self.factor_exposure()
        
        report = {
            'generated_at': datetime.now().isoformat(),
            'summary': metrics,
            'positions': positions.to_dict() if not positions.empty else {},
            'sectors': sectors.to_dict() if not sectors.empty else {},
            'factors': factors,
            'alerts': self.alerts[-10:]  # Last 10 alerts
        }
        
        if format == 'json':
            return json.dumps(report, indent=2, default=str)
        
        return report
    
    def get_daily_summary(self) -> str:
        """Get daily summary as text"""
        metrics = self.get_risk_metrics()
        
        summary = f"""
Risk Daily Summary
==================
Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}

Portfolio Value: ¥{metrics['portfolio_value']:,.0f}
Total P&L: ¥{metrics['total_pnl']:,.0f} ({metrics['return_pct']:.2%})
Positions: {metrics['position_count']}

Risk Metrics
-----------
VaR (95%): ¥{metrics['var_95']:,.0f}
CVaR (95%): ¥{metrics['cvar_95']:,.0f}
Volatility: {metrics['volatility']:.2%}
Max Drawdown: {metrics['max_drawdown']:.2%}
Sharpe Ratio: {metrics['sharpe_ratio']:.2f}
Beta: {metrics['beta']:.2f}

Alerts: {len(self.alerts)}
"""
        
        return summary
    
    # ==================== Visualization ====================
    
    def start_dashboard(self, port: int = 8050):
        """Start web dashboard (simplified - would use Dash/Streamlit)"""
        print(f"Starting risk dashboard on port {port}...")
        print("In production, would use Dash or Streamlit for visualization")
        
        # Would implement:
        # import dash
        # app = dash.Dash(__name__)
        # ...
        # app.run_server(port=port)
    
    def plot_pnl_history(self):
        """Plot P&L history"""
        # Would use plotly/matplotlib
        pass
    
    def plot_scenarios(self):
        """Plot stress test scenarios"""
        pass


def main():
    """Demo"""
    print("Quant Risk Dashboard")
    print("=" * 50)
    
    # Initialize
    dashboard = RiskDashboard(initial_capital=1000000)
    
    # Add positions
    dashboard.add_position('600519', 1000, 1800.0, 1850.0, 'Consumer')
    dashboard.add_position('000858', 5000, 45.0, 48.0, 'Consumer')
    dashboard.add_position('600036', 10000, 35.0, 34.0, 'Finance')
    
    # Get metrics
    metrics = dashboard.get_risk_metrics()
    
    print(f"Portfolio Value: ¥{metrics['portfolio_value']:,.0f}")
    print(f"VaR (95%): ¥{metrics['var_95']:,.0f}")
    print(f"Sharpe: {metrics['sharpe_ratio']:.2f}")
    print(f"Max Drawdown: {metrics['max_drawdown']:.2%}")
    
    # Stress test
    scenarios = {
        'Market Crash -20%': -0.20,
        'Covid -30%': -0.30,
        'Rate Hike -10%': -0.10
    }
    
    results = dashboard.stress_test(scenarios)
    print("\nStress Test:")
    for name, result in results.items():
        print(f"  {name}: ¥{result['pnl']:,.0f}")


if __name__ == "__main__":
    main()
