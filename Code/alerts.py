class AlertEngine:
    def __init__(self, storage):
        self.storage = storage

    def check(self, metric, value, params):
        if metric == "zscore":
            th = params.get("threshold", 2.0)
            if abs(value) >= th:
                return True
        return False
