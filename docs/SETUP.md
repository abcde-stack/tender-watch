# Tender Watch beginner setup (Windows and macOS)

This guide is written for people who can use a computer but have never written code.
If you are a journalist, lawyer, researcher, or curious citizen who just wants to get
Tender Watch running on your own laptop, follow the steps in order and you will get
there. Take your time. Nothing here can damage your computer.

The Linux instructions live in the main `README.md`. This file covers Windows and
macOS only.

---

## Before you start, please read this

Tender Watch has two separate jobs:

1. **Build the data.** This is a one time step that reads the raw government data and
   cleans it. It is heavy: it takes about **45 minutes** and uses about **16 GB of
   memory (RAM)** while it runs. You only ever do this once (or again when fresh data
   comes out).
2. **Run the dashboard.** This is the part you actually use. It is light and starts in
   a few seconds. You can open and close it as often as you like without rebuilding
   anything.

**Honest advice.** Building the data is genuinely a technical task. It needs a
reasonably powerful computer (16 GB of RAM is a practical minimum, and you need about
40 GB of free disk space), plus a large download of the source files. If that sounds
like a lot, the easier path is to use a hosted copy of Tender Watch if one is
available, so you never have to build anything. This guide is for the case where you
do want to build it yourself.

A quick word on what these tools are, in plain language:

- **Python** is the programming language the dashboard is written in. You install it
  once. You do not need to learn it.
- **DuckDB** is a small, fast data engine that does the heavy lifting of cleaning the
  data. It has no server and no setup beyond installing it.
- **Streamlit** is the thing that turns the data into the web page you click around in.
- **Terminal** (on macOS) or **PowerShell** (on Windows) is a window where you type
  commands instead of clicking. You will copy and paste the commands from this guide.

---

## Part 1: Windows

### Step 1. Open PowerShell

PowerShell is the command window you will type into.

1. Click the Start menu.
2. Type `PowerShell`.
3. Click **Windows PowerShell** in the results.

A dark window with a blinking cursor opens. This is where the commands below go. To
run a command, click in the window, paste the command, and press Enter.

### Step 2. Install Python

1. Go to https://www.python.org/downloads/ in your browser.
2. Click the big yellow **Download Python** button. It gives you the right version for
   Windows automatically.
3. Open the file you downloaded.
4. **Important:** on the first screen of the installer, tick the box at the bottom that
   says **Add python.exe to PATH**. This one checkbox saves a lot of trouble later.
5. Click **Install Now** and wait for it to finish, then click Close.

Now confirm it worked. In PowerShell, type this and press Enter:

```
python --version
```

You should see something like `Python 3.12.x`. If you instead see an error, close
PowerShell, open it again (so it picks up the new install), and try once more.

### Step 3. Install DuckDB

In the same PowerShell window, type:

```
winget install DuckDB.cli
```

Press Enter and let it finish. (`winget` is Windows' built in installer and is present
on Windows 10 and 11.)

If `winget` is not found on your machine, install DuckDB manually instead:

1. Go to https://duckdb.org/docs/installation/.
2. Choose Windows and the command line client, and download the zip.
3. Unzip it. Inside is a file called `duckdb.exe`.
4. Remember the folder you unzipped it into. You will need its full path later.

After installing, **close PowerShell and open it again**, then check:

```
duckdb --version
```

If you see a version number, you are set. If you installed manually and this does not
work, do not worry: you can still run everything by typing the full path to
`duckdb.exe` in place of the word `duckdb` in the commands later on.

### Step 4. Get the Tender Watch code

Open the project page at https://github.com/abcde-stack/tender-watch in your browser,
download it as a ZIP (look for the green **Code** button, then **Download ZIP**), and
unzip it. Or, if you know how to use Git:

```
git clone https://github.com/abcde-stack/tender-watch.git
```

Then move into the folder. In PowerShell, type `cd ` (the letters c and d followed by
a space), then drag the unzipped `tender-watch` folder from File Explorer onto the
PowerShell window. It pastes the path for you. Press Enter. Your prompt should now show
that you are inside the `tender-watch` folder.

