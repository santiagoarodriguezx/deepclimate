"""
Database models for SIATA Intelligence.
Canonical schema matching the project requirements:
- stations
- variables
- observations (indexed on station, variable, observed_at)
- events (detected anomalies and multi-station episodes)
- ingestion_runs (provenance and historical data lake metadata)
"""

import datetime
from sqlalchemy import (
    Column, Integer, Float, String, Boolean, DateTime,
    ForeignKey, Text, Index
)
from sqlalchemy.orm import declarative_base, relationship

Base = declarative_base()


class Station(Base):
    __tablename__ = "stations"

    id = Column(String(64), primary_key=True)  # canonical id, e.g. "ITA-CJUS" or "METEO-1019"
    source_id = Column(String(64), index=True)  # original SIATA numerical id, e.g. "28"
    name = Column(String(255), nullable=False)
    code = Column(String(64), index=True)       # e.g. "ITA-CJUS", "MED-PJIC"
    municipality = Column(String(128), index=True)
    latitude = Column(Float, nullable=False)
    longitude = Column(Float, nullable=False)
    altitude = Column(Float, nullable=True)
    station_type = Column(String(64), index=True)  # air_quality, meteorology, pluviometric, stream_level
    active = Column(Boolean, default=True)
    subbasin = Column(String(128), nullable=True)
    neighborhood = Column(String(128), nullable=True)
    metadata_json = Column(Text, nullable=True)   # JSON string for extra fields

    observations = relationship("Observation", back_populates="station", cascade="all, delete-orphan")

    def to_dict(self):
        return {
            "id": self.id,
            "source_id": self.source_id,
            "name": self.name,
            "code": self.code,
            "municipality": self.municipality,
            "latitude": self.latitude,
            "longitude": self.longitude,
            "altitude": self.altitude,
            "station_type": self.station_type,
            "active": self.active,
            "subbasin": self.subbasin,
            "neighborhood": self.neighborhood
        }


class Variable(Base):
    __tablename__ = "variables"

    id = Column(String(32), primary_key=True)   # canonical: PM25, PM10, O3, NO2, CO, SO2, temperature, humidity, pressure, wind_speed, wind_direction, rain, river_level
    code = Column(String(32), unique=True, index=True)
    name = Column(String(128), nullable=False)
    unit = Column(String(32), nullable=False)
    category = Column(String(64), index=True)   # air_quality, meteorology, hydrology
    description = Column(Text, nullable=True)

    observations = relationship("Observation", back_populates="variable")

    def to_dict(self):
        return {
            "id": self.id,
            "code": self.code,
            "name": self.name,
            "unit": self.unit,
            "category": self.category,
            "description": self.description
        }


class Observation(Base):
    __tablename__ = "observations"

    id = Column(Integer, primary_key=True, autoincrement=True)
    station_id = Column(String(64), ForeignKey("stations.id"), nullable=False, index=True)
    variable_id = Column(String(32), ForeignKey("variables.id"), nullable=False, index=True)
    observed_at = Column(DateTime, nullable=False, index=True)
    value = Column(Float, nullable=False)
    raw_value = Column(String(64), nullable=True)
    unit = Column(String(32), nullable=False)
    quality_code = Column(String(64), nullable=True)      # e.g. "2.1", "null", "MSFLCode"
    quality_status = Column(String(32), default="good")  # good, doubtful, unvalidated, extreme_value
    source = Column(String(128), nullable=False)         # siata_layer_service, siata_meteo_json, siata_ideam_historical
    ingested_at = Column(DateTime, default=datetime.datetime.utcnow)

    station = relationship("Station", back_populates="observations")
    variable = relationship("Variable", back_populates="observations")

    __table_args__ = (
        Index("idx_station_var_obs", "station_id", "variable_id", "observed_at", unique=True),
        Index("idx_var_obs", "variable_id", "observed_at"),
        Index("idx_observed_at", "observed_at"),
    )

    def to_dict(self):
        return {
            "id": self.id,
            "station_id": self.station_id,
            "variable_id": self.variable_id,
            "observed_at": self.observed_at.isoformat() if self.observed_at else None,
            "value": self.value,
            "raw_value": self.raw_value,
            "unit": self.unit,
            "quality_code": self.quality_code,
            "quality_status": self.quality_status,
            "source": self.source,
            "ingested_at": self.ingested_at.isoformat() if self.ingested_at else None
        }


