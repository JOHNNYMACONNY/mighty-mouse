from traffic_light import TrafficLight

def test_traffic_light_cycle():
    light = TrafficLight()
    
    assert light.get_state() == "red", f"Expected 'red', got '{light.get_state()}'"
    light.advance()
    assert light.get_state() == "green", f"Expected 'green', got '{light.get_state()}'"
    light.advance()
    assert light.get_state() == "yellow", f"Expected 'yellow', got '{light.get_state()}'"
    light.advance()
    assert light.get_state() == "red", f"Expected 'red' after wrap, got '{light.get_state()}'"
    
    print("PASS")

if __name__ == "__main__":
    test_traffic_light_cycle()
