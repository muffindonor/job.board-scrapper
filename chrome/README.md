# Pinned Chrome for Testing Binaries

This folder contains pinned Chrome and ChromeDriver binaries used by
`job_scraper.py`. Using these instead of the system Chrome installation
means a silent Chrome auto-update can never break the scraper overnight.

## Folder structure

```
chrome/
├── chrome-win64/
│   ├── chrome.exe
│   └── ... (other Chrome files)
└── chromedriver-win64/
    ├── chromedriver.exe
    └── ... (other ChromeDriver files)
```

## First-time setup

1. Go to https://googlechromelabs.github.io/chrome-for-testing/#stable
2. Download both `chrome / win64` and `chromedriver / win64` for the same
   version (they must match exactly).
3. Unzip both into this `chrome/` folder. The zip files already contain the
   named subfolders (`chrome-win64/` and `chromedriver-win64/`), so just
   extracting here produces the correct structure above.
4. Verify the two key paths exist:
   - `chrome\chrome-win64\chrome.exe`
   - `chrome\chromedriver-win64\chromedriver.exe`

## Disable Chrome auto-updates (important)

The system Chrome installation will still auto-update itself in the
background, which won't affect these pinned binaries directly -- but if
`webdriver-manager` or any other tool is also present it could pick up
the wrong version. More importantly, UC (undetected-chromedriver) reads
the *actual binary* version, so keeping things consistent matters.

Disable the Google Update services so nothing drifts under you:

1. Press `Win + R`, type `services.msc`, press Enter.
2. Find **Google Update Service (gupdate)** -- right-click → Properties →
   Startup type: **Disabled** → Stop → OK.
3. Find **Google Update Service (gupdatem)** -- same steps.

## Updating Chrome

When you want to update to a newer Chrome version:

1. Download the new `chrome-win64` and `chromedriver-win64` zips from
   https://googlechromelabs.github.io/chrome-for-testing/#stable
2. Delete the old `chrome-win64/` and `chromedriver-win64/` subfolders.
3. Unzip the new ones here.
4. No code changes needed -- `job_scraper.py` reads the binary directly
   and does not hardcode a version number.

## Why not webdriver-manager?

`webdriver-manager` makes a version-check network call on every Selenium
invocation and re-downloads ChromeDriver whenever Chrome updates. In a
scheduled overnight scraper that runs 88 URLs this means ~80 redundant
network calls per run, a zip download on any day Chrome silently updated,
and the constant risk of a version mismatch breaking the entire Selenium
tier mid-run. Pinned binaries eliminate all of this.
