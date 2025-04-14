"""
Web interface for the BunkrDownloader application.
"""
from flask import Flask, render_template, request, jsonify, url_for, redirect, flash, send_from_directory
import threading
import queue
import logging
import os
import time
import json
from datetime import datetime
from werkzeug.utils import secure_filename
from ..controller import DownloadController
from ..config import DEFAULT_DOWNLOAD_PATH

# Configure logging for web UI
web_logger = logging.getLogger("bunkrd.web")
log_formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
log_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), 'logs')
os.makedirs(log_dir, exist_ok=True)
log_file = os.path.join(log_dir, 'bunkr_web.log')
file_handler = logging.FileHandler(log_file)
file_handler.setFormatter(log_formatter)
file_handler.setLevel(logging.INFO)
web_logger.addHandler(file_handler)
web_logger.setLevel(logging.INFO)

# Define paths for static and template folders
current_dir = os.path.dirname(os.path.abspath(__file__))
template_dir = os.path.join(current_dir, 'templates')
static_dir = os.path.join(current_dir, 'static')

# Initialize Flask application with explicit template and static folders
app = Flask(__name__, 
           template_folder=template_dir,
           static_folder=static_dir)
app.secret_key = os.urandom(24)

# Configure a default download directory
DEFAULT_WEB_DOWNLOAD_DIR = os.path.join(DEFAULT_DOWNLOAD_PATH, "web_downloads")

# Create download queue and job tracking
download_queue = queue.Queue()
active_jobs = {}
job_results = {}

# Background worker thread
worker_thread = None

# Track whether worker has been started
worker_started = False

# Add template filters
@app.template_filter('timestamp_to_datetime')
def timestamp_to_datetime(timestamp):
    """Convert a UNIX timestamp to a formatted date string."""
    try:
        dt = datetime.fromtimestamp(timestamp)
        return dt.strftime('%Y-%m-%d %H:%M:%S')
    except (ValueError, TypeError):
        return 'Unknown'

@app.template_filter('format_duration')
def format_duration(seconds):
    """Format a duration in seconds to a human-readable string."""
    try:
        seconds = float(seconds)
        minutes, seconds = divmod(seconds, 60)
        hours, minutes = divmod(minutes, 60)
        
        if hours > 0:
            return f"{int(hours)}h {int(minutes)}m {int(seconds)}s"
        elif minutes > 0:
            return f"{int(minutes)}m {int(seconds)}s"
        else:
            return f"{seconds:.1f}s"
    except (ValueError, TypeError):
        return 'Unknown'

class WebProgressTracker:
    """Track download progress for a job to display in the web UI."""
    
    def __init__(self, job_id):
        """Initialize progress tracker for a job."""
        self.job_id = job_id
        self.status = "initializing"
        self.message = "Preparing download..."
        self.total_files = 0
        self.completed_files = 0
        self.current_file = ""
        self.current_file_progress = 0
        self.start_time = time.time()
        self.end_time = None
        self.file_statuses = {}  # Dictionary to track each file's status
        self.file_sizes = {}     # Dictionary to track file sizes
    
    def update_status(self, status, message=None):
        """Update job status and message."""
        self.status = status
        if message:
            self.message = message
        
        if status in ["completed", "failed", "error"]:
            self.end_time = time.time()
        
        # Update job info
        if self.job_id in active_jobs:
            job = active_jobs[self.job_id]
            job["status"] = status
            if message:
                job["message"] = message
            if self.end_time:
                job["end_time"] = self.end_time
                job["duration"] = self.end_time - self.start_time
    
    def update_album_progress(self, total_files, completed_files, current_file=None):
        """Update progress for album download."""
        self.total_files = total_files
        self.completed_files = completed_files
        if current_file:
            self.current_file = current_file
        
        # Calculate overall progress percentage (0-100)
        if self.total_files > 0:
            overall_progress = int((self.completed_files / self.total_files) * 100)
        else:
            overall_progress = 0
        
        # Update job info
        if self.job_id in active_jobs:
            job = active_jobs[self.job_id]
            job["total_files"] = total_files
            job["completed_files"] = completed_files
            job["progress"] = overall_progress
            if current_file:
                job["current_file"] = current_file
            
            # Also update file statuses in job info
            job["file_statuses"] = self.file_statuses
            job["file_sizes"] = self.file_sizes
    
    def update_file_status(self, filename, status, size=None):
        """Update status of a specific file."""
        self.file_statuses[filename] = status
        if size is not None:
            self.file_sizes[filename] = size
        
        # Update job info
        if self.job_id in active_jobs:
            job = active_jobs[self.job_id]
            if "file_statuses" not in job:
                job["file_statuses"] = {}
            if "file_sizes" not in job:
                job["file_sizes"] = {}
            job["file_statuses"][filename] = status
            if size is not None:
                job["file_sizes"][filename] = size
    
    def update_file_progress(self, filename, progress, total_size=None):
        """Update download progress of a specific file."""
        # Track current file being downloaded and its progress
        self.current_file = filename
        self.current_file_progress = progress
        
        # Update file size if provided
        if total_size is not None and filename in self.file_sizes:
            self.file_sizes[filename] = total_size
        
        # Update job info
        if self.job_id in active_jobs:
            job = active_jobs[self.job_id]
            job["current_file"] = filename
            job["current_file_progress"] = progress
            
            # Also update file size in job info if provided
            if total_size is not None:
                if "file_sizes" not in job:
                    job["file_sizes"] = {}
                job["file_sizes"][filename] = total_size

