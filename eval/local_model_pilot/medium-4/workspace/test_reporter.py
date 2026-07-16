import json
from reporter import ReportGenerator


def test_export_json():
    data = [{"name": "Alice", "age": 30}]
    gen = ReportGenerator(data)
    assert json.loads(gen.export_json()) == data


def test_export_csv_empty():
    gen = ReportGenerator([])
    assert gen.export_csv() == ""


def test_export_csv_simple():
    data = [{"name": "Alice", "age": 30}, {"name": "Bob", "age": 25}]
    gen = ReportGenerator(data)
    expected = "age,name\n30,Alice\n25,Bob\n"
    assert gen.export_csv().replace("\r\n", "\n") == expected


def test_export_csv_escaping():
    data = [
        {"name": 'Alice "CEO"', "notes": "has a comma, and a\nnewline"},
        {"name": "Bob", "notes": "normal"},
    ]
    gen = ReportGenerator(data)
    csv_str = gen.export_csv().replace("\r\n", "\n")
    assert "name,notes\n" in csv_str
    assert '"Alice ""CEO"""' in csv_str
    assert '"has a comma, and a\nnewline"' in csv_str
    assert "Bob,normal\n" in csv_str
