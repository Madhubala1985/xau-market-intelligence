from pathlib import Path


def test_required_directories_exist():
    required_dirs = [
        "src/data",
        "src/broker",
        "src/execution",
        "src/risk",
        "src/structure",
        "src/regime",
        "src/liquidity",
        "src/orderflow",
        "src/strategy",
        "src/trade_management",
        "src/journal",
        "src/reflection",
        "src/backtest",
        "src/utils",
        "tests",
        "configs",
        "data/raw",
        "data/processed",
        "logs",
        "reports",
        "scripts",
    ]

    for directory in required_dirs:
        assert Path(directory).is_dir(), f"Missing directory: {directory}"
