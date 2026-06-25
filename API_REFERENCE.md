# API Reference — OrthoASession

Single entry point for upper layers (UI, scripts, web).  
Module: `orthoaget.session` — class `OrthoASession`.

---

## Lifecycle

### `OrthoASession(urls_file=URLS_FILE)`

Opens a Chrome session and connects to OrthoAdvance.  
On subsequent calls, the session is restored from the persistent Chrome profile — no re-login required as long as the server-side session is still valid.  
Raises `OrthoAConnectionError` if the connection fails.

```python
session = OrthoASession()
# ... calls ...
session.end()

# or as a context manager (recommended):
with OrthoASession() as session:
    ...
```

### `end()`

Closes the browser. Called automatically when exiting a `with` block.

---

## Read methods

### `get_proth_records() → list[dict]`

Fetches all prosthetist acts (pagination handled automatically).

**Returns** — list of dicts, one per act:

| Key | Type | Description |
|-----|------|-------------|
| `Prothésiste` | str | Prosthetist name |
| `Patient` | str | Patient name |
| `Date du rdv` | str ISO | Appointment date and time |
| `Acte prothésiste` | str | Act type |
| `Date d'envoi au labo` | str ISO | Date sent to lab |
| `Date de réception` | str ISO | Date received from lab |
| `PE` | str ISO \| `""` | PE date (empty if absent) |
| `Durée` | str | Duration |
| `Commentaires` | str | Free-text comments |
| `url` | str | Full act URL (used by `fetch_act` / `confirm_act_done`) |
| `patient_url` | str | Patient clinical URL |

---

### `get_users_records() → list[dict]`

Fetches the full patient list.

**Returns** — list of dicts:

| Key | Type | Description |
|-----|------|-------------|
| `id` | int | OrthoAdvance identifier |
| `name` | str | First name + Last name |

---

### `get_user_by_id(user_id: int) → dict | None`

Returns a patient's full profile from the local cache (`users_db.json`).  
Rebuilds the cache if the ID is missing.

**Parameter** — `user_id`: numeric OrthoAdvance identifier.  
**Returns** — dict `{name, ...}` or `None` if not found.

---

### `get_name_by_id(user_id: int) → str | None`

Shortcut: returns only the patient name for a given ID.

---

### `get_stats_records() → dict`

Computes appointment statistics per patient.

**Returns** — `{str(patient_id): {..., "rdvs": [...]}}`:

```python
{
  "42": {
    # user fields except id and name
    "rdvs": [
      {
        "date": "2026-03-15",
        "plage": "P55",
        "temps_praticien": 30,   # minutes
        "temps_total": 45
      },
      ...
    ]
  },
  ...
}
```

---

### `get_calendar_records() → dict`

Fetches the full planning configuration (current year + next year) and all daily events.  
**Note**: makes one HTTP request per open day — may be slow.

**Returns**:

```python
{
  "jt": {
    "Day type A": [
      {
        "metatype": {...},        # metatype description dict
        "startminutes": 480,      # start time in minutes since midnight
        "duration": 30,
        "praticien_id": 7,
        "fauteuil": "F1"          # normalised chair name
      },
      ...
    ],
    ...
  },
  "events": [
    {
      "date": "2026-06-15T09:00+02:00",
      "startminutes": 540,
      "duration": 30,
      "praticien_id": 7,
      "fauteuil": "F1",
      "patient_id": 42,           # None for slots without a patient
      "metatype": "123"           # metatype id
    },
    ...
  ],
  "alldaysyear": [
    {"date": "2026-06-15", "jt_name": "Day type A"},
    ...
  ]
}
```

---

### `get_echeances_records(dayin: str, dayout: str) → list[dict]`

Fetches payment schedule records for the given date range.  
Patient names are anonymized: `"ID Patient"` is replaced by the numeric OrthoAdvance ID (looked up from the local cache).

**Parameters**:
- `dayin`: `str` `"YYYY-MM-DD"` — start date
- `dayout`: `str` `"YYYY-MM-DD"` — end date

**Returns** — list of dicts:

| Key | Type | Description |
|-----|------|-------------|
| `ID Patient` | int \| str | Numeric patient ID (or original name if not found in cache) |
| `Date` | str ISO | Due date |
| `Dû` | float | Amount due |
| `Acte` | str | Act label |

---

### `get_income_records(dayin=None, dayout=None) → list[dict]`

Fetches collected income for a date range.  
Defaults to today only.

