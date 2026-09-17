from pathlib import Path
import duckdb
import sys

SCRIPT_DIR = Path(__file__).resolve().parent
DATA_DIR = SCRIPT_DIR.parent / "data"
DB_FILE = SCRIPT_DIR / "mcollector.duckdb"
CHANNELS_FILE = DATA_DIR / "channels.csv"
OBJECTS_FILE = DATA_DIR / "objects.csv"
CSV_FILES = sorted(DATA_DIR.glob("ext-journal-*.csv"))

print("=" * 70)
print("ИНИЦИАЛИЗАЦИЯ MCollector DuckDB")
print("=" * 70)
print(f"DATA_DIR : {DATA_DIR}")
print(f"DATABASE : {DB_FILE}")
print(f"CHANNELS : {CHANNELS_FILE}")
print(f"Журналов : {len(CSV_FILES)}")

if not DATA_DIR.exists():
    raise FileNotFoundError(f"Не найдена папка: {DATA_DIR}")
if not CHANNELS_FILE.exists():
    raise FileNotFoundError(f"Не найден: {CHANNELS_FILE}")
if not CSV_FILES:
    raise FileNotFoundError(f"Не найдены ext-journal-*.csv в {DATA_DIR}")

for f in CSV_FILES:
    print(f"  - {f.name}")
print()

if DB_FILE.exists():
    answer = input(f"{DB_FILE.name} уже существует. Пересоздать? [y/N]: ").strip().lower()
    if answer != "y":
        print("Отменено.")
        sys.exit(0)
    DB_FILE.unlink()

con = duckdb.connect(str(DB_FILE))

try:
    # При необходимости уменьши число потоков, если машина сильно загружена.
    con.execute("PRAGMA threads=8")
    con.execute("PRAGMA preserve_insertion_order=false")

    print("=== 1. CHANNELS ===")
    con.execute(f"""
        CREATE TABLE channels AS
        SELECT *
        FROM read_csv_auto('{CHANNELS_FILE.as_posix()}', header=true, sample_size=-1)
    """)
    print("Каналов:", con.execute("SELECT COUNT(*) FROM channels").fetchone()[0])

    print("\n=== 2. OBJECTS ===")
    con.execute(f"""
        CREATE TABLE objects AS
        SELECT *
        FROM read_csv_auto('{OBJECTS_FILE.as_posix()}', header=true, sample_size=-1)
    """)

    print("Объектов:", con.execute("SELECT COUNT(*) FROM objects").fetchone()[0])

    print("\n=== 3. EVENTS ===")
    con.execute("""
        CREATE TABLE events (
            ид_события BIGINT,
            ид_канала_данных BIGINT,
            дата DATE,
            время TIME,
            тревожное BOOLEAN,
            значение_датчика VARCHAR
        )
    """)

    for i, csv_file in enumerate(CSV_FILES, 1):
        print(f"[{i}/{len(CSV_FILES)}] Загружаю {csv_file.name} ...", flush=True)
        con.execute(f"""
            INSERT INTO events
            SELECT
                CAST(ид_события AS BIGINT),
                CAST(ид_канала_данных AS BIGINT),
                CAST(дата AS DATE),
                CAST(время AS TIME),
                CAST(тревожное AS BOOLEAN),
                CAST(значение_датчика AS VARCHAR)
            FROM read_csv(
                '{csv_file.as_posix()}',
                header=true,
                columns={{
                    'ид_события': 'BIGINT',
                    'ид_канала_данных': 'BIGINT',
                    'дата': 'DATE',
                    'время': 'TIME',
                    'тревожное': 'BOOLEAN',
                    'значение_датчика': 'VARCHAR'
                }},
                ignore_errors=false
            )
        """)
        total = con.execute("SELECT COUNT(*) FROM events").fetchone()[0]
        print(f"    Загружено: {total:,}".replace(",", " "), flush=True)

    print("\n=== 3. CHECK ===")
    result = con.execute("""
        SELECT COUNT(*), MIN(дата), MAX(дата), COUNT(DISTINCT ид_канала_данных)
        FROM events
    """).fetchone()
    print(f"events   : {result[0]:,}".replace(",", " "))
    print(f"min_date : {result[1]}")
    print(f"max_date : {result[2]}")
    print(f"channels : {result[3]:,}".replace(",", " "))

    print("\n=== 4. YEARS ===")
    for year, count in con.execute("""
        SELECT YEAR(дата), COUNT(*)
        FROM events
        GROUP BY 1
        ORDER BY 1
    """).fetchall():
        print(f"{year}: {count:,}".replace(",", " "))

    print("\n=== 5. SAVE ===")
    con.execute("CHECKPOINT")
    print("CHECKPOINT выполнен.")

finally:
    con.close()

print("\n" + "=" * 70)
print("ГОТОВО")
print("=" * 70)
print(f"База: {DB_FILE}")
print("Можно подключать её к DBeaver.")
