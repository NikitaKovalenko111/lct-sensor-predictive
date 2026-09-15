from pathlib import Path
import csv
import sys

INPUT_DIR = Path("model/dataset/data")

OUTPUT_FILE = Path("model/dataset/data/events_all.csv")

FILES = [
    "ext-journal-2019.csv",
    "ext-journal-2020.csv",
    "ext-journal-2021.csv",
    "ext-journal-2022.csv",
    "ext-journal-2023.csv",
    "ext-journal-2024.csv",
    "ext-journal-2025.csv",
    "ext-journal-2026.csv",
]


def count_lines(path):
    """Быстро считает строки, не загружая файл в память."""
    with open(path, "rb") as f:
        return sum(1 for _ in f)


def main():
    output_exists = OUTPUT_FILE.exists()

    if output_exists:
        answer = input(
            f"{OUTPUT_FILE} уже существует. Перезаписать? [y/N]: "
        ).strip().lower()

        if answer != "y":
            print("Отменено.")
            sys.exit(0)

    total_rows = 0
    reference_header = None

    with open(
        OUTPUT_FILE,
        "w",
        encoding="utf-8-sig",
        newline="",
        buffering=1024 * 1024
    ) as outfile:

        writer = None

        for i, filename in enumerate(FILES, start=1):
            path = INPUT_DIR / filename

            if not path.exists():
                print(f"[ОШИБКА] Файл не найден: {path}")
                sys.exit(1)

            print(f"\n[{i}/{len(FILES)}] Обрабатываю {filename}...")

            with open(
                path,
                "r",
                encoding="utf-8-sig",
                newline="",
                buffering=1024 * 1024
            ) as infile:

                reader = csv.reader(infile)

                try:
                    header = next(reader)
                except StopIteration:
                    print("  Файл пустой — пропускаю.")
                    continue

                # Проверяем структуру
                if reference_header is None:
                    reference_header = header
                    writer = csv.writer(outfile)
                    writer.writerow(header)
                elif header != reference_header:
                    print("\n[ОШИБКА] Заголовок отличается!")
                    print("Ожидалось:")
                    print(reference_header)
                    print("Получено:")
                    print(header)
                    sys.exit(1)

                rows = 0

                for row in reader:
                    writer.writerow(row)
                    rows += 1

                    # Периодический прогресс
                    if rows % 1_000_000 == 0:
                        print(f"  обработано: {rows:,} строк")

                total_rows += rows

                print(f"  готово: {rows:,} строк")

    print("\n" + "=" * 60)
    print("ОБЪЕДИНЕНИЕ ЗАВЕРШЕНО")
    print("=" * 60)
    print(f"Итоговый файл: {OUTPUT_FILE}")
    print(f"Всего строк:   {total_rows:,}")
    print(f"Размер файла:  {OUTPUT_FILE.stat().st_size / 1024**3:.2f} GB")


if __name__ == "__main__":
    main()