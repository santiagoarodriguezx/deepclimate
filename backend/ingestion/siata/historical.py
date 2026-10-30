"""
Historical Dataset Ingestion and Data Lake Manager.
Downloads, validates, checks checksums, unzips, normalizes and ingests
official SIATA / IDEAM monthly historical datasets from https://siata.gov.co/IDEAM/
Preserves raw files and metadata for full reproducibility.
"""

import os
import io
import re
import json
import hashlib
import zipfile
import datetime
import xlrd
from typing import Dict, Any, List, Optional
from sqlalchemy.orm import Session
from backend.database.repository import EnvironmentalRepository
from backend.ingestion.siata.client import SiataClient

BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
RAW_LAKE_DIR = os.path.join(BASE_DIR, "data", "raw", "siata")
os.makedirs(RAW_LAKE_DIR, exist_ok=True)


class HistoricalLakeManager:
    IDEAM_BASE_URL = "https://siata.gov.co/IDEAM"
    MAX_ARCHIVE_BYTES = 256 * 1024 * 1024
    MAX_XLS_BYTES = 64 * 1024 * 1024

    VARIABLE_MAP = {
        "PM2.5": "PM25",
        "PM10": "PM10",
        "Ozono": "O3",
        "O3": "O3",
        "NO2": "NO2",
        "NO": "NO",
        "CO": "CO",
        "SO2": "SO2",
        "Temperatura": "temperature",
        "TAire10_SSR": "temperature",
        "Humedad": "humidity",
        "HAire10_SSR": "humidity",
        "Presion": "pressure",
        "P_SSR": "pressure",
        "Precipitacion": "rain",
        "PLiquida_SSR": "rain",
        "VelocidadViento": "wind_speed",
        "VViento_SSR": "wind_speed",
        "DireccionViento": "wind_direction",
        "DViento_SSR": "wind_direction"
    }

    def __init__(self, timeout: float = 30.0):
        self.client = SiataClient(
            headers={"User-Agent": "SIATA-Intelligence/1.0 (environmental research)"},
            timeout=timeout,
        )

    def list_available_archives(self) -> List[str]:
        """Discovers all monthly valid zip files on SIATA IDEAM directory."""
        try:
            resp = self.client.get(f"{self.IDEAM_BASE_URL}/")
            if resp.status_code != 200:
                return []
            matches = set(re.findall(r'href=["\'](DatosValidados_[^"\']+\.zip)["\']', resp.text, re.IGNORECASE))
            months = {name.lower(): index for index, name in enumerate(
                ["enero", "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto", "septiembre", "octubre", "noviembre", "diciembre"], 1
            )}
            def archive_key(filename):
                match = re.search(r"_([A-Za-z]+)(\d{4})\.zip$", filename)
                if not match:
                    return (0, 0, filename)
                return (int(match.group(2)), months.get(match.group(1).lower(), 0), filename)
            return sorted(matches, key=archive_key)
        except Exception as e:
            print(f"Error listing IDEAM directory: {e}")
            return []

    def ingest_archive(
        self,
        zip_filename: str,
        db: Session,
        max_xls_files: int = 15
    ) -> Dict[str, Any]:
        """
        Downloads archive, verifies checksum, parses XLS files, normalizes timestamps and values,
        and saves observations to database and raw lake.
        """
        if os.path.basename(zip_filename) != zip_filename or not re.fullmatch(r"DatosValidados_[A-Za-z0-9_-]+\.zip", zip_filename):
            raise ValueError("Nombre de archivo histórico inválido.")

        repo = EnvironmentalRepository(db)
        source_url = f"{self.IDEAM_BASE_URL}/{zip_filename}"
        local_zip_path = os.path.join(RAW_LAKE_DIR, zip_filename)
        meta_path = f"{local_zip_path}.meta.json"

        # 1. Download or load from raw storage lake
        if os.path.exists(local_zip_path):
            if os.path.getsize(local_zip_path) > self.MAX_ARCHIVE_BYTES:
                raise ValueError("El archivo histórico supera el límite permitido.")
            with open(local_zip_path, "rb") as f:
                content = f.read()
        else:
            chunks = bytearray()
            with self.client.stream("GET", source_url) as resp:
                resp.raise_for_status()
                try:
                    length = int(resp.headers.get("Content-Length", 0))
                except ValueError as exc:
                    raise ValueError("SIATA devolvió un tamaño de archivo inválido.") from exc
                if length > self.MAX_ARCHIVE_BYTES:
                    raise ValueError("El archivo histórico supera el límite permitido.")
                for chunk in resp.iter_bytes():
                    chunks.extend(chunk)
                    if len(chunks) > self.MAX_ARCHIVE_BYTES:
                        raise ValueError("El archivo histórico supera el límite permitido.")
            content = bytes(chunks)
            with open(local_zip_path, "wb") as f:
                f.write(content)

        # 2. Checksum calculation
        sha256_hash = hashlib.sha256(content).hexdigest()
        file_size = len(content)

        # Check if already processed
        if repo.is_file_processed(source_url, sha256_hash):
            return {
                "status": "already_processed",
                "zip_filename": zip_filename,
                "sha256": sha256_hash
            }

        # 3. Save raw metadata
        meta = {
            "source_url": source_url,
            "downloaded_at": datetime.datetime.utcnow().isoformat(),
            "sha256": sha256_hash,
            "file_size": file_size,
            "parser_version": "1.0.0",
            "schema_version": "1.0.0"
        }
        with open(meta_path, "w", encoding="utf-8") as f:
            json.dump(meta, f, indent=2)

        # 4. Decompress and parse XLS files
        observations_to_insert = []
        processed_files_count = 0

        max_xls_files = max(1, min(int(max_xls_files), 15))
        with zipfile.ZipFile(io.BytesIO(content)) as z:
            files = [info for info in z.infolist() if info.filename.lower().endswith(".xls")]
            unpacked = 0
            for info in files:
                if processed_files_count >= max_xls_files:
                    break
                xls_name = info.filename
                unpacked += info.file_size
                if info.file_size > self.MAX_XLS_BYTES or unpacked > self.MAX_ARCHIVE_BYTES:
                    continue
                raw_xls = z.read(xls_name)
                try:
                    wb = xlrd.open_workbook(file_contents=raw_xls)
                    sheet = wb.sheet_by_index(0)
                    if sheet.nrows < 2:
                        continue

                    # Header mapping
                    headers = [str(sheet.cell_value(0, c)).strip() for c in range(sheet.ncols)]
                    header_idx = {h: i for i, h in enumerate(headers)}

                    for r in range(1, sheet.nrows):
                        st_code = str(sheet.cell_value(r, header_idx.get("NombreEstacion", 0))).strip()
                        raw_var = str(sheet.cell_value(r, header_idx.get("Variable", 1))).strip()
                        raw_unit = str(sheet.cell_value(r, header_idx.get("Unidad", 2))).strip()
                        date_str = str(sheet.cell_value(r, header_idx.get("FechaInicio", 3))).strip()
                        val = sheet.cell_value(r, header_idx.get("Concentracion", 6))
                        msfl_code = str(sheet.cell_value(r, header_idx.get("MSFLCode", 7))).strip()

                        # Canonical variable lookup
                        can_var = self.VARIABLE_MAP.get(raw_var)
                        if not can_var:
                            for k, v in self.VARIABLE_MAP.items():
                                if k.lower() in raw_var.lower() or k.lower() in xls_name.lower():
                                    can_var = v
                                    break
                        if not can_var:
                            continue

                        # Value validation
                        try:
                            num_val = float(val)
                            if num_val < -900 or num_val > 9999:  # Filter null/flag values like -999
                                continue
                        except (ValueError, TypeError):
                            continue

                        # Parse timestamp e.g. "01/07/2026 12:00:00 am"
                        obs_dt = None
                        for fmt in ["%d/%m/%Y %I:%M:%S %p", "%d/%m/%Y %H:%M:%S", "%Y-%m-%d %H:%M:%S", "%d/%m/%Y %I:%M %p"]:
                            try:
                                parsed = datetime.datetime.strptime(date_str, fmt)
                                obs_dt = parsed.replace(tzinfo=datetime.timezone(datetime.timedelta(hours=-5))).astimezone(datetime.timezone.utc).replace(tzinfo=None)
                                break
                            except ValueError:
                                pass

                        if not obs_dt:
                            continue

                        # Quality status
                        quality_status = "good"
                        if msfl_code and msfl_code.lower() not in ["null", "0", "ok", ""]:
                            quality_status = "doubtful"

                        observations_to_insert.append({
                            "station_id": st_code,
                            "variable_id": can_var,
                            "observed_at": obs_dt,
                            "value": num_val,
                            "raw_value": str(val),
                            "unit": raw_unit or "µg/m³",
                            "quality_code": msfl_code,
                            "quality_status": quality_status,
                            "source": f"ideam_historical:{zip_filename}"
                        })

                    processed_files_count += 1
                except Exception as e:
                    print(f"Error parsing {xls_name}: {e}")

        # 5. Insert batch into database
        inserted_records = repo.bulk_insert_observations(observations_to_insert)

        # 6. Record ingestion provenance run
        repo.record_ingestion_run({
            "source_url": source_url,
            "sha256": sha256_hash,
            "file_size": file_size,
            "records_count": inserted_records,
            "parser_version": "1.0.0",
            "schema_version": "1.0.0",
            "status": "completed"
        })

        return {
            "status": "completed",
            "zip_filename": zip_filename,
            "sha256": sha256_hash,
            "xls_files_parsed": processed_files_count,
            "records_inserted": inserted_records,
            "raw_lake_path": local_zip_path
        }

    def close(self):
        self.client.close()
