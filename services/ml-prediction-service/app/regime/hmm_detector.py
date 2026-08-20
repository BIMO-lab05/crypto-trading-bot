"""
Hidden Markov Model (HMM) Regime Detector
Advanced regime detection using probabilistic state transitions

Author: Phase 6.3 ML Team
Date: 2025-12-11
Version: 1.0.0

HMM Regime Detection:
    - Uses Gaussian HMM to model regime transitions
    - Trains on historical data (returns, volatility, volume)
    - Predicts regime probability distribution
    - Detects regime transitions before they're obvious

States:
    - State 0: Trending (low volatility, strong direction)
    - State 1: Ranging (low volatility, no direction)
    - State 2: Volatile (high volatility, any direction)
"""

import logging
import numpy as np
import pandas as pd
from datetime import datetime
from typing import Dict, List, Optional, Tuple, Any
from dataclasses import dataclass, field
from enum import Enum
from pydantic import BaseModel, Field
import pickle
import os

# Configure module logger
logger = logging.getLogger(__name__)

# Try to import hmmlearn (optional dependency)
try:
    from hmmlearn.hmm import GaussianHMM
    HMM_AVAILABLE = True
except ImportError:
    HMM_AVAILABLE = False
    logger.warning(
        "hmmlearn not installed. HMM regime detection unavailable. "
        "Install with: pip install hmmlearn"
    )


# =============================================================================
# Enums and Data Models
# =============================================================================

class HMMRegimeState(str, Enum):
    """
    HMM regime states (learned from data)

    Note: Actual meaning of states is learned from data
    These labels are assigned post-training based on state characteristics
    """
    TRENDING = "TRENDING"       # Low volatility, strong directional movement
    RANGING = "RANGING"         # Low volatility, no strong direction
    VOLATILE = "VOLATILE"       # High volatility, unpredictable moves


class HMMRegimePrediction(BaseModel):
    """HMM regime prediction result"""
    symbol: str = Field(..., description="Trading pair")
    timestamp: datetime = Field(default_factory=datetime.utcnow)

    # Most likely state
    predicted_state: HMMRegimeState = Field(..., description="Most probable regime state")
    state_probability: float = Field(..., ge=0.0, le=1.0, description="Probability of predicted state")

    # Full probability distribution
    state_probabilities: Dict[str, float] = Field(
        default_factory=dict,
        description="Probability distribution over all states"
    )

    # Transition info
    likely_next_state: Optional[HMMRegimeState] = Field(
        None,
        description="Most likely next regime state"
    )
    transition_probability: Optional[float] = Field(
        None,
        description="Probability of transitioning to next state"
    )

    # Model metadata
    model_trained: bool = Field(default=False, description="Whether model is trained")
    n_observations_used: int = Field(default=0, description="Observations used for prediction")


@dataclass
class HMMModelMetadata:
    """Metadata for trained HMM model"""
    symbol: str
    trained_at: datetime = field(default_factory=datetime.utcnow)
    n_states: int = 3
    n_training_samples: int = 0
    feature_names: List[str] = field(default_factory=list)
    state_labels: Dict[int, str] = field(default_factory=dict)
    convergence_score: float = 0.0
    log_likelihood: float = 0.0


# =============================================================================
# HMM Regime Detector
# =============================================================================

