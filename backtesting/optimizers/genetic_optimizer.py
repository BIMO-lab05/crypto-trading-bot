"""
Genetic Algorithm Parameter Optimizer
Created: 2025-12-06
Purpose: Evolutionary parameter optimization using genetic algorithms

Genetic Algorithm Process:
1. Initialize population: Random parameter sets
2. Evaluate fitness: Run backtest, calculate Sharpe/Profit/etc
3. Selection: Best performers survive
4. Crossover: Combine parameters from parents
5. Mutation: Random parameter changes
6. Repeat for N generations

Advantages:
- Efficient for large parameter spaces (avoids exhaustive search)
- Can escape local optima through mutation
- Mimics natural selection for parameter evolution
"""

import logging
from typing import Dict, List, Any, Callable, Optional, Tuple
from dataclasses import dataclass, field
import numpy as np
import random
from concurrent.futures import ProcessPoolExecutor, as_completed
import json
import copy

logger = logging.getLogger(__name__)


@dataclass
class GeneticConfig:
    """Configuration for genetic algorithm optimization"""

    # Population settings
    population_size: int = 50  # Number of individuals per generation
    max_generations: int = 30  # Number of evolution cycles

    # Genetic operators
    mutation_rate: float = 0.10  # Probability of parameter mutation (10%)
    crossover_rate: float = 0.70  # Probability of crossover (70%)
    elitism_count: int = 5  # Top N individuals that survive unchanged

    # Selection method
    tournament_size: int = 5  # Number of individuals competing for selection

    # Fitness metric
    fitness_metric: str = 'sharpe_ratio'  # Metric to optimize

    # Convergence criteria
    min_improvement_threshold: float = 0.001  # Stop if improvement < 0.1%
    convergence_generations: int = 5  # Stop if no improvement for N generations

    # Parallel processing
    max_workers: int = 4  # CPU cores for parallel evaluation


@dataclass
class Individual:
    """Represents a single parameter set (individual) in the population"""
    parameters: Dict[str, Any]
    fitness: float = 0.0
    generation: int = 0
    backtest_results: Dict[str, Any] = field(default_factory=dict)

    def mutate(self, parameter_ranges: Dict[str, Tuple], mutation_rate: float) -> 'Individual':
        """
        Mutate parameters with given probability

        Args:
            parameter_ranges: Dict of {param_name: (min, max, step/type)}
            mutation_rate: Probability of mutation per parameter

        Returns:
            New Individual with potentially mutated parameters
        """
        new_params = copy.deepcopy(self.parameters)

        for param_name, value in new_params.items():
            if random.random() < mutation_rate:
                # Get parameter range
                param_range = parameter_ranges[param_name]

                if isinstance(param_range, tuple) and len(param_range) >= 2:
                    min_val, max_val = param_range[0], param_range[1]

                    # Determine if integer or float
                    if isinstance(value, int):
                        new_params[param_name] = random.randint(min_val, max_val)
                    else:
                        new_params[param_name] = random.uniform(min_val, max_val)

                elif isinstance(param_range, list):
                    # Categorical parameter
                    new_params[param_name] = random.choice(param_range)

        return Individual(parameters=new_params, generation=self.generation + 1)

    @staticmethod
    def crossover(parent1: 'Individual', parent2: 'Individual') -> Tuple['Individual', 'Individual']:
        """
        Perform uniform crossover between two parents

        Args:
            parent1: First parent individual
            parent2: Second parent individual

        Returns:
            Two offspring individuals with mixed parameters
        """
        child1_params = {}
        child2_params = {}

        for param_name in parent1.parameters.keys():
            if random.random() < 0.5:
                # Swap parameters between children
                child1_params[param_name] = parent1.parameters[param_name]
                child2_params[param_name] = parent2.parameters[param_name]
            else:
                child1_params[param_name] = parent2.parameters[param_name]
                child2_params[param_name] = parent1.parameters[param_name]

        child1 = Individual(parameters=child1_params, generation=max(parent1.generation, parent2.generation) + 1)
        child2 = Individual(parameters=child2_params, generation=max(parent1.generation, parent2.generation) + 1)

        return child1, child2


@dataclass
class GeneticResults:
    """Results from genetic algorithm optimization"""
    config: GeneticConfig
    best_individual: Individual
    evolution_history: List[Dict[str, Any]]

    # Final statistics
    total_generations: int = 0
    total_evaluations: int = 0
    convergence_reason: str = ""

    def to_dict(self) -> Dict[str, Any]:
        """Convert results to dictionary"""
        return {
            'config': {
                'population_size': self.config.population_size,
                'max_generations': self.config.max_generations,
                'mutation_rate': self.config.mutation_rate,
                'crossover_rate': self.config.crossover_rate,
            },
            'best_solution': {
                'parameters': self.best_individual.parameters,
                'fitness': round(self.best_individual.fitness, 4),
                'generation_found': self.best_individual.generation,
            },
            'optimization_stats': {
                'total_generations': self.total_generations,
                'total_evaluations': self.total_evaluations,
                'convergence_reason': self.convergence_reason,
            },
            'evolution_history': self.evolution_history,
        }