class EnvironmentalEvent(Base):
    __tablename__ = "environmental_events"

    id = Column(Integer, primary_key=True, autoincrement=True)
    event_type = Column(String(64), index=True)  # air_quality_anomaly, spatial_anomaly, rain_event, sensor_failure, etc.
    severity = Column(String(32), default="medium")  # low, medium, high, critical
    title = Column(String(255), nullable=False)
    description = Column(Text, nullable=False)
    detected_at = Column(DateTime, default=datetime.datetime.utcnow, index=True)
    station_ids_json = Column(Text, nullable=False)  # JSON array of station IDs
    evidence_json = Column(Text, nullable=False)     # JSON object with statistics, values, z-scores
    active = Column(Boolean, default=True)

    def to_dict(self):
        import json
        return {
            "id": self.id,
            "event_type": self.event_type,
            "severity": self.severity,
            "title": self.title,
            "description": self.description,
            "detected_at": self.detected_at.isoformat() if self.detected_at else None,
            "station_ids": json.loads(self.station_ids_json) if self.station_ids_json else [],
            "evidence": json.loads(self.evidence_json) if self.evidence_json else {},
            "active": self.active
        }


class IngestionRun(Base):
    __tablename__ = "ingestion_runs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    source_url = Column(String(512), nullable=False)
    sha256 = Column(String(64), nullable=False)
    file_size = Column(Integer, default=0)
    records_count = Column(Integer, default=0)
    downloaded_at = Column(DateTime, default=datetime.datetime.utcnow)
    parser_version = Column(String(32), default="1.0.0")
    schema_version = Column(String(32), default="1.0.0")
    status = Column(String(32), default="completed")  # completed, failed
    error_message = Column(Text, nullable=True)

    def to_dict(self):
        return {
            "id": self.id,
            "source_url": self.source_url,
            "sha256": self.sha256,
            "file_size": self.file_size,
            "records_count": self.records_count,
            "downloaded_at": self.downloaded_at.isoformat() if self.downloaded_at else None,
            "parser_version": self.parser_version,
            "status": self.status
        }


class ModelRun(Base):
    __tablename__ = "model_runs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    model_name = Column(String(128), nullable=False)
    station_id = Column(String(64), nullable=False, index=True)
    variable_id = Column(String(32), nullable=False, index=True)
    trained_at = Column(DateTime, nullable=False)
    training_points = Column(Integer, nullable=False)
    validation_points = Column(Integer, nullable=False)
    train_start = Column(DateTime, nullable=False)
    train_end = Column(DateTime, nullable=False)
    metrics_json = Column(Text, nullable=False)
    artifact_json = Column(Text, nullable=False)

    def to_dict(self, include_artifact: bool = False):
        import json
        result = {
            "id": self.id,
            "model_name": self.model_name,
            "station_id": self.station_id,
            "variable_id": self.variable_id,
            "trained_at": self.trained_at.isoformat() if self.trained_at else None,
            "training_points": self.training_points,
            "validation_points": self.validation_points,
            "train_start": self.train_start.isoformat() if self.train_start else None,
            "train_end": self.train_end.isoformat() if self.train_end else None,
            "metrics": json.loads(self.metrics_json),
        }
        if include_artifact:
            result["artifact"] = json.loads(self.artifact_json)
        return result


