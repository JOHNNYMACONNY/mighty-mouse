from pipeline import DataPipeline


def test_pipeline_success():
    data = [
        {
            "Name": "Item A",
            "Price": "10.5",
            "Quantity": "2",
            "Status": "active",
        },
        {
            "Name": "Item B",
            "Price": "5.0",
            "Quantity": "10",
            "Status": "inactive",
        },
        {
            "Name": "Item C",
            "Price": "20.0",
            "Quantity": "1",
            "Status": "active",
        },
    ]
    pipeline = DataPipeline(data)
    result = pipeline.run()

    # Only active items (A and C) should be returned
    assert len(result) == 2

    # Check lowercased keys
    assert "total" in result[0]
    assert result[0]["total"] == 21.0
    assert result[0]["name"] == "Item A"

    assert "total" in result[1]
    assert result[1]["total"] == 20.0
    assert result[1]["name"] == "Item C"


def test_pipeline_missing_keys():
    # If price or quantity is missing, default total to 0.0
    data = [
        {"Price": "10.0", "Status": "active"},  # missing quantity
        {"Quantity": "5", "Status": "active"},  # missing price
    ]
    pipeline = DataPipeline(data)
    result = pipeline.run()
    assert len(result) == 2
    assert result[0]["total"] == 0.0
    assert result[1]["total"] == 0.0
