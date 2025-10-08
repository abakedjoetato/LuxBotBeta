"""
S3 Utility Module for Discord Music Queue Bot
Handles all interactions with a Backblaze S3-compatible bucket.
"""

import aioboto3
import os
import logging
from typing import Optional, Dict

class S3Client:
    """
    An asynchronous client for handling S3 operations with Backblaze B2.
    """

    def __init__(self):
        self.endpoint_url: Optional[str] = os.getenv("B2_ENDPOINT_URL")
        self.aws_access_key_id: Optional[str] = os.getenv("B2_ACCESS_KEY_ID")
        self.aws_secret_access_key: Optional[str] = os.getenv("B2_SECRET_ACCESS_KEY")
        self.bucket_name: Optional[str] = os.getenv("B2_BUCKET_NAME")
        self.is_configured = False

        if not all([self.endpoint_url, self.aws_access_key_id, self.aws_secret_access_key, self.bucket_name]):
            logging.warning("S3_CLIENT: Missing one or more required B2 environment variables. S3 functionality will be disabled.")
            return

        self.session = aioboto3.Session(
            aws_access_key_id=self.aws_access_key_id,
            aws_secret_access_key=self.aws_secret_access_key,
        )
        self.is_configured = True
        logging.info("S3_CLIENT: aioboto3 session created and configured.")

    async def generate_presigned_upload_url(self, object_name: str, content_type: str, expires_in: int = 3600) -> Optional[str]:
        """
        Generates a pre-signed URL for uploading a file to the S3 bucket.

        :param object_name: The key (path/filename) for the object in the bucket.
        :param content_type: The MIME type of the file to be uploaded.
        :param expires_in: Time in seconds for the pre-signed URL to remain valid.
        :return: The pre-signed URL, or None if an error occurs.
        """
        async with self.session.client("s3", endpoint_url=self.endpoint_url) as s3_client:
            try:
                url = await s3_client.generate_presigned_url(
                    'put_object',
                    Params={'Bucket': self.bucket_name, 'Key': object_name, 'ContentType': content_type},
                    ExpiresIn=expires_in
                )
                return url
            except Exception as e:
                logging.error(f"S3_CLIENT: Failed to generate pre-signed upload URL for {object_name}: {e}", exc_info=True)
                return None

    def get_public_file_url(self, object_name: str) -> str:
        """
        Constructs the public URL for a file already in the bucket.
        Assumes the bucket has public read access.

        :param object_name: The key (path/filename) for the object in the bucket.
        :return: The public URL for the object.
        """
        # B2 public URLs are typically in the format: https://<bucket_name>.<endpoint_without_https>
        # Or you can use the f-string format with your custom domain if you have one.
        # This example uses the standard B2 format.
        base_url = self.endpoint_url.replace("https://", "")
        return f"https://{self.bucket_name}.{base_url}/{object_name}"

    async def upload_file_from_path(self, file_path: str, object_name: str) -> bool:
        """
        Uploads a local file directly to the S3 bucket.
        Used by the data migration script.

        :param file_path: The local path to the file to upload.
        :param object_name: The desired key (path/filename) for the object in the bucket.
        :return: True if upload was successful, False otherwise.
        """
        async with self.session.client("s3", endpoint_url=self.endpoint_url) as s3_client:
            try:
                with open(file_path, "rb") as f:
                    await s3_client.upload_fileobj(f, self.bucket_name, object_name)
                logging.info(f"S3_CLIENT: Successfully uploaded {file_path} to {object_name}.")
                return True
            except FileNotFoundError:
                logging.error(f"S3_CLIENT: Local file not found for upload: {file_path}")
                return False
            except Exception as e:
                logging.error(f"S3_CLIENT: Failed to upload file {file_path}: {e}", exc_info=True)
                return False

    async def upload_file_from_bytes(self, file_bytes: bytes, object_name: str, content_type: str) -> bool:
        """
        Uploads a file from a bytes object directly to the S3 bucket.

        :param file_bytes: The file content as bytes.
        :param object_name: The desired key (path/filename) for the object in the bucket.
        :param content_type: The MIME type of the file.
        :return: True if upload was successful, False otherwise.
        """
        import io
        async with self.session.client("s3", endpoint_url=self.endpoint_url) as s3_client:
            try:
                with io.BytesIO(file_bytes) as f:
                    await s3_client.upload_fileobj(f, self.bucket_name, object_name, ExtraArgs={'ContentType': content_type})
                logging.info(f"S3_CLIENT: Successfully uploaded bytes to {object_name}.")
                return True
            except Exception as e:
                logging.error(f"S3_CLIENT: Failed to upload bytes to {object_name}: {e}", exc_info=True)
                return False