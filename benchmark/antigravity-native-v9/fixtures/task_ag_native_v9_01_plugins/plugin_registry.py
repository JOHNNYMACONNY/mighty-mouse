class PluginRegistry:
    def __init__(self):
        self._plugins = {}

    def register(self, name, depends_on=None):
        self._plugins[name] = depends_on or []

    def load_all(self):
        visited = set()
        in_progress = set()
        order = []

        def visit(name):
            if name in in_progress:
                raise ValueError(f"Circular dependency: {name}")
            if name in visited:
                return
            in_progress.add(name)
            for dep in self._plugins.get(name, []):
                visit(dep)
            in_progress.remove(name)
            visited.add(name)
            order.append(name)

        for p in self._plugins:
            visit(p)
        return order
