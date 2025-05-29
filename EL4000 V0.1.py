# -*- coding: utf-8 -*-
"""
Created on Wed May  7 00:03:01 2025

@author: leonh
"""

"""
el4000_ide.py – read every EL3500/4000 *.BIN in the current working directory
and write one consolidated CSV called `el4000_export.csv`.

Open this file in your IDE and press ‑‑► Run.  Tested on Python ≥3.9.
"""

import csv, logging, struct, sys
from datetime import datetime
from datetime import timedelta
from pathlib import Path
from typing import Iterator, Tuple
import matplotlib.pyplot as plt

# --- configuration ---------------------------------------------------------

LOG = logging.getLogger("el4000")
logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")

MAGIC = b"\xE0\xC5\xEA"                    # start of each record block :contentReference[oaicite:1]{index=1}
SAMPLE_LEN = 5
TIMESTAMP_LEN = 5
BLOCK_OVERHEAD = len(MAGIC) + TIMESTAMP_LEN

# helper to convert the 5‑byte logger timestamp into a datetime object
def _decode_timestamp(raw: bytes) -> datetime:
    month, day, year_offset, hour, minute = raw
    return datetime(year=2000 + year_offset, month=month, day=day,
                    hour=hour, minute=minute)

# helper to convert a 5‑byte sample into physical values
def _decode_sample(raw: bytes) -> Tuple[float, float, int, float, float]:
    voltage_tenth, current_mA, pf_percent = struct.unpack(">HHB", raw)  # big‑endian :contentReference[oaicite:2]{index=2}
    voltage = voltage_tenth / 10.0               # V
    current = current_mA / 1000.0                # A
    pf = pf_percent / 100.0                      # 0‑1
    watt = voltage * current * pf               # W
    va = voltage * current                      # VA
    return voltage, current, pf_percent, watt, va

def parse_data_file(path: Path) -> Iterator[Tuple[datetime, float, float, int, float, float]]:
    data = path.read_bytes()
    pos = 0
    while True:
        # search for next header
        idx = data.find(MAGIC, pos)
        if idx == -1:
            break
        pos = idx + len(MAGIC)
        # guard against truncated block
        if pos + TIMESTAMP_LEN > len(data):
            break
        # decode the block’s “base” timestamp
        ts_raw = data[pos:pos + TIMESTAMP_LEN]
        pos += TIMESTAMP_LEN
        base_ts = _decode_timestamp(ts_raw)
        sample_index = 0

        # iterate over samples until we meet FF‑padding or next header
        while pos + SAMPLE_LEN <= len(data):
            # stop on padding (FF FF FF FF..) or new header
            if data[pos] == 0xFF or data[pos:pos + len(MAGIC)] == MAGIC:
                break
            sample_raw = data[pos:pos + SAMPLE_LEN]
            pos += SAMPLE_LEN
            # advance by one minute per sample
            yield (base_ts + timedelta(minutes=sample_index),
                   *_decode_sample(sample_raw))
            sample_index += 1

        # continue scanning from current pos for next header

def export_all(bin_dir: Path | str = ".") -> Path:
    bin_dir = Path(bin_dir)
    output = bin_dir / "el4000_export.csv"
    # 1) Collect every row from every .bin
    all_rows: list[tuple[datetime, float, float, int, float, float]] = []

    for binfile in sorted(bin_dir.glob("*.bin")):
        if binfile.name.lower() == "setupel3.bin":
            LOG.debug("Skipping settings file %s", binfile.name)
            continue
        LOG.info("Reading %s", binfile.name)
        for row in parse_data_file(binfile):
            all_rows.append(row)

    # 2) Sort by the datetime field (at index 0)
    all_rows.sort(key=lambda rec: rec[0])

    # 3) Write them out in ascending order
    with output.open("w", newline="") as fh:
        writer = csv.writer(fh)
        writer.writerow(["datetime", "voltage_V", "current_A",
                         "power_factor_%", "watt_W", "va_VA"])
        for rec in all_rows:
            writer.writerow(rec)

    LOG.info("Wrote %d samples to %s", len(all_rows), output)
    return output



def plot_watt_over_time(csv_path: Path | str = "el4000_export.csv") -> None:
    """
    Reads the CSV produced by export_all() and plots watt_W over datetime.
    """
    csv_path = Path(csv_path)
    if not csv_path.exists():
        raise FileNotFoundError(f"{csv_path!r} not found. Run export_all() first.")
    
    times: list[datetime] = []
    watts: list[float] = []
    
    with csv_path.open(newline='') as fh:
        reader = csv.reader(fh)
        header = next(reader)
        # find the index of the watt_W column
        try:
            watt_idx = header.index("watt_W")
        except ValueError:
            raise ValueError(f"'watt_W' column not in {csv_path}")

        for row in reader:
            # assume ISO-format timestamp in col 0
            ts = datetime.fromisoformat(row[0])
            w  = float(row[watt_idx])
            times.append(ts)
            watts.append(w)

    # plot
    plt.figure()
    plt.plot(times, watts)
    plt.xlabel("Time")
    plt.ylabel("Power (W)")
    plt.title("EL4000: Wattage Over Time")
    plt.gcf().autofmt_xdate()  # rotate & format dates
    plt.tight_layout()
    plt.show()


# convenience entry‑point when running the module
if __name__ == "__main__":
    try:
        out = export_all(r"C:\Users\leonh\Desktop\Datenlogs\Stromlogger\2024")    # ← put your folder here
    except Exception as exc:        # noqa: broad‑except
        LOG.exception("Fatal error: %s", exc)
        sys.exit(1)
    plot_watt_over_time(out)
