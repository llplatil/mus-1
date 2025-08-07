import os
import logging
from .base_plugin import BasePlugin
from google.cloud import storage
import requests
import google.auth.transport.requests
import google.oauth2.id_token

logger = logging.getLogger(__name__)

class GcpMoSeq2OrchestratorPlugin(BasePlugin):
    """Plugin to manage uploading videos to GCP, triggering MoSeq2, and retrieving results."""

    plugin_name = "GCP MoSeq2 Orchestrator"
    plugin_short_description = "Uploads videos, runs MoSeq2 on GCP, downloads results."
    plugin_version = "0.1.0"
    plugin_author = "MUS1 Team"
    plugin_license = "MIT"

    # Define required input fields for the UI
    required_fields = {
        "gcp_project_id": {"type": "string", "label": "GCP Project ID", "tooltip": "Your Google Cloud project ID (e.g., mus1-455803)"},
        "gcp_bucket_name": {"type": "string", "label": "GCS Bucket Name", "tooltip": "Name of the GCS bucket (e.g., moseq2)"},
        "moseq2_runner_url": {"type": "string", "label": "Cloud Run Service URL", "tooltip": "The HTTPS URL of your deployed MoSeq2 Cloud Run service"},
        "video_file_path": {"type": "file", "label": "Local Video File", "tooltip": "Select the video file to process"}
    }

    # Define optional input fields
    optional_fields = {
        "cleanup_after_download": {"type": "boolean", "label": "Delete GCP Video After Download?", "default": True, "tooltip": "If checked, the video file in GCS will be deleted after results are downloaded."}
    }

    # Define the capabilities this plugin offers
    analysis_capabilities = [
        {
            "name": "gcp_upload_and_run_moseq2",
            "label": "Upload and Run MoSeq2 on GCP",
            "description": "Uploads the video to GCS and triggers the MoSeq2 analysis job on Cloud Run."
        },
        {
            "name": "gcp_check_and_download_moseq2",
            "label": "Check and Download MoSeq2 Results",
            "description": "Checks for MoSeq2 results in GCS and downloads them if available."
        },
        {
            "name": "gcp_cleanup_video",
            "label": "Clean Up GCP Video",
            "description": "Deletes the source video file from GCS."
        }
        # We might add separate upload/run/download/cleanup later if needed
    ]

    def __init__(self):
        super().__init__()
        # Initialization specific to this plugin, if any
        pass

    def get_required_fields(self):
        return self.required_fields

    def get_optional_fields(self):
        return self.optional_fields

    def get_analysis_capabilities(self):
        return self.analysis_capabilities

    def validate_experiment(self, experiment_metadata, capability_name):
        """Validates prerequisites before running a capability."""
        logger.info(f"Validating experiment {experiment_metadata.experiment_id} for capability {capability_name}")
        params = experiment_metadata.plugin_params.get(self.plugin_name, {})
        results = experiment_metadata.analysis_results.get(self.plugin_name, {})

        required_plugin_params = list(self.required_fields.keys())
        for field in required_plugin_params:
            if field not in params or not params[field]:
                 raise ValueError(f"Missing required plugin parameter '{field}' for {self.plugin_name}")

        if capability_name == "gcp_upload_and_run_moseq2":
            if not os.path.exists(params["video_file_path"]):
                raise ValueError(f"Local video file not found at: {params['video_file_path']}")

        elif capability_name == "gcp_check_and_download_moseq2":
            if not params.get("gcp_results_uri_prefix"):
                raise ValueError(f"Missing 'gcp_results_uri_prefix' in params. Run 'Upload and Run' first.")

        elif capability_name == "gcp_cleanup_video":
            if not params.get("gcp_video_uri"):
                raise ValueError(f"Missing 'gcp_video_uri' in params. Run 'Upload and Run' first.")

        logger.info(f"Validation successful for {capability_name}")
        return True


    def analyze_experiment(self, experiment_metadata, capability_name, data_manager):
        """Executes the selected GCP capability."""
        logger.info(f"Running capability '{capability_name}' for experiment {experiment_metadata.experiment_id}")
        params = experiment_metadata.plugin_params.setdefault(self.plugin_name, {})
        results = experiment_metadata.analysis_results.setdefault(self.plugin_name, {})
        optional_params = {k: params.get(k, v.get('default')) for k, v in self.optional_fields.items()}

        gcp_project_id = params["gcp_project_id"]
        gcp_bucket_name = params["gcp_bucket_name"]
        moseq2_runner_url = params["moseq2_runner_url"]
        local_video_path = params["video_file_path"]

        try:
            storage_client = storage.Client(project=gcp_project_id)
            bucket = storage_client.bucket(gcp_bucket_name)

            if capability_name == "gcp_upload_and_run_moseq2":
                self._upload_video(experiment_metadata, bucket, local_video_path, params)
                self._trigger_moseq2_run(experiment_metadata, moseq2_runner_url, params)
                experiment_metadata.processing_stage = "gcp_processing"
                logger.info(f"Video uploaded and MoSeq2 run triggered for {experiment_metadata.experiment_id}")

            elif capability_name == "gcp_check_and_download_moseq2":
                download_path = self._download_results(experiment_metadata, bucket, data_manager, params, results)
                if download_path:
                    results["local_results_path"] = download_path
                    experiment_metadata.processing_stage = "gcp_results_downloaded"
                    logger.info(f"Results downloaded to {download_path}")
                    if optional_params.get("cleanup_after_download") and params.get("gcp_video_uri"):
                        logger.info("Cleanup specified, deleting GCP video.")
                        self._delete_gcs_object(bucket, params["gcp_video_uri"])
                        params.pop("gcp_video_uri", None) # Remove from params if deleted
                        # Consider adding a cleanup capability for results too?
                        experiment_metadata.processing_stage = "gcp_complete_cleaned"
                else:
                    logger.info(f"Results not yet available for {experiment_metadata.experiment_id}")
                    # Keep stage as gcp_processing

            elif capability_name == "gcp_cleanup_video":
                if params.get("gcp_video_uri"):
                    self._delete_gcs_object(bucket, params["gcp_video_uri"])
                    params.pop("gcp_video_uri", None)
                    logger.info(f"GCP video deleted for {experiment_metadata.experiment_id}")
                    # Potentially update stage if needed
                else:
                    logger.warning("No GCP video URI found to clean up.")

            else:
                raise ValueError(f"Unknown capability: {capability_name}")

        except Exception as e:
            logger.error(f"Error during capability '{capability_name}' for experiment {experiment_metadata.experiment_id}: {e}", exc_info=True)
            # Potentially update processing_stage to reflect error state
            experiment_metadata.processing_stage = "gcp_error"
            raise # Re-raise the exception to signal failure

        return experiment_metadata # Return updated metadata

    # --- Helper Methods --- 

    def _upload_video(self, experiment_metadata, bucket, local_video_path, params):
        """Uploads the local video to GCS."""
        video_filename = os.path.basename(local_video_path)
        # Sanitize filename for GCS path if needed
        gcs_video_path = f"videos/{experiment_metadata.subject_id}/{experiment_metadata.experiment_id}/{video_filename}"
        blob = bucket.blob(gcs_video_path)

        logger.info(f"Uploading {local_video_path} to gs://{bucket.name}/{gcs_video_path}")
        blob.upload_from_filename(local_video_path)
        logger.info("Upload complete.")

        params["gcp_video_uri"] = f"gs://{bucket.name}/{gcs_video_path}"

    def _trigger_moseq2_run(self, experiment_metadata, runner_url, params):
        """Sends a request to the Cloud Run service to start MoSeq2."""
        if not params.get("gcp_video_uri"):
            raise ValueError("Cannot trigger run: gcp_video_uri not set.")

        gcs_results_prefix = f"results/{experiment_metadata.subject_id}/{experiment_metadata.experiment_id}/"
        params["gcp_results_uri_prefix"] = f"gs://{params['gcp_bucket_name']}/{gcs_results_prefix}"

        payload = {
            "input_video_uri": params["gcp_video_uri"],
            "output_results_uri_prefix": params["gcp_results_uri_prefix"]
            # Add any other parameters your Cloud Run script expects
        }

        logger.info(f"Triggering MoSeq2 run via {runner_url} with payload: {payload}")

        # Get authentication token for Cloud Run
        # Ensure your service account (or user credentials via ADC) has 'roles/run.invoker'
        try:
            auth_req = google.auth.transport.requests.Request()
            id_token = google.oauth2.id_token.fetch_id_token(auth_req, runner_url)
            headers = {'Authorization': f'Bearer {id_token}', 'Content-Type': 'application/json'}
        except Exception as e:
            logger.error(f"Failed to get ID token for Cloud Run: {e}. Ensure ADC is set up and service account has invoker role.", exc_info=True)
            # If your Cloud Run service allows unauthenticated access, remove token logic:
            # headers = {'Content-Type': 'application/json'}
            # raise # Or handle based on whether auth is required
            raise ValueError(f"Authentication failed for Cloud Run: {e}")

        try:
            response = requests.post(runner_url, json=payload, headers=headers, timeout=60) # Adjust timeout
            response.raise_for_status() # Raise an exception for bad status codes (4xx or 5xx)
            logger.info(f"Cloud Run trigger successful. Status Code: {response.status_code}. Response: {response.text[:500]}...")
            # Note: This usually returns quickly, the job runs async on Cloud Run.
            # You might get a job ID or similar in the response if your runner provides one.
            # Store it in 'results' if needed: results["gcp_job_id"] = response.json().get("job_id")

        except requests.exceptions.RequestException as e:
            logger.error(f"Error triggering Cloud Run job: {e}", exc_info=True)
            raise

    def _download_results(self, experiment_metadata, bucket, data_manager, params, results):
        """Checks for and downloads results files from GCS."""
        gcs_results_prefix_uri = params.get("gcp_results_uri_prefix")
        if not gcs_results_prefix_uri:
            raise ValueError("Cannot download results: 'gcp_results_uri_prefix' not set.")

        # Assumes format gs://bucket_name/prefix/
        prefix = gcs_results_prefix_uri.replace(f"gs://{bucket.name}/", "")
        logger.info(f"Checking for results in gs://{bucket.name}/{prefix}")

        blobs = list(bucket.list_blobs(prefix=prefix))

        if not blobs:
            logger.info("No result files found yet.")
            return None # Indicate results not ready

        # Determine local download directory using DataManager/Project structure
        # Example: <project_root>/data/<subject_id>/<experiment_id>/gcp_moseq2_results/
        base_path = data_manager.get_experiment_data_path(experiment_metadata)
        download_dir = os.path.join(base_path, "gcp_moseq2_results")
        os.makedirs(download_dir, exist_ok=True)
        logger.info(f"Found {len(blobs)} result file(s). Downloading to {download_dir}")

        for blob in blobs:
            # Avoid downloading the 'folder' itself if represented as a blob
            if blob.name.endswith('/'): 
                continue 
            local_filename = os.path.basename(blob.name)
            local_filepath = os.path.join(download_dir, local_filename)
            logger.debug(f"Downloading {blob.name} to {local_filepath}")
            blob.download_to_filename(local_filepath)

        logger.info("Result download complete.")
        return download_dir # Return the path where results were saved

    def _delete_gcs_object(self, bucket, gcs_uri):
        """Deletes a single object from GCS given its URI."""
        if not gcs_uri.startswith(f"gs://{bucket.name}/"):
            logger.error(f"Cannot delete object: URI {gcs_uri} does not match bucket {bucket.name}")
            return
        blob_name = gcs_uri.replace(f"gs://{bucket.name}/", "")
        blob = bucket.blob(blob_name)
        try:
            logger.info(f"Attempting to delete gs://{bucket.name}/{blob_name}")
            blob.delete()
            logger.info(f"Successfully deleted gs://{bucket.name}/{blob_name}")
        except storage.exceptions.NotFound:
            logger.warning(f"Object gs://{bucket.name}/{blob_name} not found for deletion.")
        except Exception as e:
            logger.error(f"Failed to delete object gs://{bucket.name}/{blob_name}: {e}", exc_info=True)
            # Don't raise here, allow process to continue if cleanup fails 