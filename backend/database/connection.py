"""
Database connection and session factory for SIATA Intelligence.
Supports PostgreSQL (with TimescaleDB) and SQLite with WAL mode.
"""

import os
from contextlib import contextmanager
from dotenv import load_dotenv
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker
from backend.database.models import Base, Variable

load_dotenv()

# Base path for data
BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
DATA_DIR = os.path.join(BASE_DIR, "data")
os.makedirs(DATA_DIR, exist_ok=True)

DEFAULT_SQLITE_PATH = os.path.join(DATA_DIR, "siata_intelligence.db")
DATABASE_URL = os.getenv("DATABASE_URL", f"sqlite:///{DEFAULT_SQLITE_PATH}")

connect_args = {}
if DATABASE_URL.startswith("sqlite"):
    connect_args = {"check_same_thread": False, "timeout": 30}

engine = create_engine(
    DATABASE_URL,
    connect_args=connect_args,
    pool_pre_ping=True
)

# Enable SQLite Write-Ahead Logging (WAL) and foreign keys for high-performance concurrent writes
if DATABASE_URL.startswith("sqlite"):
    @event.listens_for(engine, "connect")
    def set_sqlite_pragma(dbapi_connection, connection_record):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.execute("PRAGMA synchronous=NORMAL")
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


@contextmanager
def get_db():
    """Context manager for database sessions."""
    db = SessionLocal()
    try:
        yield db
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def get_db_session():
    """FastAPI dependency for database sessions."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db():
    """Initializes tables and seeds canonical variables."""
    Base.metadata.create_all(bind=engine)
    seed_canonical_variables()


def seed_canonical_variables():
    """Seeds the official canonical environmental variables."""
    canonical = [
        Variable(
            id="PM25",
            code="PM25",
            name="Material Particulado PM2.5",
            unit="µg/m³",
            category="air_quality",
            description="Partículas finas respirables de diámetro menor a 2.5 micrómetros."
        ),
        Variable(
            id="PM10",
            code="PM10",
            name="Material Particulado PM10",
            unit="µg/m³",
            category="air_quality",
            description="Partículas torácicas respirables de diámetro menor a 10 micrómetros."
        ),
        Variable(
            id="O3",
            code="O3",
            name="Ozono Troposférico",
            unit="µg/m³",
            category="air_quality",
            description="Ozono a nivel del suelo, contaminante secundario formado fotoquímicamente."
        ),
        Variable(
            id="NO2",
            code="NO2",
            name="Dióxido de Nitrógeno",
            unit="µg/m³",
            category="air_quality",
            description="Gas reactivo generado principalmente por emisiones de tráfico y combustión."
        ),
        Variable(
            id="NO",
            code="NO",
            name="Monóxido de Nitrógeno",
            unit="µg/m³",
            category="air_quality",
            description="Óxido de nitrógeno primario procedente de combustión de vehículos."
        ),
        Variable(
            id="CO",
            code="CO",
            name="Monóxido de Carbono",
            unit="mg/m³",
            category="air_quality",
            description="Gas tóxico producido por combustión incompleta de hidrocarburos."
        ),
        Variable(
            id="SO2",
            code="SO2",
            name="Dióxido de Azufre",
            unit="µg/m³",
            category="air_quality",
            description="Gas producido por fuentes industriales y diésel sulfuroso."
        ),
        Variable(
            id="temperature",
            code="temperature",
            name="Temperatura del Aire",
            unit="°C",
            category="meteorology",
            description="Temperatura ambiente medida a 2m o 10m de altura."
        ),
        Variable(
            id="humidity",
            code="humidity",
            name="Humedad Relativa",
            unit="%",
            category="meteorology",
            description="Porcentaje de vapor de agua respecto a la saturación."
        ),
        Variable(
            id="pressure",
            code="pressure",
            name="Presión Atmosférica",
            unit="hPa",
            category="meteorology",
            description="Presión barométrica atmosférica local en el Valle de Aburrá."
        ),
        Variable(
            id="wind_speed",
            code="wind_speed",
            name="Velocidad del Viento",
            unit="m/s",
            category="meteorology",
            description="Velocidad media horizontal del viento."
        ),
        Variable(
            id="wind_direction",
            code="wind_direction",
            name="Dirección del Viento",
            unit="°",
            category="meteorology",
            description="Dirección azimutal de origen del viento en grados (0-360°)."
        ),
        Variable(
            id="rain",
            code="rain",
            name="Precipitación Acumulada",
            unit="mm",
            category="hydrology",
            description="Lámina de lluvia acumulada registrada por pluviómetro."
        ),
        Variable(
            id="river_level",
            code="river_level",
            name="Nivel de Cuenca / Río",
            unit="m",
            category="hydrology",
            description="Nivel del agua en cauces de quebradas o río Medellín."
        ),
    ]

    with get_db() as db:
        for var in canonical:
            existing = db.query(Variable).filter(Variable.id == var.id).first()
            if not existing:
                db.add(var)
        db.commit()