class HMMRegimeDetector:
    """
    Hidden Markov Model (HMM) based regime detector

    Uses Gaussian HMM to:
    - Model market regimes as hidden states
    - Learn regime transition probabilities
    - Predict current regime from observations
    - Forecast likely regime transitions

    Features used for HMM:
    - Returns (1h, 4h, 24h)
    - Volatility (rolling std)
    - Volume ratio (vs 20-period avg)
    - Momentum indicators

    Usage:
        detector = HMMRegimeDetector()

        # Train on historical data
        detector.train(prices_df, symbol="BTCUSDT")

        # Predict current regime
        prediction = detector.predict(recent_prices_df)

        # Get state probabilities
        probs = detector.get_state_probabilities(recent_prices_df)
    """

    # Default configuration
    DEFAULT_N_STATES: int = 3
    DEFAULT_N_ITER: int = 100
    DEFAULT_COVARIANCE_TYPE: str = "full"
    MIN_TRAINING_SAMPLES: int = 500

    def __init__(
        self,
        n_states: int = 3,
        n_iter: int = 100,
        covariance_type: str = "full",
        models_dir: str = "models/hmm",
        random_state: int = 42
    ):
        """
        Initialize HMM Regime Detector

        Args:
            n_states: Number of hidden states (default: 3)
            n_iter: Maximum iterations for EM algorithm (default: 100)
            covariance_type: Type of covariance matrix (default: "full")
            models_dir: Directory to save/load models
            random_state: Random seed for reproducibility
        """
        self.n_states = n_states
        self.n_iter = n_iter
        self.covariance_type = covariance_type
        self.models_dir = models_dir
        self.random_state = random_state

        # Model storage (per symbol)
        self._models: Dict[str, Any] = {}
        self._metadata: Dict[str, HMMModelMetadata] = {}
        self._scalers: Dict[str, Any] = {}  # For feature normalization

        # Feature configuration
        self.feature_names = [
            "returns_1h",
            "returns_4h",
            "volatility_10",
            "volume_ratio",
            "momentum_5",
        ]

        # Create models directory if it doesn't exist
        if models_dir:
            os.makedirs(models_dir, exist_ok=True)

        logger.info(
            f"HMMRegimeDetector initialized: states={n_states}, "
            f"iter={n_iter}, cov_type={covariance_type}"
        )

        if not HMM_AVAILABLE:
            logger.warning("HMM functionality disabled - hmmlearn not installed")

    # =============================================================================
    # Training Methods
    # =============================================================================

    def train(
        self,
        prices: pd.DataFrame,
        symbol: str = "UNKNOWN"
    ) -> HMMModelMetadata:
        """
        Train HMM on historical price data

        Args:
            prices: DataFrame with OHLCV data (minimum 500 rows)
            symbol: Trading pair symbol

        Returns:
            HMMModelMetadata with training results

        Raises:
            RuntimeError: If hmmlearn not available
            ValueError: If insufficient training data
        """
        if not HMM_AVAILABLE:
            raise RuntimeError(
                "hmmlearn not installed. "
                "Install with: pip install hmmlearn"
            )

        logger.info(f"Training HMM for {symbol} with {len(prices)} samples")

        # Validate data
        if len(prices) < self.MIN_TRAINING_SAMPLES:
            raise ValueError(
                f"Insufficient training data: {len(prices)} samples "
                f"(minimum: {self.MIN_TRAINING_SAMPLES})"
            )

        # Prepare features
        features, scaler = self._prepare_features(prices, fit_scaler=True)

        if len(features) < self.MIN_TRAINING_SAMPLES:
            raise ValueError(
                f"Insufficient valid features after preparation: "
                f"{len(features)} (minimum: {self.MIN_TRAINING_SAMPLES})"
            )

        # Store scaler
        self._scalers[symbol] = scaler

        # Initialize and train HMM
        model = GaussianHMM(
            n_components=self.n_states,
            covariance_type=self.covariance_type,
            n_iter=self.n_iter,
            random_state=self.random_state,
            verbose=False
        )

        # Fit model
        try:
            model.fit(features)
            converged = model.monitor_.converged
            log_likelihood = model.score(features)
        except Exception as e:
            logger.error(f"HMM training failed: {e}")
            raise RuntimeError(f"HMM training failed: {e}")

        # Store model
        self._models[symbol] = model

        # Label states based on characteristics
        state_labels = self._label_states(model, features)

        # Create metadata
        metadata = HMMModelMetadata(
            symbol=symbol,
            trained_at=datetime.utcnow(),
            n_states=self.n_states,
            n_training_samples=len(features),
            feature_names=self.feature_names,
            state_labels=state_labels,
            convergence_score=1.0 if converged else 0.5,
            log_likelihood=log_likelihood
        )

        self._metadata[symbol] = metadata

        logger.info(
            f"HMM training complete for {symbol}: "
            f"converged={converged}, log_likelihood={log_likelihood:.2f}"
        )

        return metadata

    def _prepare_features(
        self,
        prices: pd.DataFrame,
        fit_scaler: bool = False
    ) -> Tuple[np.ndarray, Optional[Any]]:
        """
        Prepare features for HMM training/prediction

        Features:
        - returns_1h: 1-hour returns
        - returns_4h: 4-hour returns
        - volatility_10: 10-period rolling volatility
        - volume_ratio: Volume vs 20-period average
        - momentum_5: 5-period price momentum

        Args:
            prices: DataFrame with OHLCV data
            fit_scaler: Whether to fit new scaler (True for training)

        Returns:
            Tuple of (features array, scaler)
        """
        df = prices.copy()

        # Ensure numeric columns
        for col in ['close', 'volume']:
            df[col] = pd.to_numeric(df[col], errors='coerce')

        # Calculate features
        # Returns
        df['returns_1h'] = df['close'].pct_change()
        df['returns_4h'] = df['close'].pct_change(4)

        # Volatility (rolling std of returns)
        df['volatility_10'] = df['returns_1h'].rolling(10).std()

        # Volume ratio
        df['volume_ma_20'] = df['volume'].rolling(20).mean()
        df['volume_ratio'] = df['volume'] / (df['volume_ma_20'] + 1e-10)

        # Momentum
        df['momentum_5'] = (df['close'] - df['close'].shift(5)) / df['close'].shift(5)

        # Select features and drop NaN
        features_df = df[self.feature_names].dropna()

        # Convert to numpy
        features = features_df.values

        # Normalize features (important for HMM)
        scaler = None
        if fit_scaler:
            from sklearn.preprocessing import StandardScaler
            scaler = StandardScaler()
            features = scaler.fit_transform(features)
        elif hasattr(self, '_scalers') and len(self._scalers) > 0:
            # Use existing scaler (first available for now)
            # In practice, should use symbol-specific scaler
            pass

        return features, scaler

    def _label_states(
        self,
        model: Any,
        features: np.ndarray
    ) -> Dict[int, str]:
        """
        Label HMM states based on their characteristics

        Analyzes mean and variance of each state to assign labels:
        - High returns variance + high volatility = VOLATILE
        - Low volatility + directional mean = TRENDING
        - Low volatility + near-zero mean = RANGING

        Args:
            model: Trained GaussianHMM model
            features: Training features

        Returns:
            Dict mapping state index to label
        """
        labels = {}

        # Get state means
        state_means = model.means_  # Shape: (n_states, n_features)

        # Indices in feature vector
        volatility_idx = self.feature_names.index('volatility_10')
        returns_idx = self.feature_names.index('returns_1h')

        # Analyze each state
        for i in range(self.n_states):
            mean_returns = state_means[i][returns_idx]
            mean_volatility = state_means[i][volatility_idx]

            # High volatility = Volatile state
            if mean_volatility > 0.5:  # Normalized scale
                labels[i] = HMMRegimeState.VOLATILE.value
            # Strong directional returns = Trending
            elif abs(mean_returns) > 0.3:  # Normalized scale
                labels[i] = HMMRegimeState.TRENDING.value
            # Low volatility, no direction = Ranging
            else:
                labels[i] = HMMRegimeState.RANGING.value

        # Ensure all labels are unique (adjust if needed)
        used_labels = set()
        for i in range(self.n_states):
            if labels[i] in used_labels:
                # Assign based on remaining labels
                all_labels = [s.value for s in HMMRegimeState]
                for label in all_labels:
                    if label not in used_labels:
                        labels[i] = label
                        break
            used_labels.add(labels[i])

        logger.debug(f"State labels assigned: {labels}")
        return labels

    # =============================================================================
    # Prediction Methods
    # =============================================================================

    def predict(
        self,
        prices: pd.DataFrame,
        symbol: str = "UNKNOWN"
    ) -> HMMRegimePrediction:
        """
        Predict current regime using trained HMM

        Args:
            prices: Recent DataFrame with OHLCV data
            symbol: Trading pair symbol

        Returns:
            HMMRegimePrediction with state probabilities

        Raises:
            RuntimeError: If model not trained for symbol
        """
        if not HMM_AVAILABLE:
            return self._create_default_prediction(symbol)

        # Check if model exists
        if symbol not in self._models:
            logger.warning(f"No HMM model trained for {symbol}")
            return self._create_default_prediction(symbol)

        model = self._models[symbol]
        metadata = self._metadata.get(symbol)

        # Prepare features
        features, _ = self._prepare_features(prices, fit_scaler=False)

        if len(features) == 0:
            logger.warning(f"No valid features for {symbol}")
            return self._create_default_prediction(symbol)

        # Normalize with stored scaler
        if symbol in self._scalers:
            features = self._scalers[symbol].transform(features)

        # Get state probabilities for last observation
        try:
            state_probs = model.predict_proba(features)
            current_state_probs = state_probs[-1]  # Last observation

            # Get predicted sequence
            predicted_states = model.predict(features)
            current_state = predicted_states[-1]
        except Exception as e:
            logger.error(f"HMM prediction failed: {e}")
            return self._create_default_prediction(symbol)

        # Map to labeled states
        state_labels = metadata.state_labels if metadata else {}
        predicted_label = state_labels.get(current_state, HMMRegimeState.RANGING.value)

        # Build probability distribution
        prob_distribution = {}
        for i, prob in enumerate(current_state_probs):
            label = state_labels.get(i, f"STATE_{i}")
            prob_distribution[label] = round(prob, 4)

        # Get transition probabilities for next state
        transmat = model.transmat_
        next_state_probs = transmat[current_state]
        likely_next_idx = np.argmax(next_state_probs)
        likely_next_label = state_labels.get(likely_next_idx, HMMRegimeState.RANGING.value)

        return HMMRegimePrediction(
            symbol=symbol,
            timestamp=datetime.utcnow(),
            predicted_state=HMMRegimeState(predicted_label),
            state_probability=float(current_state_probs[current_state]),
            state_probabilities=prob_distribution,
            likely_next_state=HMMRegimeState(likely_next_label),
            transition_probability=float(next_state_probs[likely_next_idx]),
            model_trained=True,
            n_observations_used=len(features)
        )

    def get_state_probabilities(
        self,
        prices: pd.DataFrame,
        symbol: str = "UNKNOWN"
    ) -> Dict[str, float]:
        """
        Get probability distribution over regime states

        Args:
            prices: Recent DataFrame with OHLCV data
            symbol: Trading pair symbol

        Returns:
            Dict mapping state labels to probabilities
        """
        prediction = self.predict(prices, symbol)
        return prediction.state_probabilities

    def get_transition_matrix(
        self,
        symbol: str
    ) -> Optional[np.ndarray]:
        """
        Get regime transition probability matrix

        Args:
            symbol: Trading pair symbol

        Returns:
            Transition matrix or None if model not trained
        """
        if symbol not in self._models:
            return None

        return self._models[symbol].transmat_

    def _create_default_prediction(
        self,
        symbol: str
    ) -> HMMRegimePrediction:
        """
        Create default prediction when model unavailable

        Args:
            symbol: Trading pair symbol

        Returns:
            Default HMMRegimePrediction (uniform distribution)
        """
        return HMMRegimePrediction(
            symbol=symbol,
            timestamp=datetime.utcnow(),
            predicted_state=HMMRegimeState.RANGING,
            state_probability=0.33,
            state_probabilities={
                HMMRegimeState.TRENDING.value: 0.33,
                HMMRegimeState.RANGING.value: 0.34,
                HMMRegimeState.VOLATILE.value: 0.33
            },
            likely_next_state=HMMRegimeState.RANGING,
            transition_probability=0.5,
            model_trained=False,
            n_observations_used=0
        )

    # =============================================================================
    # Model Persistence
    # =============================================================================

    def save_model(self, symbol: str) -> str:
        """
        Save trained model to disk

        Args:
            symbol: Trading pair symbol

        Returns:
            Path to saved model file
        """
        if symbol not in self._models:
            raise ValueError(f"No model trained for {symbol}")

        # Create filename
        filename = f"hmm_{symbol.lower()}.pkl"
        filepath = os.path.join(self.models_dir, filename)

        # Save model, metadata, and scaler together
        save_data = {
            'model': self._models[symbol],
            'metadata': self._metadata.get(symbol),
            'scaler': self._scalers.get(symbol)
        }

        with open(filepath, 'wb') as f:
            pickle.dump(save_data, f)

        logger.info(f"HMM model saved to {filepath}")
        return filepath

    def load_model(self, symbol: str) -> bool:
        """
        Load trained model from disk

        Args:
            symbol: Trading pair symbol

        Returns:
            True if loaded successfully, False otherwise
        """
        filename = f"hmm_{symbol.lower()}.pkl"
        filepath = os.path.join(self.models_dir, filename)

        if not os.path.exists(filepath):
            logger.warning(f"Model file not found: {filepath}")
            return False

        try:
            with open(filepath, 'rb') as f:
                save_data = pickle.load(f)

            self._models[symbol] = save_data['model']
            self._metadata[symbol] = save_data['metadata']
            self._scalers[symbol] = save_data['scaler']

            logger.info(f"HMM model loaded from {filepath}")
            return True

        except Exception as e:
            logger.error(f"Failed to load model: {e}")
            return False

    def is_model_trained(self, symbol: str) -> bool:
        """
        Check if model is trained for a symbol

        Args:
            symbol: Trading pair symbol

        Returns:
            True if model exists, False otherwise
        """
        return symbol in self._models

    def get_model_info(self, symbol: str) -> Optional[Dict[str, Any]]:
        """
        Get information about trained model

        Args:
            symbol: Trading pair symbol

        Returns:
            Dict with model info or None
        """
        if symbol not in self._models:
            return None

        metadata = self._metadata.get(symbol)
        model = self._models[symbol]

        return {
            'symbol': symbol,
            'n_states': self.n_states,
            'feature_names': self.feature_names,
            'trained_at': metadata.trained_at.isoformat() if metadata else None,
            'n_training_samples': metadata.n_training_samples if metadata else 0,
            'state_labels': metadata.state_labels if metadata else {},
            'log_likelihood': metadata.log_likelihood if metadata else 0.0,
            'transition_matrix': model.transmat_.tolist() if hasattr(model, 'transmat_') else None
        }