### Step 5. Install the Python add ons

These are the extra Python pieces the dashboard needs. From inside the `tender-watch`
folder, type:

```
pip install -r requirements.txt
```

This downloads and installs DuckDB for Python, Streamlit, pandas, and rapidfuzz. Wait
for it to finish.

### Step 6. Put the source data in the project folder

Tender Watch does not include the raw government data, because it is several gigabytes.
Place these files directly inside the `tender-watch` folder (the same folder that holds
the `etl` and `app` folders):

1. `aoc_tenders.db` and `tenders_vps.db`, downloaded from the data source listed in the
   README (the public mirror).
2. Optionally, `registered_companies.csv` (the MCA company list). This is only needed
   for the company identity feature and can be skipped.

The scripts already look for these files by name in the project folder, so there is
nothing to edit. These files stay on your computer only; they are never uploaded or
committed.

The MCA list is the Ministry of Corporate Affairs company master data from data.gov.in.
A redacted 20 row sample showing the columns your file should have is included at
`docs\registered_companies.sample.csv`. After you download the data, make sure its
header row matches the sample, then save it as `registered_companies.csv` in the
project folder.

### Step 7. Build the data (the long step)

This is the 45 minute, 16 GB step. Close other heavy programs first to free up memory.
From inside the `tender-watch` folder, run the commands below one at a time, waiting
for each to finish before starting the next.

```
duckdb tender_watch.duckdb ".read etl/run.sql"
duckdb tender_watch.duckdb ".read etl/04_build_summary.sql"
duckdb tender_watch.duckdb ".read etl/06_dq_report.sql"
duckdb tender_watch.duckdb ".read etl/08_state_hierarchy.sql"
duckdb tender_watch.duckdb ".read etl/10_central_hierarchy.sql"
duckdb tender_watch.duckdb ".read etl/11_mca_crosswalk.sql"
```

The first command is the long one. It can look like nothing is happening for a long
time. That is normal. As long as the window has not returned you to a fresh prompt, it
is still working. The five commands after it are quick.

If you installed DuckDB manually and `duckdb` is not recognised, replace the word
`duckdb` at the start of each line with the full path to `duckdb.exe` in quotes, for
example `"C:/Users/you/Downloads/duckdb/duckdb.exe"`.

Skip the last command (`11_mca_crosswalk.sql`) if you do not have the company CSV. The
dashboard still works; it just will not show the company identity card.

### Step 8. Open the dashboard

```
streamlit run app/dashboard.py
```

Your web browser opens automatically at `http://localhost:8501`. That is Tender Watch.

To stop it, click back in the PowerShell window and press `Ctrl` and `C` together. To
start it again another day, open PowerShell, move into the `tender-watch` folder
(Step 4), and run the `streamlit run app/dashboard.py` command again. You do **not**
need to rebuild the data; that is already done.

---

## Part 2: macOS

### Step 1. Open Terminal

1. Press `Command` and the space bar together to open Spotlight search.
2. Type `Terminal`.
3. Press Enter.

A window with a text prompt opens. This is where you paste the commands below, then
press Return to run each one.

### Step 2. Install Homebrew (a helper that installs the other tools)

Homebrew is the standard way to install developer tools on a Mac. Paste this single
line into Terminal and press Return:

```
/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
```

It may ask for your Mac password (the one you log in with). As you type the password
nothing appears on screen; that is normal. Press Return. Follow any final instructions
it prints, especially if it tells you to run an extra `echo`/`eval` line to finish
setup. When it is done, confirm it works:

```
brew --version
```

### Step 3. Install Python and DuckDB

With Homebrew installed, both tools are one command each:

```
brew install python
brew install duckdb
```

Confirm both:

```
python3 --version
duckdb --version
```

On a Mac the Python command is usually `python3` (with a 3 on the end), not `python`.
Use `python3` and `pip3` wherever this guide shows `python` and `pip`.

### Step 4. Get the Tender Watch code