def process_queue():
    """Background thread to process download queue."""
    global worker_started
    
    worker_started = True
    web_logger.info("Download worker started")
    
    while True:
        try:
            # Get job from queue with timeout
            try:
                job = download_queue.get(timeout=1)
            except queue.Empty:
                continue
                
            job_id = job['id']
            url = job['url']
            download_dir = job['download_dir']
            
            # Create progress tracker
            tracker = WebProgressTracker(job_id)
            
            # Update job status
            tracker.update_status('processing', f"Processing URL: {url}")
            
            try:
                # Set up controller with appropriate settings for this job
                proxy = job.get('proxy')
                max_concurrent = job.get('concurrent_count', 3) if job.get('concurrent') else 1
                min_delay = job.get('min_delay', 1.0)
                max_delay = job.get('max_delay', 3.0)
                no_robots_check = job.get('no_robots_check', False)
                
                # Import here to avoid circular imports
                from .controller_wrapper import WebUIController
                
                # Create controller instance for this job with progress tracking
                job_controller = WebUIController(
                    tracker,
                    proxy_url=proxy,
                    max_concurrent_downloads=max_concurrent,
                    min_delay=min_delay,
                    max_delay=max_delay,
                    respect_robots_txt=not no_robots_check
                )
                
                # Process URL
                success = job_controller.process_url(url, download_dir)
                
                # Update job status based on result if not already updated by controller
                if job_id in active_jobs:
                    if success and active_jobs[job_id]["status"] != "completed":
                        tracker.update_status('completed', "Download completed successfully")
                    elif not success and active_jobs[job_id]["status"] not in ["error", "failed"]:
                        tracker.update_status('failed', "Download failed")
                
                    # Move from active to completed
                    job_results[job_id] = active_jobs.pop(job_id)
                
            except Exception as e:
                error_msg = f"Error processing job: {str(e)}"
                web_logger.exception(error_msg)
                tracker.update_status('error', error_msg)
                
                # Move to results
                if job_id in active_jobs:
                    job_results[job_id] = active_jobs.pop(job_id)
                
            finally:
                # Mark task as done in queue
                download_queue.task_done()
                
        except Exception as e:
            web_logger.exception(f"Unexpected error in worker thread: {str(e)}")
            time.sleep(5)  # Avoid tight loop if something is wrong

@app.route('/')
def index():
    """Home page with download form."""
    # Get list of recent jobs
    recent_jobs = list(job_results.values())[-5:] if job_results else []
    
    return render_template('index.html',
                         download_dir=DEFAULT_WEB_DOWNLOAD_DIR,
                         active_jobs=active_jobs,
                         recent_jobs=recent_jobs)

