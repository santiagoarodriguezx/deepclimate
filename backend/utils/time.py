import datetime


BOGOTA = datetime.timezone(datetime.timedelta(hours=-5))


def parse_siata_local_time(value: str) -> datetime.datetime | None:
    """Convert SIATA's local wall time to the database's naive-UTC convention."""
    try:
        local = datetime.datetime.strptime(value.strip(), "%Y-%m-%d %H:%M:%S")
    except (AttributeError, ValueError):
        return None
    return local.replace(tzinfo=BOGOTA).astimezone(datetime.timezone.utc).replace(tzinfo=None)