class GeneticOptimizer:
    """
    Genetic Algorithm Parameter Optimizer

    Uses evolutionary computation to find optimal strategy parameters.
    More efficient than grid search for large parameter spaces.

    Usage:
        config = GeneticConfig(population_size=50, max_generations=30)
        optimizer = GeneticOptimizer(config)

        parameter_ranges = {
            'rsi_period': (6, 20, 1),  # min, max, step
            'macd_fast': (3, 12, 1),
            'stop_loss_atr': (1.5, 4.0, 0.1),
        }

        results = optimizer.optimize(
            data=historical_data,
            parameter_ranges=parameter_ranges,
            backtest_engine=engine
        )

        print(f"Best parameters: {results.best_individual.parameters}")
        print(f"Fitness: {results.best_individual.fitness:.4f}")
    """

    def __init__(self, config: Optional[GeneticConfig] = None):
        """Initialize genetic optimizer"""
        self.config = config or GeneticConfig()
        logger.info(f"Initialized GeneticOptimizer with population={self.config.population_size}")

    def initialize_population(
        self,
        parameter_ranges: Dict[str, Any]
    ) -> List[Individual]:
        """
        Create initial random population

        Args:
            parameter_ranges: Dict of {param_name: (min, max) or [choices]}

        Returns:
            List of randomly generated individuals
        """
        population = []

        for i in range(self.config.population_size):
            parameters = {}

            for param_name, param_range in parameter_ranges.items():
                if isinstance(param_range, tuple) and len(param_range) >= 2:
                    # Numeric parameter with range
                    min_val, max_val = param_range[0], param_range[1]

                    # Check if integer or float
                    if len(param_range) >= 3 and param_range[2] == 'int':
                        parameters[param_name] = random.randint(min_val, max_val)
                    else:
                        parameters[param_name] = random.uniform(min_val, max_val)

                elif isinstance(param_range, list):
                    # Categorical parameter
                    parameters[param_name] = random.choice(param_range)

            individual = Individual(parameters=parameters, generation=0)
            population.append(individual)

        logger.info(f"Initialized population with {len(population)} individuals")
        return population

    def evaluate_fitness(
        self,
        individual: Individual,
        backtest_engine: Any,
        data: Any
    ) -> Individual:
        """
        Evaluate fitness of an individual by running backtest

        Args:
            individual: Individual to evaluate
            backtest_engine: Backtesting engine
            data: Historical data

        Returns:
            Individual with updated fitness score
        """
        try:
            # Run backtest with individual's parameters
            results = backtest_engine.run(
                data=data,
                strategy_params=individual.parameters
            )

            # Extract fitness metric
            fitness = results.get(self.config.fitness_metric, 0)

            # Penalize if insufficient trades
            if results.get('total_trades', 0) < 10:
                fitness *= 0.5  # 50% penalty for low trade count

            # Update individual
            individual.fitness = fitness
            individual.backtest_results = results

        except Exception as e:
            logger.error(f"Error evaluating individual: {e}")
            individual.fitness = -999  # Assign very low fitness on error

        return individual

    def tournament_selection(
        self,
        population: List[Individual]
    ) -> Individual:
        """
        Select individual using tournament selection

        Args:
            population: Current population

        Returns:
            Selected individual
        """
        # Randomly select tournament contestants
        tournament = random.sample(population, self.config.tournament_size)

        # Return best individual from tournament
        winner = max(tournament, key=lambda ind: ind.fitness)
        return winner

    def evolve_generation(
        self,
        population: List[Individual],
        parameter_ranges: Dict[str, Any]
    ) -> List[Individual]:
        """
        Create next generation through selection, crossover, and mutation

        Args:
            population: Current population
            parameter_ranges: Parameter constraints

        Returns:
            New population for next generation
        """
        # Sort population by fitness
        population.sort(key=lambda ind: ind.fitness, reverse=True)

        new_population = []

        # Elitism: Keep top performers unchanged
        elite = population[:self.config.elitism_count]
        new_population.extend(copy.deepcopy(elite))

        # Generate offspring to fill remaining population
        while len(new_population) < self.config.population_size:
            # Selection
            parent1 = self.tournament_selection(population)
            parent2 = self.tournament_selection(population)

            # Crossover
            if random.random() < self.config.crossover_rate:
                child1, child2 = Individual.crossover(parent1, parent2)
            else:
                child1 = copy.deepcopy(parent1)
                child2 = copy.deepcopy(parent2)

            # Mutation
            child1 = child1.mutate(parameter_ranges, self.config.mutation_rate)
            child2 = child2.mutate(parameter_ranges, self.config.mutation_rate)

            new_population.append(child1)
            if len(new_population) < self.config.population_size:
                new_population.append(child2)

        return new_population

    def optimize(
        self,
        data: Any,
        parameter_ranges: Dict[str, Any],
        backtest_engine: Any
    ) -> GeneticResults:
        """
        Run complete genetic algorithm optimization

        Args:
            data: Historical data for backtesting
            parameter_ranges: Parameter constraints
            backtest_engine: Backtesting engine

        Returns:
            GeneticResults with best solution and evolution history
        """
        logger.info("="*60)
        logger.info("GENETIC ALGORITHM OPTIMIZATION STARTING")
        logger.info("="*60)

        # Initialize population
        population = self.initialize_population(parameter_ranges)

        # Track evolution
        evolution_history = []
        best_fitness_history = []
        total_evaluations = 0
        convergence_reason = "Completed all generations"

        # Evolution loop
        for generation in range(self.config.max_generations):
            logger.info(f"Generation {generation + 1}/{self.config.max_generations}")

            # Evaluate fitness for all individuals
            for individual in population:
                if individual.fitness == 0.0:  # Not yet evaluated
                    self.evaluate_fitness(individual, backtest_engine, data)
                    total_evaluations += 1

            # Find best individual
            population.sort(key=lambda ind: ind.fitness, reverse=True)
            best_individual = population[0]
            avg_fitness = np.mean([ind.fitness for ind in population])
            worst_fitness = population[-1].fitness

            # Log generation statistics
            logger.info(f"  Best Fitness: {best_individual.fitness:.4f}")
            logger.info(f"  Avg Fitness:  {avg_fitness:.4f}")
            logger.info(f"  Worst Fitness: {worst_fitness:.4f}")
            logger.info(f"  Best Params: {best_individual.parameters}")

            # Save history
            evolution_history.append({
                'generation': generation + 1,
                'best_fitness': round(best_individual.fitness, 4),
                'avg_fitness': round(avg_fitness, 4),
                'worst_fitness': round(worst_fitness, 4),
                'best_parameters': best_individual.parameters,
            })
            best_fitness_history.append(best_individual.fitness)

            # Check convergence
            if len(best_fitness_history) >= self.config.convergence_generations:
                recent_improvement = (
                    best_fitness_history[-1] - best_fitness_history[-self.config.convergence_generations]
                )
                if abs(recent_improvement) < self.config.min_improvement_threshold:
                    convergence_reason = f"Converged after {generation + 1} generations (no improvement)"
                    logger.info(f"  {convergence_reason}")
                    break

            # Evolve to next generation
            if generation < self.config.max_generations - 1:
                population = self.evolve_generation(population, parameter_ranges)

        # Final results
        population.sort(key=lambda ind: ind.fitness, reverse=True)
        best_individual = population[0]

        results = GeneticResults(
            config=self.config,
            best_individual=best_individual,
            evolution_history=evolution_history,
            total_generations=len(evolution_history),
            total_evaluations=total_evaluations,
            convergence_reason=convergence_reason
        )

        logger.info("="*60)
        logger.info("GENETIC ALGORITHM OPTIMIZATION COMPLETE")
        logger.info(f"Best Fitness: {best_individual.fitness:.4f}")
        logger.info(f"Best Parameters: {best_individual.parameters}")
        logger.info(f"Convergence: {convergence_reason}")
        logger.info("="*60)

        return results

    def save_results(self, results: GeneticResults, filepath: str):
        """Save genetic algorithm results to JSON"""
        with open(filepath, 'w') as f:
            json.dump(results.to_dict(), f, indent=2)
        logger.info(f"Saved genetic algorithm results to {filepath}")

    def load_results(self, filepath: str) -> Dict[str, Any]:
        """Load genetic algorithm results from JSON"""
        with open(filepath, 'r') as f:
            results_dict = json.load(f)
        logger.info(f"Loaded genetic algorithm results from {filepath}")
        return results_dict


# Example usage
if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)

    # Example configuration
    config = GeneticConfig(
        population_size=20,
        max_generations=10,
        mutation_rate=0.10,
        crossover_rate=0.70
    )

    optimizer = GeneticOptimizer(config)

    # Example parameter ranges
    parameter_ranges = {
        'rsi_period': (6, 20, 'int'),
        'rsi_oversold': (20, 35, 'int'),
        'rsi_overbought': (65, 80, 'int'),
        'macd_fast': (3, 12, 'int'),
        'macd_slow': (21, 35, 'int'),
        'stop_loss_pct': (0.01, 0.05),  # 1% to 5%
        'take_profit_pct': (0.03, 0.10),  # 3% to 10%
    }

    print(f"Genetic Optimizer initialized")
    print(f"Population: {config.population_size}")
    print(f"Generations: {config.max_generations}")
    print(f"Parameter space: {parameter_ranges}")