@app.route('/submit', methods=['POST'])
def submit():
    """Handle form submission for downloading a URL."""
    # Start worker thread if not already running
    global worker_thread, worker_started
    if worker_thread is None or not worker_thread.is_alive():
        worker_thread = threading.Thread(target=process_queue)
        worker_thread.daemon = True
        worker_thread.start()
        worker_started = True
    
    # Get form data
    url_input = request.form.get('url', '').strip()
    download_dir = request.form.get('download_dir', DEFAULT_WEB_DOWNLOAD_DIR)
    use_proxy = request.form.get('use_proxy') == 'on'
    concurrent = request.form.get('concurrent') == 'on'
    
    # Get advanced options
    try:
        concurrent_count = int(request.form.get('concurrent_count', 3))
        min_delay = float(request.form.get('min_delay', 1.0))
        max_delay = float(request.form.get('max_delay', 3.0))
    except (ValueError, TypeError):
        concurrent_count = 3
        min_delay = 1.0
        max_delay = 3.0
    
    # Validate ranges
    concurrent_count = max(1, min(concurrent_count, 10))
    min_delay = max(0.1, min_delay)
    max_delay = max(min_delay, max_delay)
    
    no_robots_check = request.form.get('no_robots_check') == 'on'
    
    # Validate URL
    if not url_input:
        flash("Please enter a URL to download", "error")
        return redirect(url_for('index'))
    
    # Validate download directory
    if not download_dir:
        download_dir = DEFAULT_WEB_DOWNLOAD_DIR
    
    # Make sure download directory exists
    os.makedirs(download_dir, exist_ok=True)
    
    # Generate a job ID
    job_id = f"job_{int(time.time())}_{len(active_jobs) + len(job_results)}"
    
    # Create job info
    job_info = {
        'id': job_id,
        'url': url_input,
        'download_dir': download_dir,
        'status': 'queued',
        'start_time': time.time(),
        'proxy': use_proxy,
        'concurrent': concurrent,
        'concurrent_count': concurrent_count,
        'min_delay': min_delay,
        'max_delay': max_delay,
        'no_robots_check': no_robots_check,
        'progress': 0,
        'message': 'Job queued',
        'total_files': 0,
        'completed_files': 0
    }
    
    # Add to active jobs
    active_jobs[job_id] = job_info
    
    # Queue the job
    download_queue.put(job_info)
    
    flash(f"Download job started for: {url_input}", "success")
    return redirect(url_for('status', job_id=job_id))

@app.route('/status/<job_id>')
def status(job_id):
    """Display status page for a job."""
    if job_id in active_jobs:
        return render_template('status.html', job=active_jobs[job_id])
    elif job_id in job_results:
        return render_template('results.html', job=job_results[job_id])
    else:
        flash("Job not found", "error")
        return redirect(url_for('index'))

@app.route('/api/status/<job_id>')
def api_status(job_id):
    """API endpoint to get job status as JSON."""
    if job_id in active_jobs:
        return jsonify(active_jobs[job_id])
    elif job_id in job_results:
        return jsonify(job_results[job_id])
    else:
        return jsonify({"error": "Job not found"}), 404

@app.route('/jobs')
def jobs():
    """List all jobs (active and completed)."""
    return render_template('jobs.html', 
                         active_jobs=active_jobs, 
                         completed_jobs=job_results)

@app.route('/downloads/<path:filename>')
def download_file(filename):
    """Serve a downloaded file."""
    # This is a basic implementation - would need more security in production
    return send_from_directory(DEFAULT_WEB_DOWNLOAD_DIR, filename)

def main():
    """Run the Flask application."""
    # Ensure download directory exists
    os.makedirs(DEFAULT_WEB_DOWNLOAD_DIR, exist_ok=True)
    
    # Ensure static directories exist
    static_dir = os.path.join(os.path.dirname(__file__), 'static')
    css_dir = os.path.join(static_dir, 'css')
    js_dir = os.path.join(static_dir, 'js')
    
    os.makedirs(css_dir, exist_ok=True)
    os.makedirs(js_dir, exist_ok=True)
    
    # Make sure templates directory exists
    templates_dir = os.path.join(os.path.dirname(__file__), 'templates')
    os.makedirs(templates_dir, exist_ok=True)
    
    web_logger.info(f"Starting web server on port 5000")
    web_logger.info(f"Download directory: {DEFAULT_WEB_DOWNLOAD_DIR}")
    
    # Start the web server
    app.run(host='0.0.0.0', port=5000, debug=True)

if __name__ == '__main__':
    main()