# =============================================================================
# Standalone Usage Example
# =============================================================================

if __name__ == "__main__":
    # Configure logging
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )

    print("=" * 80)
    print("HMM REGIME DETECTOR - DEMO")
    print("=" * 80)

    if not HMM_AVAILABLE:
        print("\n[WARNING] hmmlearn not installed. Install with: pip install hmmlearn")
        print("Demo will show default (untrained) behavior.\n")

    # Create sample data
    np.random.seed(42)
    n_candles = 1000

    # Generate synthetic data with regime changes
    close_prices = np.zeros(n_candles)
    volumes = np.zeros(n_candles)

    price = 50000
    for i in range(n_candles):
        # Simulate different regimes
        if i < 300:
            # Trending up
            price += np.random.normal(20, 50)
            volumes[i] = np.random.uniform(2000, 4000)
        elif i < 500:
            # Ranging
            price += np.random.normal(0, 30)
            volumes[i] = np.random.uniform(1000, 2000)
        elif i < 700:
            # Volatile
            price += np.random.normal(0, 200)
            volumes[i] = np.random.uniform(5000, 10000)
        else:
            # Trending down
            price += np.random.normal(-20, 50)
            volumes[i] = np.random.uniform(3000, 5000)

        close_prices[i] = max(price, 40000)

    # Create DataFrame
    dates = pd.date_range(start='2024-01-01', periods=n_candles, freq='1h')
    df = pd.DataFrame({
        'timestamp': dates,
        'open': close_prices - np.random.uniform(0, 100, n_candles),
        'high': close_prices + np.random.uniform(0, 200, n_candles),
        'low': close_prices - np.random.uniform(0, 200, n_candles),
        'close': close_prices,
        'volume': volumes
    })

    # Initialize detector
    detector = HMMRegimeDetector(models_dir="/tmp/hmm_models")

    if HMM_AVAILABLE:
        # Train model
        print("\nTraining HMM on historical data...")
        metadata = detector.train(df, symbol="BTCUSDT")
        print(f"  Training samples: {metadata.n_training_samples}")
        print(f"  Log-likelihood: {metadata.log_likelihood:.2f}")
        print(f"  State labels: {metadata.state_labels}")

        # Predict current regime
        print("\nPredicting current regime...")
        prediction = detector.predict(df.tail(100), symbol="BTCUSDT")
        print(f"  Predicted state: {prediction.predicted_state}")
        print(f"  State probability: {prediction.state_probability:.2%}")
        print(f"  Likely next state: {prediction.likely_next_state}")
        print(f"  Transition probability: {prediction.transition_probability:.2%}")

        # Show state probabilities
        print("\nState probabilities:")
        for state, prob in prediction.state_probabilities.items():
            print(f"  {state}: {prob:.2%}")

        # Get transition matrix
        print("\nTransition matrix:")
        transmat = detector.get_transition_matrix("BTCUSDT")
        if transmat is not None:
            print(transmat.round(3))

        # Save model
        filepath = detector.save_model("BTCUSDT")
        print(f"\nModel saved to: {filepath}")
    else:
        # Show default behavior
        print("\nUsing default (untrained) prediction...")
        prediction = detector.predict(df.tail(100), symbol="BTCUSDT")
        print(f"  Predicted state: {prediction.predicted_state}")
        print(f"  Model trained: {prediction.model_trained}")

    print("\n" + "=" * 80)
