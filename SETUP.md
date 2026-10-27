# Setup guide (Mac)

How to install, run and update the Tyre Debrief app on a Mac. A first-time setup takes about 10 minutes.

| You do this | When |
|---|---|
| Steps 1–4 | Once, on a new Mac |
| Step 5 | Every time you want to use the app |
| Step 8 | When you get a new version |

---

## What you need

- A Mac (Apple silicon or Intel) with an internet connection for the install.
- **Python 3.13** (3.12 also works). Step 1 shows how to get it.
- *Optional:* a free **Gemini API key** for AI-written debriefs and questions. Without one, the app still works and writes the debrief from a built-in template.
- *Optional:* the Team Plus session files, if you want the built-in sample sessions (step 6).

---

## 1. Install Python

1. Go to <https://www.python.org/downloads/> and download **Python 3.13** for macOS.
2. Open the downloaded file and click through the installer.
3. Open the **Terminal** app and check it worked:

   ```bash
   python3.13 --version
   ```

   It should print `Python 3.13.x`.

---

## 2. Get the project

Use **one** of these:

**A. From a zip file**
Unzip it (double-click), then put the `tyre-debrief` folder wherever you like, for example in Documents.

**B. From GitHub**
```bash
cd ~/Documents
git clone https://github.com/<your-username>/tyre-debrief.git
```

Then go into the folder in Terminal. The easiest way: type `cd ` (with a space), drag the `tyre-debrief` folder into the Terminal window, and press Enter. Check you're in the right place:

```bash
ls
```

You should see `backend`, `frontend`, `requirements.txt` and `SETUP.md`.

---

## 3. Install the app

Run these one at a time, inside the `tyre-debrief` folder:

```bash
python3.13 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

- The first line creates a private Python environment for the app, in a folder called `.venv`.
- The second switches to it. You'll see `(.venv)` at the start of the Terminal line.
- The third installs everything the app needs. It takes about a minute.

**Check it worked:**

```bash
python -m pytest -q
```

All tests should pass. Two are skipped if the Team Plus session files aren't there (step 6); that's normal.

---

## 4. Add your AI key (optional)

Skip this step if you received a `.env` file with the project. It's already set up.

1. Create the settings file from the example:
   ```bash
   cp .env.example .env
   ```
2. Open it in TextEdit:
   ```bash
   open -e .env
   ```
3. Paste your key after `GEMINI_API_KEY=` and save. Get a free key at <https://aistudio.google.com/apikey>.
4. *Optional backup AI:* paste an OpenRouter key after `OPENROUTER_API_KEY=` (free at <https://openrouter.ai/keys>).

Never share or upload `.env`; it holds your keys. It's already excluded from git.

---

## 5. Start the app

In Terminal, inside the `tyre-debrief` folder:

```bash
source .venv/bin/activate
python -m uvicorn backend.main:app
```

Then open **<http://localhost:8000>** in your browser.

- **Upload a session:** drag in the logger's `.xrk` file or a `.csv` export from Race Studio, optionally fill in the car details, and click **Generate debrief**.
- The top-right of the page shows **"AI narrative · gemini"** when your key works, or **"AI off"** without one.
- **To stop the app,** click in Terminal and press **Ctrl + C**.

---

## 6. Add the sample sessions (optional)

The **"No file handy?"** box on the upload page lists the Team Plus sessions. They aren't included with the code (sponsor data), so copy them from the team's shared drive:

```bash
mkdir -p data/raw data/xrk
```

- Put the CSV files in `tyre-debrief/data/raw/`.
- Put the XRK files in `tyre-debrief/data/xrk/`.

Restart the app (step 5). The list groups usable track sessions separately from files that can't be analysed.

---

## 7. Other useful commands

Run these with `(.venv)` showing, inside the `tyre-debrief` folder:

| What | Command |
|---|---|
| Run the tests | `python -m pytest -q` |
| Analyse every sample session and write a summary | `python -m scripts.batch_report data/raw,data/xrk docs/session_results.md` |
| Measure how often the AI passes the fact check (uses API quota) | `python -m scripts.faithfulness_eval data/raw docs/faithfulness_results.md 3` |
| Run on a different port | `python -m uvicorn backend.main:app --port 8001` |

Thresholds (temperature window, camber targets, pressure target and so on) are in `config/thresholds.yaml`. Changes apply to the next report; there's no need to restart.

---

## 8. Updating to a new version

1. Stop the app (**Ctrl + C**).
2. Get the new code:
   - **From GitHub:** `git pull`
   - **From a zip:** copy the new files over the old ones. Keep your `.venv` folder, `.env` file and `data` folder.
3. Update the installed packages. This is safe to run every time; if nothing changed it finishes in seconds:
   ```bash
   source .venv/bin/activate
   pip install -r requirements.txt
   ```
4. Start the app again (step 5).

`CHANGES.md` lists what changed in each version. Reports saved before an update may not show the newest sections; upload the session again to get them.

---

## If something goes wrong

| Problem | Fix |
|---|---|
| `python3.13: command not found` | Python isn't installed. Do step 1. |
| `No module named …` | You're not in the app's environment. Run `source .venv/bin/activate` inside the `tyre-debrief` folder. |
| `pip install` fails | Run `python -m pip install --upgrade pip`, then step 3 again. Check `python --version` says 3.12 or 3.13. |
| "Address already in use" | The app is already running in another Terminal window. Close it, or use another port (step 7). |
| Page says "AI off" | No key in `.env`, a typo in the key name, or the app wasn't restarted after adding it (step 4). |
| "This session has no tyre-temperature data…" or "…no real track running" | The file itself has no usable data: the tyre sensors didn't log, or it's a paddock recording. Try another session. |
| Debrief says "Template narrative" | The AI was slow, rate-limited or failed the fact check. The findings are still complete; try again later for an AI-written debrief. |
| Commands don't work after closing Terminal | Go back into the folder (step 2) and activate again (first line of step 5). |
