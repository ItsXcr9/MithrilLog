"""
MithrilLog Advanced Predictor

Production-ready forecasting and predictive analytics:
- Multi-horizon time-series forecasting
- Capacity planning predictions
- Seasonal decomposition
- Confidence intervals with uncertainty quantification
"""

from __future__ import annotations

import logging
import math
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple
from collections import deque

logger = logging.getLogger("mithrillog.analytics.predictor")


@dataclass
class ForecastPoint:
    """A single forecasted data point."""
    timestamp: datetime
    value: float
    lower_bound: float
    upper_bound: float
    confidence: float
    horizon_hours: int


@dataclass
class CapacityAlert:
    """Capacity planning alert."""
    metric_name: str
    current_value: float
    predicted_value: float
    threshold: float
    predicted_breach_time: Optional[datetime]
    severity: str  # warning, critical
    recommendation: str


class AdvancedPredictor:
    """
    Advanced prediction engine with multiple forecasting methods.
    
    Features:
    - Exponential smoothing (Holt-Winters)
    - Moving average with seasonal adjustment
    - Trend extrapolation
    - Multi-horizon forecasting
    - Capacity breach prediction
    """
    
    def __init__(self, history_size: int = 168):  # 1 week of hourly data
        self.history_size = history_size
        self._metric_history: Dict[str, deque] = {}
    
    def add_observation(self, metric_name: str, timestamp: datetime, value: float):
        """Add a new observation to metric history."""
        if metric_name not in self._metric_history:
            self._metric_history[metric_name] = deque(maxlen=self.history_size)
        
        self._metric_history[metric_name].append((timestamp, value))
    
    def get_history(self, metric_name: str) -> List[Tuple[datetime, float]]:
        """Get historical observations for a metric."""
        return list(self._metric_history.get(metric_name, []))
    
    def forecast_exponential_smoothing(
        self,
        metric_name: str,
        horizons: List[int] = [1, 6, 24, 72],
        alpha: float = 0.3,  # Level smoothing
        beta: float = 0.1,   # Trend smoothing
        gamma: float = 0.2,  # Seasonal smoothing
        seasonal_period: int = 24,  # Hourly seasonality
    ) -> List[ForecastPoint]:
        """
        Holt-Winters exponential smoothing with trend and seasonality.
        
        Args:
            metric_name: Metric to forecast
            horizons: List of hours ahead to predict
            alpha: Level smoothing parameter (0-1)
            beta: Trend smoothing parameter (0-1)
            gamma: Seasonal smoothing parameter (0-1)
            seasonal_period: Length of seasonal cycle (hours)
        """
        history = self.get_history(metric_name)
        
        if len(history) < seasonal_period * 2:
            # Not enough data, fall back to simple moving average
            return self._simple_forecast(metric_name, horizons)
        
        values = [v for _, v in history]
        n = len(values)
        
        # Initialize level, trend, and seasonal components
        level = sum(values[:seasonal_period]) / seasonal_period
        trend = (sum(values[seasonal_period:2*seasonal_period]) - sum(values[:seasonal_period])) / (seasonal_period ** 2)
        
        seasonal = [0.0] * seasonal_period
        for i in range(seasonal_period):
            season_values = [values[j] for j in range(i, min(n, seasonal_period * 2), seasonal_period)]
            if season_values:
                seasonal[i] = sum(season_values) / len(season_values) - level
        
        # Apply exponential smoothing
        for i in range(seasonal_period, n):
            season_idx = i % seasonal_period
            prev_level = level
            
            # Update level
            level = alpha * (values[i] - seasonal[season_idx]) + (1 - alpha) * (level + trend)
            
            # Update trend
            trend = beta * (level - prev_level) + (1 - beta) * trend
            
            # Update seasonal
            seasonal[season_idx] = gamma * (values[i] - level) + (1 - gamma) * seasonal[season_idx]
        
        # Calculate residual standard deviation for confidence intervals
        residuals = []
        l, t = level, trend
        for i in range(min(seasonal_period, n)):
            predicted = l + seasonal[i % seasonal_period]
            residuals.append(values[-(i+1)] - predicted)
        
        residual_std = math.sqrt(sum(r ** 2 for r in residuals) / len(residuals)) if residuals else 1.0
        
        # Generate forecasts
        last_time = history[-1][0]
        forecasts = []
        
        for h in horizons:
            future_time = last_time + timedelta(hours=h)
            season_idx = (n + h) % seasonal_period
            
            # Point forecast
            predicted = level + h * trend + seasonal[season_idx]
            
            # Prediction interval widens with horizon
            error_factor = 1 + 0.1 * math.sqrt(h)
            margin = 1.96 * residual_std * error_factor
            
            # Confidence decreases with horizon
            confidence = max(0.5, 1.0 - 0.01 * h)
            
            forecasts.append(ForecastPoint(
                timestamp=future_time,
                value=max(0, predicted),  # Values can't be negative
                lower_bound=max(0, predicted - margin),
                upper_bound=predicted + margin,
                confidence=confidence,
                horizon_hours=h,
            ))
        
        return forecasts
    
    def _simple_forecast(
        self,
        metric_name: str,
        horizons: List[int],
    ) -> List[ForecastPoint]:
        """Simple moving average forecast when insufficient data."""
        history = self.get_history(metric_name)
        
        if not history:
            return []
        
        values = [v for _, v in history]
        avg = sum(values) / len(values)
        std = math.sqrt(sum((v - avg) ** 2 for v in values) / len(values)) if len(values) > 1 else avg * 0.1
        
        last_time = history[-1][0]
        forecasts = []
        
        for h in horizons:
            margin = 1.96 * std * (1 + 0.1 * math.sqrt(h))
            
            forecasts.append(ForecastPoint(
                timestamp=last_time + timedelta(hours=h),
                value=avg,
                lower_bound=max(0, avg - margin),
                upper_bound=avg + margin,
                confidence=max(0.4, 0.8 - 0.02 * h),
                horizon_hours=h,
            ))
        
        return forecasts
    
    def predict_capacity_breach(
        self,
        metric_name: str,
        threshold: float,
        max_horizon_hours: int = 72,
    ) -> Optional[CapacityAlert]:
        """
        Predict when a metric will breach a threshold.
        
        Uses trend extrapolation to estimate breach time.
        """
        history = self.get_history(metric_name)
        
        if len(history) < 12:  # Need at least 12 observations
            return None
        
        values = [v for _, v in history]
        current_value = values[-1]
        
        # Already breached?
        if current_value >= threshold:
            return CapacityAlert(
                metric_name=metric_name,
                current_value=current_value,
                predicted_value=current_value,
                threshold=threshold,
                predicted_breach_time=history[-1][0],
                severity="critical",
                recommendation=f"{metric_name} has already exceeded threshold ({current_value:.1f} >= {threshold:.1f}). Immediate action required.",
            )
        
        # Calculate trend (using last 24 data points or all if fewer)
        recent = values[-min(24, len(values)):]
        if len(recent) < 2:
            return None
        
        # Linear regression for trend
        n = len(recent)
        x_mean = (n - 1) / 2
        y_mean = sum(recent) / n
        
        numerator = sum((i - x_mean) * (recent[i] - y_mean) for i in range(n))
        denominator = sum((i - x_mean) ** 2 for i in range(n))
        
        if denominator == 0:
            return None
        
        slope = numerator / denominator  # Change per observation
        
        # If trend is flat or downward, no breach predicted
        if slope <= 0:
            return None
        
        # How many steps until breach?
        steps_to_breach = (threshold - current_value) / slope
        hours_to_breach = steps_to_breach
        
        if hours_to_breach > max_horizon_hours:
            return None  # Too far in future
        
        breach_time = history[-1][0] + timedelta(hours=hours_to_breach)
        predicted_value = current_value + slope * max_horizon_hours
        
        severity = "critical" if hours_to_breach < 12 else "warning"
        
        return CapacityAlert(
            metric_name=metric_name,
            current_value=current_value,
            predicted_value=predicted_value,
            threshold=threshold,
            predicted_breach_time=breach_time,
            severity=severity,
            recommendation=f"At current rate, {metric_name} will exceed {threshold:.0f} in approximately {hours_to_breach:.0f} hours. Consider scaling or optimization.",
        )
    
    def detect_trend(
        self,
        metric_name: str,
        window_hours: int = 24,
    ) -> Dict[str, Any]:
        """
        Detect and classify the trend in a metric.
        
        Returns trend direction, magnitude, and significance.
        """
        history = self.get_history(metric_name)
        
        if len(history) < window_hours:
            return {
                "metric": metric_name,
                "trend": "insufficient_data",
                "slope": 0,
                "direction": None,
                "magnitude": None,
                "r_squared": 0,
            }
        
        values = [v for _, v in history[-window_hours:]]
        n = len(values)
        
        if n < 2:
            return {"metric": metric_name, "trend": "insufficient_data"}
        
        # Linear regression
        x_mean = (n - 1) / 2
        y_mean = sum(values) / n
        
        numerator = sum((i - x_mean) * (values[i] - y_mean) for i in range(n))
        denominator = sum((i - x_mean) ** 2 for i in range(n))
        
        slope = numerator / denominator if denominator != 0 else 0
        intercept = y_mean - slope * x_mean
        
        # R-squared for trend significance
        ss_res = sum((values[i] - (intercept + slope * i)) ** 2 for i in range(n))
        ss_tot = sum((values[i] - y_mean) ** 2 for i in range(n))
        r_squared = 1 - (ss_res / ss_tot) if ss_tot > 0 else 0
        
        # Classify trend
        if abs(slope) < y_mean * 0.01:  # Less than 1% change per hour
            direction = "stable"
            magnitude = "low"
        elif slope > 0:
            direction = "increasing"
            magnitude = "high" if slope > y_mean * 0.05 else "moderate"
        else:
            direction = "decreasing"
            magnitude = "high" if abs(slope) > y_mean * 0.05 else "moderate"
        
        # Trend significance
        significant = r_squared > 0.5
        
        return {
            "metric": metric_name,
            "trend": direction if significant else "noisy",
            "slope": slope,
            "slope_per_hour": slope,
            "direction": direction,
            "magnitude": magnitude,
            "r_squared": r_squared,
            "significant": significant,
            "window_hours": window_hours,
            "current_value": values[-1],
            "predicted_24h": values[-1] + slope * 24 if significant else None,
        }
    
    def seasonal_decomposition(
        self,
        metric_name: str,
        period: int = 24,
    ) -> Dict[str, List[float]]:
        """
        Decompose time series into trend, seasonal, and residual components.
        
        Uses additive decomposition: Y = Trend + Seasonal + Residual
        """
        history = self.get_history(metric_name)
        
        if len(history) < period * 2:
            return {"error": "Insufficient data for seasonal decomposition"}
        
        values = [v for _, v in history]
        n = len(values)
        
        # Calculate trend using centered moving average
        trend = []
        half_period = period // 2
        
        for i in range(n):
            if i < half_period or i >= n - half_period:
                trend.append(None)
            else:
                window = values[i - half_period:i + half_period + 1]
                trend.append(sum(window) / len(window))
        
        # Calculate seasonal component
        detrended = []
        for i in range(n):
            if trend[i] is not None:
                detrended.append(values[i] - trend[i])
            else:
                detrended.append(None)
        
        seasonal = [0.0] * period
        for s in range(period):
            season_values = [detrended[i] for i in range(s, n, period) if detrended[i] is not None]
            if season_values:
                seasonal[s] = sum(season_values) / len(season_values)
        
        # Normalize seasonal (sum to zero)
        seasonal_mean = sum(seasonal) / period
        seasonal = [s - seasonal_mean for s in seasonal]
        
        # Calculate residual
        residual = []
        for i in range(n):
            if trend[i] is not None:
                residual.append(values[i] - trend[i] - seasonal[i % period])
            else:
                residual.append(None)
        
        return {
            "original": values,
            "trend": [t if t is not None else 0 for t in trend],
            "seasonal": [seasonal[i % period] for i in range(n)],
            "residual": [r if r is not None else 0 for r in residual],
            "period": period,
            "seasonal_pattern": seasonal,  # One full cycle
        }


# Singleton instance
_predictor: Optional[AdvancedPredictor] = None


def get_predictor() -> AdvancedPredictor:
    """Get or create the singleton predictor instance."""
    global _predictor
    if _predictor is None:
        _predictor = AdvancedPredictor()
    return _predictor
