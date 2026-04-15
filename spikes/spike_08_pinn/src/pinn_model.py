"""PINN 代理模型 — Stub"""


class PINNSurrogateModel:
    def __init__(self, input_dim: int = 10, output_dim: int = 3):
        pass

    def predict(self, inputs):
        raise NotImplementedError

    def predict_batch(self, inputs):
        raise NotImplementedError
