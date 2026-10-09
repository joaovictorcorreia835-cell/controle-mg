from datetime import datetime
from zoneinfo import ZoneInfo
def now(): return datetime.now(ZoneInfo("America/Sao_Paulo")).replace(tzinfo=None)
def today(): return now().date()