Open https://github.com/abcde-stack/tender-watch, download it as a ZIP and unzip it,
or use Git:

```
git clone https://github.com/abcde-stack/tender-watch.git
```

Move into the folder. Type `cd ` (c, d, space) and then drag the `tender-watch` folder
from Finder onto the Terminal window so it pastes the path, and press Return.

### Step 5. Install the Python add ons

From inside the `tender-watch` folder:

```
pip3 install -r requirements.txt
```

### Step 6. Put the source data in the project folder

Place these files directly inside the `tender-watch` folder (the same folder that holds
the `etl` and `app` folders):

1. `aoc_tenders.db` and `tenders_vps.db`, downloaded from the data source in the README.
2. Optionally, `registered_companies.csv` (the MCA company list), for the company
   identity feature.

The scripts already look for these files by name in the project folder, so there is
nothing to edit. These files stay on your computer only; they are never uploaded or
committed.

The MCA list is the Ministry of Corporate Affairs company master data from data.gov.in.
A redacted 20 row sample showing the columns your file should have is included at
`docs/registered_companies.sample.csv`. After you download the data, make sure its
header row matches the sample, then save it as `registered_companies.csv` in the
project folder.

### Step 7. Build the data (the long step)

This takes about 45 minutes and uses about 16 GB of memory. Close other heavy apps
first. From inside the `tender-watch` folder, run these one at a time:

```
duckdb tender_watch.duckdb ".read etl/run.sql"
duckdb tender_watch.duckdb ".read etl/04_build_summary.sql"
duckdb tender_watch.duckdb ".read etl/06_dq_report.sql"
duckdb tender_watch.duckdb ".read etl/08_state_hierarchy.sql"
duckdb tender_watch.duckdb ".read etl/10_central_hierarchy.sql"
duckdb tender_watch.duckdb ".read etl/11_mca_crosswalk.sql"
```

The first command is the slow one and can look frozen for a long time. That is normal.
Skip the last command if you do not have the company CSV.

### Step 8. Open the dashboard

```
streamlit run app/dashboard.py
```

Your browser opens at `http://localhost:8501`. To stop it, press `Control` and `C` in
Terminal. To start it again later, reopen Terminal, move into the `tender-watch`
folder, and run the same `streamlit run` command. No rebuild needed.

---

## If something goes wrong

- **`python` or `duckdb` is "not recognised" or "command not found".** Close the
  terminal window and open a fresh one, then try again. Newly installed tools are only
  picked up by terminal windows opened after the install. On Windows, also make sure
  you ticked **Add python.exe to PATH** during the Python install (Step 2).
- **On a Mac, `python` does not work but `python3` does.** That is expected. Use
  `python3` and `pip3`.
- **The build seems frozen.** The first build command genuinely takes around 45
  minutes and prints little while it works. Leave it. It is done when your normal
  command prompt returns.
- **The build runs out of memory or crashes.** The build needs roughly 16 GB of RAM.
  Close other applications and try again. If your machine has less than 16 GB, building
  locally may not be practical, and a hosted copy is the better option.
- **The dashboard opens but a page is empty.** You may have skipped a build step.
  Re run the six build commands in Step 7 in order. If you skipped the company CSV step
  on purpose, only the company identity card is affected; everything else works.

---

## What the build numbers mean

For reference, a clean build measured these numbers on a fast desktop with a 16 core
processor (an AMD Ryzen 9 7950X, 16 cores and 32 threads) and 64 GB of RAM:

- About **44 minutes** of run time for the main `run.sql` step.
- A peak memory use of about **16 GB**.
- Around **40 GB** of free disk needed for the working file and the cleaned outputs.

DuckDB spreads the work across all available processor cores, so the time scales with
your machine. On a typical 4 core or 8 core laptop the same build will take noticeably
longer than the 44 minutes above, often well over an hour, even though the memory and
disk needs are about the same. Plan for that and leave it running.

These numbers are why building from source is best thought of as a one time, technical
setup. Day to day use of the dashboard afterwards is fast and light.
