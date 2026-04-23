from processor import DataProcessor
import os

def test_refactor():
    processor = DataProcessor()
    
    assert processor.process("local") == "RAW_LOCAL_DATA_PROCESSED"
    assert processor.process("remote") == "RAW_REMOTE_DATA_PROCESSED"
    
    # Ensure the new files exist
    assert os.path.exists("loader.py"), "loader.py must exist"
    assert os.path.exists("parser.py"), "parser.py must exist"
    
    # Ensure they are actually imported and used
    with open("processor.py", "r") as f:
        content = f.read()
        assert "from loader import" in content or "import loader" in content
        assert "from parser import" in content or "import parser" in content

    print("PASS")

if __name__ == "__main__":
    test_refactor()
