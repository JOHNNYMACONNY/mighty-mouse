from plugin_registry import PluginRegistry

def test_linear_dependency():
    reg = PluginRegistry()
    reg.register("core")
    reg.register("auth", depends_on=["core"])
    reg.register("api", depends_on=["auth"])
    order = reg.load_all()
    # core must come before auth; auth before api
    assert order.index("core") < order.index("auth")
    assert order.index("auth") < order.index("api")

def test_diamond_dependency():
    # A depends on B and C; B and C both depend on D
    reg = PluginRegistry()
    reg.register("D")
    reg.register("B", depends_on=["D"])
    reg.register("C", depends_on=["D"])
    reg.register("A", depends_on=["B", "C"])
    order = reg.load_all()
    assert order.index("D") < order.index("B")
    assert order.index("D") < order.index("C")
    assert order.index("B") < order.index("A")
    assert order.index("C") < order.index("A")

def test_circular_raises():
    reg = PluginRegistry()
    reg.register("X", depends_on=["Y"])
    reg.register("Y", depends_on=["X"])
    raised = False
    try:
        reg.load_all()
    except ValueError:
        raised = True
    assert raised, "Should have raised ValueError for circular dependency"

def test_no_deps():
    reg = PluginRegistry()
    reg.register("standalone")
    order = reg.load_all()
    assert order == ["standalone"]

if __name__ == "__main__":
    test_linear_dependency()
    test_diamond_dependency()
    test_circular_raises()
    test_no_deps()
    print("PASS")
