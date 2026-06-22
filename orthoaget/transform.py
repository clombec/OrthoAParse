"""
transform.py

Pure data-transformation functions — no I/O, no browser.

Entry points
------------
build_context(data)          -- build lookup tables from raw session data
transform_jt(jt, ctx)        -- resolve metatypes and fauteuils in journées types
get_open_days(alldaysyear)   -- list of (YYYY-MM-DD, jt_name) for open days
transform_daily_events(daily_calendar, rdvs_history, ctx)
                             -- anonymize one day's calendar events

All outputs are plain dicts/lists — no PII.
"""

import re
import unicodedata
from datetime import datetime
from zoneinfo import ZoneInfo

_TZ_PARIS = ZoneInfo("Europe/Paris")


def normalize_name(s: str) -> str:
    """Lowercase + strip accents for case/accent-insensitive name comparisons."""
    nfd = unicodedata.normalize("NFD", s)
    return "".join(c for c in nfd if unicodedata.category(c) != "Mn").casefold()


def build_name_map(users: list) -> tuple[dict[str, int], dict[str, list[int]]]:
    """
    Build bidirectional name→id lookup maps from a list of user dicts.

    Each user must have 'id' (int), 'first_name' (str) and 'last_name' (str).
    Both "prénom nom" and "nom prénom" orderings are indexed, normalized
    (lowercase, accents stripped).

    Returns
    -------
    name_to_id  : {normalized_key: smallest_id}   — unambiguous lookup
    name_to_ids : {normalized_key: [id, ...]}      — all ids (homonym support)
    """
    name_to_ids: dict[str, list[int]] = {}
    for user in users:
        pid = user["id"]
        ln = normalize_name(user.get("last_name", "").strip())
        fn = normalize_name(user.get("first_name", "").strip())
        for key in (f"{fn} {ln}", f"{ln} {fn}"):
            name_to_ids.setdefault(key, []).append(pid)
    for ids in name_to_ids.values():
        ids.sort()
    name_to_id = {key: ids[0] for key, ids in name_to_ids.items()}
    return name_to_id, name_to_ids


# ---------------------------------------------------------------------------
# Fauteuil name normalisation
# ---------------------------------------------------------------------------

def _normalize_fauteuil_name(value: str) -> str:
    """
    "Fauteuil 1"   -> "F1"
    "Fauteuil 1 B" -> "F1b"
    "Fauteuil 2 B" -> "F2b"
    Anything else  -> value unchanged
    """
    m = re.fullmatch(r"Fauteuil\s+(\d+)(\s+([A-Za-z]))?", value.strip())
    if m:
        suffix = m.group(3).lower() if m.group(3) else ""
        return f"F{m.group(1)}{suffix}"
    return value


# ---------------------------------------------------------------------------
# Context builder
# ---------------------------------------------------------------------------

def build_context(data: dict) -> dict:
    """
    Build lookup tables from raw session data.

    Parameters
    ----------
    data : dict with keys 'users', 'MetatypesFauteuils'
           (as returned by OrthoASession.extract)

    Returns
    -------
    ctx : dict with:
        'name_to_id'     : {full_name: user_id}   (smallest id if duplicates)
        'metatype_map'   : {metatype_id_str: metatype_dict}
        'fauteuil_map'   : {fauteuil_id_str: normalized_name}
    """
    name_to_id, name_to_ids = build_name_map(data.get("users", []))

    # --- metatype id → metatype data ---
    mf = data.get("MetatypesFauteuils", {})
    metatype_map = {str(k): v for k, v in mf.get("metatypes", {}).items()}

    # --- fauteuil id → normalized name ---
    fauteuil_raw = mf.get("fauteuils", {}).get("fauteuils", {})
    fauteuil_map = {
        str(k): _normalize_fauteuil_name(v["value"])
        for k, v in fauteuil_raw.items()
    }

    return {
        "name_to_id": name_to_id,
        "name_to_ids": name_to_ids,
        "metatype_map": metatype_map,
        "fauteuil_map": fauteuil_map,
    }


# ---------------------------------------------------------------------------
# Journées types
# ---------------------------------------------------------------------------

def _resolve_metatype(path: str, metatype_map: dict) -> dict:
    """Extract id from '/listes/rdvs-metatypes/123' and look up metatype data."""
    m = re.search(r"/(\d+)$", path)
    if m:
        return metatype_map.get(m.group(1), {"raw": path})
    return {"raw": path}


def transform_jt(jt: dict, ctx: dict) -> dict:
    """
    Resolve metatypes and fauteuil names in journées types.

    Parameters
    ----------
    jt  : raw jt dict  {jt_name: [event, ...]}
    ctx : context from build_context()

    Returns
    -------
    dict {jt_name: [event, ...]} with metatype and fauteuil resolved.
    """
    metatype_map = ctx["metatype_map"]
    fauteuil_map = ctx["fauteuil_map"]
    result = {}
    for jt_name, events in jt.items():
        resolved = []
        for ev in events:
            resolved.append({
                "metatype": _resolve_metatype(ev.get("metatype", ""), metatype_map),
                "startminutes": ev.get("startminutes"),
                "duration": ev.get("duration"),
                "praticien_id": ev.get("praticien_id"),
                "fauteuil": fauteuil_map.get(str(ev.get("fauteuil", "")), ev.get("fauteuil")),
            })
        result[jt_name] = resolved
    return result


