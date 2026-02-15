"""

from __future__ import annotations

GCS Storage Abstraction for Reclaim Tracking Data

Handles persistent storage of:
- Session SQLite databases (tracking data)
- Digest HTML files

This enables quality monitoring to work across Cloud Run container restarts
by persisting tracking data to GCS instead of ephemeral /tmp storage.
"""

import logging
import os

from google.api_core import exceptions
from google.cloud import storage

logger = logging.getLogger(__name__)

# GCS configuration
BUCKET_NAME = os.getenv("RECLAIM_TRACKING_BUCKET", os.getenv("SHOPQ_TRACKING_BUCKET", "reclaim-tracking"))
PROJECT_ID = os.getenv("GCP_PROJECT", "shopq-467118")

# GCS paths
SESSIONS_PREFIX = "sessions/"
DIGESTS_PREFIX = "digests/"


class StorageClient:
    """GCS storage client for Reclaim tracking data"""

    def __init__(self, bucket_name: str = BUCKET_NAME, project_id: str = PROJECT_ID):
        """Initialize GCS client

        Args:
            bucket_name: GCS bucket name
            project_id: GCP project ID
        """
        self.bucket_name = bucket_name
        self.project_id = project_id
        self._client = None
        self._bucket = None

    @property
    def client(self) -> storage.Client:
        """Lazy-load GCS client"""
        if self._client is None:
            try:
                self._client = storage.Client(project=self.project_id)
            except Exception as e:
                logger.error(f"Failed to initialize GCS client: {e}")
                raise
        return self._client

    @property
    def bucket(self) -> storage.Bucket:
        """Lazy-load GCS bucket"""
        if self._bucket is None:
            try:
                self._bucket = self.client.bucket(self.bucket_name)
            except Exception as e:
                logger.error(f"Failed to get GCS bucket {self.bucket_name}: {e}")
                raise
        return self._bucket

    def upload_session_db(self, session_id: str, db_path: str) -> bool:
        """Upload session SQLite database to GCS

        Args:
            session_id: Session identifier (e.g., "20251108_143022")
            db_path: Path to local SQLite database file

        Returns:
            True if upload succeeded, False otherwise
        """
        try:
            if not os.path.exists(db_path):
                logger.warning(f"Database file not found: {db_path}")
                return False

            blob_name = f"{SESSIONS_PREFIX}{session_id}.db"
            blob = self.bucket.blob(blob_name)

            logger.info(f"Uploading session DB to gs://{self.bucket_name}/{blob_name}")
            blob.upload_from_filename(db_path)
            logger.info(f"Successfully uploaded session DB: {session_id}")
            return True

        except exceptions.GoogleAPIError as e:
            logger.error(f"GCS API error uploading session DB {session_id}: {e}")
            return False
        except Exception as e:
            logger.error(f"Failed to upload session DB {session_id}: {e}")
            return False

    def upload_digest_html(self, session_id: str, html_content: str) -> bool:
        """Upload digest HTML to GCS

        Args:
            session_id: Session identifier
            html_content: HTML content string

        Returns:
            True if upload succeeded, False otherwise
        """
        try:
            blob_name = f"{DIGESTS_PREFIX}{session_id}.html"
            blob = self.bucket.blob(blob_name)

            logger.info(f"Uploading digest HTML to gs://{self.bucket_name}/{blob_name}")
            blob.upload_from_string(html_content, content_type="text/html")
            logger.info(f"Successfully uploaded digest HTML: {session_id}")
            return True

        except exceptions.GoogleAPIError as e:
            logger.error(f"GCS API error uploading digest HTML {session_id}: {e}")
            return False
        except Exception as e:
            logger.error(f"Failed to upload digest HTML {session_id}: {e}")
            return False

    def download_session_db(self, session_id: str, dest_path: str | None = None) -> str | None:
        """Download session SQLite database from GCS

        Args:
            session_id: Session identifier
            dest_path: Optional destination path. If None, creates temp file.

        Returns:
            Path to downloaded file, or None if download failed
        """
        try:
            blob_name = f"{SESSIONS_PREFIX}{session_id}.db"
            blob = self.bucket.blob(blob_name)

            if not blob.exists():
                logger.warning(f"Session DB not found in GCS: {blob_name}")
                return None

            # Create temp file if dest_path not provided
            if dest_path is None:
                import tempfile

                fd, dest_path = tempfile.mkstemp(suffix=f"_{session_id}.db")
                os.close(fd)

            logger.info(f"Downloading session DB from gs://{self.bucket_name}/{blob_name}")
            blob.download_to_filename(dest_path)
            logger.info(f"Successfully downloaded session DB to {dest_path}")
            return dest_path

        except exceptions.GoogleAPIError as e:
            logger.error(f"GCS API error downloading session DB {session_id}: {e}")
            return None
        except Exception as e:
            logger.error(f"Failed to download session DB {session_id}: {e}")
            return None

    def download_digest_html(self, session_id: str) -> str | None:
        """Download digest HTML from GCS

        Args:
            session_id: Session identifier

        Returns:
            HTML content string, or None if download failed
        """
        try:
            blob_name = f"{DIGESTS_PREFIX}{session_id}.html"
            blob = self.bucket.blob(blob_name)

            if not blob.exists():
                logger.warning(f"Digest HTML not found in GCS: {blob_name}")
                return None

            logger.info(f"Downloading digest HTML from gs://{self.bucket_name}/{blob_name}")
            html_content = blob.download_as_text()
            logger.info(f"Successfully downloaded digest HTML: {session_id}")
            return html_content

        except exceptions.GoogleAPIError as e:
            logger.error(f"GCS API error downloading digest HTML {session_id}: {e}")
            return None
        except Exception as e:
            logger.error(f"Failed to download digest HTML {session_id}: {e}")
            return None

    def list_sessions(self, max_results: int = 50) -> list[str]:
        """List available session IDs in GCS

        Args:
            max_results: Maximum number of sessions to return

        Returns:
            List of session IDs (newest first)
            Side Effects:
                Modifies local data structures
        """
        try:
            blobs = self.client.list_blobs(
                self.bucket_name, prefix=SESSIONS_PREFIX, max_results=max_results
            )

            session_ids = []
            for blob in blobs:
                # Extract session_id from path: sessions/20251108_143022.db
                filename = blob.name.replace(SESSIONS_PREFIX, "")
                session_id = filename.replace(".db", "")
                session_ids.append(session_id)

            # Sort by session_id (newest first - relies on timestamp format)
            session_ids.sort(reverse=True)
            return session_ids

        except Exception as e:
            logger.error(f"Failed to list sessions: {e}")
            return []


# Global instance
_storage_client = None


def get_storage_client() -> StorageClient:
    """Get global storage client instance"""
    global _storage_client
    if _storage_client is None:
        _storage_client = StorageClient()
    return _storage_client
