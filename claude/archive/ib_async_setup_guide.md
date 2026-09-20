# Setting up ib_async with your Interactive Brokers account

A quick note first: there's no package actually called "ib-sync." You're almost certainly thinking of **ib_insync**, the popular Python wrapper for the IB TWS API — but that project was archived by its author in 2024. Its actively maintained successor is **ib_async**, which is a drop-in replacement with the same API. This guide sets up ib_async.

Also important: this connects over a local socket (127.0.0.1) between your Python script and TWS or IB Gateway running on the *same machine*. It can't be run from a cloud session like this one — everything below needs to happen in a terminal on your own computer.

## 1. Install TWS or IB Gateway

- **TWS** (Trader Workstation) is the full desktop trading platform.
- **IB Gateway** is a lighter-weight app with no trading UI — just the connection layer. Most people building an algo prefer this since it uses less memory and has less surface area.

Download whichever you prefer from IBKR's site and install it. Log in with your username (`bengysiu85`) and password directly in the app — never paste your IBKR password into a chat with Claude or anywhere else.

You'll need IBKR's two-factor login (IBKR Mobile app push, or an IB Key) to complete login, as IBKR requires 2FA for most accounts.

**Strongly recommended while building and testing:** log into your **paper trading** account, not your live account, until the algo is working the way you want.

## 2. Enable API access

In TWS: click the gear icon (top right) → **API → Settings**.
In IB Gateway: **Configure → Settings → API → Settings**.

Set:

- ✅ **Enable ActiveX and Socket Clients**
- **Socket port** — note this value, you'll need it in your script:
  - TWS live: `7496`
  - TWS paper: `7497`
  - IB Gateway live: `4001`
  - IB Gateway paper: `4002`
- Add `127.0.0.1` to **Trusted IPs**
- Leave **Read-Only API** checked until you're ready to let the script place real orders — uncheck it only when you actually want it submitting trades
- Click **Apply**, then **OK**

Leave TWS/Gateway running — your script connects to it, it doesn't run standalone.

## 3. Install ib_async

In a terminal on your machine (a virtual environment is recommended):

```bash
python3 -m venv ibkr-env
source ibkr-env/bin/activate      # on Windows: ibkr-env\Scripts\activate
pip install ib_async
```

## 4. Test the connection

Use the `test_connection.py` script provided alongside this guide. Run it with TWS/Gateway open and logged in:

```bash
python test_connection.py
```

If everything's wired up correctly you'll see `Connected: True`, your account number(s), and a slice of your account summary printed out.

Things that commonly trip this up:
- **Port mismatch** — double check paper vs. live and TWS vs. Gateway.
- **clientId collision** — if another script or the TWS/Gateway API log shows a client already connected with that ID, change `CLIENT_ID` to a different integer.
- **Firewall/antivirus** blocking local socket connections — whitelist TWS/Gateway if needed.
- **TWS auto-logout** — TWS/Gateway logs itself out roughly every 24 hours (configurable) and needs you to log back in (with 2FA). For an algo that needs to run unattended for long stretches, people typically use a helper like **IBC (IB Controller)** or **ibeam** to automate the relaunch/login — worth looking into once the basic connection is working, not before.

## macOS + VS Code walkthrough

Everything below runs in a normal VS Code project on your Mac — not in this chat.

1. **Check/install Python 3.10+.** Open Terminal.app (or VS Code's own terminal later) and run `python3 --version`. macOS ships an old system Python that's best left alone — if you don't have 3.10+, install via Homebrew:
   ```bash
   # if you don't have Homebrew yet:
   /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
   brew install python@3.12
   ```

2. **Install VS Code** if you don't have it already — [code.visualstudio.com](https://code.visualstudio.com) or `brew install --cask visual-studio-code`.

3. **Install the VS Code Python extensions.** Open VS Code → Extensions panel (⌘⇧X) → install **Python** (`ms-python.python`, publisher Microsoft) and **Python Environments** (adds the environment-management sidebar; Pylance comes bundled).

4. **Open your project folder.** `File → Open Folder…`, pick or create a folder for this (e.g. `~/ibkr-algo`). If VS Code asks whether you trust the folder, click **Yes, I trust the authors**.

5. **Create a virtual environment.** Open the Command Palette (⌘⇧P) → **Python: Create Environment** → **Venv** → select your Python 3.10+ interpreter. This creates a `.venv` folder in your project and VS Code will offer to select it automatically.
   (Equivalent from the integrated terminal, ⌃\`: `python3 -m venv .venv`.)

6. **Confirm the interpreter is selected.** Click the Python version shown in the bottom status bar, or ⌘⇧P → **Python: Select Interpreter**, and pick the one under `.venv`. Any new integrated terminal you open should now show `(.venv)` in the prompt.

7. **Install ib_async.** In the integrated terminal (with `.venv` active):
   ```bash
   pip install ib_async
   ```
   (Or: Python sidebar → Environment Managers → your env → right-click → **Manage Packages** → search `ib_async` → install.)

8. **Add the test script.** Save the `test_connection.py` file I sent you into this same project folder.

9. **Enable API access in TWS/IB Gateway** as described in step 2 above, and leave TWS/Gateway open and logged into your **paper trading** account.

10. **Run it.** Open `test_connection.py` in VS Code and either click the ▷ **Run** button (top right), or right-click in the editor → **Run Python File in Terminal**. For breakpoint debugging instead, press **F5** and choose **Python File** the first time — VS Code will generate a `.vscode/launch.json` you can reuse.

macOS-specific snags:
- If TWS/Gateway's installer says it "cannot be opened because the developer cannot be verified," right-click the app → **Open** to bypass Gatekeeper once.
- macOS Firewall may prompt to allow incoming connections for TWS/Gateway the first time it starts — click **Allow**.
- If `python3` isn't found after installing via Homebrew, open a fresh terminal (or `source ~/.zshrc`) so your `PATH` picks it up.

## 5. Where your algo actually runs

Because the connection is local-socket-only, the trading logic itself needs to run as a script on your own machine (or a VPS you control that also runs TWS/Gateway) — not inside this Claude session. I'm happy to help you write and iterate on the strategy code here; you'll just run and test it locally, and can paste back results, errors, or data for me to help debug.

## Reference

- [ib_async on GitHub](https://github.com/ib-api-reloaded/ib_async)
- [ib_insync on GitHub (archived)](https://github.com/erdewit/ib_insync)
- [IBKR Campus: Installing & Configuring TWS for the API](https://ibkrcampus.com/campus/trading-lessons/installing-configuring-tws-for-the-api)
