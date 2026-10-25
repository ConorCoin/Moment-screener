# How to Run

Folder (this project lives here):
```
C:\Users\ccoyne\AppData\Roaming\Claude\scratch-workspaces\a127102f-8b59-46d9-a222-b1f3f281e3d9\833decd2-71c2-45c1-b820-d31dd876d600\scratch-2026-10-25-5ebf92\momentum_screener
```

## First-time setup

Open a terminal (PowerShell or Command Prompt) in that folder, then:

```bash
pip install -r requirements.txt
```

## Run the daily screen

```bash
python main.py
```

This refreshes the ticker universe, updates price data, runs the screen, and writes a new
report to `reports\YYYY-MM-DD.md` in this folder. Takes under a minute.

## Quick peek without writing a report

```bash
python screener.py
```

Prints the current long/short candidates and today's triggers straight to the console.

## Other individual pieces (for debugging)

```bash
python universe.py   # rebuild/print the ticker universe
python data.py        # just update price data
python sector.py      # just print sector rankings
```

See `README.md` in this same folder for how the screening logic actually works.

## Before acting on a trigger

This screener is pure price/volume — no fundamentals, no news. Before trading anything in
the "triggers" section of a report, hand that `reports/<date>.md` file to an LLM agent and
ask it to check current market conditions, news/catalysts, and basic fundamentals on each
triggered ticker. See the "Recommended: qualitative review" section in `README.md`.
