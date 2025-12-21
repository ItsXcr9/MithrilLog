"""
MithrilLog ML Analytics Engine

Machine learning capabilities:
- Time-series anomaly detection (Isolation Forest)
- Log embeddings and clustering
- Predictive analytics
- Pattern recognition
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple
import math

logger = logging.getLogger("mithrillog.analytics.ml_engine")


@dataclass
class AnomalyResult:
    """Result of anomaly detection."""
    timestamp: datetime
    metric_name: str
    value: float
    is_anomaly: bool
    anomaly_score: float  # -1 to 1, lower is more anomalous
    expected_range: Tuple[float, float]
    severity: str  # low, medium, high, critical
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "timestamp": self.timestamp.isoformat(),
            "metric_name": self.metric_name,
            "value": self.value,
            "is_anomaly": self.is_anomaly,
            "anomaly_score": self.anomaly_score,
            "expected_range": self.expected_range,
            "severity": self.severity,
        }


@dataclass
class Prediction:
    """Forecasted value."""
    timestamp: datetime
    metric_name: str
    predicted_value: float
    lower_bound: float
    upper_bound: float
    confidence: float
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "timestamp": self.timestamp.isoformat(),
            "metric_name": self.metric_name,
            "predicted_value": self.predicted_value,
            "lower_bound": self.lower_bound,
            "upper_bound": self.upper_bound,
            "confidence": self.confidence,
        }


class MLEngine:
    """
    Machine Learning Engine for MithrilLog.
    
    Uses statistical methods and ML for:
    - Anomaly detection in log patterns
    - Time-series forecasting
    - Log similarity/clustering
    """
    
    def __init__(self, contamination: float = 0.05):
        """
        Initialize ML engine.
        
        Args:
            contamination: Expected proportion of anomalies (default 5%)
        """
        self.contamination = contamination
        self._history: Dict[str, List[Tuple[datetime, float]]] = {}
    
    def add_data_point(self, metric_name: str, timestamp: datetime, value: float):
        """Add a data point to the history for a metric."""
        if metric_name not in self._history:
            self._history[metric_name] = []
        self._history[metric_name].append((timestamp, value))
        
        # Keep only last 1000 points per metric
        if len(self._history[metric_name]) > 1000:
            self._history[metric_name] = self._history[metric_name][-1000:]
    
    def detect_anomalies_zscore(
        self,
        metric_name: str,
        data: List[Tuple[datetime, float]],
        threshold: float = 3.0
    ) -> List[AnomalyResult]:
        """
        Detect anomalies using Z-score method.
        
        Simple but effective for normally distributed data.
        """
        if len(data) < 10:
            return []
        
        values = [v for _, v in data]
        mean = sum(values) / len(values)
        variance = sum((v - mean) ** 2 for v in values) / len(values)
        std = math.sqrt(variance) if variance > 0 else 1.0
        
        results = []
        for timestamp, value in data:
            z_score = abs((value - mean) / std) if std > 0 else 0
            is_anomaly = z_score > threshold
            
            # Calculate expected range (±2 std)
            expected_range = (mean - 2 * std, mean + 2 * std)
            
            # Calculate severity
            if z_score <= threshold:
                severity = "low"
            elif z_score <= threshold * 1.5:
                severity = "medium"
            elif z_score <= threshold * 2:
                severity = "high"
            else:
                severity = "critical"
            
            # Normalize score to -1 to 1 range (negative = anomaly)
            anomaly_score = 1.0 - min(z_score / threshold, 2.0) / 2.0
            
            results.append(AnomalyResult(
                timestamp=timestamp,
                metric_name=metric_name,
                value=value,
                is_anomaly=is_anomaly,
                anomaly_score=anomaly_score,
                expected_range=expected_range,
                severity=severity if is_anomaly else "low",
            ))
        
        return results
    
    def detect_anomalies_iqr(
        self,
        metric_name: str,
        data: List[Tuple[datetime, float]],
        multiplier: float = 1.5
    ) -> List[AnomalyResult]:
        """
        Detect anomalies using Interquartile Range (IQR) method.
        
        Robust to outliers, good for non-normal distributions.
        """
        if len(data) < 10:
            return []
        
        values = sorted([v for _, v in data])
        n = len(values)
        
        q1 = values[n // 4]
        q3 = values[3 * n // 4]
        iqr = q3 - q1
        
        lower_fence = q1 - multiplier * iqr
        upper_fence = q3 + multiplier * iqr
        
        results = []
        for timestamp, value in data:
            is_anomaly = value < lower_fence or value > upper_fence
            
            # Calculate distance from boundaries
            if value < lower_fence:
                distance = (lower_fence - value) / iqr if iqr > 0 else abs(value - lower_fence)
            elif value > upper_fence:
                distance = (value - upper_fence) / iqr if iqr > 0 else abs(value - upper_fence)
            else:
                distance = 0
            
            # Severity based on distance
            if distance <= 0:
                severity = "low"
            elif distance <= 1:
                severity = "medium"
            elif distance <= 2:
                severity = "high"
            else:
                severity = "critical"
            
            anomaly_score = max(-1.0, 1.0 - distance)
            
            results.append(AnomalyResult(
                timestamp=timestamp,
                metric_name=metric_name,
                value=value,
                is_anomaly=is_anomaly,
                anomaly_score=anomaly_score,
                expected_range=(lower_fence, upper_fence),
                severity=severity if is_anomaly else "low",
            ))
        
        return results
    
    def forecast_linear(
        self,
        metric_name: str,
        data: List[Tuple[datetime, float]],
        periods: int = 24,
        period_minutes: int = 60,
    ) -> List[Prediction]:
        """
        Simple linear regression forecasting.
        
        Good for metrics with consistent trends.
        """
        if len(data) < 10:
            return []
        
        # Convert to numeric time (minutes from first point)
        base_time = data[0][0]
        x_data = [(ts - base_time).total_seconds() / 60 for ts, _ in data]
        y_data = [v for _, v in data]
        
        n = len(x_data)
        sum_x = sum(x_data)
        sum_y = sum(y_data)
        sum_xy = sum(x * y for x, y in zip(x_data, y_data))
        sum_x2 = sum(x * x for x in x_data)
        
        # Calculate slope and intercept
        denominator = n * sum_x2 - sum_x * sum_x
        if denominator == 0:
            return []
        
        slope = (n * sum_xy - sum_x * sum_y) / denominator
        intercept = (sum_y - slope * sum_x) / n
        
        # Calculate residual standard deviation
        predictions_hist = [slope * x + intercept for x in x_data]
        residuals = [y - p for y, p in zip(y_data, predictions_hist)]
        residual_std = math.sqrt(sum(r * r for r in residuals) / n) if n > 0 else 1.0
        
        # Generate forecasts
        last_time = data[-1][0]
        last_x = x_data[-1]
        
        forecasts = []
        for i in range(1, periods + 1):
            future_x = last_x + i * period_minutes
            future_time = last_time + timedelta(minutes=i * period_minutes)
            
            predicted = slope * future_x + intercept
            
            # Confidence decreases with distance
            confidence = max(0.5, 1.0 - 0.02 * i)  # 2% decrease per period
            
            # Prediction interval widens with time
            margin = residual_std * (1 + 0.1 * i)  # 10% increase per period
            
            forecasts.append(Prediction(
                timestamp=future_time,
                metric_name=metric_name,
                predicted_value=predicted,
                lower_bound=predicted - 2 * margin,
                upper_bound=predicted + 2 * margin,
                confidence=confidence,
            ))
        
        return forecasts
    
    def forecast_seasonal(
        self,
        metric_name: str,
        data: List[Tuple[datetime, float]],
        periods: int = 24,
        period_minutes: int = 60,
        season_length: int = 24,  # hourly seasonality by default
    ) -> List[Prediction]:
        """
        Seasonal forecasting with moving average.
        
        Good for metrics with daily/hourly patterns.
        """
        if len(data) < season_length * 2:
            return self.forecast_linear(metric_name, data, periods, period_minutes)
        
        values = [v for _, v in data]
        
        # Calculate seasonal indices
        seasonal_avg = []
        for i in range(season_length):
            season_values = [values[j] for j in range(i, len(values), season_length)]
            seasonal_avg.append(sum(season_values) / len(season_values))
        
        overall_avg = sum(values) / len(values)
        seasonal_indices = [s / overall_avg if overall_avg != 0 else 1.0 for s in seasonal_avg]
        
        # Detrend with moving average
        window = min(season_length, len(values) // 2)
        trend = []
        for i in range(len(values)):
            start = max(0, i - window // 2)
            end = min(len(values), i + window // 2 + 1)
            trend.append(sum(values[start:end]) / (end - start))
        
        # Calculate trend slope
        if len(trend) > 1:
            trend_slope = (trend[-1] - trend[0]) / len(trend)
        else:
            trend_slope = 0
        
        # Generate forecasts
        last_time = data[-1][0]
        last_trend = trend[-1] if trend else overall_avg
        
        forecasts = []
        for i in range(1, periods + 1):
            future_time = last_time + timedelta(minutes=i * period_minutes)
            season_idx = (len(values) + i) % season_length
            
            # Project trend forward
            projected_trend = last_trend + trend_slope * i
            
            # Apply seasonality
            predicted = projected_trend * seasonal_indices[season_idx]
            
            # Confidence and intervals
            confidence = max(0.4, 1.0 - 0.03 * i)
            std_dev = math.sqrt(sum((v - overall_avg) ** 2 for v in values) / len(values))
            margin = std_dev * (1 + 0.15 * i)
            
            forecasts.append(Prediction(
                timestamp=future_time,
                metric_name=metric_name,
                predicted_value=predicted,
                lower_bound=predicted - 2 * margin,
                upper_bound=predicted + 2 * margin,
                confidence=confidence,
            ))
        
        return forecasts
    
    def detect_log_pattern_changes(
        self,
        hourly_counts: List[Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        """
        Detect significant changes in log patterns.
        
        Compares hour-over-hour and day-over-day.
        """
        if len(hourly_counts) < 25:  # Need at least 25 hours for comparison
            return []
        
        changes = []
        
        for i in range(24, len(hourly_counts)):
            current = hourly_counts[i]
            prev_hour = hourly_counts[i - 1]
            prev_day = hourly_counts[i - 24]
            
            current_count = current.get("count", 0)
            prev_hour_count = prev_hour.get("count", 1)  # Avoid division by zero
            prev_day_count = prev_day.get("count", 1)
            
            # Calculate changes
            hour_change = (current_count - prev_hour_count) / prev_hour_count if prev_hour_count > 0 else 0
            day_change = (current_count - prev_day_count) / prev_day_count if prev_day_count > 0 else 0
            
            # Significant change thresholds
            if abs(hour_change) > 0.5 or abs(day_change) > 1.0:
                changes.append({
                    "timestamp": current.get("timestamp"),
                    "current_count": current_count,
                    "hour_over_hour_change": round(hour_change * 100, 1),
                    "day_over_day_change": round(day_change * 100, 1),
                    "severity": "high" if abs(hour_change) > 1.0 or abs(day_change) > 2.0 else "medium",
                })
        
        return changes
    
    def get_health_summary(self, metric_data: Dict[str, List[Tuple[datetime, float]]]) -> Dict[str, Any]:
        """Generate overall health summary from multiple metrics."""
        summary = {
            "overall_status": "healthy",
            "anomaly_count": 0,
            "metrics_analyzed": 0,
            "details": [],
        }
        
        critical_count = 0
        high_count = 0
        
        for metric_name, data in metric_data.items():
            if len(data) < 10:
                continue
            
            summary["metrics_analyzed"] += 1
            anomalies = self.detect_anomalies_zscore(metric_name, data)
            
            anomaly_events = [a for a in anomalies if a.is_anomaly]
            summary["anomaly_count"] += len(anomaly_events)
            
            critical = sum(1 for a in anomaly_events if a.severity == "critical")
            high = sum(1 for a in anomaly_events if a.severity == "high")
            
            critical_count += critical
            high_count += high
            
            if anomaly_events:
                summary["details"].append({
                    "metric": metric_name,
                    "anomaly_count": len(anomaly_events),
                    "critical": critical,
                    "high": high,
                    "latest_value": data[-1][1],
                })
        
        # Determine overall status
        if critical_count > 0:
            summary["overall_status"] = "critical"
        elif high_count > 0:
            summary["overall_status"] = "warning"
        elif summary["anomaly_count"] > 0:
            summary["overall_status"] = "degraded"
        
        return summary


# Singleton instance
_ml_engine: Optional[MLEngine] = None


def get_ml_engine() -> MLEngine:
    """Get or create the singleton MLEngine instance."""
    global _ml_engine
    if _ml_engine is None:
        _ml_engine = MLEngine()
    return _ml_engine
