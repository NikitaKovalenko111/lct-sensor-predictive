from pathlib import Path
import duckdb

SCRIPT_DIR = Path(__file__).resolve().parent
DATA_DIR = SCRIPT_DIR.parent / "data"

EVENTS_PATTERN = (DATA_DIR / "ext-journal-*.csv").as_posix()
CHANNELS_FILE = (DATA_DIR / "channels.csv").as_posix()

print("DATA_DIR:", DATA_DIR)
print("EVENTS:", EVENTS_PATTERN)
print("CHANNELS:", CHANNELS_FILE)

con = duckdb.connect("mcollector.duckdb")

print("\n=== ОБЪЁМ ДАННЫХ ===")
print(con.execute(f'''
    SELECT COUNT(*) AS events,
           MIN(дата) AS min_date,
           MAX(дата) AS max_date,
           COUNT(DISTINCT ид_канала_данных) AS channels
    FROM read_csv_auto('{EVENTS_PATTERN}')
''').fetchdf().to_string(index=False))

print("\n=== ПО ГОДАМ ===")
print(con.execute(f'''
    SELECT YEAR(дата) AS year, COUNT(*) AS events
    FROM read_csv_auto('{EVENTS_PATTERN}')
    GROUP BY year ORDER BY year
''').fetchdf().to_string(index=False))

print("\n=== ТРЕВОЖНЫЕ СОБЫТИЯ ===")
print(con.execute(f'''
    SELECT тревожное, COUNT(*) AS events
    FROM read_csv_auto('{EVENTS_PATTERN}')
    GROUP BY тревожное ORDER BY тревожное
''').fetchdf().to_string(index=False))

print("\n=== ТИПЫ ДАТЧИКОВ ===")
print(con.execute(f'''
    SELECT тип_датчика, COUNT(*) AS channels
    FROM read_csv_auto('{CHANNELS_FILE}')
    GROUP BY тип_датчика ORDER BY channels DESC
''').fetchdf().to_string(index=False))

print("\n=== ТЕМПЕРАТУРНЫЕ КАНАЛЫ ===")
print("Каналов:", con.execute(f'''
    SELECT COUNT(*) FROM read_csv_auto('{CHANNELS_FILE}')
    WHERE тип_датчика = 'Датчик температуры'
''').fetchone()[0])

print("\n=== СОБЫТИЯ ТЕМПЕРАТУРЫ ===")
print(con.execute(f'''
    SELECT COUNT(*) AS events,
           COUNT(TRY_CAST(e.значение_датчика AS DOUBLE)) AS numeric_events,
           COUNT(*) - COUNT(TRY_CAST(e.значение_датчика AS DOUBLE)) AS non_numeric_events
    FROM read_csv_auto('{EVENTS_PATTERN}') e
    JOIN read_csv_auto('{CHANNELS_FILE}') c
      ON e.ид_канала_данных = c.ид_канала_данных
    WHERE c.тип_датчика = 'Датчик температуры'
''').fetchdf().to_string(index=False))

print("\n=== СТАТИСТИКА ТЕМПЕРАТУРЫ ===")
print(con.execute(f'''
    SELECT MIN(TRY_CAST(e.значение_датчика AS DOUBLE)) AS min_value,
           MAX(TRY_CAST(e.значение_датчика AS DOUBLE)) AS max_value,
           AVG(TRY_CAST(e.значение_датчика AS DOUBLE)) AS mean_value,
           STDDEV(TRY_CAST(e.значение_датчика AS DOUBLE)) AS std_value,
           MEDIAN(TRY_CAST(e.значение_датчика AS DOUBLE)) AS median_value
    FROM read_csv_auto('{EVENTS_PATTERN}') e
    JOIN read_csv_auto('{CHANNELS_FILE}') c
      ON e.ид_канала_данных = c.ид_канала_данных
    WHERE c.тип_датчика = 'Датчик температуры'
      AND TRY_CAST(e.значение_датчика AS DOUBLE) IS NOT NULL
''').fetchdf().to_string(index=False))

print("\n=== ПОПУЛЯРНЫЕ ЗНАЧЕНИЯ ТЕМПЕРАТУРЫ ===")
print(con.execute(f'''
    SELECT e.значение_датчика, COUNT(*) AS events
    FROM read_csv_auto('{EVENTS_PATTERN}') e
    JOIN read_csv_auto('{CHANNELS_FILE}') c
      ON e.ид_канала_данных = c.ид_канала_данных
    WHERE c.тип_датчика = 'Датчик температуры'
    GROUP BY e.значение_датчика
    ORDER BY events DESC LIMIT 30
''').fetchdf().to_string(index=False))

print("\n=== СОСТОЯНИЯ ТЕМПЕРАТУРНЫХ ДАТЧИКОВ ===")
print(con.execute(f'''
    SELECT e.значение_датчика, COUNT(*) AS events
    FROM read_csv_auto('{EVENTS_PATTERN}') e
    JOIN read_csv_auto('{CHANNELS_FILE}') c
      ON e.ид_канала_данных = c.ид_канала_данных
    WHERE c.тип_датчика = 'Датчик температуры'
      AND TRY_CAST(e.значение_датчика AS DOUBLE) IS NULL
    GROUP BY e.значение_датчика ORDER BY events DESC
''').fetchdf().to_string(index=False))

print("\n=== СОБЫТИЯ НА ТЕМПЕРАТУРНЫЙ КАНАЛ ===")
print(con.execute(f'''
    SELECT e.ид_канала_данных, c.название_датчика,
           COUNT(*) AS events, MIN(e.дата) AS first_date, MAX(e.дата) AS last_date
    FROM read_csv_auto('{EVENTS_PATTERN}') e
    JOIN read_csv_auto('{CHANNELS_FILE}') c
      ON e.ид_канала_данных = c.ид_канала_данных
    WHERE c.тип_датчика = 'Датчик температуры'
    GROUP BY e.ид_канала_данных, c.название_датчика
    ORDER BY events DESC LIMIT 20
''').fetchdf().to_string(index=False))

con.close()
print("\nГотово.")
