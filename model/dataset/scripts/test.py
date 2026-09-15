from pathlib import Path

print(Path.cwd())
print(list(Path("../data").glob("ext-*.csv")))