**Parameters**:
- `dayin`: `str` `"YYYY-MM-DD"` — start date (default: today)
- `dayout`: `str` `"YYYY-MM-DD"` — end date (default: today)

**Returns** — list of dicts aggregated by date:

```python
[
  {"date": "15/06/2026", "amount": 1250.00},
  ...
]
```

---

### `get_html_table_items(url_name: str) → list[dict]`

Returns all rows of a paginated HTML browse-list table defined in `urls.yaml`.

**Parameter** — `url_name`: key in `urls.yaml` with type `html_paginated`.  
**Returns** — list of dicts `{"path": str, "title": str}`.

---

## Write methods

The two-step flow — fetch then confirm — separates reading from writing so the user can validate before any change is committed.  
Both methods require an open `OrthoASession`. Since the persistent Chrome profile avoids re-login, opening a session is fast.

```python
with OrthoASession() as session:
    records = session.get_proth_records()

    # One act at a time — show form_display to the user, then on confirm:
    form_data, form_display, is_expired = session.fetch_act(records[0]["url"])
    if not is_expired:
        session.confirm_act_done(records[0]["url"], form_data)
```

For multiple acts, reuse the same session:

```python
with OrthoASession() as session:
    records = session.get_proth_records()
    for rec in records:
        form_data, form_display, is_expired = session.fetch_act(rec["url"])
        if not is_expired:
            session.confirm_act_done(rec["url"], form_data)
```

---

### `fetch_act(url: str) → tuple[dict | None, dict | None, bool]`

GETs a single act page and parses its form fields.

**Parameter**:
- `url`: full act URL (the `url` field from `get_proth_records`)

**Returns** — `(form_data, form_display, is_expired)`:
- `form_data`: raw dict `{name: value}` for passing to `confirm_act_done` — select fields contain the path value (e.g. `/medical/prothesiste/actes/36`)
- `form_display`: same structure but select fields contain the human-readable label (e.g. `Analyse empreinte go max`) — use this for display only
- `is_expired`: `True` if the session has expired (redirect detected); both dicts are `None` in that case

**Raises** — `RuntimeError` if no form is found at the URL.

---

### `confirm_act_done(url: str, form_data: dict) → bool`

Submits the act form with `done=1` to mark it as realised.

**Parameters**:
- `url`: same URL passed to `fetch_act`
- `form_data`: dict returned by `fetch_act`

**Returns** — `True` on success.

---

### `sort_html_table_items(url_name: str) → list[dict]`

Sorts rows of a paginated HTML browse-list table alphabetically (case- and accent-insensitive) by POSTing reorder requests to OrthoAdvance.

**Parameter** — `url_name`: key in `urls.yaml` with type `html_paginated`.  
**Returns** — sorted list of dicts `{"path": str, "title": str}`.

---

## Utility methods

### `user_url(user_id) → str`

Builds the OrthoAdvance clinical URL for a given patient.

**Parameter** — `user_id`: numeric identifier.  
**Returns** — full URL `https://.../ang/#!/users/<id>/clinique/compact/`.

---

### `extract(entries=None, params=None) → dict`

Low-level method — downloads and parses one or more entries defined in `urls.yaml`.  
Prefer the domain-specific methods above; use `extract` only to access entries not yet wrapped.

**Parameters**:
- `entries`: `list[str]` — `urls.yaml` keys to fetch. If `None`, all entries are fetched.
- `params`: `dict` — placeholder substitutions `{key}` applied to matching URLs.

**Returns** — `{entry_name: parsed_data, ...}`  
**Raises** — `KeyError` if an entry is not found in `urls.yaml`.

---

## Exceptions

| Exception | Raised by | Cause |
|-----------|-----------|-------|
| `OrthoAdl.OrthoAConnectionError` | `__init__` | Login / connection failure |
| `OrthoAdl.OrthoADownloadError` | any extract method | Page download failure |
| `KeyError` | `extract()` | Unknown entry in `urls.yaml` |
| `RuntimeError` | `fetch_act`, `sort_html_table_items` | No form found / unexpected response |

```python
import OrthoABase.OrthoAdl as OrthoAdl

try:
    with OrthoASession() as session:
        records = session.get_proth_records()
except OrthoAdl.OrthoAConnectionError as e:
    # Connection unavailable
    ...
except OrthoAdl.OrthoADownloadError as e:
    # Page could not be downloaded
    ...
```
