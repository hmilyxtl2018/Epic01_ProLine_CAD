"""PINN 训练器 — Stub"""
from dataclasses import dataclass


@dataclass
class TrainHistory:
    initial_loss: float = float("inf")
    final_loss: float = float("inf")


class PINNTrainer:
    def __init__(self, model=None, learning_rate: float = 1e-3, epochs: int = 100):
        pass

    def train(self, dataset) -> TrainHistory:
        raise NotImplementedError