class RegionalDatum(Base):
    """Gridded/reanalysis products kept apart from SIATA station observations."""

    __tablename__ = "regional_data"

    id = Column(Integer, primary_key=True, autoincrement=True)
    source_id = Column(String(64), nullable=False, index=True)
    record_type = Column(String(32), nullable=False, index=True)  # forecast, reanalysis
    variable_id = Column(String(64), nullable=False, index=True)
    valid_at = Column(DateTime, nullable=False, index=True)
    vintage_id = Column(String(64), nullable=False)
    issued_at = Column(DateTime, nullable=True)
    value = Column(Float, nullable=False)
    unit = Column(String(32), nullable=False)
    latitude = Column(Float, nullable=False)
    longitude = Column(Float, nullable=False)
    elevation_m = Column(Float, nullable=True)
    spatial_resolution = Column(String(128), nullable=False)
    temporal_resolution = Column(String(64), nullable=False)
    quality_status = Column(String(32), nullable=False, default="provider_model")
    metadata_json = Column(Text, nullable=True)
    fetched_at = Column(DateTime, nullable=False, default=datetime.datetime.utcnow)

    __table_args__ = (
        Index(
            "idx_regional_data_vintage",
            "source_id", "record_type", "variable_id", "valid_at", "vintage_id",
            unique=True,
        ),
        Index("idx_regional_data_source_valid", "source_id", "valid_at"),
    )

    def to_dict(self):
        import json
        return {
            "id": self.id,
            "source_id": self.source_id,
            "record_type": self.record_type,
            "variable_id": self.variable_id,
            "valid_at": self.valid_at.isoformat() if self.valid_at else None,
            "vintage_id": self.vintage_id,
            "issued_at": self.issued_at.isoformat() if self.issued_at else None,
            "value": self.value,
            "unit": self.unit,
            "latitude": self.latitude,
            "longitude": self.longitude,
            "elevation_m": self.elevation_m,
            "spatial_resolution": self.spatial_resolution,
            "temporal_resolution": self.temporal_resolution,
            "quality_status": self.quality_status,
            "metadata": json.loads(self.metadata_json) if self.metadata_json else {},
            "fetched_at": self.fetched_at.isoformat() if self.fetched_at else None,
        }


class SourceRun(Base):
    """Durable source ingestion status and compact checkpoints for the scheduler."""

    __tablename__ = "source_runs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    source_id = Column(String(64), nullable=False, index=True)
    started_at = Column(DateTime, nullable=False, index=True)
    finished_at = Column(DateTime, nullable=True)
    status = Column(String(32), nullable=False, index=True)
    records_count = Column(Integer, nullable=False, default=0)
    latency_ms = Column(Integer, nullable=True)
    error_message = Column(Text, nullable=True)
    metadata_json = Column(Text, nullable=True)

    def to_dict(self):
        import json
        return {
            "id": self.id,
            "source_id": self.source_id,
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "finished_at": self.finished_at.isoformat() if self.finished_at else None,
            "status": self.status,
            "records_count": self.records_count,
            "latency_ms": self.latency_ms,
            "error_message": self.error_message,
            "metadata": json.loads(self.metadata_json) if self.metadata_json else {},
        }


class JevDecisionRecord(Base):
    """Audit trail for typed, policy-checked pipeline decisions."""

    __tablename__ = "jev_decisions"

    id = Column(Integer, primary_key=True, autoincrement=True)
    action = Column(String(64), nullable=False, index=True)
    subject = Column(String(128), nullable=False, index=True)
    allowed = Column(Boolean, nullable=False)
    reason = Column(Text, nullable=False)
    engine = Column(String(64), nullable=False)
    external_provider_status = Column(String(32), nullable=False, default="unavailable")
    created_at = Column(DateTime, nullable=False, default=datetime.datetime.utcnow, index=True)
    metadata_json = Column(Text, nullable=True)

    def to_dict(self):
        import json
        return {
            "id": self.id,
            "action": self.action,
            "subject": self.subject,
            "allowed": self.allowed,
            "reason": self.reason,
            "engine": self.engine,
            "external_provider_status": self.external_provider_status,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "metadata": json.loads(self.metadata_json) if self.metadata_json else {},
        }


class JobLease(Base):
    """Database lease preventing duplicate scheduled jobs across API processes."""

    __tablename__ = "job_leases"

    job_id = Column(String(64), primary_key=True)
    owner_id = Column(String(64), nullable=False)
    locked_until = Column(DateTime, nullable=False, index=True)
    updated_at = Column(DateTime, nullable=False, default=datetime.datetime.utcnow)
