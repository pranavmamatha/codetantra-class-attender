#!/usr/bin/env python3
"""
Flask Dashboard for Auto Class Joiner Monitoring
Provides real-time logs, screenshots, and control interface
"""

from flask import Flask, render_template, jsonify, send_from_directory, request, Response
import os
import json
import glob
import datetime
from pathlib import Path
import threading
import time

app = Flask(__name__)

# Configuration
LOGS_DIR = "/app/logs_ashwin"
SCREENSHOTS_DIR = "/app/logs_ashwin"
LOG_FILE = os.path.join(LOGS_DIR, "class_joiner.log")
SCREENSHOT_TRIGGER_FILE = os.path.join(LOGS_DIR, "take_screenshot")

# Ensure directories exist
os.makedirs(LOGS_DIR, exist_ok=True)

class LogMonitor:
    def __init__(self):
        self.latest_logs = []
        self.max_logs = 100
        self.last_position = 0

    def get_latest_logs(self, lines=50):
        """Get the latest log entries"""
        try:
            if not os.path.exists(LOG_FILE):
                return []

            with open(LOG_FILE, 'r') as f:
                all_lines = f.readlines()
                return [line.strip() for line in all_lines[-lines:] if line.strip()]
        except Exception as e:
            return [f"Error reading logs: {str(e)}"]

    def get_new_logs_since_position(self):
        """Get new log entries since last check"""
        try:
            if not os.path.exists(LOG_FILE):
                return [], 0

            with open(LOG_FILE, 'r') as f:
                f.seek(self.last_position)
                new_content = f.read()
                self.last_position = f.tell()

                if new_content:
                    new_lines = [line.strip() for line in new_content.split('\n') if line.strip()]
                    return new_lines, self.last_position

        except Exception as e:
            return [f"Error reading new logs: {str(e)}"], self.last_position

        return [], self.last_position

log_monitor = LogMonitor()

def get_screenshots():
    """Get list of available screenshots"""
    screenshot_patterns = [
        os.path.join(SCREENSHOTS_DIR, "screenshot_*.png"),
        os.path.join(SCREENSHOTS_DIR, "screenshots", "screenshot_*.png")
    ]

    screenshots = []
    for pattern in screenshot_patterns:
        screenshots.extend(glob.glob(pattern))

    # Sort by modification time (newest first)
    screenshots.sort(key=lambda x: os.path.getmtime(x), reverse=True)

    screenshot_data = []
    for screenshot in screenshots[:10]:  # Limit to 10 most recent
        try:
            stat = os.stat(screenshot)
            screenshot_data.append({
                'filename': os.path.basename(screenshot),
                'path': screenshot,
                'size': stat.st_size,
                'modified': datetime.datetime.fromtimestamp(stat.st_mtime).strftime('%Y-%m-%d %H:%M:%S'),
                'modified_timestamp': stat.st_mtime
            })
        except Exception as e:
            print(f"Error processing screenshot {screenshot}: {e}")

    return screenshot_data

@app.route('/')
def dashboard():
    """Main dashboard page"""
    return render_template('dashboard.html')

@app.route('/api/logs')
def get_logs():
    """API endpoint to get latest logs"""
    lines = request.args.get('lines', 50, type=int)
    logs = log_monitor.get_latest_logs(lines)
    return jsonify({'logs': logs})

@app.route('/api/logs/stream')
def stream_logs():
    """Server-sent events for real-time log streaming"""
    def generate():
        while True:
            new_logs, _ = log_monitor.get_new_logs_since_position()
            if new_logs:
                for log_line in new_logs:
                    yield f"data: {json.dumps({'log': log_line, 'timestamp': datetime.datetime.now().isoformat()})}\n\n"
            time.sleep(1)

    return Response(generate(), mimetype='text/plain')

@app.route('/api/screenshots')
def get_screenshots_api():
    """API endpoint to get available screenshots"""
    screenshots = get_screenshots()
    return jsonify({'screenshots': screenshots})

@app.route('/api/screenshot/trigger')
def trigger_screenshot():
    """API endpoint to trigger a screenshot"""
    try:
        # Create the trigger file
        with open(SCREENSHOT_TRIGGER_FILE, 'w') as f:
            f.write(f"Screenshot requested at {datetime.datetime.now()}")
        return jsonify({'success': True, 'message': 'Screenshot triggered successfully'})
    except Exception as e:
        return jsonify({'success': False, 'message': f'Error triggering screenshot: {str(e)}'})

