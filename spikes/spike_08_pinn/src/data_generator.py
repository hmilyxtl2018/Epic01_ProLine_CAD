"""PINN 训练数据生成 — Stub"""
from dataclasses import dataclass


@dataclass
class SimDataset:
    input_dim: int = 0
    output_dim: int = 0
    inputs: object = None
    outputs: object = None

    def __len__(self):
        return 0

    def __getitem__(self, idx):
        raise NotImplementedError


class SimDataGenerator:
    def __init__(self, station_count: int = 5, cycle_time_range: tuple = (20, 40)):
        pass

    def generate(self, n_samples: int = 100, seed: int = 42) -> SimDataset:
        raise NotImplementedError
