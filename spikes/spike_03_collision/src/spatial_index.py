"""空间索引 — Stub"""


class SpatialIndex:
    size: int = 0

    def build(self, assets: list):
        raise NotImplementedError

    def query(self, asset: dict) -> list:
        raise NotImplementedError

    def update(self, asset: dict):
        raise NotImplementedError