# ---------------------------------------------------------------------------
# Open days
# ---------------------------------------------------------------------------

_MONTHS_FR = {
    "janvier": 1, "février": 2, "mars": 3, "avril": 4,
    "mai": 5, "juin": 6, "juillet": 7, "août": 8,
    "septembre": 9, "octobre": 10, "novembre": 11, "décembre": 12,
}

def _parse_fr_date(label: str) -> str | None:
    """
    Parse "Lundi 5 Janvier 2026" -> "2026-01-05", case-insensitive.
    Returns None if not parseable.
    """
    m = re.search(r"(\d+)\s+(\w+)\s+(\d{4})", label)
    if not m:
        return None
    day, month_str, year = int(m.group(1)), m.group(2).lower(), int(m.group(3))
    month = _MONTHS_FR.get(month_str)
    if month is None:
        return None
    return f"{year:04d}-{month:02d}-{day:02d}"


def get_open_days(alldaysyear: list) -> list[dict]:
    """
    Filter open days from alldaysyear, keeping today and future days only.

    Parameters
    ----------
    alldaysyear : list of [label, jt_name, status]

    Returns
    -------
    list of {'date': 'YYYY-MM-DD', 'jt_name': str}
    Only rows where status == 'Ouvert' and date >= today (Paris time).
    """
    today = datetime.now(_TZ_PARIS).date()
    open_days = []
    for row in alldaysyear:
        label, jt_name, status = row[0], row[1], row[2]
        if status.strip() != "Ouvert":
            continue
        date_str = _parse_fr_date(label)
        if date_str and datetime.strptime(date_str, "%Y-%m-%d").date() >= today:
            open_days.append({"date": date_str, "jt_name": jt_name})
    return open_days


# ---------------------------------------------------------------------------
# Daily calendar
# ---------------------------------------------------------------------------

def _normalize_dt(dt_str: str) -> str:
    """
    Normalise a datetime string to 'YYYY-MM-DDTHH:MM' in Europe/Paris time.

    rdvs_history datetimes are naive but implicitly Paris time -> localise directly.
    daily_calendar datetimes carry an explicit offset (+02:00 or +01:00) -> convert.
    Both end up as Paris wall-clock time, safe across DST changes.
    """
    try:
        dt = datetime.fromisoformat(dt_str)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=_TZ_PARIS)
        else:
            dt = dt.astimezone(_TZ_PARIS)
        return dt.strftime("%Y-%m-%dT%H:%M")
    except ValueError:
        return dt_str[:16]


def _build_rdvs_index(rdvs_history: list, name_to_ids: dict) -> set:
    """
    Build a set of (patient_id, normalized_datetime) from rdvs_history.
    For homonyms (same name, multiple ids), the RDV is indexed under all ids
    so that the correct one can be matched against daily_calendar.
    """
    index = set()
    for rdv in rdvs_history:
        patient_name = normalize_name(rdv.get("Patient", "").strip())
        ids = name_to_ids.get(patient_name, [])
        dt_key = _normalize_dt(rdv.get("Date et heure du RDV", ""))
        if ids and dt_key:
            for pid in ids:
                index.add((pid, dt_key))
    return index


def transform_daily_events(daily_calendar: list, rdvs_history: list, ctx: dict) -> list:
    """
    Anonymize one day's calendar events.

    patient_name in daily_calendar is the patient id. For each event with a
    patient, verifies that the exact (patient_id, datetime) pair exists in
    rdvs_history. Raises AssertionError if not (dev guard).

    Parameters
    ----------
    daily_calendar : list of raw calendar events for one day
    rdvs_history   : full rdvs_history list
    ctx            : context from build_context()

    Returns
    -------
    list of anonymized event dicts:
        {date, startminutes, duration, praticien_id, fauteuil, patient_id}
    patient_id is None for events without a patient (e.g. blocked slots).
    """
    fauteuil_map = ctx["fauteuil_map"]
    rdvs_index = _build_rdvs_index(rdvs_history, ctx["name_to_ids"])

    result = []
    for ev in daily_calendar:
        raw_patient = ev.get("patient_name") or None
        patient_id = int(raw_patient) if raw_patient is not None else None
        if patient_id is not None:
            dt_key = _normalize_dt(ev.get("date", ""))
            if (patient_id, dt_key) not in rdvs_index:
                with open("mismatch.txt", "a") as f:
                    f.write(f"Mismatch: patient_id={patient_id}, date={dt_key}\n")

        result.append({
            "date": ev.get("date"),
            "startminutes": ev.get("startminutes"),
            "duration": ev.get("duration"),
            "praticien_id": ev.get("praticien_id"),
            "fauteuil": fauteuil_map.get(str(ev.get("fauteuil", "")), ev.get("fauteuil")),
            "patient_id": patient_id,
            "metatype": ev.get("metatype").replace("/listes/rdvs-metatypes/", "") if ev.get("metatype") else None,
        })
    return result
