class PluginRegistry:
    """
    Plugins can declare dependencies on other plugins.
    load_all() must load them in dependency order.
    Raises ValueError if a circular dependency is detected.
    """

    def __init__(self):
        self._plugins = {}   # name -> list of dependency names
        self._load_order = []

    def register(self, name, depends_on=None):
        self._plugins[name] = depends_on or []

    def load_all(self):
        """Topological sort. Raises ValueError on cycle."""
        visited = set()
        in_progress = set()
        self._load_order = []

        def visit(name):
            if name in in_progress:
                raise ValueError(f"Circular dependency detected at '{name}'")
            if name in visited:
                return
            in_progress.add(name)
            for dep in self._plugins.get(name, []):
                visit(dep)
            in_progress.remove(name)
            visited.add(name)
            self._load_order.append(name)

        for plugin in self._plugins:
            visit(plugin)

        return self._load_order