@app.route('/screenshots/<path:filename>')
def serve_screenshot(filename):
    """Serve screenshot files"""
    # Try different possible directories
    possible_dirs = [
        os.path.join(SCREENSHOTS_DIR, "screenshots"),
        SCREENSHOTS_DIR,
        "/tmp/screenshots",
        "/tmp"
    ]

    for directory in possible_dirs:
        filepath = os.path.join(directory, filename)
        if os.path.exists(filepath):
            return send_from_directory(directory, filename)

    return "Screenshot not found", 404

@app.route('/api/status')
def get_status():
    """Get application status"""
    try:
        # Check if log file exists and get last modified time
        log_exists = os.path.exists(LOG_FILE)
        last_log_time = None
        if log_exists:
            last_log_time = datetime.datetime.fromtimestamp(os.path.getmtime(LOG_FILE)).isoformat()

        # Check if main application is running (based on recent log activity)
        app_running = False
        if log_exists:
            current_time = time.time()
            log_modified_time = os.path.getmtime(LOG_FILE)
            app_running = (current_time - log_modified_time) < 300  # 5 minutes

        # Get recent screenshots count
        screenshots = get_screenshots()
        recent_screenshots = len([s for s in screenshots if time.time() - s['modified_timestamp'] < 3600])  # Last hour

        return jsonify({
            'app_running': app_running,
            'log_file_exists': log_exists,
            'last_log_time': last_log_time,
            'recent_screenshots': recent_screenshots,
            'total_screenshots': len(screenshots)
        })
    except Exception as e:
        return jsonify({'error': str(e)})

# HTML Template embedded in the Python file
DASHBOARD_HTML = '''
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Auto Class Joiner Dashboard</title>
    <style>
        * {
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }

        body {
            font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            min-height: 100vh;
            padding: 20px;
        }

        .dashboard {
            max-width: 1400px;
            margin: 0 auto;
            background: rgba(255, 255, 255, 0.95);
            border-radius: 15px;
            box-shadow: 0 20px 40px rgba(0, 0, 0, 0.1);
            overflow: hidden;
        }

        .header {
            background: linear-gradient(135deg, #2c3e50, #3498db);
            color: white;
            padding: 30px;
            text-align: center;
        }

        .header h1 {
            font-size: 2.5em;
            margin-bottom: 10px;
        }

        .status-bar {
            display: flex;
            justify-content: center;
            gap: 30px;
            margin-top: 20px;
        }

        .status-item {
            display: flex;
            align-items: center;
            gap: 10px;
        }

        .status-indicator {
            width: 12px;
            height: 12px;
            border-radius: 50%;
            background: #e74c3c;
        }

        .status-indicator.active {
            background: #2ecc71;
            animation: pulse 2s infinite;
        }

        @keyframes pulse {
            0% { opacity: 1; }
            50% { opacity: 0.5; }
            100% { opacity: 1; }
        }

        .main-content {
            padding: 30px;
            display: grid;
            grid-template-columns: 1fr 1fr;
            gap: 30px;
            min-height: 600px;
        }

        .panel {
            background: white;
            border-radius: 10px;
            box-shadow: 0 5px 15px rgba(0, 0, 0, 0.08);
            overflow: hidden;
        }

        .panel-header {
            background: #f8f9fa;
            padding: 20px;
            border-bottom: 1px solid #e9ecef;
            display: flex;
            justify-content: space-between;
            align-items: center;
        }

        .panel-header h3 {
            color: #2c3e50;
            font-size: 1.3em;
        }

        .btn {
            background: #3498db;
            color: white;
            border: none;
            padding: 10px 20px;
            border-radius: 5px;
            cursor: pointer;
            font-size: 14px;
            transition: background 0.3s;
        }

        .btn:hover {
            background: #2980b9;
        }

        .btn:disabled {
            background: #95a5a6;
            cursor: not-allowed;
        }

        .btn.success {
            background: #27ae60;
        }

        .btn.success:hover {
            background: #229954;
        }

        .logs-container {
            height: 500px;
            overflow-y: auto;
            background: #1e1e1e;
            color: #f8f8f2;
            font-family: 'Courier New', monospace;
            font-size: 13px;
            padding: 20px;
        }

        .log-line {
            margin-bottom: 5px;
            padding: 3px 0;
            word-wrap: break-word;
        }

        .log-line.info {
            color: #8be9fd;
        }

        .log-line.error {
            color: #ff5555;
        }

        .log-line.warning {
            color: #ffb86c;
        }

        .screenshots-grid {
            padding: 20px;
            max-height: 500px;
            overflow-y: auto;
        }

        .screenshot-item {
            display: flex;
            align-items: center;
            padding: 15px;
            border-bottom: 1px solid #e9ecef;
            transition: background 0.3s;
        }

        .screenshot-item:hover {
            background: #f8f9fa;
        }

        .screenshot-thumb {
            width: 80px;
            height: 60px;
            object-fit: cover;
            border-radius: 5px;
            margin-right: 15px;
        }

        .screenshot-info {
            flex-grow: 1;
        }

        .screenshot-filename {
            font-weight: bold;
            color: #2c3e50;
            margin-bottom: 5px;
        }

        .screenshot-meta {
            color: #7f8c8d;
            font-size: 12px;
        }

        .auto-refresh {
            display: flex;
            align-items: center;
            gap: 10px;
        }

        .auto-refresh input[type="checkbox"] {
            transform: scale(1.2);
        }

        .loading {
            text-align: center;
            padding: 40px;
            color: #7f8c8d;
        }

        .controls {
            background: #f8f9fa;
            padding: 20px;
            border-top: 1px solid #e9ecef;
            display: flex;
            gap: 15px;
            justify-content: center;
        }

        .notification {
            position: fixed;
            top: 20px;
            right: 20px;
            padding: 15px 25px;
            background: #27ae60;
            color: white;
            border-radius: 5px;
            box-shadow: 0 5px 15px rgba(0, 0, 0, 0.2);
            z-index: 1000;
            opacity: 0;
            transform: translateX(100%);
            transition: all 0.3s ease;
        }

        .notification.show {
            opacity: 1;
            transform: translateX(0);
        }

        .notification.error {
            background: #e74c3c;
        }

        @media (max-width: 768px) {
            .main-content {
                grid-template-columns: 1fr;
                gap: 20px;
            }

            .status-bar {
                flex-direction: column;
                gap: 10px;
            }
        }
    </style>
</head>
<body>
    <div class="dashboard">
        <div class="header">
            <h1>Auto Class Joiner Dashboard</h1>
            <div class="status-bar">
                <div class="status-item">
                    <div class="status-indicator" id="app-status"></div>
                    <span id="app-status-text">Checking...</span>
                </div>
                <div class="status-item">
                    <div class="status-indicator" id="log-status"></div>
                    <span id="log-status-text">Logs: Unknown</span>
                </div>
                <div class="status-item">
                    <div class="status-indicator" id="screenshot-status"></div>
                    <span id="screenshot-status-text">Screenshots: Unknown</span>
                </div>
            </div>
        </div>

        <div class="main-content">
            <div class="panel">
                <div class="panel-header">
                    <h3>Real-time Logs</h3>
                    <div class="auto-refresh">
                        <input type="checkbox" id="auto-scroll" checked>
                        <label for="auto-scroll">Auto-scroll</label>
                    </div>
                </div>
                <div class="logs-container" id="logs-container">
                    <div class="loading">Loading logs...</div>
                </div>
            </div>

            <div class="panel">
                <div class="panel-header">
                    <h3>Screenshots</h3>
                    <button class="btn success" id="take-screenshot">Take Screenshot</button>
                </div>
                <div class="screenshots-grid" id="screenshots-container">
                    <div class="loading">Loading screenshots...</div>
                </div>
            </div>
        </div>

        <div class="controls">
            <button class="btn" id="refresh-logs">Refresh Logs</button>
            <button class="btn" id="refresh-screenshots">Refresh Screenshots</button>
            <button class="btn" id="clear-logs">Clear Display</button>
        </div>
    </div>

    <div class="notification" id="notification"></div>

    <script>
        class Dashboard {
            constructor() {
                this.autoScroll = true;
                this.eventSource = null;
                this.init();
            }

            init() {
                this.bindEvents();
                this.loadInitialData();
                this.startRealTimeUpdates();
                this.updateStatus();

                // Update status every 30 seconds
                setInterval(() => this.updateStatus(), 30000);
                // Refresh screenshots every 60 seconds
                setInterval(() => this.loadScreenshots(), 60000);
            }

            bindEvents() {
                document.getElementById('take-screenshot').addEventListener('click', () => this.takeScreenshot());
                document.getElementById('refresh-logs').addEventListener('click', () => this.loadLogs());
                document.getElementById('refresh-screenshots').addEventListener('click', () => this.loadScreenshots());
                document.getElementById('clear-logs').addEventListener('click', () => this.clearLogs());
                document.getElementById('auto-scroll').addEventListener('change', (e) => {
                    this.autoScroll = e.target.checked;
                });
            }

            async loadInitialData() {
                await Promise.all([
                    this.loadLogs(),
                    this.loadScreenshots()
                ]);
            }

            async loadLogs() {
                try {
                    const response = await fetch('/api/logs?lines=100');
                    const data = await response.json();
                    this.displayLogs(data.logs, false);
                } catch (error) {
                    console.error('Error loading logs:', error);
                    this.showNotification('Error loading logs', 'error');
                }
            }

            async loadScreenshots() {
                try {
                    const response = await fetch('/api/screenshots');
                    const data = await response.json();
                    this.displayScreenshots(data.screenshots);
                } catch (error) {
                    console.error('Error loading screenshots:', error);
                    this.showNotification('Error loading screenshots', 'error');
                }
            }

            async updateStatus() {
                try {
                    const response = await fetch('/api/status');
                    const data = await response.json();

                    // Update app status
                    const appStatus = document.getElementById('app-status');
                    const appStatusText = document.getElementById('app-status-text');
                    if (data.app_running) {
                        appStatus.classList.add('active');
                        appStatusText.textContent = 'App: Running';
                    } else {
                        appStatus.classList.remove('active');
                        appStatusText.textContent = 'App: Stopped';
                    }

                    // Update log status
                    const logStatus = document.getElementById('log-status');
                    const logStatusText = document.getElementById('log-status-text');
                    if (data.log_file_exists) {
                        logStatus.classList.add('active');
                        logStatusText.textContent = `Logs: Active`;
                    } else {
                        logStatus.classList.remove('active');
                        logStatusText.textContent = 'Logs: No file';
                    }

                    // Update screenshot status
                    const screenshotStatus = document.getElementById('screenshot-status');
                    const screenshotStatusText = document.getElementById('screenshot-status-text');
                    if (data.total_screenshots > 0) {
                        screenshotStatus.classList.add('active');
                        screenshotStatusText.textContent = `Screenshots: ${data.total_screenshots} total, ${data.recent_screenshots} recent`;
                    } else {
                        screenshotStatus.classList.remove('active');
                        screenshotStatusText.textContent = 'Screenshots: None';
                    }
                } catch (error) {
                    console.error('Error updating status:', error);
                }
            }

            startRealTimeUpdates() {
                // Note: Server-sent events might not work in all environments
                // Fall back to polling if needed
                try {
                    this.eventSource = new EventSource('/api/logs/stream');
                    this.eventSource.onmessage = (event) => {
                        const data = JSON.parse(event.data);
                        this.appendLog(data.log);
                    };
                    this.eventSource.onerror = () => {
                        console.log('SSE connection failed, falling back to polling');
                        this.eventSource.close();
                        this.startPolling();
                    };
                } catch (error) {
                    console.log('SSE not supported, using polling');
                    this.startPolling();
                }
            }

            startPolling() {
                // Poll for new logs every 3 seconds
                setInterval(async () => {
                    try {
                        const response = await fetch('/api/logs?lines=10');
                        const data = await response.json();
                        // This is a simplified approach - in production you'd want to track the last seen log
                        if (data.logs.length > 0) {
                            const container = document.getElementById('logs-container');
                            const lastLog = container.lastElementChild?.textContent;
                            const newLog = data.logs[data.logs.length - 1];
                            if (lastLog !== newLog) {
                                this.appendLog(newLog);
                            }
                        }
                    } catch (error) {
                        console.error('Polling error:', error);
                    }
                }, 3000);
            }

            displayLogs(logs, append = false) {
                const container = document.getElementById('logs-container');
                if (!append) {
                    container.innerHTML = '';
                }

                logs.forEach(log => {
                    this.appendLog(log, false);
                });

                if (this.autoScroll) {
                    container.scrollTop = container.scrollHeight;
                }
            }

            appendLog(logText, scroll = true) {
                const container = document.getElementById('logs-container');
                const logElement = document.createElement('div');
                logElement.className = 'log-line';

                // Add appropriate class based on log level
                if (logText.includes('ERROR')) {
                    logElement.classList.add('error');
                } else if (logText.includes('WARNING')) {
                    logElement.classList.add('warning');
                } else if (logText.includes('INFO')) {
                    logElement.classList.add('info');
                }

                logElement.textContent = logText;
                container.appendChild(logElement);

                // Keep only last 500 log lines to prevent memory issues
                while (container.children.length > 500) {
                    container.removeChild(container.firstChild);
                }

                if (this.autoScroll && scroll) {
                    container.scrollTop = container.scrollHeight;
                }
            }

            displayScreenshots(screenshots) {
                const container = document.getElementById('screenshots-container');

                if (screenshots.length === 0) {
                    container.innerHTML = '<div class="loading">No screenshots available</div>';
                    return;
                }

                container.innerHTML = '';
                screenshots.forEach(screenshot => {
                    const item = document.createElement('div');
                    item.className = 'screenshot-item';

                    item.innerHTML = `
                        <img src="/screenshots/${screenshot.filename}" alt="Screenshot" class="screenshot-thumb" onclick="window.open('/screenshots/${screenshot.filename}', '_blank')">
                        <div class="screenshot-info">
                            <div class="screenshot-filename">${screenshot.filename}</div>
                            <div class="screenshot-meta">
                                ${screenshot.modified} | ${this.formatFileSize(screenshot.size)}
                            </div>
                        </div>
                    `;

                    container.appendChild(item);
                });
            }

            async takeScreenshot() {
                const button = document.getElementById('take-screenshot');
                const originalText = button.textContent;
                button.disabled = true;
                button.textContent = 'Taking...';

                try {
                    const response = await fetch('/api/screenshot/trigger');
                    const data = await response.json();

                    if (data.success) {
                        this.showNotification('Screenshot triggered successfully!');
                        // Refresh screenshots after a delay
                        setTimeout(() => this.loadScreenshots(), 3000);
                    } else {
                        this.showNotification(data.message || 'Failed to trigger screenshot', 'error');
                    }
                } catch (error) {
                    this.showNotification('Error triggering screenshot', 'error');
                } finally {
                    button.disabled = false;
                    button.textContent = originalText;
                }
            }

            clearLogs() {
                document.getElementById('logs-container').innerHTML = '';
            }

            formatFileSize(bytes) {
                if (bytes === 0) return '0 B';
                const k = 1024;
                const sizes = ['B', 'KB', 'MB', 'GB'];
                const i = Math.floor(Math.log(bytes) / Math.log(k));
                return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + ' ' + sizes[i];
            }

            showNotification(message, type = 'success') {
                const notification = document.getElementById('notification');
                notification.textContent = message;
                notification.className = `notification ${type} show`;

                setTimeout(() => {
                    notification.classList.remove('show');
                }, 3000);
            }
        }

        // Initialize dashboard when DOM is loaded
        document.addEventListener('DOMContentLoaded', () => {
            new Dashboard();
        });
    </script>
</body>
</html>
'''

# Create templates directory and save the template
def create_templates():
    templates_dir = os.path.join(os.path.dirname(__file__), 'templates')
    os.makedirs(templates_dir, exist_ok=True)

    template_path = os.path.join(templates_dir, 'dashboard.html')
    if not os.path.exists(template_path):
        with open(template_path, 'w') as f:
            f.write(DASHBOARD_HTML)

# Alternative route that serves HTML directly without template file
@app.route('/direct')
def dashboard_direct():
    """Direct HTML rendering without template files"""
    return DASHBOARD_HTML

if __name__ == '__main__':
    # Create templates directory and HTML template on startup
    create_templates()

    print("Flask Dashboard starting...")
    print("Dashboard will be available at:")
    print("- http://localhost:5000 (main dashboard)")
    print("- http://localhost:5000/direct (direct HTML)")
    print("\nFeatures:")
    print("- Real-time log monitoring")
    print("- Screenshot gallery with thumbnails")
    print("- One-click screenshot trigger")
    print("- Application status monitoring")
    print("- Auto-refresh capabilities")

    app.run(host='0.0.0.0', port=5002, debug=False, threaded=True)